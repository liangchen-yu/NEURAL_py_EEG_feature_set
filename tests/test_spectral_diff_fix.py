"""spectral_diff after the fix from the MATLAB NEURAL, MATLAB commit a279ddd
(2020-04-23): the result is the median of the N_epochs - 1 differences between
consecutive spectrogram windows. Before the fix, one unfilled 0 was also in
the median, which lowered the result. These tests show that the fixed
spectral_diff is right; the regression tests only show that it equals the
original NEURAL with that one line changed.

The differences are recomputed here independently from the spectrogram:
NEURAL's gen_STFT gives the windows' power spectra; the frequency bins of each
band, the scaling, the differences and the median are computed below without
NEURAL's code. Synthetic signals only (seeded white noise at 64 Hz).
"""
import warnings

import numpy as np
import pytest

from NEURAL_py_EEG import NEURAL_parameters, spectral_features

FS = 64

# NEURAL's default spectral settings at 64 Hz: 2 s windows (128 samples, a hop
# of 64 samples), so the spectrum has 2 bins per Hz. The bins of each default
# band, first and last included: the first band starts at the bin of 0.5 Hz
# rounded up, each later band starts at the previous band's last bin (as in
# NEURAL), and each band ends at its upper edge rounded down.
BAND_BINS = [(1, 8), (8, 14), (14, 26), (26, 60)]  # 0.5-4, 4-7, 7-13, 13-30 Hz


def params():
    return NEURAL_parameters.NEURAL_parameters()["spectral"]


def noise(seconds, seed=0):
    return np.random.default_rng(seed).standard_normal(seconds * FS)


def spectrogram(x):
    p = params()
    S, _, f_scale, _ = spectral_features.gen_STFT(x, p["L_window"], p["window_type"], p["overlap"], FS)
    assert f_scale == 2  # bins per Hz, as BAND_BINS assumes
    assert [list(band) for band in p["freq_bands"]] == [[0.5, 4], [4, 7], [7, 13], [13, 30]]
    return S


def window_differences(x):
    """For each band, the N_epochs - 1 differences between consecutive windows:
    the mean squared difference of their band spectra, each band scaled by its
    largest value. NaN where either window's spectrum is NaN.
    Returns an array [bands, N_epochs - 1]."""
    S = spectrogram(x)
    nan_window = np.isnan(S).all(axis=1)
    result = []
    for first, last in BAND_BINS:
        band = S[:, first:last + 1]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all windows NaN: the maximum is NaN
            band = band / np.nanmax(band)
        d = np.full(len(band) - 1, np.nan)
        valid = ~nan_window[:-1] & ~nan_window[1:]
        d[valid] = np.mean((band[1:][valid] - band[:-1][valid]) ** 2, axis=1)
        result.append(d)
    return np.array(result)


def median_of_valid(d):
    valid = d[~np.isnan(d)]
    return np.median(valid) if valid.size else np.nan


def run_spectral_diff(x):
    return spectral_features.spectral_diff(x.copy(), FS, "spectral_diff", params())


def medians_used(monkeypatch, x):
    """Run spectral_diff and return the arrays it passes to np.nanmedian (one per band)."""
    calls = []
    original = np.nanmedian

    def recording_nanmedian(a, *args, **kwargs):
        calls.append(np.array(a, dtype=float))
        return original(a, *args, **kwargs)

    monkeypatch.setattr(spectral_features.np, "nanmedian", recording_nanmedian)
    result = run_spectral_diff(x)
    monkeypatch.undo()
    return result, calls


@pytest.mark.parametrize("seconds", [64, 8])
def test_median_is_over_n_epochs_minus_1_differences(monkeypatch, seconds):
    """The median is taken over exactly N_epochs - 1 values, the real
    differences, with no extra 0."""
    x = noise(seconds)
    n_windows = spectrogram(x).shape[0]
    assert n_windows == {64: 63, 8: 7}[seconds]

    result, calls = medians_used(monkeypatch, x)
    assert len(calls) == len(BAND_BINS)
    expected = window_differences(x)
    for band, values in enumerate(calls):
        assert values.shape == (n_windows - 1,)
        assert np.all(values > 0)  # white noise: every real difference is positive
        np.testing.assert_allclose(values, expected[band], rtol=1e-12, atol=0)
    assert result.shape == (len(BAND_BINS),)


@pytest.mark.parametrize("seconds, seed", [(64, 0), (64, 1), (8, 2), (8, 3), (3, 4)])
def test_result_is_median_of_the_window_differences(seconds, seed):
    """spectral_diff equals the median of the independently computed
    window-to-window differences, in every band. With 3 s there are 2 windows,
    so a single difference: the result is that difference."""
    x = noise(seconds, seed)
    expected = np.array([median_of_valid(d) for d in window_differences(x)])
    np.testing.assert_allclose(run_spectral_diff(x), expected, rtol=1e-12, atol=0)


def test_nan_windows_are_left_out(monkeypatch):
    """Documented NaN handling: a window with a NaN sample has an all-NaN
    spectrum; the differences that involve it are NaN and left out of the
    median. Here 11 NaN samples (from sample 1280, i.e. 20 s) fall in
    windows 19 and 20 (windows k cover samples 64k to 64k + 127), so
    differences 18, 19 and 20 are NaN."""
    x = noise(64)
    x[1280:1291] = np.nan
    S = spectrogram(x)
    assert np.flatnonzero(np.isnan(S).all(axis=1)).tolist() == [19, 20]
    assert not np.isnan(S[[18, 21]]).any()

    result, calls = medians_used(monkeypatch, x)
    for values in calls:
        assert values.shape == (S.shape[0] - 1,)
        assert np.flatnonzero(np.isnan(values)).tolist() == [18, 19, 20]
        assert np.all(values[~np.isnan(values)] > 0)
    expected = np.array([median_of_valid(d) for d in window_differences(x)])
    assert np.all(np.isfinite(expected))
    np.testing.assert_allclose(result, expected, rtol=1e-12, atol=0)


@pytest.mark.filterwarnings("ignore:All-NaN axis encountered:RuntimeWarning")  # also from np.nanmax
@pytest.mark.parametrize("case, warning", [
    ("1 s: one window", "Mean of empty slice"),
    ("2.98 s: one window", "Mean of empty slice"),
    ("every window NaN", "All-NaN slice encountered"),
])
def test_no_valid_difference_gives_nan(case, warning):
    """With no window-to-window difference to take the median of, the result
    is NaN (as the MATLAB median of an empty array), not 0, and numpy warns.
    Any input shorter than 3 s (191 samples here) is a single window; a NaN
    every 64 samples puts a NaN in every window."""
    if case.startswith("every"):
        x = noise(8)
        x[::64] = np.nan
        assert np.isnan(spectrogram(x)).all()
    else:
        x = noise(1) if case.startswith("1 s") else noise(3)[:191]
        assert spectrogram(x).shape[0] == 1
    with pytest.warns(RuntimeWarning, match=warning):
        result = run_spectral_diff(x)
    assert np.isnan(result).all()
