import json
import re
import shutil

import pytest

from neurovisual.cli import main
from neurovisual.config import Config
from neurovisual.runner import run
from neurovisual.sources import SimulatedSource
from neurovisual.viewer import load_track, write_viewer


def embedded_data(html):
    match = re.search(r'<script id="session-data" type="application/json">(.*?)</script>', html, re.S)
    assert match is not None
    return json.loads(match.group(1))


@pytest.fixture(scope="module")
def viewer_sessions(tmp_path_factory):
    root = tmp_path_factory.mktemp("viewer")
    original, custom = root / "original", root / "custom"
    base = Config(baseline_seconds=0.4)
    config = Config.load("examples/visual-custom.json", base=base)
    for path, settings in ((original, base), (custom, config)):
        run(SimulatedSource(duration=12, scenarios=["blink"], speed=0), settings,
            record=path, osc=False, print_interval=0)
    return original, custom


def test_viewer_preserves_recorded_values_order_and_invalid_windows(viewer_sessions, tmp_path):
    original, _ = viewer_sessions
    before = {path.name: path.read_bytes() for path in original.iterdir()}
    target = write_viewer(original, tmp_path / "viewer.html")
    data = embedded_data(target.read_text())
    stored = [json.loads(line) for line in before["controls.jsonl"].decode().splitlines()]
    frames = data["tracks"][0]["frames"]
    assert [row["timestamp"] for row in frames] == [row["timestamp"] for row in stored]
    assert [row["visual"] for row in frames] == [row["visual"] for row in stored]
    assert [row["status"]["motion_available"] for row in frames] == [row["status"]["motion_available"] for row in stored]
    assert any(row["status"]["valid"] for row in frames)
    assert any(not row["status"]["valid"] and row["visual"]["pulse"] for row in frames)
    assert any("suspected_artifact" in row["status"]["reasons"] for row in frames)
    assert before == {path.name: path.read_bytes() for path in original.iterdir()}


def test_comparison_uses_same_eeg_and_preserves_two_distinct_mappings(viewer_sessions, tmp_path):
    original, custom = viewer_sessions
    target = write_viewer(original, tmp_path / "compare.html", custom)
    tracks = embedded_data(target.read_text())["tracks"]
    assert len(tracks) == 2
    assert tracks[0]["mapping"]["color"] == "alpha" and tracks[1]["mapping"]["color"] == "theta"
    assert tracks[1]["addresses"]["color"] == "/arte/tono"
    assert [row["features"] for row in tracks[0]["frames"]] == [row["features"] for row in tracks[1]["frames"]]
    assert any(a["visual"]["color"] != b["visual"]["color"] for a, b in zip(tracks[0]["frames"], tracks[1]["frames"]))


@pytest.mark.parametrize("filename", ["raw.jsonl", "features.jsonl"])
def test_comparison_rejects_different_eeg_or_processing(viewer_sessions, tmp_path, filename):
    original, custom = viewer_sessions
    other = tmp_path / "different"
    shutil.copytree(custom, other)
    rows = [json.loads(line) for line in (other / filename).read_text().splitlines()]
    if filename == "raw.jsonl":
        next(row for row in rows if row["samples"])["samples"][0][0] += 20
    else:
        next(row for row in rows if row["channel_powers_uv2"])["channel_powers_uv2"]["ch1"]["alpha"] *= 1.5
    (other / filename).write_text("\n".join(json.dumps(row) for row in rows))
    with pytest.raises(ValueError, match=f"Difiere {filename}"):
        write_viewer(original, tmp_path / "rejected.html", other)
    assert not (tmp_path / "rejected.html").exists()


def test_raw_only_recording_reports_how_to_generate_controls(tmp_path):
    with pytest.raises(ValueError, match="primero ejecutar run/replay con --record"):
        write_viewer("examples/recordings/openbci", tmp_path / "invalid.html")


@pytest.mark.parametrize("case", ["duplicate", "nan", "range", "channels", "flags", "empty"])
def test_corrupt_controls_fail_with_clear_context(viewer_sessions, tmp_path, case):
    original, _ = viewer_sessions
    other = tmp_path / "bad"
    shutil.copytree(original, other)
    frames = [json.loads(line) for line in (other / "controls.jsonl").read_text().splitlines()]
    if case == "duplicate":
        frames[1]["timestamp"] = frames[0]["timestamp"]
    elif case == "nan":
        frames[0]["visual"]["color"] = float("nan")
    elif case == "range":
        frames[0]["visual"]["flow"] = 1.2
    elif case == "channels":
        frames[0]["status"]["channels"] = [1]
    elif case == "flags":
        frames[0]["status"]["valid"] = True  # disconnected and uncalibrated at the first tick
    else:
        frames = []
    (other / "controls.jsonl").write_text("\n".join(json.dumps(row) for row in frames))
    with pytest.raises(ValueError, match="controls.jsonl"):
        load_track(other)


def test_session_labels_cannot_escape_json_into_executable_html(viewer_sessions, tmp_path):
    original, _ = viewer_sessions
    other = tmp_path / "labels"
    shutil.copytree(original, other)
    manifest = json.loads((other / "metadata.json").read_text())
    label = '</script><script>window.injected=true</script><img src="external">'
    manifest["source"]["source"] = label
    (other / "metadata.json").write_text(json.dumps(manifest))
    html = write_viewer(other, tmp_path / "escaped.html").read_text()
    assert label not in html
    assert embedded_data(html)["tracks"][0]["source"] == label


def test_cli_exports_comparison_and_protects_recording_filenames(viewer_sessions, tmp_path, capsys):
    original, custom = viewer_sessions
    target = tmp_path / "cli.html"
    assert main(["view", str(original), "--compare", str(custom), "--output", str(target)]) == 0
    assert "Visor guardado" in capsys.readouterr().out
    assert len(embedded_data(target.read_text())["tracks"]) == 2
    before = (original / "raw.jsonl").read_bytes()
    with pytest.raises(SystemExit) as exc:
        main(["view", str(original), "--output", str(original / "raw.jsonl")])
    assert exc.value.code == 2
    assert "como .html" in capsys.readouterr().err
    assert (original / "raw.jsonl").read_bytes() == before
