from dataclasses import dataclass
import numpy as np


@dataclass
class Quality:
    channels: list[float]
    global_score: float
    motion: float
    reasons: list[str]
    valid: bool
    motion_available: bool

    def to_dict(self):
        return dict(channels=self.channels, global_score=self.global_score,
                    motion=self.motion, reasons=self.reasons, valid=self.valid,
                    motion_available=self.motion_available)


def assess(raw, imu, config, complete=True):
    scores = np.ones(8)
    reasons = []
    if not len(raw):
        return Quality([0.0] * 8, 0.0, 0.0, ["no_data"], False, False)
    for ch in range(8):
        x = raw[:, ch]
        good = x[np.isfinite(x)]
        if len(good) != len(x):
            scores[ch] = 0
            reasons.append(f"missing:ch{ch + 1}")
        if len(good) == 0:
            continue
        if np.ptp(good) < config.flat_uv:
            scores[ch] = 0
            reasons.append(f"flat:ch{ch + 1}")
        # Electrode DC offsets can be tens of millivolts. Assess excursions
        # around the current past-window median without changing recorded data.
        if np.max(np.abs(good - np.median(good))) > config.amplitude_uv:
            scores[ch] = 0
            reasons.append(f"amplitude:ch{ch + 1}")
    # Detect short flat segments too; not just a whole window that has gone flat.
    tail = raw[-max(2, int(len(raw) * 0.15)):]
    for ch in range(8):
        if np.all(np.isfinite(tail[:, ch])) and np.ptp(tail[:, ch]) < config.flat_uv:
            scores[ch] = 0
            if f"flat:ch{ch + 1}" not in reasons:
                reasons.append(f"flat:ch{ch + 1}")
    available = imu is not None and len(imu) > 1 and np.all(np.isfinite(imu))
    motion = 0.0
    if available:
        # Dynamic acceleration after removing the per-window gravity/offset median.
        dynamic = np.linalg.norm(imu - np.median(imu, axis=0), axis=1)
        motion = float(np.clip(np.max(dynamic) / config.motion_g, 0, 1))
        if motion >= 1:
            scores *= 0.25
            reasons.append("motion")
    if not complete:
        reasons.append("warming_up")
    global_score = float(np.mean(scores))
    # Any failed channel invalidates the feature vector in phase 1.
    valid = bool(complete and min(scores) >= config.min_quality and not reasons)
    return Quality(scores.tolist(), global_score, motion, reasons, valid, bool(available))
