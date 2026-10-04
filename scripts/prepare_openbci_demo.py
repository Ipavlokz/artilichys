"""Reproducible offline import of the pinned, publicly distributed OpenBCI sample.

Users do not need to run this: the prepared recording is included in Git.
No filtering, centering, interpolation or channel duplication is performed.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re

import numpy as np

from neurovisual.config import Config
from neurovisual.model import SourceMetadata

UPSTREAM_COMMIT = "e23869e7b5cc621e733d8fa0d81f05d477264306"
UPSTREAM_PATH = "OpenBCI_GUI/data/EEG_Sample_Data/OpenBCI_GUI-v6-meditation.txt"
ORIGINAL_SHA256 = "54588140869b984562d20f95b1badd3dc4c25592d923f09e9becf30ff9121712"
SOURCE_URL = f"https://raw.githubusercontent.com/OpenBCI/OpenBCI_GUI/{UPSTREAM_COMMIT}/{UPSTREAM_PATH}"


def prepare(input_path, output_path, start_seconds=30.0, duration_seconds=60.0):
    original = Path(input_path).read_bytes()
    if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256:
        raise ValueError("El archivo no coincide con la grabación OpenBCI verificada (SHA-256)")
    text = original.decode("utf-8-sig")
    rate_match = re.search(r"%Sample Rate = ([\d.]+) Hz", text)
    count_match = re.search(r"%Number of channels = (\d+)", text)
    if not rate_match or not count_match or int(count_match[1]) != 8:
        raise ValueError("Faltan frecuencia explícita u ocho canales en la cabecera")
    fs = float(rate_match[1])
    if start_seconds < 0 or duration_seconds <= 0:
        raise ValueError("Inicio debe ser >= 0 y duración > 0")
    # Keep exact original lines as a compressed excerpt, including native times.
    comments, content = [], []
    for line in text.splitlines(keepends=True):
        (comments if line.startswith("%") else content).append(line)
    start = round(start_seconds * fs)
    stop = start + round(duration_seconds * fs)
    selected = content[1:][start:stop]
    if len(selected) != stop - start or not selected:
        raise ValueError("El intervalo solicitado excede la grabación original")
    reader = csv.DictReader(io.StringIO(content[0] + "".join(selected)), skipinitialspace=True)
    eeg_columns = [f"EXG Channel {i}" for i in range(8)]
    imu_columns = [f"Accel Channel {i}" for i in range(3)]
    required = {"Sample Index", "Timestamp", *eeg_columns, *imu_columns}
    if not required <= set(reader.fieldnames or []):
        raise ValueError("Faltan columnas de canal, contador, tiempo o acelerómetro")
    rows = list(reader)
    indexes = np.array([int(row["Sample Index"]) for row in rows])
    steps = np.diff(indexes) % 256
    if np.any((steps == 0) | (steps > 128)):
        raise ValueError("Contador duplicado o discontinuidad ambigua; no se reconstruye silenciosamente")
    ticks = np.r_[0, np.cumsum(steps)]
    timestamps = ticks / fs
    samples = np.array([[float(row[col]) for col in eeg_columns] for row in rows])
    imu = np.array([[float(row[col]) for col in imu_columns] for row in rows])
    native_times = np.array([int(row["Timestamp"]) for row in rows])
    excerpt = ("".join(comments) + content[0] + "".join(selected)).encode("utf-8")
    conversion = {
        "upstream_commit": UPSTREAM_COMMIT, "upstream_url": SOURCE_URL,
        "original_sha256": ORIGINAL_SHA256, "excerpt_sha256": hashlib.sha256(excerpt).hexdigest(),
        "selected_original_rows_zero_based": [start, stop],
        "selected_samples": len(rows), "missing_counter_samples": int(np.sum(steps - 1)),
        "timebase": "relative seconds from unwrapped 8-bit sample counter / header sample rate; gaps retained",
        "native_timestamp_units": "milliseconds", "native_timestamp_first": int(native_times[0]),
        "native_timestamp_last": int(native_times[-1]),
        "native_duplicate_timestamps": int(np.sum(np.diff(native_times) == 0)),
        "native_timestamps_preserved_in": "original_excerpt.txt.gz",
        "signal_transform": "none; original EEG uV values, channel order and acceleration retained",
    }
    metadata = SourceMetadata(fs, [f"ch{i}" for i in range(1, 9)], "uV", "OpenBCI Cyton public recording",
                              groups={}, auxiliary={
                                  "original_eeg_columns": eeg_columns, "original_imu_columns": imu_columns,
                                  "imu_units": "g", "channel_positions": "not documented; no anatomical groups inferred",
                                  "electrical_reference": "not documented in the source file",
                                  "conditions": "no music/reference annotations; reference means technical calibration only",
                                  "license": "MIT; bundled official OpenBCI GUI sample",
                                  "units_evidence": f"https://github.com/OpenBCI/OpenBCI_GUI/blob/{UPSTREAM_COMMIT}/OpenBCI_GUI/BoardCyton.pde",
                                  **conversion})
    metadata.validate()
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=False)
    (output / "original_excerpt.txt.gz").write_bytes(gzip.compress(excerpt, mtime=0))
    (output / "metadata.json").write_text(json.dumps({"schema_version": 1, "source": metadata.to_dict(),
                                                     "config": Config().to_dict(), "conversion": conversion}, indent=2) + "\n", encoding="utf-8")
    with (output / "raw.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for offset in range(0, len(rows), max(1, round(fs * 0.05))):
            end = min(offset + round(fs * 0.05), len(rows))
            block = {"received_at": float(timestamps[end - 1] + 1 / fs), "connected": True,
                     "timestamps": timestamps[offset:end].tolist(), "samples": samples[offset:end].tolist(),
                     "imu": imu[offset:end].tolist(), "markers": []}
            handle.write(json.dumps(block, allow_nan=False, separators=(",", ":")) + "\n")
    return conversion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Original OpenBCI file matching the pinned SHA-256")
    parser.add_argument("--output", required=True, help="New directory")
    parser.add_argument("--start", type=float, default=30)
    parser.add_argument("--duration", type=float, default=60)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.input, args.output, args.start, args.duration), indent=2))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
