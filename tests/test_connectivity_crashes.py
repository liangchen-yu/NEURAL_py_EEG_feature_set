"""Connectivity features with few channels or missing labels.

Before the fix, connectivity_features.main_connectivity crashed for exactly
2 channels (IndexError), connectivity_BSI crashed with a single left channel
(reported as "Feature function not found"), and missing channel labels
crashed too. These tests check the fixed behaviour, which follows the intent
of MATLAB connectivity_features.m (see CHANGELOG for the deliberate
differences), that the usual 8-channel case is unchanged (within the
regression tolerance), and
the only case where a value computed before changes (BSI, one left channel,
a band of only the 0 Hz bin).

Input: 64 s of the deterministic synthetic EEG from synthetic_edf.py, as
NEURAL's 8 bipolar channels (edge_cases.bipolar), every 4th sample (64 Hz).
"""
import warnings

import numpy as np
import pytest

import edge_cases
from NEURAL_py_EEG import NEURAL_parameters, connectivity_features, spectral_features

FS = 64
FEATURES = [
    "connectivity_BSI",
    "connectivity_corr",
    "connectivity_coh_mean",
]
# connectivity_coh_max and connectivity_coh_freqmax were also tested here;
# they were removed to match neural_eeg_features 0.6.1.
N_BANDS = len(NEURAL_parameters.NEURAL_parameters()["connectivity"]["freq_bands"])

# 8-channel results of the code before the fix (commit 5c98791) on the input
# below; the fix must not change them.
BEFORE_FIX_8_CHANNELS = {
    "connectivity_BSI": [0.09515272147710148, 0.16261624341324804, 0.11367511201690306, 0.1254726208695133],
    "connectivity_corr": [0.564449488108129, 0.442008107866694, 0.514278679749087, 0.43687027383538074],
    "connectivity_coh_mean": [0.343306016862116, 0.34162271189851795, 0.4054417832353553, 0.33653316636455693],
}


@pytest.fixture(scope="module")
def eeg():
    """The 8 bipolar channels (rows) and their labels."""
    bip = edge_cases.bipolar(edge_cases.referential(seconds=64))
    return bip.to_numpy().T[:, ::4].copy(), list(bip.columns)


def channels(eeg, names):
    x, labels = eeg
    return x[[labels.index(n) for n in names]].copy(), np.array(names)


def connectivity(x, labels, feature, params=None):
    with warnings.catch_warnings():
        # NEURAL's own DeprecationWarnings (e.g. "left or right channel?") are not tested here
        warnings.simplefilter("ignore", DeprecationWarning)
        return np.asarray(connectivity_features.main_connectivity(x, FS, feature, labels, params))


@pytest.mark.parametrize("feature", FEATURES)
def test_two_labelled_channels_give_finite_values(eeg, feature):
    """Crash 1: exactly 2 channels raised IndexError. A left/right pair
    (C3_O1, C4_O2) must give a finite value per frequency band."""
    x, labels = channels(eeg, ["C3_O1", "C4_O2"])
    result = connectivity(x, labels, feature)
    assert result.shape == (N_BANDS,)
    assert np.isfinite(result).all()


ONE_LEFT_TWO_RIGHT = {
    "pair first": ["C3_O1", "C4_O2", "C4_T4"],
    # the unmatched right channel first: code that takes the first right
    # channel (iright[0]) instead of the pair gives a different value
    "unmatched first": ["C3_O1", "C4_T4", "C4_O2"],
}


@pytest.mark.parametrize("order", ONE_LEFT_TWO_RIGHT)
def test_bsi_with_one_left_and_two_right_channels(eeg, order):
    """Crash 2: one left channel made connectivity_BSI fail ("Feature function
    not found"). With 1 left and 2 right channels, BSI must be finite and use
    the left channel and its paired right channel (C4_O2, wherever it is
    listed), so it equals the BSI of that pair alone."""
    x, labels = channels(eeg, ONE_LEFT_TWO_RIGHT[order])
    result = connectivity(x, labels, "connectivity_BSI")
    assert result.shape == (N_BANDS,)
    assert np.isfinite(result).all()

    x_pair, labels_pair = channels(eeg, ["C3_O1", "C4_O2"])
    np.testing.assert_array_equal(result, connectivity(x_pair, labels_pair, "connectivity_BSI"))


