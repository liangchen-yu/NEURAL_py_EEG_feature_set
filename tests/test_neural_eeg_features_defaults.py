"""This repository's NEURAL at its defaults against the reference package
neural_eeg_features 0.6.1 at its defaults, on the same synthetic inputs.

The reference values are in tests/data/reference_neural_eeg_features_0.6.1.json,
made once by tests/make_reference_neural_eeg_features.py with the reference
package (not needed here). The inputs are rebuilt (tests/neural_eeg_features_inputs.py)
and checked against the SHA-256 stored with the values.

Each feature is compared per input and level (summary; per channel; per
epoch, matched by start time), within the regression tolerance of
tests/neural_outputs.py. A comparison that cannot pass before a later change is
a strict expected failure naming that change (needs, DONE): when a change
lands, it is added to DONE, and its comparisons must then pass (a strict
expected failure that passes fails the run). Each comparison first requires
exactly the reference's bands as columns. Expected failures are limited to
AssertionError, so an error in NEURAL or in this test is not hidden; the one
known error of NEURAL on these inputs is matched exactly (KNOWN_FAILURES) and
expected only by its own comparisons.
"""
import contextlib
import copy
import hashlib
import io
import json
import traceback
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import make_reference_neural_eeg_features as generator
import neural_eeg_features_inputs as inputs
import neural_outputs
from NEURAL_py_EEG import NEURAL_parameters, connectivity_features, generate_all_features, utils

FIXTURE = Path(__file__).parent / "data" / generator.OUTPUT_NAME
REFERENCE = json.loads(FIXTURE.read_text(encoding="utf-8"))
RTOL, ATOL = neural_outputs.RTOL, neural_outputs.ATOL

# The changes, in order, after which this repository's defaults and
# conventions match the reference package's (docs/CHANGES_vs_neural_eeg_features_0.6.1.md).
CHANGES = {
    "3c": "3c (rEEG: its own 128 s / 50 % windows and the single 1-20 Hz band)",
    "3d": "3d (ordinary epochs of 16 s with 75 % overlap)",
    "3e": "3e (spectral windows: 4 s Blackman-Harris, 75 %, FFT length 4096)",
    "3f": "3f (connectivity: Welch PSD, 4 s Blackman-Harris windows, 75 %, FFT length 4096, analytic "
          "threshold from the actual window count)",
    "4": "step 4 (feature filters: whole-recording SOS band-pass)",
    "5": "step 5 (missing data: 20 % rule, NaN epochs and pairs)",
    "6": "step 6 (burst detector and IBI features)",
}
ORDER = list(CHANGES)
DONE = set()  # the changes made so far; each commit of step 3 and later adds its own


def needs(feature, case):
    """The changes this feature's comparison on this input needs."""
    group = feature.split("_")[0]
    if group == "IBI":
        return {"6"}
    if feature in ("spectral_power", "spectral_relative_power"):
        result = {"3d"}  # periodogram of the epoch: only the epochs
    elif group == "spectral":
        result = {"3d", "3e"}
    elif feature in ("connectivity_BSI", "connectivity_coh_mean"):
        result = {"3d", "3f"}
    elif group == "rEEG":
        # Its own windows; filtered signals. Not step 5, even with NaN: the
        # reference's rEEG bypasses the epoch NaN threshold, and these inputs'
        # NaN leave every 128 s window below NEURAL's 50 % (checked: 3c's
        # windows on the reference's whole-recording filter, with NEURAL's
        # rEEG code, match all 15 rEEG comparisons of each input).
        return {"3c", "4"}
    else:  # amplitude, FD, connectivity_corr: filtered signals within the epochs
        result = {"3d", "4"}
    if np.isnan(inputs.make_input(case)[0]).any():
        result.add("5")
    return result


class KnownExtractorFailure(Exception):
    """generate_all_features fails, in exactly the way listed in KNOWN_FAILURES."""


# (input, feature): (exception type, message, function and exception that
# cause it, the change that removes it). Only these errors become
# KnownExtractorFailure (an expected failure); any other error is an error.
KNOWN_FAILURES = {
    ("64 Hz with missing samples", "connectivity_coh_mean"): (
        ValueError, "Feature function not found: connectivity_coh_mean", "gen_cross_spectrum", ValueError,
        "operands could not be broadcast", "5"),
}


def known_failure(case, feature, error):
    """KnownExtractorFailure if error is exactly the known failure of
    (case, feature): NaN samples removed separately from the two channels of a
    pair leave them different numbers of windows (7 and 8), which
    gen_cross_spectrum cannot multiply; reported by main_connectivity as
    "Feature function not found". The reference package excludes a pair with
    NaN from that epoch (step 5)."""
    known = KNOWN_FAILURES.get((case, feature))
    if known is None:
        return None
    kind, message, function, cause_kind, cause_message, change = known
    cause = error.__context__
    if (type(error) is kind and str(error) == message and type(cause) is cause_kind
            and cause_message in str(cause) and function in [f.name for f in traceback.extract_tb(cause.__traceback__)]):
        return KnownExtractorFailure("%s on %s, until %s: %s (%s in %s: %s)"
                                     % (feature, case, CHANGES[change], error, cause_kind.__name__, function, cause))
    return None


