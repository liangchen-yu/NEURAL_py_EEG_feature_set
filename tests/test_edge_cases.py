"""Regression tests for the edge cases fixed in this fork: inputs an EDF file
cannot hold (pre-existing NaN, +/-inf), the EDF export, other kinds of row
index, read-only arrays, and the window types SciPy removed. Each compares
this repository's NEURAL with reference values made by the ORIGINAL NEURAL
(commit 78c9425):

  tests/data/reference_edge_cases.json  original NEURAL with pandas 2.3.3
  tests/data/reference_input_types.json original NEURAL with pandas 2.3.3
  tests/data/reference_windows.json     original NEURAL in Brian Murphy's 2020
                                        environment (SciPy 1.3.1, which still
                                        had these window functions)

The inputs and steps are in tests/edge_cases.py; tests/make_reference.py
made the reference files.
"""
import json
from pathlib import Path

import pytest

import edge_cases
import neural_outputs

DATA = Path(__file__).parent / "data"
ORIGINAL_COMMIT = "78c94258e4a3e6504e469f418443c78926e1a6be"

# NEURAL's numpy maths on NaN and infinity gives RuntimeWarnings such as
# "Mean of empty slice" or "invalid value encountered"; the original gives
# the same ones. They are expected here, so they are not shown.
pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def edge():
    return load("reference_edge_cases.json")


@pytest.fixture(scope="module")
def windows():
    return load("reference_windows.json")


@pytest.fixture(scope="module")
def input_types():
    return load("reference_input_types.json")


def check(new, reference, group, case="edge cases"):
    neural_outputs.compare_tree(neural_outputs.to_json(new), reference, case, group)


def test_edge_references_come_from_the_original_neural(edge, windows, input_types):
    for reference in (edge, windows, input_types):
        made_with = reference["made_with"]
        assert made_with["neural_commit"] == ORIGINAL_COMMIT
        assert made_with["neural_sha256_verified"] is True
        assert made_with["neural_has_pandas3_fix"] is False
    assert edge["made_with"]["pandas"] == "2.3.3"
    assert input_types["made_with"]["pandas"] == "2.3.3"
    assert windows["made_with"]["scipy"] == "1.3.1"


def test_index_types_match_original(input_types):
    """The same EEG with a datetime, text or integer row index, through
    generate_all_features, the preprocessing steps and overlap_epochs: the same
    results as the original with pandas 2.3.3, and the same errors where the
    original stopped (pandas 3 alone made the datetime and text cases fail)."""
    check(edge_cases.index_type_results(), input_types["index_types"], "index types")


def test_read_only_arrays_match_original(input_types):
    """gen_coherence with read-only arrays (as pandas 3 gives) returns the
    original's values and leaves its inputs unchanged."""
    new = edge_cases.read_only_results(read_only=True)
    assert new["inputs_unchanged"] is True
    check(new, input_types["read_only"], "read-only arrays")


def test_preexisting_nan_matches_original(edge):
    """NaN already in the data: the same cleaned EEG, artefact report and
    features, and the referential DataFrame filled in the same way."""
    check(edge_cases.nan_case_results(), edge["nan_input"], "pre-existing NaN")


def test_inf_line_matches_original(edge):
    """The line of remove_artefacts that turns +inf into NaN (and leaves -inf)."""
    check(edge_cases.inf_line_results(), edge["inf_line"], "+inf line")


def test_real_inf_input_fails_like_original(edge):
    """This real +/-inf input (runs of +inf and -inf in two electrodes): the
    original stops with an error in its filter, and so does this code (same
    error, same place). Not a fix; it documents that behaviour is unchanged."""
    assert edge_cases.inf_input_failure() == edge["inf_input"]


# NEURAL's default header uses physical minimum -5482.288 (9 characters); an
# EDF header field holds 8, so pyedflib warns and stores -5482.28, exactly as
# it does for the original. Expected, so not shown.
@pytest.mark.filterwarnings("ignore:Physical minimum:UserWarning")
def test_edf_export_matches_original(edge, tmp_path):
    """save_pd_as_edf, for both kinds of header: the written files hold the
    same digital samples and the same values in the checked header fields
    (label, unit, sample frequency, physical and digital range), and the
    caller's DataFrame is changed in the same way (NaN set to 0). It checks
    what pyedflib reads back, not the raw file bytes, which also hold the
    time the file was written."""
    check(edge_cases.export_results(tmp_path), edge["edf_export"], "EDF export")


def test_window_types_match_2020_original(windows):
    """Windows 'tuke', 'bart', 'blackmanharris' and every window-dependent
    feature computed with them, against the original in the 2020 environment."""
    new = edge_cases.window_results()
    # Each feature must really have used its window type (otherwise the
    # comparison would pass without testing anything).
    for name, entry in new["features"].items():
        assert entry["window_calls"] > 0, "%s did not use its window" % name
    assert len(new["features"]) == 3 * (len(edge_cases.SPECTRAL_WINDOW_FEATURES) + len(edge_cases.REEG_FEATURES) + 1)
    check(new, windows["windows"], "window types", case="2020 env.")
