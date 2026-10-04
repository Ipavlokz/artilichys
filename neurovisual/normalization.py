import numpy as np

KEYS = ("theta", "alpha", "beta", "posterior_alpha", "spectral_balance")


class Normalizer:
    """A fixed personal baseline. Only valid reference windows train it."""

    def __init__(self, config):
        self.config = config
        self.samples = []
        self.elapsed = 0.0
        self.bounds = {}
        self.state = None

    @property
    def ready(self):
        return bool(self.bounds)

    def observe(self, features, dt, reference=True):
        if not self.ready and reference:
            self.samples.append(features.copy())
            self.elapsed += dt
            if self.elapsed + 1e-9 >= self.config.baseline_seconds:
                for key in KEYS:
                    x = np.array([s[key] for s in self.samples if s[key] is not None])
                    if not len(x):
                        continue
                    center = float(np.median(x))
                    mad = float(np.median(np.abs(x - center))) * 1.4826
                    # A stable baseline still needs a finite, useful dynamic range.
                    width = max(3 * mad, abs(center) * 0.5, 0.25 if key == "spectral_balance" else 1.0)
                    self.bounds[key] = (center - width, center + width)
        if not self.ready:
            return None
        target = {}
        for key in KEYS:
            if features[key] is None or key not in self.bounds:
                target[key] = 0.5
            else:
                lo, hi = self.bounds[key]
                target[key] = float(np.clip((features[key] - lo) / (hi - lo), 0, 1))
        target["lateral_balance"] = float(np.clip(features["lateral_balance"] or 0, -1, 1))
        a = 1 - np.exp(-dt / self.config.smooth_seconds)
        if self.state is None:
            self.state = target
        else:
            self.state = {k: float(self.state[k] + a * (target[k] - self.state[k])) for k in target}
        return self.state.copy()

    def to_dict(self):
        return {"ready": self.ready, "valid_reference_seconds": self.elapsed,
                "bounds": self.bounds, "windows": len(self.samples)}
