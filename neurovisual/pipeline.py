import numpy as np

from .acquisition import Acquisition
from .artifacts import detect
from .features import extract
from .mapping import VisualMapper
from .normalization import Normalizer
from .output import FEATURE_KEYS, messages
from .processing import CausalFilter
from .quality import Quality, assess
from .recording import SessionRecorder, block_dict


class Pipeline:
    def __init__(self, metadata, config, record_path=None):
        self.metadata = metadata
        self.config = config
        self.acquisition = Acquisition(metadata)
        self.filter = CausalFilter(metadata.sample_rate, config)
        self.normalizer = Normalizer(config)
        feature_available = {key: True for key in FEATURE_KEYS}
        feature_available["posterior_alpha"] = bool(metadata.groups.get("posterior"))
        feature_available["lateral_balance"] = bool(metadata.groups.get("left") and metadata.groups.get("right"))
        self.mapper = VisualMapper(config, available_features=feature_available)
        self.recorder = None
        if record_path is not None:
            self.recorder = SessionRecorder(record_path, metadata, config,
                                            {"causal": True, "sos": self.filter.sos.tolist(),
                                             "notch_applied": self.filter.notch_applied})
        self.timestamps = np.empty(0)
        self.raw = np.empty((0, 8))
        self.processed = np.empty((0, 8))
        self.imu = np.empty((0, 3))
        self.connected = False
        self.seen_connection = False
        self.awaiting_reconnect = False
        self.last_arrival = None
        self.last_sample = None
        self.settle_until = None
        self.last_feature = None
        self.condition = "reference"
        self.condition_since = -np.inf
        self.pending = {key: 0 for key in ("blink", "muscle", "reconnect")}
        self.active = {"blink": False, "muscle": False}
        self.last_event = {"blink": -np.inf, "muscle": -np.inf}
        self.last_artifact = -np.inf
        self.quality = Quality([0.0] * 8, 0.0, 0.0, ["no_data"], False, False)
        self.normalized = {key: 0.5 for key in FEATURE_KEYS}
        self.normalized["lateral_balance"] = 0.0
        self.valid_windows = 0
        self.invalid_windows = 0

    def log(self, name, data):
        if self.recorder:
            self.recorder.write(name, data)

    def event(self, kind, timestamp):
        self.pending[kind] = 1
        self.log("events", {"timestamp": timestamp, "kind": kind, "suspected": kind != "reconnect"})

    def reset_signal(self):
        self.filter.reset()
        self.timestamps = np.empty(0)
        self.raw = np.empty((0, 8))
        self.processed = np.empty((0, 8))
        self.imu = np.empty((0, 3))
        self.settle_until = None
        self.last_sample = None
        self.active = {"blink": False, "muscle": False}
        self.quality = Quality([0.0] * 8, 0.0, 0.0, ["warming_up"], False, False)

    def ingest(self, block):
        self.log("raw", block_dict(block))
        self.acquisition.validate(block)
        previous = self.connected
        self.connected = bool(block.connected)
        for marker in block.markers:
            self.condition = marker["condition"]
            self.condition_since = float(marker["timestamp"])
            self.log("events", {"kind": "condition", **marker})
        if not self.connected:
            self.awaiting_reconnect = self.seen_connection
            if previous:
                self.reset_signal()
                self.log("events", {"timestamp": block.received_at, "kind": "disconnect"})
            self.mapper.accept(None, block.received_at, False)
            return
        if not len(block.timestamps):
            return
        if self.awaiting_reconnect:
            self.event("reconnect", block.received_at)
            self.reset_signal()
            self.awaiting_reconnect = False
        self.seen_connection = True
        fs = self.metadata.sample_rate
        if self.last_sample is not None and block.timestamps[0] - self.last_sample > 1.5 / fs:
            self.reset_signal()
            self.log("events", {"timestamp": block.received_at, "kind": "sample_gap"})
        # A packet gap may occur inside a block, not only at its boundary.
        starts = [0, *(np.flatnonzero(np.diff(block.timestamps) > 1.5 / fs) + 1).tolist()]
        stops = [*starts[1:], len(block.timestamps)]
        filtered = np.empty_like(block.samples)
        for start, stop in zip(starts, stops):
            if start:
                self.reset_signal()
                self.log("events", {"timestamp": float(block.timestamps[start]), "kind": "sample_gap"})
            if self.settle_until is None:
                self.settle_until = float(block.timestamps[start]) + self.config.settle_seconds
            filtered[start:stop] = self.filter.apply(block.samples[start:stop])
        self.last_arrival = block.received_at
        self.last_sample = float(block.timestamps[-1])
        self.log("processed", {"timestamps": block.timestamps, "samples": filtered,
                               "received_at": block.received_at})
        tail = starts[-1]
        self.timestamps = np.concatenate([self.timestamps, block.timestamps[tail:]])
        self.raw = np.vstack([self.raw, block.samples[tail:]])
        self.processed = np.vstack([self.processed, filtered[tail:]])
        imu = block.imu if block.imu is not None else np.full((len(block.timestamps), 3), np.nan)
        self.imu = np.vstack([self.imu, imu[tail:]])
        keep = self.timestamps > self.last_sample - self.config.window_seconds
        self.timestamps, self.raw, self.processed, self.imu = (
            self.timestamps[keep], self.raw[keep], self.processed[keep], self.imu[keep])
        recent = self.raw[-max(4, int(fs * 0.5)):]
        flags = detect(recent, fs, self.metadata.groups, self.metadata, self.config)
        for kind, active in flags.items():
            if active:
                self.last_artifact = block.received_at
                if not self.active[kind] and block.received_at - self.last_event[kind] >= self.config.event_refractory:
                    self.event(kind, block.received_at)
                    self.last_event[kind] = block.received_at
            self.active[kind] = active
        complete = (len(self.timestamps) >= round(fs * self.config.window_seconds) - 1
                    and self.timestamps[0] >= self.settle_until
                    and np.all(np.diff(self.timestamps) <= 1.5 / fs))
        self.quality = assess(self.raw, self.imu, self.config, complete)
        if self.last_artifact >= self.timestamps[0]:
            self.quality.valid = False
            self.quality.global_score *= 0.25
            self.quality.channels = [score * 0.25 for score in self.quality.channels]
            self.quality.reasons.append("suspected_artifact")
        if not self.quality.valid:
            self.mapper.accept(None, block.received_at, False)
        if self.last_feature is None or block.received_at - self.last_feature >= 1 / self.config.feature_hz - 1e-6:
            self.compute_features(block.received_at)

    def compute_features(self, now):
        # Advance fixed feature deadlines even when source block size is not commensurate.
        dt = 1 / self.config.feature_hz
        self.last_feature = now if self.last_feature is None else self.last_feature + dt
        if now - self.last_feature > dt:
            self.last_feature = now
        quality = self.quality.to_dict()
        self.log("quality", {"timestamp": now, "connected": self.connected, **quality})
        valid = self.quality.valid
        features = channel_powers = normalized = None
        # A comparison window may not straddle a condition change.
        condition = self.condition if len(self.timestamps) and self.timestamps[0] >= self.condition_since else "transition"
        if valid:
            features, channel_powers = extract(self.processed, self.metadata)
            normalized = self.normalizer.observe(features, dt, reference=condition == "reference")
            self.valid_windows += 1
            if normalized is not None:
                self.normalized = normalized
        else:
            self.invalid_windows += 1
        self.mapper.accept(normalized, now, valid)
        self.log("features", {"timestamp": now, "window_start": float(self.timestamps[0]) if len(self.timestamps) else None,
                              "valid": valid, "condition": condition, "raw_features": features,
                              "channel_powers_uv2": channel_powers, "normalized": normalized,
                              "calibrated": self.normalizer.ready})

    def tick(self, now):
        stale = not self.connected or self.last_arrival is None or now - self.last_arrival > self.config.stale_seconds
        valid = self.quality.valid and self.normalizer.ready and not stale
        status = {**self.quality.to_dict(), "connected": self.connected, "stale": stale,
                  "valid": valid, "calibrated": self.normalizer.ready,
                  "visual_available": self.mapper.available.copy(),
                  "posterior_available": bool(self.metadata.groups.get("posterior")),
                  "lateral_available": bool(self.metadata.groups.get("left") and self.metadata.groups.get("right"))}
        if stale:
            status["channels"] = [0.0] * 8
            status["global_score"] = 0.0
            status["reasons"] = [*status["reasons"], "stale" if self.connected else "disconnected"]
        visual = self.mapper.render(now, valid)
        events = self.pending.copy()
        # Blink is a separate physical event, allowed even when its EEG window is rejected.
        visual["pulse"] = int(events["blink"] and self.connected and not stale)
        self.pending = {key: 0 for key in self.pending}
        values = messages(status, self.normalized, events, visual, self.config.visual_addresses)
        result = {"timestamp": now, "status": status, "features": self.normalized.copy(),
                  "events": events, "visual": visual, "osc": values}
        self.log("controls", result)
        return result

    def close(self):
        if self.recorder:
            self.recorder.close(self.normalizer.to_dict())
