import math

IDLE = {"color": 0.5, "intensity": 0.2, "flow": 0.25, "coherence": 0.5, "scene": 0}


class VisualMapper:
    def __init__(self, config):
        self.config = config
        self.target = IDLE.copy()
        self.current = IDLE.copy()
        self.last_valid = None
        self.last_tick = None
        self.invalid_since = None

    def accept(self, features, now, valid):
        if not valid or features is None:
            if self.invalid_since is None:
                self.invalid_since = now
            return False
        self.target = {
            "color": features["alpha"], "intensity": features["beta"],
            "flow": features["theta"], "coherence": features["posterior_alpha"],
            "scene": 0,  # fixed in phase 1: avoid arbitrary categorical switches
        }
        self.last_valid = now
        self.invalid_since = None
        return True

    def render(self, now, valid):
        dt = 0 if self.last_tick is None else max(0, now - self.last_tick)
        self.last_tick = now
        if not valid and self.invalid_since is None:
            self.invalid_since = now
        if not valid:
            elapsed = now - (self.invalid_since if self.invalid_since is not None else now)
            if elapsed <= self.config.hold_seconds:
                return self.current.copy()
            target, tau = IDLE, self.config.idle_seconds
        else:
            target, tau = self.target, self.config.smooth_seconds
        a = 1 - math.exp(-dt / tau)
        for key in ("color", "intensity", "flow", "coherence"):
            self.current[key] += a * (target[key] - self.current[key])
            self.current[key] = min(1.0, max(0.0, self.current[key]))
        self.current["scene"] = int(target["scene"])
        return self.current.copy()
