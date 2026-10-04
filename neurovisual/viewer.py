"""Export recorded artistic controls to a self-contained, offline rehearsal viewer."""
import hashlib
from importlib.resources import files
import json
import math
from pathlib import Path

from .config import Config
from .contracts import CONTINUOUS_VISUAL, FEATURE_KEYS
from .mapping import VisualMapper
from .model import SourceMetadata
from .sources.replay import session_manifest


def number(value, label, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} debe ser un número finito")
    if low is not None and not low <= value <= high:
        raise ValueError(f"{label} fuera de rango {low}–{high}")
    return value


def flag(value, label):
    if not isinstance(value, bool):
        raise ValueError(f"{label} debe ser booleano")
    return value


def load_track(path):
    path = Path(path)
    root = path if path.is_dir() else path.parent
    if not path.is_dir() and path.name != "controls.jsonl":
        raise ValueError("view requiere un directorio de sesión procesada o controls.jsonl")
    manifest = session_manifest(root)
    metadata = SourceMetadata(**manifest["source"])
    metadata.validate()
    config = Config(**manifest["config"])
    config.validate(metadata.sample_rate)
    feature_available = {key: True for key in FEATURE_KEYS}
    feature_available["posterior_alpha"] = bool(metadata.groups.get("posterior"))
    feature_available["lateral_balance"] = bool(metadata.groups.get("left") and metadata.groups.get("right"))
    expected_available = VisualMapper(config, feature_available).available
    control_path = root / "controls.jsonl"
    if not control_path.is_file():
        raise ValueError("Falta controls.jsonl: primero ejecutar run/replay con --record; una grabación cruda no incluye controles")
    frames = []
    previous = None
    with control_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
                timestamp = number(row["timestamp"], "timestamp")
                if previous is not None and timestamp <= previous:
                    raise ValueError("Los timestamps de controles deben avanzar sin duplicados")
                visual = {key: number(row["visual"][key], key, 0, 1) for key in CONTINUOUS_VISUAL}
                for key in ("pulse", "scene"):
                    value = row["visual"][key]
                    if isinstance(value, bool) or not isinstance(value, int) or key == "pulse" and value not in (0, 1):
                        raise ValueError(f"{key} debe ser entero" + (" 0/1" if key == "pulse" else ""))
                    visual[key] = value
                features = {key: number(row["features"][key], key, -1 if key == "lateral_balance" else 0, 1)
                            for key in FEATURE_KEYS}
                state = row["status"]
                status = {key: flag(state[key], key) for key in ("connected", "stale", "valid", "calibrated")}
                if status["valid"] and (not status["connected"] or status["stale"] or not status["calibrated"]):
                    raise ValueError("Ventana válida incompatible con conexión, stale o calibración")
                status["global_score"] = number(state["global_score"], "quality", 0, 1)
                status["motion"] = number(state["motion"], "motion", 0, 1)
                status["motion_available"] = flag(state.get("motion_available", False), "motion_available")
                channels = state["channels"]
                if not isinstance(channels, list) or len(channels) != 8:
                    raise ValueError("La calidad requiere ocho canales ordenados")
                status["channels"] = [number(q, "channel quality", 0, 1) for q in channels]
                reasons = state["reasons"]
                if not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons):
                    raise ValueError("reasons debe ser una lista de textos")
                status["reasons"] = reasons
                condition = state.get("condition", "unknown")
                if condition not in ("reference", "music", "unknown"):
                    raise ValueError("Condición de controles desconocida")
                status["condition"] = condition
                available = state.get("visual_available", {})
                if not isinstance(available, dict):
                    raise ValueError("visual_available debe ser un objeto de controles -> booleanos")
                status["visual_available"] = {key: flag(available.get(key, expected_available[key]), key) for key in CONTINUOUS_VISUAL}
                events = {}
                for key in ("blink", "muscle", "reconnect"):
                    value = row["events"][key]
                    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
                        raise ValueError(f"Evento {key} requiere entero 0/1")
                    events[key] = value
                frames.append({"timestamp": timestamp, "visual": visual, "features": features,
                               "status": status, "events": events})
                previous = timestamp
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                raise ValueError(f"{control_path}:{line_number}: {exc}") from exc
    if not frames:
        raise ValueError("controls.jsonl está vacío; la sesión debe generar al menos una actualización")
    track = {"name": root.name, "source": metadata.source, "sample_rate": metadata.sample_rate,
             "channels": metadata.channels, "groups": metadata.groups,
             "mapping": config.mapping_rules, "addresses": config.visual_addresses, "frames": frames,
             "summary": {"frames": len(frames), "valid_frames": sum(row["status"]["valid"] for row in frames)}}
    return root, track


def digest(path):
    if not path.is_file():
        raise ValueError(f"Falta {path.name}: comparar reglas requiere los crudos y características de ambas sesiones")
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_viewer(path, output=None, compare=None):
    root, track = load_track(path)
    tracks = [track]
    if compare is not None:
        other_root, other = load_track(compare)
        for key in ("sample_rate", "channels", "groups"):
            if track[key] != other[key]:
                raise ValueError("Las sesiones comparadas requieren la misma frecuencia y orden/grupos de canales")
        for name in ("raw.jsonl", "features.jsonl"):
            if digest(root / name) != digest(other_root / name):
                raise ValueError(f"Difiere {name}: comparar reglas requiere los mismos crudos y características. Reprocesar la misma grabación con --speed 0 cambiando sólo el mapeo")
        tracks.append(other)
    start = max(item["frames"][0]["timestamp"] for item in tracks)
    end = min(item["frames"][-1]["timestamp"] for item in tracks)
    if end < start:
        raise ValueError("Las sesiones no tienen un intervalo temporal compartido")
    data = {"schema_version": 1, "start": start, "end": end, "tracks": tracks}
    # JSON inside a script element must not let labels close that element.
    encoded = json.dumps(data, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = files("neurovisual").joinpath("templates/viewer.html").read_text(encoding="utf-8")
    target = Path(output) if output else root / "viewer.html"
    if target.suffix.lower() != ".html":
        raise ValueError("El visor debe guardarse como .html; no se sobrescriben archivos de registro")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template.replace("__SESSION_DATA__", encoded, 1), encoding="utf-8")
    return target
