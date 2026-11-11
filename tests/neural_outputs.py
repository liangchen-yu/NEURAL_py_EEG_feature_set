"""Run NEURAL on a synthetic EDF file, collect the numbers it produces, and
compare them with saved reference numbers.

make_reference.py (with the original NEURAL) and the tests (with this
repository's NEURAL) both use this file, so both collect the numbers in
exactly the same way.
"""
import copy
import json
import math

import numpy as np

# Strict tolerance. A new value a matches its reference value b if
#     |a - b| <= ATOL + RTOL * |b|
# and NaN ("not a number") must be NaN in both.
RTOL = 1e-9
ATOL = 1e-12

# NEURAL's feature groups. IBI (burst) features are not tested: they need a
# separate burst detector.
GROUPS = ("spectral", "amplitude", "connectivity", "rEEG", "FD")

# The four checks in preprocessing_EEG.art_per_channel, in NEURAL's order.
ARTEFACT_CHECKS = ("flat_zeros", "high_amplitude", "constant_values", "sudden_jumps")

# Every comparison made by compare(), for the summary printed after the tests.
RESULTS = []


def feature_group(feature):
    """NEURAL's own rule: the group is the part of the name before the first '_'."""
    return feature.split("_")[0]


def non_ibi_features():
    """NEURAL's list of all features, without the IBI ones (26 features)."""
    from NEURAL_py_EEG import NEURAL_parameters

    return [feature for feature in NEURAL_parameters.NEURAL_parameters()["FEATURE_SET_ALL"]
            if feature_group(feature) != "IBI"]


# ---------------------------------------------------------------------------
# Running NEURAL
# ---------------------------------------------------------------------------
def preprocess(edf_path):
    """NEURAL's EDF preprocessing (preprocessing_EEG.main_preprocessing): read
    the EDF, make the bipolar montage, remove artefacts, low-pass filter and
    downsample to 64 Hz. Returns NEURAL's two outputs:
    (data dictionary, artefact report)."""
    import mne
    from NEURAL_py_EEG import preprocessing_EEG

    with mne.utils.use_log_level("WARNING"):  # only hides mne's progress messages
        return preprocessing_EEG.main_preprocessing(str(edf_path))


def artefact_report(amount_removed):
    """NEURAL's artefact report as plain values: for each of its four checks,
    the % of samples removed in the worst channel; and the bipolar channels it
    removed completely (NEURAL gives the text 'None removed' if there are none)."""
    channels = amount_removed[4]
    return {
        "percent_removed_worst_channel": {
            check: float(value) for check, value in zip(ARTEFACT_CHECKS, amount_removed[:4])
        },
        "channels_removed": channels if isinstance(channels, str) else [str(c) for c in channels],
    }


def nan_runs(is_nan):
    """Where the NaN stretches are: a list of [first, last + 1] sample indices."""
    edges = np.diff(np.concatenate([[0], is_nan.astype(np.int8), [0]]))
    return [[int(a), int(b)] for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))]


def preprocessed_summary(data_dict):
    """A fingerprint of the preprocessed EEG (bipolar, 64 Hz): per channel,
    where it is NaN (removed as artefact), a few statistics, and every 500th sample."""
    eeg = data_dict["eeg_data"]
    channels = {}
    for name in eeg.columns:
        x = np.array(eeg[name], dtype=float)  # a copy; NEURAL's data are not touched
        is_nan = np.isnan(x)
        valid = x[~is_nan]
        channels[str(name)] = {
            "nan_count": int(is_nan.sum()),
            "nan_runs": nan_runs(is_nan),
            "mean": valid.mean() if valid.size else math.nan,
            "std": valid.std() if valid.size else math.nan,
            "min": valid.min() if valid.size else math.nan,
            "max": valid.max() if valid.size else math.nan,
            "every_500th_sample": x[::500],
        }
    return {
        "Fs": data_dict["Fs"],
        "ch_labels": [str(c) for c in data_dict["ch_labels"]],
        "n_samples": len(eeg),
        "channels": channels,
    }


