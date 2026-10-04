from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path


@dataclass
class Config:
    window_seconds: float = 3.0
    feature_hz: float = 5.0
    output_hz: float = 15.0
    low_hz: float = 1.0
    high_hz: float = 40.0
    filter_order: int = 4
    line_hz: float | None = 60.0
    notch_q: float = 30.0
    settle_seconds: float = 1.0
    stale_seconds: float = 0.5
    flat_uv: float = 0.5
    amplitude_uv: float = 200.0
    blink_uv: float = 100.0
    muscle_ratio: float = 0.45
    muscle_rms_uv: float = 10.0
    motion_g: float = 0.12
    min_quality: float = 0.75
    baseline_seconds: float = 5.0
    smooth_seconds: float = 0.5
    hold_seconds: float = 1.0
    idle_seconds: float = 2.0
    event_refractory: float = 0.5

    def validate(self, sample_rate):
        for name, value in asdict(self).items():
            if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError(f"Configuración inválida: {name}")
        if not (0 < self.low_hz < self.high_hz < sample_rate / 2):
            raise ValueError("Filtros incompatibles con la frecuencia declarada: 0 < low < high < Nyquist")
        if self.high_hz < 40 or self.low_hz > 4:
            raise ValueError("Las bandas de esta fase requieren low_hz <= 4 y high_hz >= 40")
        positive = ["window_seconds", "feature_hz", "output_hz", "notch_q", "stale_seconds",
                    "flat_uv", "amplitude_uv", "blink_uv", "muscle_rms_uv", "motion_g",
                    "baseline_seconds", "smooth_seconds", "idle_seconds", "event_refractory"]
        if any(getattr(self, key) <= 0 for key in positive):
            raise ValueError("Duraciones, frecuencias y umbrales deben ser positivos")
        if self.settle_seconds < 0 or self.hold_seconds < 0:
            raise ValueError("settle_seconds y hold_seconds no pueden ser negativos")
        if not (2 <= self.window_seconds <= 4 and 4 <= self.feature_hz <= 10 and 10 <= self.output_hz <= 20):
            raise ValueError("Usar ventana 2–4 s, características 4–10 Hz y OSC 10–20 Hz")
        if not (0 < self.min_quality <= 1 and 0 < self.muscle_ratio < 1):
            raise ValueError("Umbrales de calidad/ratio fuera de rango")
        if not isinstance(self.filter_order, int) or not 1 <= self.filter_order <= 8:
            raise ValueError("filter_order debe ser un entero entre 1 y 8")
        if self.line_hz is not None and self.line_hz <= 0:
            raise ValueError("line_hz debe ser positiva o null")

    @classmethod
    def load(cls, path=None):
        if path is None:
            return cls()
        try:
            return cls(**json.loads(Path(path).read_text(encoding="utf-8")))
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Configuración JSON inválida: {exc}") from exc

    def to_dict(self):
        return asdict(self)
