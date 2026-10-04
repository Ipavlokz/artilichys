import json
import socket

import numpy as np
import pytest
from pythonosc.osc_packet import OscPacket

from neurovisual.analysis import compare_conditions
from neurovisual.config import Config
from neurovisual.mapping import IDLE, VisualMapper
from neurovisual.model import Block
from neurovisual.output import OscOutput
from neurovisual.pipeline import Pipeline
from neurovisual.runner import run
from neurovisual.sources import ReplaySource, SimulatedSource
from neurovisual.sources.replay import inspect_source
from neurovisual.sources.base import Source


def read_lines(path):
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def test_invalid_features_cannot_change_visual_target_and_idle_is_smooth():
    mapper = VisualMapper(Config(hold_seconds=1, idle_seconds=2))
    high = dict(theta=1, alpha=1, beta=1, posterior_alpha=1)
    mapper.accept(high, 0, True)
    mapper.render(0, True)
    for t in np.arange(0.1, 3, 0.1):
        state = mapper.render(t, True)
    original = state.copy()
    assert not mapper.accept({key: 0 for key in high}, 3, False)
    assert mapper.render(3.5, False) == original
    decayed = mapper.render(5, False)
    assert IDLE["intensity"] < decayed["intensity"] < original["intensity"]
    assert mapper.target["intensity"] == 1


@pytest.fixture(scope="module")
def fault_session(tmp_path_factory):
    path = tmp_path_factory.mktemp("faults") / "session"
    source = SimulatedSource(duration=45, scenarios=["blink", "muscle", "motion", "flat", "missing", "disconnect", "stalled"], speed=0)
    summary = run(source, Config(), record=path, osc=False, print_interval=0)
    return path, summary


def test_full_pipeline_artifacts_dropout_freeze_and_recovery(fault_session):
    path, summary = fault_session
    assert summary["valid_windows"] > 5 and summary["invalid_windows"] > 5
    assert summary["baseline"]["ready"]
    events = read_lines(path / "events.jsonl")
    assert {"blink", "muscle", "disconnect", "reconnect", "sample_gap"} <= {e["kind"] for e in events}
    quality = read_lines(path / "quality.jsonl")
    reasons = {reason for row in quality for reason in row["reasons"]}
    assert {"suspected_artifact", "motion", "flat:ch8", "missing:ch6"} <= reasons
    controls = read_lines(path / "controls.jsonl")
    assert any(not row["status"]["connected"] for row in controls)
    assert any(row["status"]["connected"] and row["status"]["stale"] for row in controls)
    assert any(row["status"]["valid"] and row["timestamp"] > 42 for row in controls)
    assert sum(row["events"]["blink"] for row in controls) >= 1
    for row in controls:
        assert all(0 <= row["visual"][key] <= 1 for key in ("color", "intensity", "flow", "coherence"))
        assert -1 <= row["features"]["lateral_balance"] <= 1
        assert isinstance(row["visual"]["scene"], int)
    features = read_lines(path / "features.jsonl")
    assert all(row["raw_features"] is None for row in features if not row["valid"])
    # Missing raw samples survive recording even though no feature is emitted for them.
    raw = read_lines(path / "raw.jsonl")
    assert any(value is None for row in raw for sample in row["samples"] for value in sample)


def test_session_replay_preserves_raw_times_channels_and_processing(fault_session, tmp_path):
    path, _ = fault_session
    source = ReplaySource(path, speed=0)
    replay = tmp_path / "replayed"
    result = run(source, Config(), record=replay, osc=False, print_interval=0)
    assert result["baseline"]["ready"]
    assert read_lines(path / "raw.jsonl") == read_lines(replay / "raw.jsonl")
    assert read_lines(path / "processed.jsonl") == read_lines(replay / "processed.jsonl")
    assert read_lines(path / "features.jsonl") == read_lines(replay / "features.jsonl")
    inspected = inspect_source(ReplaySource(path / "raw.jsonl", speed=0))
    assert inspected["samples"] > 10000 and inspected["missing_values"] > 0


