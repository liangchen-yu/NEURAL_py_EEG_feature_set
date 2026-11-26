"""generate_all_features: complete epochs only, as in neural_eeg_features 0.6.1
(the reference package; its docs/definitions.md, "Missing data and recording
boundaries": "Ordinary epochs are complete windows only: trailing incomplete
data do not create an additional epoch. A recording shorter than one ordinary
epoch raises ValueError when ordinary features are requested.").

With an epoch of L samples (floor(EPOCH_LENGTH * Fs)) and a hop of H samples,
N samples give (N - L) // H + 1 epochs, epoch k holding samples k * H to
k * H + L - 1. Before, NEURAL also made a final epoch padded with NaN
(ceil((N - (L - H)) / H) epochs; the unused copy
preprocessing_EEG.overlap_epochs keeps that rule). A recording shorter than
one epoch raises ValueError when an epoch-based feature is requested; IBI
features (whole recording) and an empty request still work.

Synthetic data only.
"""
import contextlib
import io
import warnings

import numpy as np
import pandas as pd
import pytest

from NEURAL_py_EEG import IBI_features, NEURAL_parameters, generate_all_features, preprocessing_EEG, utils

LABELS = ["C3_O1", "C4_O2"]


def epoch_layout(Fs):
    params = NEURAL_parameters.NEURAL_parameters()
    hop, L, dum = utils.gen_epoch_window(params["EPOCH_OVERLAP"], params["EPOCH_LENGTH"], "rect", Fs)
    return int(hop), int(L)


def edge_lengths(Fs):
    """(N, expected number of epochs or None for ValueError)."""
    hop, L = epoch_layout(Fs)
    return [(L - 1, None), (L, 1), (L + hop - 1, 1), (L + hop, 2), (L + 3 * hop, 4),
            (L + 3 * hop + hop // 2, 4)]


def data(N, Fs, seed=1):
    rng = np.random.default_rng(seed)
    return {"eeg_data": pd.DataFrame(rng.normal(size=(N, 2)), columns=LABELS), "Fs": Fs, "ch_labels": LABELS}


def run(N, Fs, feat_set):
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore")
        return generate_all_features.generate_all_features(data(N, Fs), feat_set=feat_set)


@pytest.mark.parametrize("Fs", [64, 256, 63.93])
def test_epoch_counts_and_starts(Fs):
    """At an even (64, 256 Hz) and an odd (63.93 Hz: 4091 samples) epoch
    length: L - 1 samples raise; L and L + H - 1 give one epoch; L + H two;
    L + 3H (divides evenly) and L + 3.5H four. Epoch k is exactly samples
    k * H to k * H + L - 1 (rectangular window), without NaN."""
    hop, L = epoch_layout(Fs)
    for N, expected in edge_lengths(Fs):
        x = np.arange(N, dtype=float)
        if expected is None:
            with pytest.raises(ValueError, match="shorter than one analysis epoch"):
                generate_all_features.overlap_epochs(x, Fs, 64, 50)
            assert generate_all_features.epoch_count(N, Fs, 64, 50) == 0
            continue
        epochs = generate_all_features.overlap_epochs(x, Fs, 64, 50)
        assert epochs.shape == (expected, L), (Fs, N)
        assert generate_all_features.epoch_count(N, Fs, 64, 50) == expected
        assert not np.isnan(epochs).any()
        for k in range(expected):
            np.testing.assert_array_equal(epochs[k], x[k * hop:k * hop + L])


@pytest.mark.parametrize("Fs", [64, 256, 63.93])
def test_same_as_the_old_rule_without_the_padded_epoch(Fs):
    """The old rule (kept by preprocessing_EEG.overlap_epochs) gave the same
    complete epochs, plus a NaN-padded final epoch when the samples after the
    last complete epoch did not fill another hop; nothing else differs."""
    hop, L = epoch_layout(Fs)
    for N, expected in edge_lengths(Fs):
        if expected is None:
            continue
        x = np.random.default_rng(N).normal(size=N)
        new = generate_all_features.overlap_epochs(x, Fs, 64, 50)
        with contextlib.redirect_stdout(io.StringIO()):
            old = preprocessing_EEG.overlap_epochs(x, Fs, 64, 50)[0]
        np.testing.assert_array_equal(new, old[:expected])
        padded = (N - L) % hop != 0
        assert old.shape[0] == expected + padded, (Fs, N)
        if padded:
            assert np.isnan(old[-1]).any() and not np.isnan(old[-1]).all()


@pytest.mark.parametrize("Fs", [64, 100, 250, 256, 63.93, 127.99])
@pytest.mark.parametrize("overlap", [50, 75])
def test_hop_matches_the_reference_package(Fs, overlap):
    """The hop is unchanged; it equals the reference package's
    size - int(size * overlap // 100) (extraction._epochs)."""
    hop, L, dum = utils.gen_epoch_window(overlap, 64, "rect", Fs)
    assert hop == L - int(L * overlap // 100)


def test_short_recording_raises_before_any_work(monkeypatch):
    """The error names both lengths and comes before any feature is computed
    (here an IBI feature, requested first, is not computed)."""
    calls = []
    monkeypatch.setattr(IBI_features, "main_IBI", lambda *args, **kwargs: calls.append("IBI"))
    monkeypatch.setattr(generate_all_features, "overlap_epochs", lambda *args, **kwargs: calls.append("epochs"))
    message = (r"Recording is shorter than one analysis epoch: 4032 samples \(63 s at 64 Hz\); "
               r"an epoch is 4096 samples \(EPOCH_LENGTH = 64 s\)")
    with pytest.raises(ValueError, match=message):
        generate_all_features.generate_all_features(data(63 * 64, 64), feat_set=["IBI_burst_number", "spectral_power"])
    assert calls == []


@pytest.mark.parametrize("feature", ["spectral_power", "spectral_edge_frequency", "FD", "amplitude_env_mean",
                                     "rEEG_median", "connectivity_BSI", "connectivity_corr"])
def test_every_epoch_based_feature_needs_one_epoch(feature):
    with pytest.raises(ValueError, match="shorter than one analysis epoch"):
        run(64 * 64 - 1, 64, [feature])


@pytest.mark.parametrize("Fs", [64, 256, 63.93])
@pytest.mark.parametrize("feat_set", [["IBI_burst_number"], []], ids=["IBI only", "empty"])
def test_requests_without_epoch_features_still_work(Fs, feat_set):
    """At every edge length, including one sample short of an epoch: no
    epoch rows, no error."""
    for N, expected in edge_lengths(Fs):
        per_epochs, names, feat_st, median_ch, median_all = run(N, Fs, feat_set)
        assert median_ch.shape[0] == (expected or 0), (Fs, N)
        assert median_all.shape == (1, len(names))


@pytest.mark.parametrize("Fs", [64, 256, 63.93])
def test_output_shapes_follow_the_epochs(Fs):
    """feats_median_ch has one row and feats_per_epochs one entry per epoch,
    for per-channel and connectivity features."""
    for N, expected in edge_lengths(Fs):
        if expected is None:
            continue
        per_epochs, names, feat_st, median_ch, median_all = run(N, Fs, ["spectral_power", "connectivity_BSI"])
        assert median_ch.shape == (expected, 8), (Fs, N)
        assert np.shape(per_epochs) == (2, expected, 4), (Fs, N)
