"""Regression tests: this repository's NEURAL must give the same numbers as
the original NEURAL (commit 78c9425) on the same synthetic EDF files.

The reference numbers in tests/data/ were made by tests/make_reference.py
with the original NEURAL and pandas 2.3.3. Each test runs the code in this
repository on the same inputs and compares every number, with a strict
tolerance (see neural_outputs.RTOL and ATOL). Run with:  pytest
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


def test_reference_has_all_26_non_ibi_features(reference):
    features = neural_outputs.non_ibi_features()
    assert len(features) == 26
    assert {neural_outputs.feature_group(f) for f in features} == set(neural_outputs.GROUPS)
    for case in CASES:
        assert list(reference[case]["features"]) == features


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
        new = neural_outputs.compute_features(data, [feature])[feature]
        if group != "connectivity":
            assert "feats_per_epochs" in new
        neural_outputs.compare_feature(new, reference[case]["features"][feature], case, group, feature)


@pytest.mark.parametrize("case", CASES)
def test_all_features_in_one_call_match(case, run_preprocessing, reference):
    """All 26 features in one generate_all_features call (the usual way)."""
    data = run_preprocessing(case)[0]
    results = neural_outputs.compute_features(data, neural_outputs.non_ibi_features())
    for feature, new in results.items():
        neural_outputs.compare_feature(new, reference[case]["features"][feature], case,
                                       "all 26 in one call", feature)
