"""generate_all_features: the number of rows preallocated for feats_median_ch
(get_max_num_epochs) equals the number of epochs (overlap_epochs). Both use
generate_all_features.epoch_count.

Before, get_max_num_epochs used the hop of a 'hamm' window, overlap_epochs
that of a 'rect' window. They differ by one sample when the epoch length in
samples is odd, i.e. at non-integer sampling rates (63.93 Hz: 4091 samples,
hops 2045 and 2046); the counts then differed for some recording lengths and
generate_all_features failed. At even epoch lengths (64, 100, 250, 256 Hz)
nothing changes.

Synthetic data only.
"""
import contextlib
import io
import warnings

import numpy as np
import pandas as pd
import pytest

from NEURAL_py_EEG import NEURAL_parameters, generate_all_features, utils

RATES = [64, 100, 250, 256, 63.93, 127.99]


def lengths(Fs):
    """Recording lengths (samples) around every epoch boundary for 1 to 12
    epochs, very short ones, and seeded random ones up to 30 minutes."""
    params = NEURAL_parameters.NEURAL_parameters()
    hop, L_epoch, dum = utils.gen_epoch_window(params["EPOCH_OVERLAP"], params["EPOCH_LENGTH"], "rect", Fs)
    result = {1, 2, 100, L_epoch - hop - 1, L_epoch - hop, L_epoch - hop + 1}
    for k in range(13):
        for delta in (-2, -1, 0, 1, 2):
            result.add(L_epoch + k * hop + delta)
            result.add(L_epoch - hop + k * hop + delta)
    rng = np.random.default_rng(2026)
    result.update(int(n) for n in rng.integers(L_epoch, int(1800 * Fs), size=40))
    return sorted(n for n in result if n > 0)


def epochs(N, Fs):
    params = NEURAL_parameters.NEURAL_parameters()
    with contextlib.redirect_stdout(io.StringIO()):  # the short-recording warning
        return generate_all_features.overlap_epochs(np.zeros(N), Fs, params["EPOCH_LENGTH"],
                                                    params["EPOCH_OVERLAP"]).shape[0]


@pytest.mark.parametrize("Fs", RATES)
def test_preallocated_rows_equal_epochs(Fs):
    """Equal whenever the count is at least 1. A recording no longer than
    L_epoch - L_hop gets 0 preallocated rows (as before) and one padded
    epoch, whose row an epoch feature adds (test_short_recording_shapes)."""
    params = NEURAL_parameters.NEURAL_parameters()
    hop, L_epoch, dum = utils.gen_epoch_window(params["EPOCH_OVERLAP"], params["EPOCH_LENGTH"], "rect", Fs)
    for N in lengths(Fs):
        rows = generate_all_features.get_max_num_epochs(params, N, Fs)
        if N <= L_epoch - hop:
            assert rows == 0 and epochs(N, Fs) == 1, (Fs, N)
        else:
            assert rows == epochs(N, Fs), (Fs, N)


# feats_median_ch shapes of the code before this change (commit 48b77fd) for
# 2 synthetic channels: (rows, columns) per feature set, for recordings of
# 100 samples, 20 s, 32 s (= L_epoch - L_hop) and 32 s + 1 sample.
SHORT_SHAPES = {
    "IBI only": [(0, 1), (0, 1), (0, 1), (1, 1)],
    "empty": [(0, 0), (0, 0), (0, 0), (1, 0)],
    "spectral_power": [(1, 4), (1, 4), (1, 4), (1, 4)],
}
FEATURE_SETS = {"IBI only": ["IBI_burst_number"], "empty": [], "spectral_power": ["spectral_power"]}


@pytest.mark.parametrize("Fs", [64, 256])
@pytest.mark.parametrize("name", sorted(SHORT_SHAPES))
def test_short_recording_shapes(Fs, name):
    """Short recordings keep the shapes of before: no row is added when no
    epoch feature runs (IBI only, or no feature); an epoch feature fills
    the one padded epoch."""
    sizes = [100, 20 * Fs, 32 * Fs, 32 * Fs + 1]
    for N, expected in zip(sizes, SHORT_SHAPES[name]):
        rng = np.random.default_rng(1)
        labels = ["C3_O1", "C4_O2"]
        data = {"eeg_data": pd.DataFrame(rng.normal(size=(N, 2)), columns=labels), "Fs": Fs, "ch_labels": labels}
        with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
            warnings.simplefilter("ignore")
            median_ch = generate_all_features.generate_all_features(data, feat_set=FEATURE_SETS[name])[3]
        assert median_ch.shape == expected, (Fs, N, name)


@pytest.mark.parametrize("Fs, odd", [(64, False), (100, False), (250, False), (256, False),
                                     (63.93, True), (127.99, True)])
def test_hamm_and_rect_hops_differ_only_for_odd_epoch_lengths(Fs, odd):
    """Why the shared count matters: at the default 50 % overlap the two
    window types' hops differ by one sample exactly when the epoch length in
    samples is odd."""
    hop_rect, L_epoch, dum = utils.gen_epoch_window(50, 64, "rect", Fs)
    hop_hamm = utils.gen_epoch_window(50, 64, "hamm", Fs)[0]
    assert (L_epoch % 2 == 1) is odd
    assert (hop_rect != hop_hamm) is odd


def test_odd_epoch_length_no_longer_fails():
    """63.93 Hz, 6137 samples (96 s): 2 epochs; the old 'hamm' count gave 3
    rows and generate_all_features failed."""
    Fs, N = 63.93, 6137
    hop_hamm, L_epoch, dum = utils.gen_epoch_window(50, 64, "hamm", Fs)
    assert int(np.ceil((N - (L_epoch - hop_hamm)) / hop_hamm)) == 3  # the old count
    assert epochs(N, Fs) == 2
    rng = np.random.default_rng(7)
    labels = ["C3_O1", "C4_O2"]
    data = {"eeg_data": pd.DataFrame(rng.normal(size=(N, 2)), columns=labels), "Fs": Fs, "ch_labels": labels}
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore", RuntimeWarning)
        per_epochs, names, feat_st, median_ch, median_all = generate_all_features.generate_all_features(
            data, feat_set=["spectral_power", "connectivity_BSI"])
    assert median_ch.shape[0] == 2
    assert np.shape(per_epochs)[1] == 2
    assert np.isfinite(median_all.to_numpy(dtype=float)).all()
