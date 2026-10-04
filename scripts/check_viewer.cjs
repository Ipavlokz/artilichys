// Optional browser check. Requires Node, Playwright and a Chromium executable.
// Usage: node scripts/check_viewer.cjs comparison.html faults.html screenshot.png
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { chromium } = require("playwright");

(async () => {
  const [comparison, faults, screenshot] = process.argv.slice(2);
  assert(comparison && faults, "Supply the comparison and fault-session HTML files");
  const browser = await chromium.launch({ executablePath: process.env.NEUROVISUAL_BROWSER || "/usr/bin/chromium", args: ["--no-sandbox"] });
  const errors = [], remoteRequests = [];
  let page;
  async function loadPage(filename) {
    if (page) await page.close();
    page = await browser.newPage({ viewport: { width: 1365, height: 1100 }, reducedMotion: "reduce" });
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => { if (/^https?:/.test(request.url())) remoteRequests.push(request.url()); });
    await page.setContent(fs.readFileSync(filename, "utf8"));
  }
  async function data() {
    return page.evaluate(() => JSON.parse(document.getElementById("session-data").textContent));
  }
  async function seek(elapsed) {
    await page.locator("#timeline").evaluate((node, value) => {
      node.value = String(value); node.dispatchEvent(new Event("input", { bubbles: true }));
    }, elapsed);
  }
  async function verifyFrames() {
    return page.evaluate(() => {
      const payload = JSON.parse(document.getElementById("session-data").textContent);
      const results = [];
      document.querySelectorAll(".track").forEach((card, trackIndex) => {
        const track = payload.tracks[trackIndex], index = Number(card.dataset.frame), frame = track.frames[index];
        if (Number(card.dataset.timestamp) !== frame.timestamp) throw new Error("Timestamp changed in rendering");
        const values = [...card.querySelectorAll("td.value")].map(node => Number(node.dataset.value));
        const expected = ["color", "intensity", "flow", "coherence", "pulse", "scene"].map(key => frame.visual[key]);
        if (values.some((value, i) => value !== expected[i])) throw new Error("Rendered controls differ from recorded values");
        if (card.classList.contains("valid") !== frame.status.valid) throw new Error("Quality state changed");
        if (Number(card.querySelector(".pulse").getAttribute("opacity")) !== frame.visual.pulse) throw new Error("Pulse changed");
        const fill = card.querySelector("svg circle").getAttribute("fill");
        if (!fill || fill.includes("NaN")) throw new Error("Invalid artistic color");
        results.push({ index, valid: frame.status.valid, connected: frame.status.connected, stale: frame.status.stale, pulse: frame.visual.pulse, color: frame.visual.color });
      });
      return results;
    });
  }
  try {
    await loadPage(comparison);
    assert.equal(await page.locator(".track").count(), 2);
    await verifyFrames();
    await page.locator("#first-valid").click();
    assert((await verifyFrames()).every(frame => frame.valid));
    const payload = await data();
    const candidate = payload.tracks[0].frames.find(frame => frame.timestamp - payload.start > 51 && frame.status.valid);
    await seek(candidate ? candidate.timestamp - payload.start + 0.002 : Number(await page.locator("#timeline").inputValue()));
    const rendered = await verifyFrames();
    assert.notEqual(rendered[0].color, rendered[1].color);
    if (screenshot) await page.screenshot({ path: screenshot, fullPage: true });
    await page.locator("#play").click();
    const before = Number(await page.locator("#timeline").inputValue());
    await page.waitForTimeout(350);
    await page.locator("#play").click();
    const paused = Number(await page.locator("#timeline").inputValue());
    assert(paused > before, "Playback did not advance");
    await page.waitForTimeout(100);
    assert.equal(Number(await page.locator("#timeline").inputValue()), paused, "Pause did not stop playback");
    await page.locator("#restart").click();
    assert.equal(Number(await page.locator("#timeline").inputValue()), 0);

    await loadPage(faults);
    const failureData = await data();
    const frames = failureData.tracks[0].frames;
    const checks = {
      valid: frame => frame.status.valid,
      blink: frame => frame.visual.pulse === 1,
      disconnected: frame => !frame.status.connected && frame.timestamp > failureData.start,
      stale: frame => frame.status.connected && frame.status.stale,
      recovered: frame => frame.timestamp - failureData.start > 42 && frame.status.valid,
    };
    for (const [name, match] of Object.entries(checks)) {
      const frame = frames.find(match);
      assert(frame, `Missing ${name} scenario`);
      await seek(frame.timestamp - failureData.start + 0.002);
      const [rendered] = await verifyFrames();
      assert(match(frames[rendered.index]), `Viewer lost ${name} scenario`);
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(remoteRequests, [], "Offline viewer requested external resources");
    console.log(JSON.stringify({ browser: "Chromium", comparison_tracks: 2, checked_states: Object.keys(checks), playback: "passed", seek: "passed", remote_requests: 0, page_errors: 0 }));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