def test_stale_source_keeps_osc_and_freezes_features():
    source = SimulatedSource(duration=10, speed=0)
    pipeline = Pipeline(source.metadata, Config(baseline_seconds=0.4))
    while not source.finished:
        block = source.read(0)
        pipeline.ingest(block)
        pipeline.tick(block.received_at)
    last = pipeline.tick(10.1)
    assert last["status"]["valid"]
    later = pipeline.tick(10.8)
    assert later["status"]["connected"] and later["status"]["stale"]
    assert later["features"] == last["features"]
    assert later["status"]["global_score"] == 0
    assert later["visual"] == last["visual"]


def test_reconnect_event_waits_for_real_data_after_empty_heartbeat():
    source = SimulatedSource(duration=1, speed=0)
    pipeline = Pipeline(source.metadata, Config())
    first = source.read(0)
    pipeline.ingest(first)
    pipeline.ingest(Block.empty(0.1, False))
    pipeline.ingest(Block.empty(0.2, True))
    t = np.arange(10) / 250 + 0.3
    pipeline.ingest(Block(t, np.ones((10, 8)), 0.34))
    assert pipeline.tick(0.34)["events"]["reconnect"] == 1
    assert pipeline.tick(0.4)["events"]["reconnect"] == 0


def test_raw_is_saved_before_schema_rejection(tmp_path):
    metadata = SimulatedSource(duration=1, speed=0).metadata
    path = tmp_path / "invalid"
    pipeline = Pipeline(metadata, Config(), path)
    with pytest.raises(ValueError):
        pipeline.ingest(Block(np.array([0.0, 0.1]), np.zeros((2, 7)), 0.1))
    pipeline.close()
    assert len(read_lines(path / "raw.jsonl")) == 1


def test_live_contract_timeout_without_blocks_still_outputs_stale_frames(tmp_path):
    class QuietLiveSource(Source):
        def __init__(self):
            simulated = SimulatedSource(duration=1, speed=0)
            self.metadata = simulated.metadata
            self.first = simulated.read(0)
            self.clock = 0
            self.finished = False

        def read(self, timeout):
            assert timeout <= 0.1
            if self.first is not None:
                block, self.first = self.first, None
                self.clock = block.received_at
                return block
            self.clock += timeout
            self.finished = self.clock >= 1.5
            return None

        def now(self):
            return self.clock

    path = tmp_path / "idle_live"
    summary = run(QuietLiveSource(), Config(), record=path, osc=False, print_interval=0)
    frames = read_lines(path / "controls.jsonl")
    assert summary["output_frames"] >= 22
    assert len(read_lines(path / "raw.jsonl")) == 1
    assert any(row["status"]["connected"] and row["status"]["stale"] for row in frames)


def test_real_udp_osc_bundle_addresses_ranges_and_types():
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(2)
    output = OscOutput(port=receiver.getsockname()[1])
    pipeline = Pipeline(SimulatedSource(duration=1, speed=0).metadata, Config())
    state = pipeline.tick(0)
    try:
        output.send(state["osc"])
        datagram, _ = receiver.recvfrom(8192)
        values = {item.message.address: item.message.params[0] for item in OscPacket(datagram).messages}
    finally:
        output.close()
        receiver.close()
    assert {f"/neuro/quality/ch{i}" for i in range(1, 9)} <= values.keys()
    assert {"/neuro/theta", "/neuro/alpha", "/neuro/beta", "/neuro/posterior_alpha",
            "/neuro/spectral_balance", "/neuro/lateral_balance", "/neuro/event/blink",
            "/neuro/event/muscle", "/neuro/event/reconnect", "/visual/scene", "/visual/pulse"} <= values.keys()
    assert isinstance(values["/visual/scene"], int)
    assert isinstance(values["/neuro/alpha"], float)
    assert values["/neuro/stale"] == 1
    assert len(values) == len(state["osc"])


def test_music_comparison_recovers_known_response_and_negative_controls(tmp_path):
    path = tmp_path / "experiment"
    run(SimulatedSource(duration=96, speed=0), Config(), record=path, osc=False, print_interval=0)
    report = compare_conditions(path)
    findings = {(row["channel"], row["band"]): row for row in report["findings"]}
    assert min(report["windows"].values()) >= 5
    assert findings["ch1", "alpha"]["classification"] == "cambio_observado"
    assert findings["ch1", "alpha"]["percent_change"] > 80
    assert findings["ch8", "alpha"]["classification"] == "compatible_con_cambio_pequeno"
    assert findings["ch1", "theta"]["classification"] == "compatible_con_cambio_pequeno"