LEVELS = ("summary", "per_channel", "epochs")


def cases():
    """(case, feature, level) for every comparison, with its expected-failure mark."""
    params = []
    for case, results in REFERENCE["results"].items():
        for feature, entry in results.items():
            for level in LEVELS:
                if level not in entry:
                    continue
                if level == "per_channel" and feature.startswith("IBI"):
                    continue  # NEURAL returns the IBI features' summary only (no per-channel values)
                remaining = sorted(needs(feature, case) - DONE, key=ORDER.index)
                # A comparison with a known extractor failure expects that failure
                # (KnownExtractorFailure, matched exactly) or, once an earlier change has
                # removed the crash, a mismatch (AssertionError), until its remaining
                # changes are DONE; any other exception is still an error.
                known = (case, feature) in KNOWN_FAILURES
                raises = (KnownExtractorFailure, AssertionError) if known else AssertionError
                marks = [pytest.mark.xfail(strict=True, raises=raises,
                                           reason="until " + CHANGES[remaining[-1]] + "; needs "
                                                  + ", ".join(remaining)
                                                  + ("; generate_all_features may fail (KNOWN_FAILURES)"
                                                     if known else ""))] if remaining else []
                params.append(pytest.param(case, feature, level, marks=marks, id="%s-%s-%s" % (case, feature, level)))
    return params


# ---------------------------------------------------------------------------
# The fixture itself
# ---------------------------------------------------------------------------
def test_fixture_provenance():
    made_with = REFERENCE["made_with"]
    assert made_with["package"] == "neural_eeg_features" and made_with["version"] == generator.VERSION == "0.6.1"
    assert made_with["module_sha256"] == generator.PINNED_SHA256
    script = Path(generator.__file__).read_bytes().replace(b"\r\n", b"\n")
    assert made_with["generator"] == "tests/make_reference_neural_eeg_features.py"
    assert made_with["generator_sha256"] == hashlib.sha256(script).hexdigest(), \
        "the generator changed since the fixture was made: remake it (see its header)"
    assert set(made_with) >= {"python", "os", "numpy", "scipy", "pandas", "numba"}


@pytest.mark.parametrize("case", list(inputs.CASES))
def test_inputs_are_the_stored_ones(case):
    """The rebuilt input is bit for bit the one the reference values were made from."""
    stored = REFERENCE["inputs"][case]
    rate, seconds, with_nan = inputs.CASES[case]
    x, rate = inputs.make_input(case)
    assert x.shape == (seconds * rate, len(inputs.CHANNELS))
    assert stored["sha256"] == inputs.sha256(x)
    assert (stored["sampling_rate_hz"], stored["seconds"], stored["channels"]) == (rate, seconds, inputs.CHANNELS)
    assert stored["seed"] == inputs.synthetic_edf.SEED
    assert [tuple(p) for p in stored["channel_pairs"]] == inputs.PAIRS
    assert bool(stored["nan_runs_seconds"]) == with_nan == bool(np.isnan(x).any())


def test_the_pairs_are_neural_s():
    """The reference package was given the left/right pairs NEURAL finds."""
    labels = np.array(inputs.CHANNELS)
    ipairs = connectivity_features.channel_hemisphere_pairs(labels)
    assert [(labels[a], labels[b]) for a, b in ipairs.T] == inputs.PAIRS


def test_fixture_settings_are_the_reference_defaults():
    """The settings the values were made with: the reference package's
    defaults (its docs/definitions.md, "Processing defaults")."""
    config = REFERENCE["config"]
    assert (config["epoch_seconds"], config["overlap_percent"], config["max_nan_percent"]) == (16, 75, 20)
    assert config["bands"] == {"delta": [0.5, 4], "theta": [4, 7], "alpha": [7, 13], "beta": [13, 30]}
    assert config["spectral"] == {"method": "psd", "window_seconds": 4, "overlap_percent": 75,
                                  "window": "blackmanharris", "n_fft": 4096, "edge_fraction": 0.95}
    assert config["connectivity"] == {"method": "psd", "window_seconds": 4, "overlap_percent": 75,
                                      "window": "blackmanharris", "n_fft": 4096, "threshold": "analytic",
                                      "alpha": 0.05, "surrogate_iterations": 500, "seed": 0}
    assert config["reeg_bands"] == {"narrow_wide": [1, 20]} and config["amplitude_bands"] is None
    assert config["reeg"] == {"window_seconds": 2, "overlap_percent": 0, "window": "rect", "log_linear": False,
                              "summary_seconds": 128, "summary_overlap_percent": 50}
    assert config["fractal"] == {"method": "higuchi", "k_max": 6, "bands": {"wide": [0.5, 30]}}
    for case, stored in REFERENCE["inputs"].items():
        expected = [f for f in NEURAL_parameters.SUPPORTED_FEATURES if case != "256 Hz" or not f.startswith("IBI")]
        assert stored["features"] == expected == list(REFERENCE["results"][case])


