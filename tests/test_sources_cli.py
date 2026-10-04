import json
import time

import numpy as np
import pytest

from neurovisual.cli import main
from neurovisual.model import SourceMetadata
from neurovisual.sources import ReplaySource, SimulatedSource
from neurovisual.sources.markers import MarkedSource
from neurovisual.sources.replay import inspect_source


def test_csv_explicit_mapping_preserves_values_and_channel_order(tmp_path):
    metadata = SourceMetadata(100, [f"ch{i}" for i in range(1, 9)], "uV", "csv")
    meta = tmp_path / "metadata.json"
    meta.write_text(json.dumps(metadata.to_dict()))
    mapping = {"timestamp": "time", **{f"ch{i}": f"E{i}" for i in range(1, 9)}}
    csv = tmp_path / "recording.csv"
    csv.write_text("time,E8,E7,E6,E5,E4,E3,E2,E1\n" + "\n".join(
        f"{t / 100},8,7,6,5,4,3,2,1" for t in range(30)))
    source = ReplaySource(csv, speed=0, metadata_path=meta, column_map=mapping)
    block = source.read(0)
    np.testing.assert_array_equal(block.samples[0], np.arange(1, 9))
    np.testing.assert_array_equal(block.timestamps, np.arange(5) / 100)
    assert block.received_at == 0.04


def test_csv_requires_metadata_and_reports_missing_column(tmp_path):
    csv = tmp_path / "bad.csv"
    csv.write_text("timestamp,ch1\n0,1\n")
    with pytest.raises(ValueError, match="requiere --metadata"):
        ReplaySource(csv)
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(SourceMetadata(250, [f"ch{i}" for i in range(1, 9)], "uV", "csv").to_dict()))
    with pytest.raises(ValueError, match="Faltan columnas"):
        ReplaySource(csv, metadata_path=metadata)


def test_source_respects_read_timeout_and_timestamp_pacing():
    source = SimulatedSource(duration=0.3, speed=1)
    start = time.monotonic()
    assert source.read(0) is None
    assert time.monotonic() - start < 0.1
    block = None
    while block is None:
        block = source.read(0.01)
    elapsed = time.monotonic() - start
    assert 0.04 <= elapsed < 1.0
    assert block.received_at == pytest.approx(0.048)


def test_external_markers_are_attached_in_source_clock(tmp_path):
    path = tmp_path / "markers.json"
    path.write_text('[{"timestamp":0,"condition":"reference"},{"timestamp":0.1,"condition":"music"}]')
    source = MarkedSource(SimulatedSource(duration=0.3, speed=0), path)
    markers = []
    while not source.finished:
        block = source.read(0)
        markers.extend(block.markers)
    assert {"timestamp": 0.1, "condition": "music"} in markers


def test_cli_simulation_inspect_and_replay(tmp_path, capsys):
    path = tmp_path / "cli_session"
    assert main(["run", "--duration", "0.3", "--speed", "0", "--no-osc", "--quiet", "--record", str(path)]) == 0
    capsys.readouterr()
    assert main(["inspect", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["samples"] == 75
    assert main(["replay", str(path), "--speed", "0", "--no-osc", "--quiet"]) == 0
    assert json.loads(capsys.readouterr().out)["output_frames"] >= 4


def test_example_csv_is_valid():
    result = inspect_source(ReplaySource("examples/sample.csv", speed=0, metadata_path="examples/sample.metadata.json"))
    assert result["samples"] == 100


def test_cli_readable_output_does_not_require_reading_json(tmp_path, capsys):
    assert main(["run", "--duration", "0.3", "--speed", "0", "--no-osc", "--no-record", "--display", "text"]) == 0
    output = capsys.readouterr().out
    assert "calibracion=PENDIENTE" in output and "Finalizado:" in output
    assert "Referencia personal:" in output
