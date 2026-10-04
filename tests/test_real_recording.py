import csv
import gzip
import hashlib
import io
import json
from pathlib import Path

import numpy as np

from neurovisual.config import Config
from neurovisual.model import Block
from neurovisual.pipeline import Pipeline
from neurovisual.runner import run
from neurovisual.sources import ReplaySource, SimulatedSource
from neurovisual.sources.replay import inspect_source

RECORDING = Path("examples/recordings/openbci")


def test_public_recording_preserves_original_physical_values_and_auxiliary_fields():
    manifest = json.loads((RECORDING / "metadata.json").read_text())
    excerpt = gzip.decompress((RECORDING / "original_excerpt.txt.gz").read_bytes())
    assert hashlib.sha256(excerpt).hexdigest() == manifest["conversion"]["excerpt_sha256"]
    lines = [line for line in excerpt.decode().splitlines() if not line.startswith("%")]
    original = list(csv.DictReader(io.StringIO("\n".join(lines)), skipinitialspace=True))
    expected_eeg = np.array([[float(row[f"EXG Channel {i}"]) for i in range(8)] for row in original])
    expected_imu = np.array([[float(row[f"Accel Channel {i}"]) for i in range(3)] for row in original])
    source = ReplaySource(RECORDING, speed=0)
    blocks = []
    while not source.finished:
        blocks.append(source.read(0))
    np.testing.assert_array_equal(np.vstack([b.samples for b in blocks]), expected_eeg)
    np.testing.assert_array_equal(np.vstack([b.imu for b in blocks]), expected_imu)
    timestamps = np.concatenate([b.timestamps for b in blocks])
    assert np.all(np.diff(timestamps) > 0)
    assert len(timestamps) == len(original) == 15000
    assert np.count_nonzero(np.diff(timestamps) > 1.5 / source.metadata.sample_rate) == 3
    assert source.metadata.units == "uV" and source.metadata.sample_rate == 250
    assert source.metadata.groups == {}  # do not invent electrode positions
    assert inspect_source(ReplaySource(RECORDING, speed=0))["timestamp_gaps"] == 3


def test_real_recording_calibrates_and_produces_controls_while_retaining_rejections(tmp_path):
    path = tmp_path / "real"
    summary = run(ReplaySource(RECORDING, speed=0), Config(), record=path, osc=False, print_interval=0)
    assert summary["baseline"]["ready"]
    assert summary["valid_windows"] > 50 and summary["invalid_windows"] > 50
    frames = [json.loads(line) for line in (path / "controls.jsonl").read_text().splitlines()]
    assert any(row["status"]["valid"] for row in frames)
    assert any("suspected_artifact" in row["status"]["reasons"] for row in frames)
    assert all(row["status"]["connected"] for row in frames[1:])
    assert all(0 <= row["visual"]["color"] <= 1 for row in frames)
    assert all(row["osc"]["/neuro/posterior_alpha/available"] == 0 for row in frames)
    events = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
    assert sum(row["kind"] == "sample_gap" for row in events) == 3


def test_custom_art_changes_controls_but_preserves_real_eeg_and_quality(tmp_path):
    original, custom = tmp_path / "original", tmp_path / "custom"
    run(ReplaySource(RECORDING, speed=0), Config(), record=original, osc=False, print_interval=0)
    run(ReplaySource(RECORDING, speed=0), Config.load("examples/visual-custom.json"),
        record=custom, osc=False, print_interval=0)
    for name in ("raw.jsonl", "processed.jsonl", "features.jsonl", "quality.jsonl", "events.jsonl"):
        assert (original / name).read_bytes() == (custom / name).read_bytes()
    before = [json.loads(line) for line in (original / "controls.jsonl").read_text().splitlines()]
    after = [json.loads(line) for line in (custom / "controls.jsonl").read_text().splitlines()]
    assert len(before) == len(after)
    assert any(abs(a["visual"]["color"] - b["visual"]["color"]) > 0.01 for a, b in zip(before, after))
    assert any(row["status"]["valid"] and row["status"]["visual_available"]["coherence"] for row in after)
    assert all(not row["status"]["posterior_available"] for row in after)
    assert all(row["osc"]["/arte/tono"] == row["visual"]["color"] for row in after)


def test_a_missing_packet_inside_one_block_resets_filter_and_feature_history(tmp_path):
    metadata = SimulatedSource(duration=1, speed=0).metadata
    pipeline = Pipeline(metadata, Config(), tmp_path / "gap")
    t = np.arange(50) / 250
    t[20:] += 1 / 250  # exactly one missing sample inside the transport block
    x = np.tile((12 * np.sin(2 * np.pi * 10 * t))[:, None], (1, 8)) + 40000
    pipeline.ingest(Block(t, x, t[-1]))
    assert pipeline.timestamps[0] == t[20]
    assert len(pipeline.timestamps) == 30 and not pipeline.quality.valid
    pipeline.close()
    processed = json.loads((tmp_path / "gap" / "processed.jsonl").read_text())
    raw = json.loads((tmp_path / "gap" / "raw.jsonl").read_text())
    assert len(processed["samples"]) == len(raw["samples"]) == 50
