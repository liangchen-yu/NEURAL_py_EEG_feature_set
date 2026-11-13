"""main_fd's frequency bands and FD method, matched to MATLAB NEURAL.

MATLAB fd_features.m (lines 40-75) uses one band per ROW of freq_bands (a
single [low, high] pair is one band; empty means one band and no filtering),
filters every band from the original x, and takes the method from
params.method ('higuchi' or 'katz').

Synthetic signals only: seeded random noise plus two sines.
"""
import sys

import numpy as np
import pytest

from NEURAL_py_EEG import NEURAL_parameters, fd_features, utils

FS = 64
BANDS = [[0.5, 4], [4, 7], [7, 13], [13, 30]]


def signal(with_nans=False):
    """32 s of synthetic EEG-like signal at 64 Hz."""
    rng = np.random.default_rng(2026)
    t = np.arange(32 * FS) / FS
    x = rng.normal(size=t.size) + 2 * np.sin(2 * np.pi * 2 * t) + np.sin(2 * np.pi * 10 * t)
    if with_nans:
        x[300:340] = np.nan
        x[1000:1003] = np.nan
    return x


def fd_params(**changes):
    """NEURAL's default FD settings, with any changes given."""
    params = NEURAL_parameters.NEURAL_parameters()["FD"]
    params.update(changes)
    return params


def band_filtered(x, low, high, replace):
    return utils.filter_butterworth_withnans(x.copy(), FS, high, low, 5, replace)[0]


def test_defaults_are_what_these_tests_assume():
    params = fd_params()
    assert params["method"] == "higuchi"
    assert params["freq_bands"] == [0.5, 30]
    assert params["FILTER_REPLACE_ARTEFACTS"] == "nans"


@pytest.mark.parametrize("with_nans", [False, True])
def test_default_settings_unchanged(with_nans):
    """Defaults: Higuchi (kmax = qmax) on x filtered to 0.5-30 Hz, exactly as
    before the change (the regression tests check the same against NEURAL)."""
    x = signal(with_nans)
    params = fd_params()
    expected = fd_features.fd_higuchi(
        band_filtered(x, 0.5, 30, params["FILTER_REPLACE_ARTEFACTS"]), params["qmax"]
    )
    np.testing.assert_array_equal(fd_features.main_fd(x, FS, "FD"), [expected])
    np.testing.assert_array_equal(fd_features.main_fd(x, FS), [expected])
    np.testing.assert_array_equal(fd_features.main_fd(x, FS, "FD", {}), [expected])


def test_four_bands_give_four_values_each_as_its_own_band():
    x = signal()
    params = fd_params(freq_bands=BANDS)
    four = fd_features.main_fd(x, FS, "FD", params)
    single = [fd_features.main_fd(x, FS, "FD", fd_params(freq_bands=band))[0] for band in BANDS]
    independent = [
        fd_features.fd_higuchi(
            band_filtered(x, low, high, params["FILTER_REPLACE_ARTEFACTS"]), params["qmax"]
        )
        for low, high in BANDS
    ]
    assert four.shape == (4,)
    assert np.all(np.isfinite(four))
    assert len(set(four)) == 4
    np.testing.assert_array_equal(four, single)
    np.testing.assert_array_equal(four, independent)


@pytest.mark.parametrize("flat_list", [[0.5, 30, 4], [0.5, 30, 4, 7], [0.5, 30, 4, 7, 13]])
def test_flat_list_is_one_band_from_its_first_two_numbers(flat_list):
    """MATLAB: a flat list is one row, so one band, freq_bands(1,1) to (1,2)."""
    x = signal()
    result = fd_features.main_fd(x, FS, "FD", fd_params(freq_bands=flat_list))
    np.testing.assert_array_equal(
        result, fd_features.main_fd(x, FS, "FD", fd_params(freq_bands=[0.5, 30]))
    )


