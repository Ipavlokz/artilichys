import csv
import json
from pathlib import Path

import numpy as np

from ..acquisition import Acquisition
from ..model import Block, SourceMetadata
from ..recording import decode_block
from .base import TimedSource


def session_manifest(path):
    path = Path(path)
    manifest = path / "metadata.json" if path.is_dir() else path.parent / "metadata.json"
    if not manifest.exists():
        raise ValueError(f"Faltan metadatos/frecuencia de muestreo: {manifest}")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("La sesión requiere schema_version=1")
    return data


def raw_blocks(path):
    path = Path(path)
    path = path / "raw.jsonl" if path.is_dir() else path
    if not path.exists():
        raise ValueError(f"No existe el archivo crudo: {path}")
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                yield decode_block(json.loads(line))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc


def csv_blocks(path, metadata, column_map):
    if "timestamp" not in column_map or not set(metadata.channels) <= set(column_map):
        raise ValueError("Mapa CSV requiere timestamp y los ocho nombres de canales")
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {column_map[key] for key in ["timestamp", *metadata.channels]}
        if not required <= set(reader.fieldnames or []):
            raise ValueError(f"Faltan columnas CSV: {sorted(required - set(reader.fieldnames or []))}")
        batch = []
        for line_number, row in enumerate(reader, 2):
            try:
                t = float(row[column_map["timestamp"]])
                x = [float(row[column_map[ch]]) if row[column_map[ch]].strip() else np.nan
                     for ch in metadata.channels]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"CSV línea {line_number}: timestamp o muestra inválida") from exc
            batch.append((t, x))
            if len(batch) >= max(1, round(metadata.sample_rate * 0.05)):
                yield Block(np.array([v[0] for v in batch]), np.array([v[1] for v in batch]), batch[-1][0])
                batch = []
        if batch:
            yield Block(np.array([v[0] for v in batch]), np.array([v[1] for v in batch]), batch[-1][0])


class ReplaySource(TimedSource):
    def __init__(self, path, speed=1, metadata_path=None, column_map=None):
        if Path(path).suffix.lower() == ".csv":
            if metadata_path is None:
                raise ValueError("CSV requiere --metadata con sample_rate, channels y units; no se infieren")
            metadata = SourceMetadata(**json.loads(Path(metadata_path).read_text(encoding="utf-8")))
            metadata.validate()
            if column_map is None:
                column_map = {key: key for key in ["timestamp", *metadata.channels]}
            blocks = csv_blocks(path, metadata, column_map)
        else:
            manifest = session_manifest(path)
            try:
                metadata = SourceMetadata(**manifest["source"])
            except (TypeError, KeyError) as exc:
                raise ValueError(f"Metadatos incompletos; se requiere sample_rate, channels, units, source: {exc}") from exc
            blocks = raw_blocks(path)
        super().__init__(metadata, blocks, speed)


def inspect_source(source):
    acquisition = Acquisition(source.metadata)
    count = 0
    missing = 0
    first = last = None
    disconnects = 0
    timestamp_gaps = 0
    while not source.finished:
        block = source.read(0)
        if block is None:
            continue
        acquisition.validate(block)
        count += len(block.timestamps)
        missing += int(np.isnan(block.samples).sum())
        disconnects += int(not block.connected)
        if len(block.timestamps):
            steps = np.diff(block.timestamps if last is None else np.r_[last, block.timestamps])
            timestamp_gaps += int(np.count_nonzero(steps > 1.5 / source.metadata.sample_rate))
            if first is None:
                first = float(block.timestamps[0])
            last = float(block.timestamps[-1])
    return {"metadata": source.metadata.to_dict(), "samples": count, "missing_values": missing,
            "first_timestamp": first, "last_timestamp": last, "disconnected_blocks": disconnects,
            "timestamp_gaps": timestamp_gaps}
