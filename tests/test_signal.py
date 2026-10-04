import numpy as np
import pytest

from neurovisual.acquisition import Acquisition
from neurovisual.artifacts import detect
from neurovisual.config import Config
from neurovisual.features import extract
from neurovisual.model import Block, SourceMetadata
from neurovisual.normalization import Normalizer
from neurovisual.processing import CausalFilter
from neurovisual.quality import assess


@pytest.fixture
def metadata():
    return SourceMetadata(250, [f"c{i}" for i in range(8)], "uV", "test",
                          {"frontal": ["c0", "c1"], "posterior": ["c6", "c7"],
                           "left": ["c2"], "right": ["c3"]})


@pytest.mark.parametrize("change", [dict(sample_rate=0), dict(sample_rate=float("nan")),
                                    dict(channels=["a"] * 8), dict(units="V"),
                                    dict(groups={"posterior": ["unknown"]}), dict(schema_version=2)])
def test_metadata_rejects_unknown_or_inconsistent_format(metadata, change):
    values = {**metadata.to_dict(), **change}
    with pytest.raises(ValueError):
        SourceMetadata(**values).validate()


def test_acquisition_preserves_channel_order_and_timestamps(metadata):
    t = np.arange(50) / 250 + 1730000000
    x = np.tile(np.arange(8), (50, 1)).astype(float)
    block = Block(t, x, t[-1])
    Acquisition(metadata).validate(block)
    np.testing.assert_array_equal(block.timestamps, t)
    np.testing.assert_array_equal(block.samples[0], np.arange(8))
    assert metadata.channels == [f"c{i}" for i in range(8)]


@pytest.mark.parametrize("kind", ["shape", "backward", "duplicate", "wrong_rate", "future", "infinity"])
def test_acquisition_rejects_bad_blocks(metadata, kind):
    t = np.arange(50) / 250
    x = np.ones((50, 8))
    if kind == "shape":
        x = x[:, :7]
    elif kind == "backward":
        t = t[::-1]
    elif kind == "duplicate":
        t[1] = t[0]
    elif kind == "wrong_rate":
        t *= 2
    elif kind == "infinity":
        x[0, 0] = np.inf
    receipt = -1 if kind == "future" else max(t)
    with pytest.raises(ValueError):
        Acquisition(metadata).validate(Block(t, x, receipt))


def test_acquisition_rejects_overlap_between_blocks(metadata):
    acquisition = Acquisition(metadata)
    block = Block(np.arange(25) / 250, np.zeros((25, 8)), 0.1)
    acquisition.validate(block)
    with pytest.raises(ValueError, match="entre bloques"):
        acquisition.validate(block)


def test_connection_status_is_an_explicit_boolean(metadata):
    with pytest.raises(ValueError, match="booleano"):
        Acquisition(metadata).validate(Block.empty(0, connected="false"))


def test_causal_filter_attenuates_drift_and_mains_but_keeps_alpha():
    fs = 250
    t = np.arange(10 * fs) / fs
    x = sum(np.sin(2 * np.pi * frequency * t) for frequency in (0.2, 10, 60))
    samples = np.tile(x[:, None], (1, 8))
    filtered = CausalFilter(fs, Config()).apply(samples)[2 * fs:, 0]
    time = t[2 * fs:]
    amplitude = lambda frequency: 2 * abs(np.mean(filtered * np.exp(-2j * np.pi * frequency * time)))
    assert amplitude(10) > 0.8
    assert amplitude(0.2) < 0.06
    assert amplitude(60) < 0.02


def test_filter_state_and_causality_are_independent_of_block_boundaries():
    rng = np.random.default_rng(34)
    x = rng.normal(size=(1800, 8))
    whole = CausalFilter(250, Config()).apply(x)
    streaming = CausalFilter(250, Config())
    parts = np.vstack([streaming.apply(part) for part in np.array_split(x, 37)])
    np.testing.assert_allclose(parts, whole, atol=1e-12)
    prefix = CausalFilter(250, Config()).apply(x[:600])
    np.testing.assert_allclose(prefix, whole[:600], atol=1e-12)


