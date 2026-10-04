import json
import math
from pathlib import Path

from .base import Source


class MarkedSource(Source):
    """Attach externally measured condition markers, using source timestamps."""

    def __init__(self, source, path):
        self.source = source
        self.metadata = source.metadata
        self.markers = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(self.markers, list):
            raise ValueError("El archivo de marcadores debe ser una lista JSON")
        for marker in self.markers:
            if (marker.get("condition") not in ("reference", "music")
                    or not isinstance(marker.get("timestamp"), (int, float))
                    or not math.isfinite(marker["timestamp"])):
                raise ValueError("Cada marcador requiere timestamp y condition reference/music")
        self.markers.sort(key=lambda item: item["timestamp"])
        self.index = 0

    @property
    def finished(self):
        return self.source.finished

    def read(self, timeout):
        block = self.source.read(timeout)
        if block is not None:
            while self.index < len(self.markers) and self.markers[self.index]["timestamp"] <= block.received_at:
                block.markers.append(self.markers[self.index])
                self.index += 1
            block.markers.sort(key=lambda item: item["timestamp"])
        return block

    def now(self):
        return self.source.now()

    def close(self):
        self.source.close()
