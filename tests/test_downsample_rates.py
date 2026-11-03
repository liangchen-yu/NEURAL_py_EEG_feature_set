"""Downsampling to 64 Hz must give 64 Hz for every input rate.

preprocessing_EEG.signal_downsample keeps every k-th sample when Fs / 64 is a
whole number and uses scipy.signal.resample_poly otherwise. Each test makes
10 s of a 5 Hz sine, downsamples it and checks the declared rate, the number
of samples and that the sine is still at 5 Hz when read at 64 Hz.
"""
import numpy as np
import pandas as pd
import pytest

from NEURAL_py_EEG import preprocessing_EEG

FS_NEW = 64
SECONDS = 10
SINE_HZ = 5


@pytest.mark.parametrize("Fs", [96, 128, 160, 200, 224, 250, 256, 288, 480, 500, 512])
def test_downsampled_rate_is_64_hz(Fs):
    t = np.arange(SECONDS * Fs) / Fs
    data = pd.DataFrame({"C3": np.sin(2 * np.pi * SINE_HZ * t)})

    out, Fs_out = preprocessing_EEG.signal_downsample(data, Fs, FS_NEW)

    assert Fs_out == FS_NEW
    y = out["C3"].to_numpy()
    assert len(y) == SECONDS * FS_NEW
    freqs = np.fft.rfftfreq(len(y), d=1 / FS_NEW)
    peak = freqs[np.argmax(np.abs(np.fft.rfft(y)))]
    assert abs(peak - SINE_HZ) <= 0.2