def compute_features(data_dict, features):
    """One call of NEURAL's generate_all_features for the given features.
    Returns NEURAL's outputs split per feature:
      columns           NEURAL's column names, one per frequency band
      feats_median_all  median over channels and epochs (the usual summary)
      feat_st           NEURAL's feat_st dictionary entry (also a summary)
      feats_median_ch   per epoch, the median over channels [epochs][bands]
                        (connectivity: the value per epoch)
      feats_per_epochs  per channel and epoch [channels][epochs][bands]; NEURAL
                        returns this only for the last per-channel feature it
                        computed, and never for connectivity features, which
                        compare pairs of channels.
    """
    from NEURAL_py_EEG import generate_all_features

    data = copy.deepcopy(data_dict)  # every call starts from the same data
    per_epochs, names, feat_st, median_ch, median_all = generate_all_features.generate_all_features(
        data, feat_set=list(features)
    )
    result = {}
    for feature in features:
        columns = [name for name in names if name.startswith(feature + "__")]
        result[feature] = {
            "columns": columns,
            "feats_median_all": median_all[columns].to_numpy(dtype=float)[0],
            "feat_st": np.atleast_1d(np.asarray(feat_st[feature], dtype=float)),
            "feats_median_ch": median_ch[columns].to_numpy(dtype=float),
        }
    per_channel_features = [f for f in features if feature_group(f) != "connectivity"]
    if per_channel_features:
        result[per_channel_features[-1]]["feats_per_epochs"] = np.asarray(per_epochs, dtype=float)
    return result


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------
def to_json(value):
    """Turn NEURAL's outputs into JSON values: arrays become lists, NaN becomes
    null (JSON has no NaN), infinity becomes "inf" or "-inf"."""
    if isinstance(value, dict):
        return {str(key): to_json(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return to_json(value.tolist())
    if isinstance(value, (list, tuple)):
        return [to_json(item) for item in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        value = float(value)
        if math.isnan(value):
            return None
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return value
    return value


def to_array(value):
    """The reverse of to_json for numbers: nested lists -> numpy array of floats."""
    def convert(item):
        if isinstance(item, list):
            return [convert(x) for x in item]
        if item is None:
            return math.nan
        return float(item)  # also turns "inf" / "-inf" back into infinity

    return np.array(convert(to_json(value)), dtype=float)


def dumps(value, indent=""):
    """JSON text with one dictionary key per line and each innermost list of
    numbers on one line. Numbers are written in full (Python's shortest exact
    form), so reading the file back gives exactly the same numbers."""
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = indent + "  "
        lines = [f"{inner}{json.dumps(key)}: {dumps(item, inner)}" for key, item in value.items()]
        return "{\n" + ",\n".join(lines) + "\n" + indent + "}"
    if isinstance(value, list) and any(isinstance(item, (list, dict)) for item in value):
        inner = indent + "  "
        return "[\n" + ",\n".join(inner + dumps(item, inner) for item in value) + "\n" + indent + "]"
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


# ---------------------------------------------------------------------------
# Comparing with the reference
# ---------------------------------------------------------------------------
def compare(new, reference, case, group, what):
    """Compare new numbers with reference numbers (same shape, NaN in the same
    places, every value within the tolerance). Records the largest
    differences for the summary and raises AssertionError on a mismatch."""
    a = np.atleast_1d(to_array(new))  # a single number becomes a list of one
    b = np.atleast_1d(to_array(reference))
    if a.shape != b.shape:
        raise AssertionError(f"{case} / {what}: shape {a.shape}, reference has {b.shape}")

    close = np.isclose(a, b, rtol=RTOL, atol=ATOL, equal_nan=True)
    finite = np.isfinite(a) & np.isfinite(b)
    abs_diff = np.abs(a - b)[finite]
    nonzero = np.abs(b[finite]) > 0
    largest_abs = float(abs_diff.max()) if abs_diff.size else 0.0
    largest_rel = float((abs_diff[nonzero] / np.abs(b[finite][nonzero])).max()) if nonzero.any() else 0.0
    RESULTS.append({
        "case": case, "group": group, "what": what, "values": int(a.size),
        "nan_places": int(np.isnan(b).sum()), "largest_abs": largest_abs,
        "largest_rel": largest_rel, "outside_tolerance": int((~close).sum()),
    })

    if not close.all():
        gap = np.abs(a - b)
        gap[np.isnan(gap)] = np.inf  # NaN in only one of the two: the worst kind
        gap[close] = -1.0  # ignore the values that match
        worst = np.unravel_index(np.argmax(gap), a.shape)
        raise AssertionError(
            f"{case} / {what}: {int((~close).sum())} of {a.size} values differ from the reference "
            f"(rtol={RTOL}, atol={ATOL}); e.g. at {tuple(int(i) for i in worst)}: "
            f"new {float(a[worst])!r}, reference {float(b[worst])!r}. NaN in new: {int(np.isnan(a).sum())}, "
            f"in reference: {int(np.isnan(b).sum())}."
        )
    return largest_abs, largest_rel


def _exact(value):
    """Text, true/false and whole numbers (and lists of only those) must match exactly."""
    if isinstance(value, list):
        return all(_exact(item) for item in value)
    return isinstance(value, (str, bool, int))


def compare_tree(new, reference, case, group, where=""):
    """Compare nested JSON values (as from to_json): text, true/false and
    whole numbers must be equal; decimal numbers are compared with compare()."""
    if isinstance(reference, dict):
        assert isinstance(new, dict) and sorted(new) == sorted(reference), (
            "%s / %s: different entries %s vs reference %s" % (case, where, sorted(new), sorted(reference)))
        for key in reference:
            compare_tree(new[key], reference[key], case, group, (where + " " + key).strip())
    elif isinstance(reference, list) and any(isinstance(item, dict) for item in reference):
        assert isinstance(new, list) and len(new) == len(reference), "%s / %s: different length" % (case, where)
        for i, (item, reference_item) in enumerate(zip(new, reference)):
            compare_tree(item, reference_item, case, group, "%s [%d]" % (where, i))
    elif _exact(reference):
        assert new == reference, "%s / %s: %r, reference %r" % (case, where, new, reference)
    else:
        compare(new, reference, case, group, where)


def compare_feature(new, reference, case, group, feature):
    """Compare all of NEURAL's outputs for one feature with the reference."""
    assert new["columns"] == reference["columns"], f"{case} / {feature}: different column names"
    for output in ("feats_median_all", "feat_st", "feats_median_ch"):
        compare(new[output], reference[output], case, group, f"{feature} {output}")
    if "feats_per_epochs" in new:
        assert "feats_per_epochs" in reference, f"{case} / {feature}: no per-channel reference values"
        compare(new["feats_per_epochs"], reference["feats_per_epochs"], case, group,
                f"{feature} feats_per_epochs")
