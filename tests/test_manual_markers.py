from concurrent.futures import ThreadPoolExecutor
import json
import socket

import numpy as np
import pytest

from neurovisual.analysis import compare_conditions
from neurovisual.cli import main
from neurovisual.config import Config
from neurovisual.model import Block
from neurovisual.runner import run
from neurovisual.sources import ReplaySource, SimulatedSource, Source
from neurovisual.sources.markers import ManualMarkedSource, MarkedSource, send_marker


class ControlledSource(Source):
    def __init__(self, blocks, clock=100.06):
        self.metadata = SimulatedSource(duration=1, speed=0).metadata
        self.blocks = list(blocks)
        self.clock = clock
        self.closed = False

    @property
    def finished(self):
        return not self.blocks

    def now(self):
        return self.clock

    def read(self, timeout):
        return self.blocks.pop(0)

    def close(self):
        self.closed = True


def sample_block(end, native=True):
    stamps = end - 0.05 + np.arange(12) / 250
    return Block(stamps, np.ones((12, 8)), end,
                 markers=[{"timestamp": stamps[0], "condition": "music"}] if native else [])


def request(client, source, condition="music", **extra):
    payload = {"id": "operator-1", "condition": condition, "label": "Cancion de prueba", **extra}
    client.sendto(json.dumps(payload).encode(), ("127.0.0.1", source.port))


def test_manual_marker_uses_source_clock_waits_for_eligible_block_and_keeps_eeg():
    underlying = ControlledSource([sample_block(100.05), sample_block(100.10)])
    source = ManualMarkedSource(underlying, port=0)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(1)
            request(client, source)
            first = source.read(0)
            assert [m["condition"] for m in first.markers] == ["reference"]
            second = source.read(0)
            ack = json.loads(client.recv(4096))
        assert ack["ok"] and ack["timestamp"] == pytest.approx(100.06)
        assert second.markers[0]["condition"] == "music"
        assert second.markers[0]["timestamp"] < second.received_at
        np.testing.assert_array_equal(second.samples, np.ones((12, 8)))
        np.testing.assert_array_equal(second.timestamps, sample_block(100.10).timestamps)
        assert source.metadata.auxiliary["condition_markers"]["controls_audio"] is False
    finally:
        source.close()
    assert underlying.closed


def test_manual_marker_is_retained_during_no_data_and_disconnection():
    source = ManualMarkedSource(ControlledSource([None, Block.empty(100.10, False)]), port=0)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(1)
            request(client, source)
            assert source.read(0) is None
            block = source.read(0)
            ack = json.loads(client.recv(4096))
        assert ack["ok"] and block.markers[-1]["condition"] == "music"
        assert not block.connected and block.samples.shape == (0, 8)
    finally:
        source.close()


def test_pending_marker_reports_failure_if_source_finishes_before_its_time():
    source = ManualMarkedSource(ControlledSource([sample_block(100.05)]), port=0)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(1)
        request(client, source)
        source.read(0)
        source.close()
        ack = json.loads(client.recv(4096))
    assert not ack["ok"] and "no incorporado" in ack["error"]


def test_invalid_marker_request_is_rejected_without_changing_condition():
    source = ManualMarkedSource(ControlledSource([sample_block(100.10)]), port=0)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(1)
            request(client, source, "unknown")
            block = source.read(0)
            ack = json.loads(client.recv(4096))
        assert not ack["ok"]
        assert [m["condition"] for m in block.markers] == ["reference"]
    finally:
        source.close()


def test_invalid_pipeline_settings_release_the_marker_port_and_source():
    underlying = ControlledSource([sample_block(100.10)])
    source = ManualMarkedSource(underlying, port=0)
    port = source.port
    with pytest.raises(ValueError):
        run(source, Config(window_seconds=0), osc=False, print_interval=0)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as replacement:
        replacement.bind(("127.0.0.1", port))
    assert underlying.closed


