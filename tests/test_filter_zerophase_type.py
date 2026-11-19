"""The filter type in utils.filter_zerophase.

MATLAB filter_zerophase.m names the filter type it builds (fir1 'bandpass',
'stop', 'low', 'high'). The Python port left scipy's firwin at its default,
pass_zero=True (keep 0 Hz), so a band-pass came out as a band-stop and a
high-pass as a low-pass. Brian Murphy's PyPI release 0.1.4 (26 Jul 2022) named
the type; that change was never on GitHub. These tests check that:
- each type passes and blocks the right frequencies;
- the low-pass and band-stop filters are exactly as before (the default
  pipeline uses only the low-pass, so default results do not change).

Synthetic sine waves only: no recordings are used.
"""
import numpy as np
import pytest
from scipy import signal

from NEURAL_py_EEG import mfiltfilt, utils

FS = 64
N = FS * 60  # 60 s
L_FILT = 501
T = np.arange(N) / FS
MIDDLE = slice(N // 4, 3 * N // 4)  # away from the filter's edge effects


def sine(f_hz):
    return np.sin(2 * np.pi * f_hz * T)


def gain(x_in, **cutoffs):
    """Output amplitude / input amplitude, in the middle of the signal."""
    y = utils.filter_zerophase(x_in.copy(), FS, L_filt=L_FILT, **cutoffs)
    return np.std(y[MIDDLE]) / np.std(x_in[MIDDLE])


@pytest.mark.parametrize("f_hz, kept", [(0.2, False), (6, True), (20, False)])
def test_band_pass_keeps_only_the_band(f_hz, kept):
    """4-8 Hz band-pass: it gave the opposite (a band-stop) before the fix."""
    g = gain(sine(f_hz), LP_fc=8, HP_fc=4)
    assert g > 0.9 if kept else g < 0.1


@pytest.mark.parametrize("f_hz, kept", [(0.1, False), (10, True)])
def test_high_pass_removes_slow_activity(f_hz, kept):
    """1 Hz high-pass: it gave a low-pass before the fix."""
    g = gain(sine(f_hz), HP_fc=1)
    assert g > 0.9 if kept else g < 0.1


def test_high_pass_removes_a_constant_offset():
    y = utils.filter_zerophase(sine(10) + 50.0, FS, HP_fc=1, L_filt=L_FILT)
    assert abs(np.mean(y[MIDDLE])) < 0.5


def old_filter(x, cutoff):
    """The filter as it was built before the fix (firwin default)."""
    b = signal.firwin(L_FILT, cutoff, window="hamming")
    return mfiltfilt.mat_filtfilt(b, np.array([1]), x.copy())


def test_low_pass_unchanged():
    """The only type the default pipeline uses (30 Hz in LPF_zero_phase)."""
    x = sine(5) + sine(28) + 0.3 * sine(31)
    new = utils.filter_zerophase(x.copy(), FS, LP_fc=20, L_filt=L_FILT)
    np.testing.assert_array_equal(new, old_filter(x, 20 / (FS / 2)))


def test_band_stop_unchanged():
    """LP_fc below HP_fc asks for a band-stop; firwin's default already gave one."""
    x = sine(2) + sine(6) + sine(20)
    new = utils.filter_zerophase(x.copy(), FS, LP_fc=4, HP_fc=8, L_filt=L_FILT)
    np.testing.assert_array_equal(new, old_filter(x, [4 / (FS / 2), 8 / (FS / 2)]))
