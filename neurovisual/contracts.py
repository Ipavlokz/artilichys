"""Shared descriptor and artistic names, independent of transports."""

FEATURE_KEYS = ("theta", "alpha", "beta", "posterior_alpha", "spectral_balance", "lateral_balance")
CONTINUOUS_VISUAL = ("color", "intensity", "flow", "coherence")
VISUAL_KEYS = (*CONTINUOUS_VISUAL, "pulse", "scene")
DEFAULT_MAPPING = {"color": "alpha", "intensity": "beta", "flow": "theta", "coherence": "posterior_alpha"}
DEFAULT_OSC_ADDRESSES = {key: f"/visual/{key}" for key in VISUAL_KEYS}