def test_done_lists_known_changes():
    assert DONE <= set(CHANGES)
    for (case, feature), known in KNOWN_FAILURES.items():
        assert feature in REFERENCE["results"][case] and known[-1] in CHANGES


# ---------------------------------------------------------------------------
# This repository's NEURAL at its defaults
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def neural():
    """generate_all_features at the defaults (params=None), one call per
    feature (feats_per_epochs holds only the last feature of a call). An
    error propagates, except a failure listed in KNOWN_FAILURES, which is
    raised as KnownExtractorFailure (each time it is asked for)."""
    computed = {}

    def get(case, feature):
        if (case, feature) not in computed:
            x, rate = inputs.make_input(case)
            data = {"eeg_data": pd.DataFrame(x, columns=inputs.CHANNELS), "Fs": rate,
                    "ch_labels": list(inputs.CHANNELS)}
            try:
                with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
                    warnings.simplefilter("ignore")
                    computed[case, feature] = generate_all_features.generate_all_features(
                        copy.deepcopy(data), feat_set=[feature])
            except Exception as error:
                known = known_failure(case, feature, error)
                if known is None:
                    raise
                computed[case, feature] = known
        if isinstance(computed[case, feature], KnownExtractorFailure):
            raise computed[case, feature]
        return computed[case, feature]

    return get


def column_names(feature, entry):
    """NEURAL's column for each of the reference's bands, in its order."""
    if entry["bands"] == {"none": None}:
        return [feature + "__05_30"]  # IBI: NEURAL names its single value after [0.5, 30]
    return [feature + "__" + generate_all_features.band_edge_label(low) + "_"
            + generate_all_features.band_edge_label(high) for low, high in entry["bands"].values()]


def epoch_rows(starts, rate):
    """The rows of NEURAL's per-epoch outputs (one per ordinary epoch) that
    start at the reference's epoch start times."""
    params = NEURAL_parameters.NEURAL_parameters()
    hop = utils.gen_epoch_window(params["EPOCH_OVERLAP"], params["EPOCH_LENGTH"], "rect", rate)[0]
    rows = [int(round(start * rate / hop)) for start in starts]
    assert all(abs(row * hop / rate - start) < 1e-9 for row, start in zip(rows, starts)), \
        "NEURAL has no epoch starting at the reference's start times %s (hop %s samples)" % (starts[:3], hop)
    return rows


def close(new, expected, what):
    new, expected = np.asarray(new, dtype=float), neural_outputs.to_array(expected)
    assert new.shape == expected.shape, "%s: shape %s, reference %s" % (what, new.shape, expected.shape)
    np.testing.assert_allclose(new, expected, rtol=RTOL, atol=ATOL, equal_nan=True, err_msg=what)


@pytest.mark.parametrize("case, feature, level", cases())
def test_matches_the_reference_package(case, feature, level, neural):
    entry = REFERENCE["results"][case][feature]
    per_epochs, names, feat_st, median_ch, median_all = neural(case, feature)
    columns = column_names(feature, entry)
    # First the complete set of bands: exactly the reference's, no more, no fewer.
    assert names == columns, "NEURAL's columns %s, the reference's bands %s" % (names, columns)
    bands = list(entry["bands"])
    band_index = [names.index(c) for c in columns]  # one feature per call: its bands in NEURAL's order

    if level == "summary":
        close(median_all[columns].to_numpy(dtype=float)[0], [entry["summary"][b] for b in bands], "summary")
        return

    rate = inputs.CASES[case][0]
    if level == "per_channel":
        values = np.asarray(per_epochs, dtype=float)
        assert values.ndim == 3 and values.shape[0] == len(inputs.CHANNELS), "per-channel values %s" % (values.shape,)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN channels
            per_channel = np.nanmedian(values, axis=1)  # NEURAL's median over epochs, per channel
        close(per_channel[:, band_index].T, [entry["per_channel"][b] for b in bands], "per channel")
        return

    epochs = entry["epochs"]
    rows = epoch_rows(epochs["start_seconds"], rate)
    if feature.startswith("connectivity"):
        values = median_ch[columns].to_numpy(dtype=float)  # [epoch][band]
        others = np.delete(values, rows, axis=0)
        close(values[rows].T, [epochs["values"][b] for b in bands], "per epoch")
        n_rows = values.shape[0]
    else:
        values = np.asarray(per_epochs, dtype=float)  # [channel][epoch][band]
        others = np.delete(values, rows, axis=1)
        close(np.moveaxis(values[:, rows][:, :, band_index], 2, 0), [epochs["values"][b] for b in bands], "per epoch")
        n_rows = values.shape[1]
    if epochs["duration_seconds"] == NEURAL_parameters.NEURAL_parameters()["EPOCH_LENGTH"]:
        assert n_rows == len(rows), "NEURAL has %d epochs, the reference %d" % (n_rows, len(rows))
    else:  # rEEG's own windows, in the rows of the ordinary epochs that start with them
        assert np.isnan(others).all(), "rows between the reference's windows must be NaN"
