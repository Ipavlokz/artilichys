import numpy as np

from .model import Block, SourceMetadata


class Acquisition:
    def __init__(self, metadata: SourceMetadata):
        metadata.validate()
        self.metadata = metadata
        self.last_sample = None
        self.last_received = None

    def validate(self, block: Block):
        t, x = block.timestamps, block.samples
        if not isinstance(block.connected, (bool, np.bool_)):
            raise ValueError("connected debe ser booleano, no texto ni un valor arbitrario")
        if t.ndim != 1 or x.shape != (len(t), 8):
            raise ValueError("Bloque inválido: samples debe tener forma (timestamps, 8)")
        if not np.isfinite(block.received_at):
            raise ValueError("received_at debe ser finito")
        if self.last_received is not None and block.received_at < self.last_received:
            raise ValueError("received_at retrocede; el adaptador debe proporcionar reloj monotónico")
        if len(t):
            if not block.connected:
                raise ValueError("Un bloque desconectado no puede contener muestras")
            if not np.all(np.isfinite(t)) or np.any(np.diff(t) <= 0):
                raise ValueError("Timestamps faltantes, duplicados o fuera de orden")
            if self.last_sample is not None and t[0] <= self.last_sample:
                raise ValueError("Los timestamps deben avanzar entre bloques")
            if t[-1] > block.received_at + 1e-6:
                raise ValueError("Una muestra tiene timestamp posterior a su recepción")
            # Allow clock jitter and gaps, but reject a declared rate that disagrees.
            if len(t) > 2:
                step = np.median(np.diff(t))
                if abs(step * self.metadata.sample_rate - 1) > 0.2:
                    raise ValueError("Los timestamps no concuerdan con sample_rate (tolerancia 20%)")
        if np.any(np.isinf(x)):
            raise ValueError("Usar NaN/null para faltantes; infinito no es una muestra válida")
        if block.imu is not None and block.imu.shape != (len(t), 3):
            raise ValueError("IMU debe tener forma (muestras, 3), en g")
        for marker in block.markers:
            stamp = marker.get("timestamp")
            if not isinstance(stamp, (int, float)) or not np.isfinite(stamp) or stamp > block.received_at:
                raise ValueError("Marcador sin timestamp válido o posterior a recepción")
            if marker.get("condition") not in ("reference", "music"):
                raise ValueError("Marcador condition debe ser reference o music")
        self.last_received = block.received_at
        if len(t):
            self.last_sample = float(t[-1])
