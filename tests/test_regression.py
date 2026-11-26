"""Regression tests: this repository's NEURAL must give the same numbers as
the original NEURAL (commit 78c9425) on the same synthetic EDF files.

The reference numbers in tests/data/ were made by tests/make_reference.py
with the original NEURAL and pandas 2.3.3. Each test runs the code in this
repository on the same inputs and compares every number, with a strict
tolerance (see neural_outputs.RTOL and ATOL). Run with:  pytest

spectral_diff is compared, with the same tolerance, with the values of the
original plus the one-line MATLAB fix a279ddd, and amplitude_skew and
amplitude_kurtosis with the values of the original plus the definitions of
neural_eeg_features 0.6.1; make_reference.py stores both in the same
reference files (neural_outputs.with_fixes).

The 7 features removed to match neural_eeg_features 0.6.1 are still in the
reference files; the tests skip them (neural_outputs.without_removed_features).

The reference files were made with the original's settings (its defaults);
the tests pass the same settings, written out in
neural_outputs.original_settings(), to this repository's generate_all_features
(params), so they keep checking those settings when the defaults change.
"""
import pytest

import neural_outputs
import synthetic_edf

CASES = synthetic_edf.CASES
ORIGINAL_COMMIT = "78c94258e4a3e6504e469f418443c78926e1a6be"


def test_reference_was_made_with_the_original_neural(reference):
    for case in CASES:
        made_with = reference[case]["made_with"]
        assert made_with["neural_commit"] == ORIGINAL_COMMIT
        assert made_with["neural_has_pandas3_fix"] is False


def test_reference_has_the_originals_26_non_ibi_features(raw_reference, reference):
    """The reference files hold the original's 26 non-IBI features; this
    repository has the same features, in the same order, without the 7 removed
    to match neural_eeg_features 0.6.1, and the tests compare exactly those."""
    features = neural_outputs.non_ibi_features()
    assert len(features) == 19
    assert {neural_outputs.feature_group(f) for f in features} == set(neural_outputs.GROUPS)
    for case in CASES:
        original = list(raw_reference[case]["features"])
        assert len(original) == 26
        assert set(neural_outputs.REMOVED_FEATURES) <= set(original)
        assert [f for f in original if f not in neural_outputs.REMOVED_FEATURES] == features
        assert list(reference[case]["features"]) == features


def test_moments_section_holds_the_bias_corrected_values(raw_reference):
    """The neural_eeg_features 0.6.1 moments section holds amplitude_skew and
    amplitude_kurtosis only, and its values are not a copy of the original's.

    This checks the STORED synthetic reference data only, where every finite
    value happens to be higher with the bias correction. It is not a general
    property: the skewness magnitude never decreases, but the corrected
    kurtosis can be lower for very flat data (see test_amplitude_moments.py)."""
    import numpy as np

    for case in CASES:
        section = raw_reference[case][neural_outputs.MOMENTS_SECTION]
        assert list(section["features"]) == list(neural_outputs.MOMENTS_FEATURES)
        for feature in neural_outputs.MOMENTS_FEATURES:
            fixed = neural_outputs.to_array(section["features"][feature]["feats_per_epochs"])
            original = neural_outputs.to_array(raw_reference[case]["features"][feature]["feats_per_epochs"])
            # NaN and +/-inf at the same places (checked separately) ...
            assert np.array_equal(np.isnan(fixed), np.isnan(original))
            assert np.array_equal(np.isinf(fixed), np.isinf(original))
            # ... and, in this stored data, every finite value higher.
            finite = np.isfinite(original)
            assert finite.any() and np.all(fixed[finite] > original[finite])


def epochs_with_nan(data):
    """For the channels generate_all_features keeps (not all NaN), whether
    each epoch of the ORIGINAL's epoch grid contains NaN: [channel][epoch], as
    the original's feats_per_epochs. The original's grid (with its NaN-padded
    final epoch) is that of preprocessing_EEG.overlap_epochs, the unchanged
    copy; generate_all_features now uses complete epochs only."""
    import numpy as np
    from NEURAL_py_EEG import preprocessing_EEG

    params = neural_outputs.original_settings()
    eeg = data["eeg_data"]
    kept = [c for c in data["ch_labels"] if not np.all(np.isnan(eeg[c]))]
    return np.array([[np.isnan(epoch).any() for epoch in preprocessing_EEG.overlap_epochs(
        eeg[c], data["Fs"], params["EPOCH_LENGTH"], params["EPOCH_OVERLAP"])[0]] for c in kept])


