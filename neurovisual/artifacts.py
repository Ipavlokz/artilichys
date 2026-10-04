import numpy as np
from scipy.signal import welch


def detect(raw, sample_rate, groups, metadata, config):
    """Conservative suspicion flags, not physiological classification."""
    flags = {"blink": False, "muscle": False}
    if len(raw) < 4 or not np.all(np.isfinite(raw)):
        return flags
    frontal = [metadata.channels.index(ch) for ch in groups.get("frontal", [])]
    f, p = welch(raw, fs=sample_rate, axis=0, nperseg=min(len(raw), int(sample_rate)),
                 detrend="constant")
    high = p[(f >= 30) & (f <= min(80, sample_rate / 2 - 1))].sum(axis=0)
    total = p[(f >= 1) & (f <= min(80, sample_rate / 2 - 1))].sum(axis=0)
    if frontal:
        x = raw[:, frontal]
        slow = p[(f >= 1) & (f <= 4)].sum(axis=0)
        # Blink-like slow frontal transient. Broadband spikes alone are not enough.
        slow_fraction = slow[frontal] / np.maximum(total[frontal], 1e-12)
        high_fraction = high[frontal] / np.maximum(total[frontal], 1e-12)
        flags["blink"] = bool(np.any((np.max(np.abs(x), axis=0) > config.blink_uv)
                                     & (np.ptp(x, axis=0) > config.blink_uv)
                                     & (slow_fraction > 0.3) & (high_fraction < 0.25)))
    rms = np.std(raw, axis=0)
    flags["muscle"] = bool(np.any((high / np.maximum(total, 1e-12) > config.muscle_ratio)
                                  & (rms > config.muscle_rms_uv)))
    return flags
