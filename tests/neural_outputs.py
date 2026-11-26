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
    """NEURAL's list of all features, without the IBI ones: 26 in the original
    NEURAL (which made the reference files), 19 in this repository."""
    from NEURAL_py_EEG import NEURAL_parameters

    return [feature for feature in NEURAL_parameters.NEURAL_parameters()["FEATURE_SET_ALL"]
            if feature_group(feature) != "IBI"]


# ---------------------------------------------------------------------------
# Features removed to match neural_eeg_features 0.6.1
# ---------------------------------------------------------------------------
# The reference files (made by the original NEURAL) still hold these 7
# features; this repository no longer computes them, so the tests drop them
# from the reference values they load (without_removed_features). Written out
# here, not read from NEURAL, so that make_reference.py and the tests do not
# depend on the code under test for this list.
REMOVED_FEATURES = (
    "amplitude_total_power",
    "amplitude_SD",
    "rEEG_mean",
    "rEEG_width",
    "rEEG_SD",
    "connectivity_coh_max",
    "connectivity_coh_freqmax",
)


def original_settings():
    """The settings of the original NEURAL (commit 78c9425), written out here
    as its NEURAL_parameters() makes them, not read from this repository's
    NEURAL. The reference files in tests/data were made with these settings
    (the original's defaults), so the tests pass them to this repository's
    generate_all_features (params) and feature functions explicitly: the
    comparisons stay at the original settings when this repository's
    defaults change to those of neural_eeg_features 0.6.1.

    One difference: FEATURE_SET_ALL leaves out the 7 REMOVED_FEATURES (the
    original lists 30 names, this repository accepts 23). Each call returns a
    new dictionary. Like the original, the four groups' 'freq_bands' are the
    same list as FREQ_BANDS."""
    params = dict()
    params['LP_fc'] = 30
    params['Fs_new'] = 64
    params['EEG_DATA_DIR'] = ''
    params['EEG_DATA_DIR_CSV'] = ''
    params['BI_MONT'] = [['F4', 'C4'], ['F3', 'C3'], ['C4', 'T4'], ['C3', 'T3'], ['C4', 'Cz'], ['Cz', 'C3'],
                         ['C4', 'O2'], ['C3', 'O1']]
    params['REMOVE_ART'] = 1
    params['ART_HIGH_VOLT'] = 1500
    params['ART_TIME_COLLAR'] = 10
    params['ART_DIFF_VOLT'] = 200
    params['ART_DIFF_TIME_COLLAR'] = 0.5
    params['ART_DIFF_MIN_TIME'] = 0.1
    params['ART_ELEC_CHECK'] = 1
    params['ART_REF_LOW_CORR'] = 0.15
    params['FILTER_REPLACE_ARTEFACTS'] = 'nans'
    for group in ('amplitude', 'rEEG', 'connectivity', 'FD'):
        params[group] = {'FILTER_REPLACE_ARTEFACTS': params['FILTER_REPLACE_ARTEFACTS']}
    params['FEATURE_SET_ALL'] = [name for name in ORIGINAL_FEATURE_SET_ALL if name not in REMOVED_FEATURES]
    params['FREQ_BANDS'] = [[0.5, 4], [4, 7], [7, 13], [13, 30]]
    params['spectral'] = dict()
    params['spectral']['method'] = 'PSD'
    params['spectral']['L_window'] = 2
    params['spectral']['window_type'] = 'hamm'
    params['spectral']['overlap'] = 50
    params['spectral']['freq_bands'] = params['FREQ_BANDS']
    params['spectral']['total_freq_bands'] = [params['FREQ_BANDS'][0][0], params['FREQ_BANDS'][-1][-1]]
    params['spectral']['SEF'] = 0.95
    params['FD']['method'] = 'higuchi'
    params['FD']['freq_bands'] = [params['FREQ_BANDS'][0][0], params['FREQ_BANDS'][-1][-1]]
    params['FD']['qmax'] = 6
    params['amplitude']['freq_bands'] = params['FREQ_BANDS']
    params['rEEG']['L_window'] = 2
    params['rEEG']['window_type'] = 'rect'
    params['rEEG']['overlap'] = 0
    params['rEEG']['APPLY_LOG_LINEAR_SCALE'] = 0
    params['rEEG']['freq_bands'] = params['FREQ_BANDS']
    params['connectivity']['method'] = 'bartlett-PSD'
    params['connectivity']['freq_bands'] = params['FREQ_BANDS']
    params['connectivity']['L_window'] = 8
    params['connectivity']['overlap'] = 75
    params['connectivity']['window_type'] = 'hamm'
    params['connectivity']['coherence_zero_level'] = 'analytic'
    params['connectivity']['coherence_zero_alpha'] = 0.05
    params['connectivity']['coherence_surr_iter'] = 500
    params['EPOCH_LENGTH'] = 64
    params['EPOCH_OVERLAP'] = 50
    params['EPOCH_IGNORE_PRC_NANS'] = 50
    return params


