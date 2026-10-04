import numpy as np

from ..model import Block, SourceMetadata
from .base import TimedSource

SCENARIOS = ("blink", "muscle", "motion", "flat", "missing", "disconnect", "stalled")
SCHEDULE = {"blink": (10, 10.4), "muscle": (14, 15), "motion": (18, 19),
            "flat": (22, 24), "missing": (26, 27), "disconnect": (30, 32),
            "stalled": (36, 38)}


class SimulatedSource(TimedSource):
    def __init__(self, duration=45, sample_rate=250, scenarios=(), seed=7, speed=1,
                 bands=None, schedule=None):
        if duration <= 0 or sample_rate <= 80:
            raise ValueError("Simulación requiere duración positiva y sample_rate > 80 Hz")
        if not set(scenarios) <= set(SCENARIOS):
            raise ValueError(f"Escenarios disponibles: {', '.join(SCENARIOS)}")
        bands = bands or {"theta": 8.0, "alpha": 12.0, "beta": 5.0}
        if set(bands) != {"theta", "alpha", "beta"} or any(not np.isfinite(v) or v < 0 for v in bands.values()):
            raise ValueError("bands requiere theta/alpha/beta con amplitudes uV finitas >= 0")
        schedule = {**SCHEDULE, **(schedule or {})}
        for key, interval in schedule.items():
            if key not in SCENARIOS or len(interval) != 2 or not 0 <= interval[0] < interval[1]:
                raise ValueError("schedule requiere escenarios con [inicio, fin] en segundos")
        metadata = SourceMetadata(sample_rate, [f"ch{i}" for i in range(1, 9)], "uV", "simulated",
                                  {"frontal": ["ch1", "ch2"], "posterior": ["ch7", "ch8"],
                                   "left": ["ch3", "ch5"], "right": ["ch4", "ch6"]},
                                  {"imu_units": "g", "seed": seed, "scenarios": list(scenarios),
                                   "schedule": schedule, "bands_uv": bands,
                                   "groups_are_synthetic": True})
        super().__init__(metadata, self._generate(metadata, duration, scenarios, seed, bands, schedule), speed)

    @staticmethod
    def _generate(metadata, duration, scenarios, seed, bands, schedule):
        rng = np.random.default_rng(seed)
        fs = metadata.sample_rate
        size = max(1, round(fs * 0.05))
        total = int(duration * fs)
        last_condition = None
        for start in range(0, total, size):
            t = np.arange(start, min(start + size, total)) / fs
            end = float((start + len(t)) / fs)
            condition = "music" if int(t[0] // 12) % 2 else "reference"
            markers = []
            if condition != last_condition:
                markers.append({"timestamp": float(t[0]), "condition": condition,
                                "label": "synthetic condition; no audio is played"})
                last_condition = condition
            active = {key: (t >= schedule[key][0]) & (t < schedule[key][1]) for key in scenarios}
            if "disconnect" in active and np.any(active["disconnect"]):
                yield Block.empty(end, False, markers)
                continue
            if "stalled" in active and np.any(active["stalled"]):
                yield Block.empty(end, True, markers)
                continue
            phase = np.arange(8) * 0.23
            # A known alpha response in ch1–4; ch5–8 are negative controls.
            music = ((t // 12).astype(int) % 2).astype(float)
            ramp = np.minimum((t % 12) / 2, 1)
            gain = 1 + 0.7 * music * ramp
            alpha_gain = np.ones((len(t), 8))
            alpha_gain[:, :4] = gain[:, None]
            x = (bands["theta"] * np.sin(2 * np.pi * 6 * t[:, None] + phase)
                 + bands["alpha"] * alpha_gain * np.sin(2 * np.pi * 10 * t[:, None] + phase)
                 + bands["beta"] * np.sin(2 * np.pi * 20 * t[:, None] + phase)
                 + rng.normal(0, 1.0, (len(t), 8)))
            imu = np.tile([0.0, 0.0, 1.0], (len(t), 1)) + rng.normal(0, 0.001, (len(t), 3))
            if "blink" in active:
                center = sum(schedule["blink"]) / 2
                blink = 180 * np.exp(-0.5 * ((t - center) / 0.065) ** 2)
                x[:, :2] += blink[:, None] * active["blink"][:, None]
            if "muscle" in active:
                x += active["muscle"][:, None] * (50 * np.sin(2 * np.pi * min(55, fs * 0.4) * t[:, None])
                                                   + rng.normal(0, 20, x.shape))
            if "motion" in active:
                imu += active["motion"][:, None] * rng.normal(0, 0.3, imu.shape)
                x += active["motion"][:, None] * rng.normal(0, 45, x.shape)
            if "flat" in active:
                x[active["flat"], 7] = 0
            if "missing" in active:
                x[active["missing"], 5] = np.nan
            yield Block(t, x, end, True, imu, markers)
