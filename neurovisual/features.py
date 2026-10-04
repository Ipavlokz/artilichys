import numpy as np
from scipy.signal import welch

BANDS = {"theta": (4, 8), "alpha": (8, 13), "beta": (13, 30)}


def extract(processed, metadata):
    f, psd = welch(processed, fs=metadata.sample_rate, axis=0,
                   nperseg=min(len(processed), int(metadata.sample_rate * 2)),
                   detrend="constant", scaling="density")
    df = f[1] - f[0]
    powers = {key: psd[(f >= lo) & (f < hi)].sum(axis=0) * df
              for key, (lo, hi) in BANDS.items()}
    values = {key: float(np.mean(value)) for key, value in powers.items()}
    posterior = [metadata.channels.index(ch) for ch in metadata.groups.get("posterior", [])]
    left = [metadata.channels.index(ch) for ch in metadata.groups.get("left", [])]
    right = [metadata.channels.index(ch) for ch in metadata.groups.get("right", [])]
    values["posterior_alpha"] = float(np.mean(powers["alpha"][posterior])) if posterior else None
    values["spectral_balance"] = float(np.log((values["alpha"] + 1e-9) / (values["beta"] + 1e-9)))
    if left and right:
        l, r = np.mean(powers["alpha"][left]), np.mean(powers["alpha"][right])
        values["lateral_balance"] = float((l - r) / max(l + r, 1e-9))
    else:
        values["lateral_balance"] = None
    channel_powers = {name: {key: float(powers[key][i]) for key in BANDS}
                      for i, name in enumerate(metadata.channels)}
    return values, channel_powers
