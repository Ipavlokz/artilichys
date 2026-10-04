"""Descriptive comparisons of annotated conditions; never causal attribution."""
import json
from pathlib import Path

import numpy as np

from .sources.replay import session_manifest


def compare_conditions(path, min_windows=5, equivalence_fraction=0.2, seed=17):
    path = Path(path)
    if not path.is_dir():
        path = path.parent
    manifest = session_manifest(path)
    metadata = manifest["source"]
    selected = {"reference": [], "music": []}
    last_end = -np.inf
    with (path / "features.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if (row["valid"] and row["condition"] in selected and row["channel_powers_uv2"]
                    and row["window_start"] >= last_end):
                selected[row["condition"]].append(row)
                last_end = row["timestamp"]
    rng = np.random.default_rng(seed)
    findings = []
    lower_limit, upper_limit = np.log(1 - equivalence_fraction), np.log(1 + equivalence_fraction)
    for channel in metadata["channels"]:
        for band in ("theta", "alpha", "beta"):
            finding = {"channel": channel, "band": band, "classification": "evidencia_insuficiente"}
            if all(len(selected[c]) >= min_windows for c in selected):
                ref = np.log(np.maximum([x["channel_powers_uv2"][channel][band] for x in selected["reference"]], 1e-12))
                music = np.log(np.maximum([x["channel_powers_uv2"][channel][band] for x in selected["music"]], 1e-12))
                effect = float(np.median(music) - np.median(ref))
                draws = (np.median(rng.choice(music, (2000, len(music))), axis=1)
                         - np.median(rng.choice(ref, (2000, len(ref))), axis=1))
                lo, hi = np.quantile(draws, [0.025, 0.975])
                finding.update(percent_change=float(np.expm1(effect) * 100),
                               descriptive_interval_percent=[float(np.expm1(lo) * 100), float(np.expm1(hi) * 100)])
                if lo > upper_limit or hi < lower_limit:
                    finding["classification"] = "cambio_observado"
                elif lo >= lower_limit and hi <= upper_limit:
                    finding["classification"] = "compatible_con_cambio_pequeno"
            findings.append(finding)
    return {"windows": {c: len(rows) for c, rows in selected.items()}, "minimum_per_condition": min_windows,
            "equivalence_fraction": equivalence_fraction, "findings": findings,
            "interpretation": "Comparación descriptiva de ventanas válidas sin solapamiento. Compatible con cambio pequeño no prueba ausencia de efecto. Intervalos bootstrap sin ajuste por comparaciones múltiples ni dependencia temporal. No atribuye causalidad a música ni detecta emociones."}