def test_quality_flags_flat_missing_and_motion():
    t = np.arange(750) / 250
    raw = np.tile((10 * np.sin(2 * np.pi * 10 * t))[:, None], (1, 8))
    clean = assess(raw, None, Config())
    assert clean.valid and not clean.motion_available
    raw[:, 3] = 0
    raw[100, 5] = np.nan
    imu = np.tile([0.0, 0.0, 1.0], (750, 1))
    imu[200, 0] = 0.5
    quality = assess(raw, imu, Config())
    assert not quality.valid
    assert quality.channels[3] == quality.channels[5] == 0
    assert "flat:ch4" in quality.reasons and "missing:ch6" in quality.reasons
    assert quality.motion == 1 and quality.motion_available


def test_synthetic_blink_is_marked_and_not_confused_with_clean_alpha(metadata):
    t = np.arange(125) / 250
    raw = np.tile((12 * np.sin(2 * np.pi * 10 * t))[:, None], (1, 8))
    assert not detect(raw, 250, metadata.groups, metadata, Config())["blink"]
    raw[:, :2] += (180 * np.exp(-0.5 * ((t - 0.25) / 0.06) ** 2))[:, None]
    assert detect(raw, 250, metadata.groups, metadata, Config())["blink"]
    assert not detect(raw, 250, {}, metadata, Config())["blink"]


def test_broadband_muscle_spikes_are_not_blink_events(metadata):
    t = np.arange(125) / 250
    muscle = 150 * np.sin(2 * np.pi * 55 * t)
    raw = np.tile(muscle[:, None], (1, 8))
    flags = detect(raw, 250, metadata.groups, metadata, Config())
    assert flags["muscle"] and not flags["blink"]


def test_band_power_and_unavailable_anatomical_groups(metadata):
    t = np.arange(750) / 250
    raw = np.tile((8 * np.sin(2 * np.pi * 6 * t) + 12 * np.sin(2 * np.pi * 10 * t)
                   + 5 * np.sin(2 * np.pi * 20 * t))[:, None], (1, 8))
    values, powers = extract(raw, metadata)
    for key, expected in [("theta", 32), ("alpha", 72), ("beta", 12.5)]:
        assert values[key] == pytest.approx(expected, rel=0.03)
        assert powers["c0"][key] == pytest.approx(expected, rel=0.03)
    metadata.groups = {}
    values, _ = extract(raw, metadata)
    assert values["posterior_alpha"] is None and values["lateral_balance"] is None


def test_normalization_uses_reference_only_and_stays_bounded():
    config = Config(baseline_seconds=0.4)
    normalizer = Normalizer(config)
    features = dict(theta=32, alpha=72, beta=12, posterior_alpha=None,
                    spectral_balance=1.8, lateral_balance=0)
    for _ in range(10):
        assert normalizer.observe(features, 0.2, reference=False) is None
    assert not normalizer.ready
    normalizer.observe(features, 0.2)
    assert normalizer.observe(features, 0.2) is not None
    bounds = normalizer.bounds.copy()
    for value in (-1e6, 1e6):
        extreme = {key: value for key in features}
        result = normalizer.observe(extreme, 10)
        assert all(0 <= result[key] <= 1 for key in result if key != "lateral_balance")
        assert -1 <= result["lateral_balance"] <= 1
    assert normalizer.bounds == bounds
    assert np.isfinite(result["posterior_alpha"])


def test_missing_values_are_not_reconstructed_for_consumers():
    x = np.ones((100, 8))
    x[10:20, 0] = np.nan
    result = CausalFilter(250, Config()).apply(x)
    assert np.isnan(result[10:20, 0]).all()
    assert np.isfinite(result[20:]).all()