def earlier_fixes(raw, feature):
    """A main reference's values for one feature with the fixes before the
    complete-epochs section applied: its own section if it has one, else the
    original's."""
    for section, features, keys in neural_outputs.FIXES[:-1]:
        if feature in features:
            return raw[section]["features"][feature]
    return raw["features"][feature]


@pytest.mark.parametrize("case", CASES)
def test_complete_epochs_section_drops_only_the_padded_epoch(case, raw_reference):
    """The complete-epochs section (made by the original with all fixes and
    complete epochs only) must hold, for every feature, exactly the values
    of the earlier references on the complete epochs: the per-epoch values
    of the first n epochs unchanged, the original's final NaN-padded epoch
    (n + 1) dropped. Its summaries must be the medians of those epochs."""
    import numpy as np
    from NEURAL_py_EEG import generate_all_features

    raw = raw_reference[case]
    section = raw[neural_outputs.COMPLETE_EPOCHS_SECTION]["features"]
    assert sorted(section) == sorted(neural_outputs.COMPLETE_EPOCHS_FEATURES)
    samples, fs = raw["preprocessed"]["n_samples"], raw["preprocessed"]["Fs"]
    n = generate_all_features.epoch_count(samples, fs, 64, 50)
    assert n == 8  # 300 s at 64 Hz: complete epochs start every 32 s, the 9th would be padded
    for feature in neural_outputs.COMPLETE_EPOCHS_FEATURES:
        new, old = section[feature], earlier_fixes(raw, feature)
        assert new["columns"] == old["columns"]
        median_ch = neural_outputs.to_array(new["feats_median_ch"])
        old_median_ch = neural_outputs.to_array(old["feats_median_ch"])
        assert median_ch.shape[0] == n and old_median_ch.shape[0] == n + 1, feature
        assert np.array_equal(median_ch, old_median_ch[:n], equal_nan=True), feature
        if neural_outputs.feature_group(feature) == "connectivity":
            per_epoch = median_ch  # the per-epoch values of a connectivity feature
            expected = np.nanmedian(per_epoch, axis=0)
        else:
            per_epoch = neural_outputs.to_array(new["feats_per_epochs"])  # [channel][epoch][band]
            old_per_epoch = neural_outputs.to_array(old["feats_per_epochs"])
            assert per_epoch.shape[1] == n and old_per_epoch.shape[1] == n + 1, feature
            assert np.array_equal(per_epoch, old_per_epoch[:, :n, :], equal_nan=True), feature
            expected = np.nanmedian(np.nanmedian(per_epoch, axis=1), axis=0)
        assert np.array_equal(neural_outputs.to_array(new["feat_st"]), expected, equal_nan=True), feature


def test_band_bins_section_differs_only_in_epochs_with_nan(raw_reference, run_preprocessing):
    """The neural_eeg_features 0.6.1 band-bins section holds spectral_power and
    spectral_relative_power only. In the STORED data, the bins change only
    where NaN samples were removed from an epoch (the periodogram is then
    shortened and band edges can fall between bins). Clean recording: every
    value equals the original's exactly (its only NaN is the padding of the
    final epoch, 44 s of data: 2816 samples, 44 bins per Hz, so the default
    band edges stay on bins). Artefacts recording: each of the two features
    changes, and only in channel-epochs that contain NaN. This checks the
    stored data only (tests/test_band_bins.py checks the rule)."""
    import numpy as np

    for case in CASES:
        section = raw_reference[case][neural_outputs.BAND_BINS_SECTION]
        assert list(section["features"]) == list(neural_outputs.BAND_BINS_FEATURES)
        has_nan = epochs_with_nan(run_preprocessing(case)[0])
        for feature in neural_outputs.BAND_BINS_FEATURES:
            fixed_all = section["features"][feature]
            original_all = raw_reference[case]["features"][feature]
            for output in ("feats_median_all", "feat_st", "feats_median_ch", "feats_per_epochs"):
                fixed = neural_outputs.to_array(fixed_all[output])
                original = neural_outputs.to_array(original_all[output])
                assert np.array_equal(np.isnan(fixed), np.isnan(original)), (case, feature, output)
            fixed = neural_outputs.to_array(fixed_all["feats_per_epochs"])
            original = neural_outputs.to_array(original_all["feats_per_epochs"])
            assert fixed.shape[:2] == has_nan.shape, (case, feature)
            changed = ~((fixed == original) | (np.isnan(fixed) & np.isnan(original)))  # [channel][epoch][band]
            changed_epochs = changed.any(axis=2)
            assert not np.any(changed_epochs & ~has_nan), "%s %s changed in an epoch without NaN" % (case, feature)
            if case == "clean":
                assert has_nan.any(axis=0).tolist() == [False] * (has_nan.shape[1] - 1) + [True]  # final epoch only
                assert not changed.any()
                for output in ("feats_median_all", "feat_st", "feats_median_ch"):
                    assert np.array_equal(neural_outputs.to_array(fixed_all[output]),
                                          neural_outputs.to_array(original_all[output]), equal_nan=True)
            else:
                assert changed_epochs.any(), "%s: %s does not change" % (case, feature)


