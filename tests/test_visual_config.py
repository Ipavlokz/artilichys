import json
import socket

import pytest
from pythonosc.osc_packet import OscPacket

from neurovisual.cli import main
from neurovisual.config import Config
from neurovisual.mapping import IDLE, VisualMapper
from neurovisual.output import OscOutput
from neurovisual.pipeline import Pipeline
from neurovisual.sources import SimulatedSource


FEATURES = dict(theta=0.2, alpha=0.8, beta=0.4, posterior_alpha=0.6,
                spectral_balance=0.9, lateral_balance=-0.6)


def test_changing_a_mapping_selects_its_input_and_preserves_other_controls():
    default = VisualMapper(Config())
    custom = VisualMapper(Config(visual_mapping={"color": "theta"}))
    default.accept(FEATURES, 0, True)
    custom.accept(FEATURES, 0, True)
    assert default.target["color"] == pytest.approx(0.8)
    assert custom.target["color"] == pytest.approx(0.2)
    for control in ("intensity", "flow", "coherence"):
        assert custom.target[control] == default.target[control]
    changed = {**FEATURES, "alpha": 0.1}
    custom.accept(changed, 1, True)
    assert custom.target["color"] == pytest.approx(0.2)


def test_mixing_inverting_and_signed_input_produce_bounded_controls():
    mapper = VisualMapper(Config(visual_mapping={
        "color": {"weights": {"alpha": 7, "theta": 3}},
        "intensity": {"weights": {"beta": 1}, "invert": True},
        "flow": "lateral_balance",
    }))
    mapper.accept(FEATURES, 0, True)
    assert mapper.target["color"] == pytest.approx(0.62)
    assert mapper.target["intensity"] == pytest.approx(0.6)
    assert mapper.target["flow"] == pytest.approx(0.2)
    for balance, expected in ((-1, 0), (0, 0.5), (1, 1)):
        mapper.accept({**FEATURES, "lateral_balance": balance}, 1, True)
        assert mapper.target["flow"] == pytest.approx(expected)


def test_custom_rules_cannot_bypass_quality_hold_and_return_to_idle():
    mapper = VisualMapper(Config(visual_mapping={"color": "theta"}))
    mapper.accept({**FEATURES, "theta": 1}, 0, True)
    mapper.render(0, True)
    before = mapper.render(2, True)
    assert not mapper.accept({**FEATURES, "theta": 0}, 2, False)
    assert mapper.render(2.5, False) == before
    after = mapper.render(4, False)
    assert IDLE["color"] < after["color"] < before["color"]
    mapper.accept({**FEATURES, "theta": 0}, 4.1, True)
    assert mapper.render(4.5, True)["color"] < after["color"]


def test_unknown_electrode_groups_keep_dependent_rules_at_idle():
    available = {key: True for key in FEATURES}
    available.update(posterior_alpha=False, lateral_balance=False)
    mapper = VisualMapper(Config(visual_mapping={
        "color": {"weights": {"alpha": 1, "posterior_alpha": 1}, "invert": True},
        "flow": "lateral_balance",
        "intensity": {"weights": {"beta": 1, "posterior_alpha": 0}},
    }), available_features=available)
    mapper.accept(FEATURES, 0, True)
    assert not mapper.available["color"] and not mapper.available["flow"]
    assert mapper.target["color"] == IDLE["color"]
    assert mapper.target["flow"] == IDLE["flow"]
    assert mapper.available["intensity"] and mapper.target["intensity"] == 0.4


@pytest.mark.parametrize("options, message", [
    ({"visual_mapping": []}, "visual_mapping"),
    ({"visual_mapping": {"unknown": "alpha"}}, "Control desconocido"),
    ({"visual_mapping": {"color": "emotion"}}, "Característica desconocida"),
    ({"visual_mapping": {"color": {"weights": {"alpha": 0}}}}, "positiva"),
    ({"visual_mapping": {"color": {"weights": {"alpha": -1}}}}, "pesos finitos"),
    ({"visual_mapping": {"color": {"weights": {"alpha": float("nan")}}}}, "pesos finitos"),
    ({"visual_mapping": {"color": {"weights": {"alpha": True}}}}, "pesos finitos"),
    ({"visual_mapping": {"color": {"weights": {"alpha": 1}, "invert": 1}}}, "invert"),
    ({"osc_addresses": {"color": "/visual/intensity"}}, "duplicadas"),
    ({"osc_addresses": {"color": "/neuro/alpha"}}, "reservadas"),
    ({"osc_addresses": {"color": "/arte/*"}}, "OSC inválida"),
    ({"osc_addresses": {"color": "/arte/color con espacios"}}, "OSC inválida"),
])
def test_unsafe_or_ambiguous_configuration_is_rejected(options, message):
    with pytest.raises(ValueError, match=message):
        Config(**options).validate(250)


