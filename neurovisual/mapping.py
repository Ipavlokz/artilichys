import math

from .contracts import CONTINUOUS_VISUAL, FEATURE_KEYS

IDLE = {"color": 0.5, "intensity": 0.2, "flow": 0.25, "coherence": 0.5, "scene": 0}


class VisualMapper:
    def __init__(self, config, available_features=None):
        config.validate_artistic()
        self.config = config
        self.rules = config.mapping_rules
        feature_available = {key: True for key in FEATURE_KEYS} if available_features is None else available_features
        self.available = {}
        for control, rule in self.rules.items():
            dependencies = [rule] if isinstance(rule, str) else [key for key, weight in rule["weights"].items() if weight > 0]
            self.available[control] = all(feature_available.get(key, False) for key in dependencies)
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
        target = IDLE.copy()
        for control, rule in self.rules.items():
            if not self.available[control]:
                continue  # missing anatomical groups never become invented measurements
            weights = {rule: 1.0} if isinstance(rule, str) else rule["weights"]
            total = sum(weights.values())
            value = 0.0
            for feature, weight in weights.items():
                if weight == 0:
                    continue
                sample = features[feature]
                if feature == "lateral_balance":
                    sample = (sample + 1) / 2
                value += sample * (weight / total)
            if isinstance(rule, dict) and rule.get("invert", False):
                value = 1 - value
            target[control] = min(1.0, max(0.0, value))
        self.target = target
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
        for key in CONTINUOUS_VISUAL:
            self.current[key] += a * (target[key] - self.current[key])
            self.current[key] = min(1.0, max(0.0, self.current[key]))
        self.current["scene"] = int(target["scene"])
        return self.current.copy()