# The original's FEATURE_SET_ALL (commit 78c9425), in its order: 30 names.
ORIGINAL_FEATURE_SET_ALL = (
    "spectral_power", "spectral_relative_power", "spectral_flatness", "spectral_diff", "spectral_entropy",
    "spectral_edge_frequency", "FD", "amplitude_total_power", "amplitude_SD", "amplitude_skew",
    "amplitude_kurtosis", "amplitude_env_mean", "amplitude_env_SD", "connectivity_BSI", "connectivity_corr",
    "connectivity_coh_mean", "connectivity_coh_max", "connectivity_coh_freqmax", "rEEG_mean", "rEEG_median",
    "rEEG_lower_margin", "rEEG_upper_margin", "rEEG_width", "rEEG_SD", "rEEG_CV", "rEEG_asymmetry",
    "IBI_length_max", "IBI_length_median", "IBI_burst_prc", "IBI_burst_number",
)


def is_removed_feature(key):
    """True for a removed feature's name, or a key that starts with it and a
    comma (e.g. "rEEG_SD, tuke window")."""
    return any(key == name or key.startswith(name + ",") for name in REMOVED_FEATURES)


def without_removed_features(tree):
    """A copy of tree (reference values as loaded from JSON) without the
    dictionary entries of the removed features, at any depth."""
    if isinstance(tree, dict):
        return {key: without_removed_features(value) for key, value in tree.items()
                if not is_removed_feature(key)}
    if isinstance(tree, list):
        return [without_removed_features(item) for item in tree]
    return tree


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


