from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np


@dataclass
class SourceMetadata:
    sample_rate: float
    channels: list[str]
    units: str
    source: str
    groups: dict[str, list[str]] = field(default_factory=dict)
    auxiliary: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def validate(self):
        if self.schema_version != 1:
            raise ValueError("Versión de formato no compatible; se requiere schema_version=1")
        if not np.isfinite(self.sample_rate) or self.sample_rate <= 0:
            raise ValueError("La fuente debe declarar una frecuencia de muestreo positiva")
        if (len(self.channels) != 8 or len(set(self.channels)) != 8
                or not all(isinstance(ch, str) and ch for ch in self.channels)):
            raise ValueError("Se requieren ocho nombres de canal únicos y su orden explícito")
        if self.units != "uV":
            raise ValueError("El contrato interno requiere uV; convertir unidades en el adaptador")
        for name, group in self.groups.items():
            if not group or len(set(group)) != len(group) or not set(group) <= set(self.channels):
                raise ValueError(f"Grupo de canales inválido: {name}")

    def to_dict(self):
        return asdict(self)


@dataclass
class Block:
    """Sample times and received_at use the same monotonic source clock, in seconds."""

    timestamps: np.ndarray
    samples: np.ndarray
    received_at: float
    connected: bool = True
    imu: np.ndarray | None = None  # acceleration in g; shape (n, 3)
    markers: list[dict] = field(default_factory=list)

    @classmethod
    def empty(cls, received_at, connected=True, markers=None):
        return cls(np.empty(0), np.empty((0, 8)), received_at, connected,
                   markers=markers or [])
