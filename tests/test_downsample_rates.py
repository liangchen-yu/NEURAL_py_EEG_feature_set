"""Downsampling to 64 Hz must give 64 Hz for every input rate.

preprocessing_EEG.signal_downsample keeps every k-th sample when Fs / 64 is a
whole number and uses scipy.signal.resample_poly otherwise. The rate test makes
10 s of a 5 Hz sine, downsamples it and checks the declared rate, the number
of samples and that the sine is still at 5 Hz when read at 64 Hz.

The other tests check that resample_poly uses the exact ratio 64/Fs, as MATLAB
resample(x, Fs_new, Fs) does: lengths that are not a whole number of seconds,
whole-second lengths (unchanged from the old length-based ratio) and all-NaN
channels.
"""
import numpy as np
import pandas as pd
import pytest
from scipy import signal

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


@pytest.mark.parametrize("Fs, N", [(200, 1001), (250, 2501), (500, 5003), (200, 720001)])
def test_odd_length_uses_exact_ratio(Fs, N):
    """A length that is not a whole number of seconds still gives exactly 64 Hz.

    resample_poly with the exact ratio 64/Fs returns ceil(N * 64 / Fs) samples.
    """
    rng = np.random.default_rng(0)
    data = pd.DataFrame({"C3": rng.standard_normal(N)})

    out, Fs_out = preprocessing_EEG.signal_downsample(data, Fs, FS_NEW)

    assert Fs_out == FS_NEW
    assert len(out["C3"]) == int(np.ceil(N * FS_NEW / Fs))


@pytest.mark.parametrize("Fs", [200, 250, 500, 1000])
def test_whole_seconds_unchanged(Fs):
    """For a whole number of seconds the output equals the old length-based formula exactly."""
    N = SECONDS * Fs
    rng = np.random.default_rng(1)
    x = rng.standard_normal(N)
    data = pd.DataFrame({"C3": x})

    out, _ = preprocessing_EEG.signal_downsample(data, float(Fs), FS_NEW)

    old = signal.resample_poly(x, round(len(x) / (Fs / FS_NEW)), len(x))
    assert np.array_equal(out["C3"].to_numpy(), old)


def test_all_nan_channel_odd_length():
    """An all-NaN channel gets the same length as the other channels."""
    Fs, N = 200, 1001
    rng = np.random.default_rng(2)
    data = pd.DataFrame({"C3": rng.standard_normal(N), "C4": np.full(N, np.nan)})

    out, _ = preprocessing_EEG.signal_downsample(data, Fs, FS_NEW)

    assert len(out["C4"]) == len(out["C3"])
    assert np.isnan(out["C4"]).all()
