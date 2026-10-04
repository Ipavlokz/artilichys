import numpy as np
from scipy import signal


class CausalFilter:
    """SOS IIR; persistent state; no future samples or zero-phase filtering."""

    def __init__(self, sample_rate, config, channels=8):
        config.validate(sample_rate)
        self.sos = signal.butter(config.filter_order, [config.low_hz, config.high_hz],
                                 btype="bandpass", fs=sample_rate, output="sos")
        self.notch_applied = config.line_hz is not None and config.line_hz < sample_rate / 2
        if self.notch_applied:
            b, a = signal.iirnotch(config.line_hz, config.notch_q, fs=sample_rate)
            self.sos = np.vstack([signal.tf2sos(b, a), self.sos])
        self.channels = channels
        self.reset()

    def reset(self):
        self.state = np.zeros((len(self.sos), 2, self.channels))
        self.last = np.zeros(self.channels)

    def apply(self, samples):
        if not len(samples):
            return samples.copy()
        missing = ~np.isfinite(samples)
        safe = samples.copy()
        # Internal continuity only. Missing values remain NaN in processed output;
        # every affected feature window is rejected, never reconstructed for use.
        for i, row in enumerate(safe):
            row[missing[i]] = self.last[missing[i]]
            self.last = row.copy()
        filtered, self.state = signal.sosfilt(self.sos, safe, axis=0, zi=self.state)
        filtered[missing] = np.nan
        return filtered
