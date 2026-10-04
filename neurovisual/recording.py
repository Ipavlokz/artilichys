from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from .model import Block


def clean(value):
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def block_dict(block):
    return {"received_at": block.received_at, "connected": block.connected,
            "timestamps": block.timestamps, "samples": block.samples,
            "imu": block.imu, "markers": block.markers}


def decode_block(data):
    try:
        samples = np.asarray(data["samples"], dtype=float)
        if samples.size == 0:
            samples = np.empty((0, 8))
        return Block(np.asarray(data["timestamps"], dtype=float), samples,
                     float(data["received_at"]), data.get("connected", True),
                     None if data.get("imu") is None else np.asarray(data["imu"], dtype=float),
                     data.get("markers", []))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Registro crudo inválido: {exc}") from exc


class SessionRecorder:
    def __init__(self, path, metadata, config, filter_info):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=False)
        manifest = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                    "source": metadata.to_dict(), "config": config.to_dict(),
                    "filter": filter_info}
        (self.path / "metadata.json").write_text(json.dumps(clean(manifest), indent=2,
                                                           allow_nan=False), encoding="utf-8")
        self.files = {name: (self.path / f"{name}.jsonl").open("w", encoding="utf-8")
                      for name in ("raw", "processed", "quality", "features", "events", "controls")}

    def write(self, name, value):
        self.files[name].write(json.dumps(clean(value), allow_nan=False, separators=(",", ":")) + "\n")
        # Preserve raw data even when processing rejects a window or exits on error.
        if name == "raw":
            self.files[name].flush()

    def close(self, normalization=None):
        for handle in self.files.values():
            handle.close()
        if normalization is not None:
            (self.path / "baseline.json").write_text(json.dumps(clean(normalization), indent=2), encoding="utf-8")