def test_config_overlay_keeps_saved_filters_and_unmentioned_rules(tmp_path):
    base = Config(low_hz=2, line_hz=50, visual_mapping={"color": "theta", "flow": "beta"},
                  osc_addresses={"color": "/arte/tono"})
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"visual_mapping": {"color": "alpha"},
                                "osc_addresses": {"flow": "/arte/flujo"}}), encoding="utf-8-sig")
    overlay = Config.load(path, base=base)
    overlay.validate(250)
    assert overlay.low_hz == 2 and overlay.line_hz == 50
    assert overlay.mapping_rules["color"] == "alpha" and overlay.mapping_rules["flow"] == "beta"
    assert overlay.visual_addresses["color"] == "/arte/tono"
    assert overlay.visual_addresses["flow"] == "/arte/flujo"
    assert base.mapping_rules["color"] == "theta"  # does not mutate saved settings


def test_renamed_visual_messages_arrive_over_udp_without_renaming_eeg():
    config = Config.load("examples/visual-custom.json")
    pipeline = Pipeline(SimulatedSource(duration=1, speed=0).metadata, config)
    frame = pipeline.tick(0)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(2)
        output = OscOutput(port=receiver.getsockname()[1])
        try:
            output.send(frame["osc"])
            packet, _ = receiver.recvfrom(8192)
        finally:
            output.close()
    values = {item.message.address: item.message.params[0] for item in OscPacket(packet).messages}
    assert len(values) == 32
    assert "/visual/color" not in values and values["/arte/tono"] == 0.5
    assert "/neuro/alpha" in values and "/neuro/quality/ch8" in values
    assert isinstance(values["/arte/tono"], float)
    assert isinstance(values["/arte/pulso"], int) and isinstance(values["/arte/escena"], int)


def test_cli_preserves_artistic_settings_on_replay_and_overlay(tmp_path, capsys):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"line_hz": 50, "visual_mapping": {"color": "theta"},
                                 "osc_addresses": {"color": "/arte/tono"}}))
    original, repeated, changed = [tmp_path / name for name in ("original", "repeated", "changed")]
    assert main(["run", "--duration", "1", "--speed", "0", "--no-osc", "--quiet",
                 "--config", str(config), "--record", str(original)]) == 0
    assert main(["replay", str(original), "--speed", "0", "--no-osc", "--quiet",
                 "--record", str(repeated)]) == 0
    overlay = tmp_path / "overlay.json"
    overlay.write_text('{"visual_mapping":{"color":"beta"}}')
    assert main(["replay", str(original), "--speed", "0", "--no-osc", "--quiet",
                 "--config", str(overlay), "--record", str(changed)]) == 0
    capsys.readouterr()
    for name in ("raw.jsonl", "processed.jsonl", "features.jsonl", "controls.jsonl"):
        assert (original / name).read_bytes() == (repeated / name).read_bytes()
    manifest = json.loads((changed / "metadata.json").read_text())
    assert manifest["config"]["line_hz"] == 50
    assert manifest["config"]["visual_mapping"]["color"] == "beta"
    assert manifest["config"]["osc_addresses"]["color"] == "/arte/tono"


def test_cli_rejects_invalid_artistic_config_before_creating_session(tmp_path, capsys):
    config = tmp_path / "bad.json"
    config.write_text('{"osc_addresses":{"color":"/neuro/alpha"}}')
    session = tmp_path / "session"
    with pytest.raises(SystemExit) as exc:
        main(["run", "--config", str(config), "--record", str(session)])
    assert exc.value.code == 2
    assert "reservadas" in capsys.readouterr().err
    assert not session.exists()