def compute_features(data_dict, features, params=None):
    """One call of NEURAL's generate_all_features for the given features, with
    the settings params (this repository's generate_all_features(...,
    params=params)); params=None makes the call without it, as
    make_reference.py does for the original NEURAL, which has no params and
    uses its own defaults (original_settings). Returns NEURAL's outputs split
    per feature:
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
    settings = {} if params is None else {"params": params}
    per_epochs, names, feat_st, median_ch, median_all = generate_all_features.generate_all_features(
        data, feat_set=list(features), **settings
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


# ---------------------------------------------------------------------------
# Fixes after the original: values of the original plus one fix
# ---------------------------------------------------------------------------
# Some features of this repository deliberately differ from the original.
# For each such fix, make_reference.py also runs the original NEURAL with only
# that fix applied (in memory) and stores the fixed features' values in each
# reference file, in a section of their own, at the same places as in the rest
# of the file. The tests compare those features with their fix section and
# every other output with the original's (with_fixes).
#
# spectral_diff: the one-line fix of MATLAB commit a279ddd (2020-04-23);
# tests/test_spectral_diff_fix.py checks that the fixed spectral_diff is right.
FIXED_FEATURE = "spectral_diff"
FIX_SECTION = "with_matlab_fix_a279ddd"

# amplitude_skew and amplitude_kurtosis: the bias-corrected definitions of
# neural_eeg_features 0.6.1; tests/test_amplitude_moments.py checks them.
MOMENTS_FEATURES = ("amplitude_skew", "amplitude_kurtosis")
MOMENTS_SECTION = "with_neural_eeg_features_0.6.1_moments"

# spectral_power and spectral_relative_power: the band-bin rule of
# neural_eeg_features 0.6.1 (each band an independent closed interval);
# tests/test_band_bins.py checks it. Only these two features: the other
# features that select bins by band (spectral_flatness, spectral_entropy,
# spectral_diff, spectral_edge_frequency, connectivity_BSI,
# connectivity_coh_mean) get the same bins under both rules for every
# stored input (test_band_bins.py checks this too).
BAND_BINS_FEATURES = ("spectral_power", "spectral_relative_power")
BAND_BINS_SECTION = "with_neural_eeg_features_0.6.1_band_bins"

# All 19 non-IBI features of this repository: complete epochs only, as in
# neural_eeg_features 0.6.1 (no NaN-padded final epoch); tests/
# test_complete_epochs.py checks the rule. This section is made with all the
# fixes above applied too, so for these features it replaces their sections.
# It covers only generate_all_features outputs (COMPLETE_EPOCHS_KEYS): the
# windows file computes its features on one 64 s array, without epochs.
COMPLETE_EPOCHS_FEATURES = (
    "spectral_power", "spectral_relative_power", "spectral_flatness", "spectral_diff",
    "spectral_entropy", "spectral_edge_frequency", "FD", "amplitude_skew", "amplitude_kurtosis",
    "amplitude_env_mean", "amplitude_env_SD", "connectivity_BSI", "connectivity_corr",
    "connectivity_coh_mean", "rEEG_median", "rEEG_lower_margin", "rEEG_upper_margin", "rEEG_CV",
    "rEEG_asymmetry",
)
COMPLETE_EPOCHS_SECTION = "with_neural_eeg_features_0.6.1_complete_epochs"
COMPLETE_EPOCHS_KEYS = ("features", "nan_input", "inf_line", "index_types")

# (section, features it holds, top-level keys of the reference it covers or
# None for all), in the order with_fixes applies them.
FIXES = (
    (FIX_SECTION, (FIXED_FEATURE,), None),
    (MOMENTS_SECTION, MOMENTS_FEATURES, None),
    (BAND_BINS_SECTION, BAND_BINS_FEATURES, None),
    (COMPLETE_EPOCHS_SECTION, COMPLETE_EPOCHS_FEATURES, COMPLETE_EPOCHS_KEYS),
)


def feature_places(tree, features, path=()):
    """Paths of the dictionary keys that name one of features (e.g.
    "spectral_diff", or "spectral_diff, tuke window")."""
    for key, value in tree.items():
        if any(key == feature or key.startswith(feature + ",") for feature in features):
            yield path + (key,)
        elif isinstance(value, dict):
            for found in feature_places(value, features, path + (key,)):
                yield found


def get(tree, path):
    for key in path:
        tree = tree[key]
    return tree


def only_features(tree, features):
    """The entries of tree for features, at the same places, and nothing else."""
    result = {}
    for path in feature_places(tree, features):
        node = result
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = get(tree, path)
    return result


def check_fix_not_lower(new, old, where):
    """Sanity check of the stored spectral_diff values: the fix removes a 0
    from a median of values >= 0, so no value can fall; NaN stays NaN, and a
    new NaN only replaces a 0 (no window-to-window difference)."""
    if isinstance(old, dict):
        for key in old:
            check_fix_not_lower(new[key], old[key], "%s %s" % (where, key))
    elif not _exact(old):
        a, b = np.atleast_1d(to_array(new)), np.atleast_1d(to_array(old))
        finite = np.isfinite(a) & np.isfinite(b)
        new_nan = np.isnan(a) & ~np.isnan(b)
        assert (a.shape == b.shape and np.all(a[finite] >= b[finite] - ATOL - RTOL * np.abs(b[finite]))
                and np.all(np.isnan(a[np.isnan(b)])) and np.all(b[new_nan] == 0)),             "%s: the values with the MATLAB fix are lower than the original's" % where


def with_fixes(reference):
    """The reference as the tests use it: each fixed feature's values from its
    fix section (FIXES, applied in order, so a later section replaces an
    earlier one at the same place), all other values the original's. A file
    without a fix section must also have none of its features within the
    section's top-level keys (reference_windows.json has no amplitude
    features, so it has no moments section; it has no generate_all_features
    outputs, so it has no complete-epochs section)."""
    reference = copy.deepcopy(reference)
    # Take all sections out first, so that no section counts as reference places.
    sections = [(section, features, keys, reference.pop(section, None)) for section, features, keys in FIXES]
    for section, features, keys, fixed in sections:
        scope = reference if keys is None else dict((key, reference[key]) for key in keys if key in reference)
        places = sorted(feature_places(scope, features))
        if fixed is None:
            assert not places, "no %s section, but the reference has %s" % (section, ", ".join(features))
            continue
        assert places == sorted(feature_places(fixed, features)), "%s does not match the reference" % section
        for path in places:
            if section == FIX_SECTION:
                check_fix_not_lower(get(fixed, path), get(reference, path), " ".join(path))
            get(reference, path[:-1])[path[-1]] = get(fixed, path)
    return reference


def compare_feature(new, reference, case, group, feature):
    """Compare all of NEURAL's outputs for one feature with the reference."""
    assert new["columns"] == reference["columns"], f"{case} / {feature}: different column names"
    for output in ("feats_median_all", "feat_st", "feats_median_ch"):
        compare(new[output], reference[output], case, group, f"{feature} {output}")
    if "feats_per_epochs" in new:
        assert "feats_per_epochs" in reference, f"{case} / {feature}: no per-channel reference values"
        compare(new["feats_per_epochs"], reference["feats_per_epochs"], case, group,
                f"{feature} feats_per_epochs")