@pytest.mark.parametrize("case", CASES)
def test_input_edf_is_byte_identical(case, reference):
    """The synthetic EDF made now is exactly the file the reference was made from."""
    assert synthetic_edf.sha256(synthetic_edf.make_edf(case)) == reference[case]["input"]["sha256"]


@pytest.mark.parametrize("case", CASES)
def test_artefact_report_matches(case, run_preprocessing, reference):
    """NEURAL's artefact report: same channels removed, same % removed by each check."""
    report = neural_outputs.artefact_report(run_preprocessing(case)[1])
    expected = reference[case]["artefact_report"]
    assert report["channels_removed"] == expected["channels_removed"]
    new, old = report["percent_removed_worst_channel"], expected["percent_removed_worst_channel"]
    assert list(new) == list(old)
    neural_outputs.compare(list(new.values()), list(old.values()), case, "artefact report",
                           "percent removed")


@pytest.mark.parametrize("case", CASES)
def test_preprocessed_eeg_matches(case, run_preprocessing, reference):
    """The preprocessed EEG (artefacts removed, filtered, 64 Hz): same channels,
    same NaN stretches, same statistics and samples."""
    summary = neural_outputs.preprocessed_summary(run_preprocessing(case)[0])
    expected = reference[case]["preprocessed"]
    for key in ("Fs", "ch_labels", "n_samples"):
        assert summary[key] == expected[key]
    for channel, values in summary["channels"].items():
        old = expected["channels"][channel]
        assert values["nan_count"] == old["nan_count"], channel
        assert values["nan_runs"] == old["nan_runs"], channel
        for key in ("mean", "std", "min", "max", "every_500th_sample"):
            neural_outputs.compare(values[key], old[key], case, "preprocessed EEG", f"{channel} {key}")


@pytest.mark.parametrize("group", neural_outputs.GROUPS)
@pytest.mark.parametrize("case", CASES)
def test_feature_group_matches(case, group, run_preprocessing, reference):
    """Each feature of one group, computed on its own: every output matches,
    including the per-channel values."""
    data = run_preprocessing(case)[0]
    features = [f for f in neural_outputs.non_ibi_features() if neural_outputs.feature_group(f) == group]
    assert features
    for feature in features:
        new = neural_outputs.compute_features(data, [feature], neural_outputs.original_settings())[feature]
        if group != "connectivity":
            assert "feats_per_epochs" in new
        neural_outputs.compare_feature(new, reference[case]["features"][feature], case, group, feature)


@pytest.mark.parametrize("case", CASES)
def test_all_features_in_one_call_match(case, run_preprocessing, reference):
    """All 19 non-IBI features in one generate_all_features call (the usual way)."""
    data = run_preprocessing(case)[0]
    results = neural_outputs.compute_features(data, neural_outputs.non_ibi_features(),
                                              neural_outputs.original_settings())
    for feature, new in results.items():
        neural_outputs.compare_feature(new, reference[case]["features"][feature], case,
                                       "all 19 in one call", feature)