def whole_spectrum_bsi(eeg, left, right):
    """BSI averaged over every frequency of the two channels' spectra (no band
    selection): what the old code returned for a band of only the 0 Hz bin."""
    spectra = [spectral_features.gen_spectrum(channels(eeg, [name])[0][0], FS,
                                              NEURAL_parameters.NEURAL_parameters()["connectivity"], 1)[0]
               for name in (left, right)]
    return np.nanmean(np.abs((spectra[0] - spectra[1]) / (spectra[0] + spectra[1])))


@pytest.mark.parametrize("order", ONE_LEFT_TWO_RIGHT)
def test_bsi_one_left_channel_band_at_0_hz(eeg, order):
    """The only case where a value computed before changes:
    1 left channel and a band of only the 0 Hz bin (freq_bands [[0, 0.1]];
    bins are 0.125 Hz apart). The old code indexed channels instead of
    frequencies and returned the whole-spectrum BSI average (0.1711 for this
    pair; for the unmatched-first order, against the wrong channel). The
    value must now be the 0 Hz value of the pair C3_O1 / C4_O2, as recorded
    (0.24434112994141818), within the regression tolerance of
    tests/neural_outputs.py (rtol 1e-9, atol 1e-12; NaN must match NaN).
    Exact bytes are not required, because they differ across machines
    (rounding in the last bits)."""
    params = NEURAL_parameters.NEURAL_parameters()["connectivity"]
    params["freq_bands"] = [[0, 0.1]]
    x, labels = channels(eeg, ONE_LEFT_TWO_RIGHT[order])
    result = connectivity(x, labels, "connectivity_BSI", params)
    assert result.dtype == np.float64 and result.shape == (1,)
    np.testing.assert_allclose(
        result, np.array([0.24434112994141818]), rtol=1e-9, atol=1e-12, equal_nan=True
    )
    assert result[0] != whole_spectrum_bsi(eeg, "C3_O1", "C4_O2")


@pytest.mark.parametrize("names", [["C3_O1", "C4_O2"], ["C3_O1", "C4_O2", "F3_C3", "F4_C4"]])
@pytest.mark.parametrize("feature", FEATURES)
def test_no_labels_warns_and_returns_nan_per_band(eeg, names, feature):
    """Without channel labels the left/right pairs are unknown (MATLAB
    867849b): a warning and one NaN per frequency band, for 2 channels and
    more. Before, both crashed."""
    x, _ = channels(eeg, names)
    with pytest.warns(UserWarning, match="channel names"):
        result = connectivity(x, np.array([]), feature)
    assert result.shape == (N_BANDS,)
    assert np.isnan(result).all()


@pytest.mark.parametrize("n_bands", [N_BANDS, 3])
@pytest.mark.parametrize("feature", FEATURES)
def test_no_left_right_pairs_gives_nan_per_band(eeg, n_bands, feature):
    """Only left channels, so no pairs (MATLAB c521173): one NaN per
    frequency band. Before, always 4 NaN values, whatever the number of bands."""
    params = NEURAL_parameters.NEURAL_parameters()["connectivity"]
    params["freq_bands"] = params["freq_bands"][:n_bands]
    x, labels = channels(eeg, ["C3_O1", "C3_T3", "F3_C3"])
    result = connectivity(x, labels, feature, params)
    assert result.shape == (n_bands,)
    assert np.isnan(result).all()


@pytest.mark.parametrize("feature", FEATURES)
def test_eight_channels_unchanged(eeg, feature):
    """The usual case, all 8 NEURAL bipolar channels with labels, worked
    before the fix and must still give the recorded pre-fix values: same
    dtype and shape, and values equal within the regression tolerance of
    tests/neural_outputs.py (rtol 1e-9, atol 1e-12; NaN must match NaN).
    Exact bytes are not required, because they differ across machines:
    rounding in the last bits, up to about 2e-10 relative on GitHub's Ubuntu
    runners."""
    x, labels = eeg
    result = connectivity(x.copy(), np.array(labels), feature)
    expected = np.array(BEFORE_FIX_8_CHANNELS[feature], dtype=np.float64)
    assert result.dtype == expected.dtype
    assert result.shape == expected.shape
    np.testing.assert_allclose(result, expected, rtol=1e-9, atol=1e-12, equal_nan=True)
