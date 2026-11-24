"""Downsampling to 64 Hz must give 64 Hz for every input rate.

preprocessing_EEG.signal_downsample keeps every k-th sample when Fs / 64 is a
whole number and uses scipy.signal.resample_poly otherwise. The rate test makes
10 s of a 5 Hz sine, downsamples it and checks the declared rate, the number
of samples and that the sine is still at 5 Hz when read at 64 Hz.

The other tests check that resample_poly uses the ratio Fs_new/Fs, as MATLAB
resample(x, Fs_new, Fs) does (exact for whole-number rates, approximated with
denominator <= 10000 otherwise): lengths that are not a whole number of seconds,
whole-second lengths (unchanged from the old length-based ratio), all-NaN
channels and a non-integer target rate. The last test documents the inherited
growth of NaN gaps during resampling.
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


def test_non_integer_target_rate():
    """A non-integer target rate (64.5 Hz) is not truncated."""
    Fs, Fs_new, N = 200, 64.5, 2001
    rng = np.random.default_rng(3)
    data = pd.DataFrame({"C3": rng.standard_normal(N)})

    out, Fs_out = preprocessing_EEG.signal_downsample(data, Fs, Fs_new)

    assert Fs_out == Fs_new
    assert len(out["C3"]) == int(np.ceil(N * Fs_new / Fs))


def test_nan_gap_grows_slightly():
    """Inherited behaviour: a NaN gap stays NaN and grows slightly, because of resample_poly's filter.

    Samples more than 1 s away from the gap are not NaN.
    """
    Fs = 200
    t = np.arange(SECONDS * Fs) / Fs
    x = np.sin(2 * np.pi * SINE_HZ * t)
    gap_start, gap_end = 4.5, 5.0  # 0.5 s gap
    x[(t >= gap_start) & (t < gap_end)] = np.nan
    data = pd.DataFrame({"C3": x})

    out, _ = preprocessing_EEG.signal_downsample(data, Fs, FS_NEW)

    y = out["C3"].to_numpy()
    t_out = np.arange(len(y)) / FS_NEW
    in_gap = (t_out >= gap_start) & (t_out < gap_end)
    far = (t_out < gap_start - 1) | (t_out >= gap_end + 1)
    assert np.isnan(y[in_gap]).all()
    assert np.isnan(y).sum() > in_gap.sum()
    assert not np.isnan(y[far]).any()
