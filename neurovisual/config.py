from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import re

from .contracts import CONTINUOUS_VISUAL, DEFAULT_MAPPING, DEFAULT_OSC_ADDRESSES, FEATURE_KEYS, VISUAL_KEYS


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
    jaw_release_seconds: float = 0.25
    visual_mapping: dict = field(default_factory=dict)
    osc_addresses: dict = field(default_factory=dict)

    @property
    def mapping_rules(self):
        return {**DEFAULT_MAPPING, **self.visual_mapping}

    @property
    def visual_addresses(self):
        return {**DEFAULT_OSC_ADDRESSES, **self.osc_addresses}

    def validate_artistic(self):
        if not isinstance(self.visual_mapping, dict):
            raise ValueError("visual_mapping debe ser un objeto JSON de controles -> características")
        if set(self.visual_mapping) - set(CONTINUOUS_VISUAL):
            raise ValueError(f"Control desconocido en visual_mapping; usar {', '.join(CONTINUOUS_VISUAL)}")
        for control, rule in self.mapping_rules.items():
            if isinstance(rule, str):
                if rule not in FEATURE_KEYS:
                    raise ValueError(f"Característica desconocida para {control}: {rule}; usar {', '.join(FEATURE_KEYS)}")
                continue
            if not isinstance(rule, dict) or set(rule) - {"weights", "invert"}:
                raise ValueError(f"Regla de {control}: usar nombre de característica o weights/invert")
            weights = rule.get("weights")
            if not isinstance(weights, dict) or not weights or set(weights) - set(FEATURE_KEYS):
                raise ValueError(f"weights de {control} requiere características conocidas y al menos un peso")
            if any(isinstance(weight, bool) or not isinstance(weight, (int, float))
                   or not math.isfinite(weight) or weight < 0 for weight in weights.values()):
                raise ValueError(f"weights de {control}: pesos finitos >= 0")
            total = sum(weights.values())
            if not math.isfinite(total) or total <= 0:
                raise ValueError(f"weights de {control}: la suma debe ser finita y positiva")
            if not isinstance(rule.get("invert", False), bool):
                raise ValueError(f"invert de {control} debe ser true o false")
        if not isinstance(self.osc_addresses, dict) or set(self.osc_addresses) - set(VISUAL_KEYS):
            raise ValueError(f"osc_addresses requiere nombres de controles: {', '.join(VISUAL_KEYS)}")
        for control, address in self.visual_addresses.items():
            if (not isinstance(address, str) or len(address) > 128
                    or re.fullmatch(r"/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", address) is None):
                raise ValueError(f"Dirección OSC inválida para {control}: comenzar con /, sin espacios/patrones, máximo 128 caracteres")
            if address in ("/neuro", "/gesture") or address.startswith(("/neuro/", "/gesture/")):
                raise ValueError("Las direcciones /neuro y /gesture están reservadas para estado EEG y gestos")
        if len(set(self.visual_addresses.values())) != len(VISUAL_KEYS):
            raise ValueError("Direcciones OSC duplicadas: cada control necesita una dirección distinta")

    def validate(self, sample_rate):
        self.validate_artistic()
        for name, value in asdict(self).items():
            if name in ("visual_mapping", "osc_addresses"):
                continue
            if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError(f"Configuración inválida: {name}")
        if not (0 < self.low_hz < self.high_hz < sample_rate / 2):
            raise ValueError("Filtros incompatibles con la frecuencia declarada: 0 < low < high < Nyquist")
        if self.high_hz < 40 or self.low_hz > 4:
            raise ValueError("Las bandas de esta fase requieren low_hz <= 4 y high_hz >= 40")
        positive = ["window_seconds", "feature_hz", "output_hz", "notch_q", "stale_seconds",
                    "flat_uv", "amplitude_uv", "blink_uv", "muscle_rms_uv", "motion_g",
                    "baseline_seconds", "smooth_seconds", "idle_seconds", "event_refractory", "jaw_release_seconds"]
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
    def load(cls, path=None, base=None):
        if path is None:
            return cls(**base.to_dict()) if base is not None else cls()
        try:
            overrides = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            if not isinstance(overrides, dict):
                raise ValueError("La configuración debe ser un objeto JSON")
            values = base.to_dict() if base is not None else {}
            for key in ("visual_mapping", "osc_addresses"):
                if isinstance(overrides.get(key), dict):
                    overrides[key] = {**values.get(key, {}), **overrides[key]}
            return cls(**{**values, **overrides})
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Configuración JSON inválida: {exc}") from exc

    def to_dict(self):
        return asdict(self)