def test_two_by_four_matrix_is_two_bands_from_columns_0_and_1():
    x = signal()
    matrix = [[0.5, 4, 99, 99], [4, 7, 99, 99]]
    result = fd_features.main_fd(x, FS, "FD", fd_params(freq_bands=matrix))
    single = [
        fd_features.main_fd(x, FS, "FD", fd_params(freq_bands=band))[0]
        for band in ([0.5, 4], [4, 7])
    ]
    np.testing.assert_array_equal(result, single)


def test_method_katz():
    x = signal()
    params = fd_params(method="katz")
    expected = fd_features.fd_katz(
        band_filtered(x, 0.5, 30, params["FILTER_REPLACE_ARTEFACTS"])
    )
    np.testing.assert_array_equal(fd_features.main_fd(x, FS, "FD", params), [expected])


def test_method_katz_does_not_need_qmax():
    """MATLAB calls fd_katz(x) without qmax (fd_features.m line 71)."""
    x = signal()
    params = fd_params(method="katz")
    del params["qmax"]
    expected = fd_features.fd_katz(
        band_filtered(x, 0.5, 30, params["FILTER_REPLACE_ARTEFACTS"])
    )
    np.testing.assert_array_equal(fd_features.main_fd(x, FS, "FD", params), [expected])


def test_unknown_method_raises():
    with pytest.raises(ValueError, match="wavelet"):
        fd_features.main_fd(signal(), FS, "FD", fd_params(method="wavelet"))


def test_explicit_names_ignore_method():
    x = signal()
    filtered = band_filtered(x, 0.5, 30, "nans")
    params_katz = fd_params(method="katz")
    np.testing.assert_array_equal(
        fd_features.main_fd(x, FS, "fd_higuchi", params_katz),
        [fd_features.fd_higuchi(filtered, params_katz["qmax"])],
    )
    np.testing.assert_array_equal(
        fd_features.main_fd(x, FS, "fd_katz", fd_params(method="higuchi")),
        [fd_features.fd_katz(filtered)],
    )


def test_empty_freq_bands_give_one_unfiltered_value():
    x = signal()
    params = fd_params(freq_bands=[])
    result = fd_features.main_fd(x, FS, "FD", params)
    np.testing.assert_array_equal(result, [fd_features.fd_higuchi(x, params["qmax"])])
    assert result[0] != fd_features.main_fd(x, FS, "FD")[0]


def test_zeros_mode_bands_do_not_leak(monkeypatch):
    """'zeros' fills NaN in place. Each band must still start from the original
    x: same result as its single-band call, every band's filter sees all the
    NaN of x, and the caller's x is unchanged."""
    x = signal(with_nans=True)
    x_before = x.copy()
    nan_count = int(np.isnan(x).sum())

    single = [
        fd_features.main_fd(
            x, FS, "FD", fd_params(freq_bands=band, FILTER_REPLACE_ARTEFACTS="zeros")
        )[0]
        for band in BANDS
    ]

    filter_inputs_nan_counts = []
    real_filter = utils.filter_butterworth_withnans

    def recording_filter(x_in, *args, **kwargs):
        # Only main_fd's own calls; the filter also calls itself for its
        # low-pass and high-pass stages.
        if sys._getframe(1).f_globals["__name__"] == fd_features.__name__:
            filter_inputs_nan_counts.append(int(np.isnan(x_in).sum()))
        return real_filter(x_in, *args, **kwargs)

    monkeypatch.setattr(fd_features.utils, "filter_butterworth_withnans", recording_filter)
    four = fd_features.main_fd(
        x, FS, "FD", fd_params(freq_bands=BANDS, FILTER_REPLACE_ARTEFACTS="zeros")
    )

    np.testing.assert_array_equal(four, single)
    # One filter call per band, each with all the NaN of the original x.
    assert filter_inputs_nan_counts == [nan_count] * len(BANDS)
    np.testing.assert_array_equal(x, x_before)