def test_cli_mark_gets_confirmation_from_real_udp_receiver(capsys):
    source = ManualMarkedSource(ControlledSource([sample_block(100.10)]), port=0)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(main, ["mark", "music", "--port", str(source.port), "--label", "Pista 1"])
            # Wait for the datagram without consuming it, then let normal read handle it.
            source.socket.settimeout(1)
            source.socket.recvfrom(4096, socket.MSG_PEEK)
            source.socket.setblocking(False)
            block = source.read(0)
            assert future.result(timeout=2) == 0
        assert block.markers[-1]["label"] == "Pista 1"
        assert "Marcador recibido: music" in capsys.readouterr().out
    finally:
        source.close()


def test_no_marker_receiver_fails_clearly():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as unused:
        unused.bind(("127.0.0.1", 0))
        with pytest.raises(ValueError, match="No llegó confirmación"):
            send_marker("music", port=unused.getsockname()[1], timeout=0.02)


@pytest.mark.parametrize("args", [
    ["run", "--speed", "0"],
    ["run", "--markers", "examples/markers.json"],
    ["run", "--no-record"],
    ["run", "--marker-port", "0"],
    ["replay", "examples/recordings/openbci"],
])
def test_cli_manual_markers_rejects_ambiguous_or_unrecorded_runs(args, capsys):
    with pytest.raises(SystemExit) as exc:
        main([*args, "--manual-markers"])
    assert exc.value.code == 2
    assert capsys.readouterr().err


@pytest.mark.parametrize("contents", [
    '[1]', '[{"timestamp":true,"condition":"music"}]',
    '[{"timestamp":0,"condition":"music"},{"timestamp":0,"condition":"reference"}]',
])
def test_file_markers_validate_schema_without_attribute_errors(tmp_path, contents):
    path = tmp_path / "markers.json"
    path.write_text(contents)
    with pytest.raises(ValueError):
        MarkedSource(SimulatedSource(duration=1, speed=0), path)


def test_explicit_file_markers_replace_simulated_conditions(tmp_path):
    path = tmp_path / "markers.json"
    path.write_text('[{"timestamp":0,"condition":"reference"}]')
    source = MarkedSource(SimulatedSource(duration=13, speed=0), path)
    markers = []
    while not source.finished:
        markers.extend(source.read(0).markers)
    assert markers == [{"timestamp": 0, "condition": "reference"}]


def test_manual_session_replays_and_compares_known_signal_without_transition_windows(tmp_path, capsys):
    class ScheduledOperator(ManualMarkedSource):
        def __init__(self):
            super().__init__(SimulatedSource(duration=96, speed=0), port=0)
            self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.next_change = 12

        def read(self, timeout):
            if self.now() >= self.next_change:
                condition = "music" if int(self.next_change / 12) % 2 else "reference"
                request(self.client, self, condition)
                self.next_change += 12
            return super().read(timeout)

        def close(self):
            self.client.close()
            super().close()

    original, replay = tmp_path / "manual", tmp_path / "replay"
    summary = run(ScheduledOperator(), Config(), record=original, osc=False, print_interval=0)
    assert summary["baseline"]["ready"]
    rows = [json.loads(line) for line in (original / "features.jsonl").read_text().splitlines()]
    assert any(row["condition"] == "transition" and row["valid"] for row in rows)
    report = compare_conditions(original)
    assert min(report["windows"].values()) >= 5
    changed_alpha = {f["channel"] for f in report["findings"]
                     if f["band"] == "alpha" and f["classification"] == "cambio_observado"}
    assert changed_alpha == {"ch1", "ch2", "ch3", "ch4"}
    run(ReplaySource(original, speed=0), Config(), record=replay, osc=False, print_interval=0)
    for name in ("raw.jsonl", "features.jsonl", "events.jsonl", "controls.jsonl"):
        assert (original / name).read_bytes() == (replay / name).read_bytes()
    output = tmp_path / "comparison.json"
    assert main(["compare", str(original), "--display", "text", "--output", str(output)]) == 0
    text = capsys.readouterr().out
    assert "Ventanas validas sin solapamiento" in text and "ch1 | alpha | cambio observado" in text
    assert "No atribuye causalidad" in text
    assert json.loads(output.read_text())["findings"] == report["findings"]
