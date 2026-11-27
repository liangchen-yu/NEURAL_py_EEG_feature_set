"""generate_all_features(..., params): settings passed explicitly.

- params=None uses NEURAL_parameters(), exactly as before; passing
  NEURAL_parameters() itself gives the same outputs.
- Every setting that generate_all_features or a feature group reads comes
  from params: changing one changes the feature as the feature function,
  called directly with the same settings, says it should; an untouched
  NEURAL_parameters() still gives the defaults.
- params is not changed by a call, and calls with different params do not
  affect each other (each feature call gets its own copy of its group).
- params without the structure of NEURAL_parameters() (a key missing, an
  unknown key, a value of the wrong kind) raises ValueError naming the
  setting, before any feature is computed.
- neural_outputs.original_settings() (the original NEURAL's settings, which
  the regression tests pass) has that structure and, for now, equals the
  defaults.

Input: the deterministic synthetic EEG of synthetic_edf.py (tests/
edge_cases.py), 4 bipolar channels (2 left/right pairs), 128 s at 64 Hz.
"""
import contextlib
import copy
import inspect
import io
import warnings

import numpy as np
import pytest

import edge_cases
import neural_outputs
from NEURAL_py_EEG import (IBI_features, NEURAL_parameters, amplitude_features, connectivity_features,
                           fd_features, generate_all_features, rEEG, spectral_features)

FS = 64
CHANNELS = ["F3_C3", "F4_C4", "C3_O1", "C4_O2"]
MAIN = {"spectral": spectral_features.main_spectral, "amplitude": amplitude_features.main_amplitude,
        "rEEG": rEEG.main_rEEG, "FD": fd_features.main_fd}
PRISTINE_DEFAULTS = NEURAL_parameters.NEURAL_parameters()


def make_data(with_nan=False):
    bip = edge_cases.bipolar(edge_cases.referential(seconds=128))[CHANNELS].iloc[::4].reset_index(drop=True)
    if with_nan:
        bip.iloc[40 * FS:40 * FS + 100, 0] = np.nan  # 1.6 s in channel F3_C3: in the first two 64 s epochs
    return {"eeg_data": bip, "Fs": FS, "ch_labels": list(CHANNELS)}


DATA = make_data()
DATA_NAN = make_data(with_nan=True)


def run(feat_set, params=None, data=DATA):
    """generate_all_features; params=None makes the call without it."""
    settings = {} if params is None else {"params": params}
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore")
        return generate_all_features.generate_all_features(copy.deepcopy(data), feat_set=feat_set, **settings)


def assert_same_outputs(a, b):
    """All five outputs of generate_all_features exactly equal (NaN = NaN)."""
    per_a, names_a, st_a, ch_a, all_a = a
    per_b, names_b, st_b, ch_b, all_b = b
    assert np.array_equal(np.asarray(per_a), np.asarray(per_b), equal_nan=True)
    assert names_a == names_b
    assert list(st_a) == list(st_b)
    for key in st_a:
        assert np.array_equal(np.asarray(st_a[key]), np.asarray(st_b[key]), equal_nan=True), key
    for x, y in ((ch_a, ch_b), (all_a, all_b)):
        assert list(x.columns) == list(y.columns) and x.shape == y.shape
        assert np.array_equal(x.to_numpy(dtype=float), y.to_numpy(dtype=float), equal_nan=True)


def direct(feature, params, data=DATA):
    """The per-epoch values of one feature computed directly with its group's
    main_* function and the epochs of params, as generate_all_features does:
    [channel][epoch][band], or [epoch][band] for connectivity."""
    group = feature.split("_")[0]
    eeg = data["eeg_data"]
    epochs = [generate_all_features.overlap_epochs(eeg[c], FS, params["EPOCH_LENGTH"], params["EPOCH_OVERLAP"])
              for c in CHANNELS]
    n_bands = generate_all_features.size_feature(feature, params)

    def used(x):
        return 100 * np.count_nonzero(np.isnan(x)) / x.size < params["EPOCH_IGNORE_PRC_NANS"]

    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore")
        if group == "connectivity":
            result = np.full((len(epochs[0]), n_bands), np.nan)
            for e in range(len(epochs[0])):
                x = np.array([epochs[c][e] for c in range(len(CHANNELS))])
                if used(x):
                    result[e] = connectivity_features.main_connectivity(
                        x, FS, feature, np.array(CHANNELS), copy.deepcopy(params["connectivity"]))
            return result
        result = np.full((len(CHANNELS), len(epochs[0]), n_bands), np.nan)
        for c in range(len(CHANNELS)):
            for e, x in enumerate(epochs[c]):
                if used(x):
                    result[c, e] = MAIN[group](x, FS, feature, copy.deepcopy(params[group]))
        return result


def per_epoch_values(feature, out):
    """generate_all_features' per-epoch values in the layout of direct()."""
    per_epochs, names, feat_st, median_ch, median_all = out
    if feature.startswith("connectivity"):
        return median_ch[[n for n in names if n.startswith(feature + "__")]].to_numpy(dtype=float)
    return np.asarray(per_epochs, dtype=float)


# ---------------------------------------------------------------------------
# params=None and the defaults
# ---------------------------------------------------------------------------
def test_params_none_equals_explicit_defaults():
    features = neural_outputs.non_ibi_features()
    assert_same_outputs(run(features), run(features, NEURAL_parameters.NEURAL_parameters()))


def test_original_settings_are_the_current_defaults():
    """The settings written out in neural_outputs.original_settings() (those
    of the original NEURAL, commit 78c9425) equal this repository's
    defaults, and have their structure. When a default changes to that of
    neural_eeg_features 0.6.1, this test lists the change."""
    original = neural_outputs.original_settings()
    NEURAL_parameters.check_parameters(original)
    assert original == NEURAL_parameters.NEURAL_parameters()


# ---------------------------------------------------------------------------
# Every setting reaches its features
# ---------------------------------------------------------------------------
def change(**settings):
    """params = NEURAL_parameters() with settings changed: a key "group.name"
    is params[group][name], a key "name" is params[name]."""
    params = NEURAL_parameters.NEURAL_parameters()
    for key, value in settings.items():
        if "." in key:
            group, name = key.split(".")
            params[group][name] = value
        else:
            params[key] = value
    return params


TWO_BANDS = [[0.5, 4], [4, 30]]
# (feature, settings, data): each setting changes the feature's values
SETTINGS_CASES = [
    ("spectral_flatness", {"spectral.L_window": 4}, DATA),
    ("spectral_entropy", {"spectral.method": "robust-PSD"}, DATA),
    ("spectral_diff", {"spectral.overlap": 75}, DATA),
    ("spectral_diff", {"spectral.window_type": "hann"}, DATA),
    ("spectral_relative_power", {"spectral.total_freq_bands": [1, 25]}, DATA),
    ("spectral_edge_frequency", {"spectral.SEF": 0.8}, DATA),
    ("spectral_edge_frequency", {"spectral.total_freq_bands": [1, 25]}, DATA),
    ("spectral_power", {"spectral.freq_bands": TWO_BANDS}, DATA),
    ("amplitude_env_mean", {"amplitude.freq_bands": TWO_BANDS}, DATA),
    ("amplitude_skew", {"amplitude.FILTER_REPLACE_ARTEFACTS": "zeros"}, DATA_NAN),
    ("rEEG_median", {"rEEG.L_window": 4}, DATA),
    ("rEEG_CV", {"rEEG.overlap": 50}, DATA),
    ("rEEG_upper_margin", {"rEEG.window_type": "hann"}, DATA),
    ("rEEG_lower_margin", {"rEEG.freq_bands": TWO_BANDS}, DATA),
    ("rEEG_asymmetry", {"rEEG.FILTER_REPLACE_ARTEFACTS": "zeros"}, DATA_NAN),
    ("FD", {"FD.method": "katz"}, DATA),
    ("FD", {"FD.qmax": 10}, DATA),
    ("FD", {"FD.freq_bands": [1, 20]}, DATA),
    ("FD", {"FD.FILTER_REPLACE_ARTEFACTS": "zeros"}, DATA_NAN),
    ("connectivity_BSI", {"connectivity.method": "PSD"}, DATA),
    ("connectivity_BSI", {"connectivity.freq_bands": TWO_BANDS}, DATA),
    ("connectivity_coh_mean", {"connectivity.L_window": 4}, DATA),
    ("connectivity_coh_mean", {"connectivity.coherence_zero_alpha": 0.5}, DATA),
    ("connectivity_coh_mean", {"connectivity.freq_bands": TWO_BANDS}, DATA),
    ("connectivity_corr", {"connectivity.freq_bands": TWO_BANDS}, DATA),
    ("connectivity_corr", {"connectivity.FILTER_REPLACE_ARTEFACTS": "zeros"}, DATA_NAN),
    ("spectral_power", {"EPOCH_LENGTH": 32}, DATA),
    ("amplitude_env_SD", {"EPOCH_OVERLAP": 75}, DATA),
    ("connectivity_BSI", {"EPOCH_LENGTH": 32, "EPOCH_OVERLAP": 25}, DATA),
    ("spectral_entropy", {"EPOCH_IGNORE_PRC_NANS": 0.1}, DATA_NAN),
]


@pytest.mark.parametrize("feature, settings, data", SETTINGS_CASES,
                         ids=["%s %s" % (f, ",".join("%s=%s" % kv for kv in s.items())) for f, s, d in SETTINGS_CASES])
def test_setting_reaches_the_feature(feature, settings, data):
    params = change(**settings)
    out = run([feature], params, data)
    expected = direct(feature, params, data)
    new = per_epoch_values(feature, out)
    # The values follow the setting, exactly as the feature function computes them with it ...
    np.testing.assert_array_equal(new, expected)
    names = out[1]
    assert names == generate_all_features.get_feature_names(params, [feature])
    # ... and differ from those with the defaults.
    default = run([feature], None, data)
    old = per_epoch_values(feature, default)
    assert names != default[1] or new.shape != old.shape or not np.array_equal(new, old, equal_nan=True)
    # An untouched NEURAL_parameters() still gives the defaults.
    assert NEURAL_parameters.NEURAL_parameters() == PRISTINE_DEFAULTS


def test_surrogate_settings_reach_the_coherence(monkeypatch):
    """coherence_zero_level 'surr' and coherence_surr_iter reach
    connectivity_coh: it asks rand_phase for that many surrogates. The
    surrogate threshold then fails (see the next test)."""
    calls = []
    real = connectivity_features.rand_phase
    monkeypatch.setattr(connectivity_features, "rand_phase",
                        lambda x, N_iter=1: calls.append(N_iter) or real(x, N_iter))
    params = change(**{"connectivity.coherence_zero_level": "surr", "connectivity.coherence_surr_iter": 3})
    with pytest.raises(ValueError, match="Feature function not found: connectivity_coh_mean"):
        run(["connectivity_coh_mean"], params)
    assert calls == [3, 3]  # the two channels of the first pair, then the failure


@pytest.mark.parametrize("settings, error", [
    ({"connectivity.coherence_zero_level": "surr"}, IndexError),  # threshold of shape (1, N) as index
    ({"connectivity.coherence_zero_level": ""}, ValueError),  # compares .lower (no call) with ""
    ({"connectivity.method": "PSD"}, TypeError),  # warnings.warn given a list as its message
], ids=["surrogate threshold", "no threshold", "Welch PSD with the analytic threshold"])
def test_known_coherence_failures_are_unchanged(settings, error):
    """Three settings of connectivity_coh_mean fail in connectivity_coh,
    with the code of main_connectivity, which is unchanged here: reported as
    "Feature function not found", the error above being the cause. With the
    Welch PSD, connectivity_coh switches to Bartlett with a warning whose
    message is a list; Python's warnings registry cannot store it, which
    fails from the second such warning on (here: the second epoch). The
    defaults (analytic threshold, Bartlett PSD) do not reach these lines."""
    params = change(**settings)
    with pytest.raises(ValueError, match="Feature function not found: connectivity_coh_mean") as raised:
        run(["connectivity_coh_mean"], params)
    assert isinstance(raised.value.__context__, error)


def test_feature_set_all_is_read_from_params():
    """feat_set=None computes the features of params['FEATURE_SET_ALL'], and
    the columns follow its order (the default order has spectral_power
    first)."""
    power = ["spectral_power__05_4", "spectral_power__4_7", "spectral_power__7_13", "spectral_power__13_30"]
    params = change(FEATURE_SET_ALL=["FD", "spectral_power"])
    per_epochs, names, feat_st, median_ch, median_all = run(None, params)
    assert names == ["FD__05_30"] + power
    assert list(feat_st) == ["FD", "spectral_power"] and list(median_all.columns) == names
    assert run(["spectral_power", "FD"])[1] == power + ["FD__05_30"]


def test_ibi_reads_no_settings():
    """The IBI features take no settings (main_IBI has no params), so params
    leaves them unchanged."""
    assert "params" not in inspect.signature(IBI_features.main_IBI).parameters
    params = change(EPOCH_LENGTH=32, EPOCH_OVERLAP=75, **{"spectral.L_window": 4})
    data = {"eeg_data": DATA["eeg_data"][CHANNELS[:1]], "Fs": FS, "ch_labels": CHANNELS[:1]}
    new, old = run(["IBI_burst_prc"], params, data), run(["IBI_burst_prc"], None, data)
    # feat_st and feats_median_all hold the IBI values (feats_median_ch has a
    # row per epoch, so its number of rows follows the epoch settings; the IBI
    # columns are NaN there)
    assert new[1] == old[1] and np.array_equal(new[2]["IBI_burst_prc"], old[2]["IBI_burst_prc"], equal_nan=True)
    assert np.array_equal(new[4].to_numpy(dtype=float), old[4].to_numpy(dtype=float), equal_nan=True)


@pytest.mark.parametrize("setting", [{"connectivity.window_type": "hann"}, {"connectivity.overlap": 50}],
                         ids=["window type", "overlap"])
def test_connectivity_window_and_overlap_reach_bsi(setting):
    """With the Welch PSD, the window type and the overlap each change BSI on
    their own (compared with the Welch PSD and the other settings at their
    defaults), as the feature function says. With the default Bartlett PSD
    they have no effect: Bartlett means a rectangular window and no overlap."""
    welch = change(**{"connectivity.method": "PSD"})
    changed = change(**dict(setting, **{"connectivity.method": "PSD"}))
    new = per_epoch_values("connectivity_BSI", run(["connectivity_BSI"], changed))
    np.testing.assert_array_equal(new, direct("connectivity_BSI", changed))
    assert not np.array_equal(new, per_epoch_values("connectivity_BSI", run(["connectivity_BSI"], welch)))
    bartlett = per_epoch_values("connectivity_BSI", run(["connectivity_BSI"], change(**setting)))
    np.testing.assert_array_equal(bartlett, per_epoch_values("connectivity_BSI", run(["connectivity_BSI"])))


def test_log_linear_switch_reaches_rEEG(monkeypatch):
    """APPLY_LOG_LINEAR_SCALE reaches gen_rEEG, which every rEEG feature uses."""
    calls = []
    real = rEEG.gen_rEEG
    monkeypatch.setattr(rEEG, "gen_rEEG", lambda *args: calls.append(args[5]) or real(*args))
    run(["rEEG_median"], change(**{"rEEG.APPLY_LOG_LINEAR_SCALE": 1}))
    assert calls and set(calls) == {1}


@pytest.mark.xfail(strict=True, reason="gen_rEEG's log-linear scaling never changes a value: its condition is "
                                       "inverted ('if not ihigh', also in the original 78c9425)")
def test_log_linear_switch_changes_rEEG():
    """The switch should scale ranges above 50 to 50 * log(range) / log(50)
    (as the reference package's reeg.range_trace does); these signals have
    such ranges, so the values should change."""
    old = per_epoch_values("rEEG_upper_margin", run(["rEEG_upper_margin"]))
    assert np.nanmax(old) > 50
    new = per_epoch_values("rEEG_upper_margin", run(["rEEG_upper_margin"], change(**{"rEEG.APPLY_LOG_LINEAR_SCALE": 1})))
    assert not np.array_equal(new, old, equal_nan=True)


# ---------------------------------------------------------------------------
# Column names: one band, distinct names for distinct bands, the feature set
# ---------------------------------------------------------------------------
FOUR = ["05_4", "4_7", "7_13", "13_30"]
# The column names of the default call, as the original NEURAL names them
# (written out; the regression tests check the non-IBI ones against the
# reference files too).
DEFAULT_COLUMNS = [
    "%s__%s" % (feature, band)
    for feature, bands in [
        ("spectral_power", FOUR), ("spectral_relative_power", FOUR), ("spectral_flatness", FOUR),
        ("spectral_diff", FOUR), ("spectral_entropy", FOUR), ("spectral_edge_frequency", ["05_30"]),
        ("FD", ["05_30"]), ("amplitude_skew", FOUR), ("amplitude_kurtosis", FOUR), ("amplitude_env_mean", FOUR),
        ("amplitude_env_SD", FOUR), ("connectivity_BSI", FOUR), ("connectivity_corr", FOUR),
        ("connectivity_coh_mean", FOUR), ("rEEG_median", FOUR), ("rEEG_lower_margin", FOUR),
        ("rEEG_upper_margin", FOUR), ("rEEG_CV", FOUR), ("rEEG_asymmetry", FOUR), ("IBI_length_max", ["05_30"]),
        ("IBI_length_median", ["05_30"]), ("IBI_burst_prc", ["05_30"]), ("IBI_burst_number", ["05_30"])]
    for band in bands]


def test_default_column_names_are_unchanged():
    assert len(DEFAULT_COLUMNS) == 74
    for params in (NEURAL_parameters.NEURAL_parameters(), neural_outputs.original_settings()):
        assert generate_all_features.get_feature_names(params, params["FEATURE_SET_ALL"]) == DEFAULT_COLUMNS


@pytest.mark.parametrize("edge, label", [
    (0.5, "05"), (4, "4"), (4.0, "4"), (30, "30"), (np.int64(7), "7"), (np.float64(13.0), "13"),
    (4.1, "4p1"), (np.float64(4.1), "4p1"), (0.25, "0p25"), (1.5, "1p5"), (0.1, "0p1"), (32.75, "32p75"),
])
def test_band_edge_label(edge, label):
    """Whole numbers and 0.5 as before; any other edge in full, so that
    distinct edges never share a label."""
    assert generate_all_features.band_edge_label(edge) == label


ONE_BAND_FEATURES = [("spectral", "spectral_power"), ("spectral", "spectral_flatness"), ("amplitude", "amplitude_skew"),
                     ("rEEG", "rEEG_median"), ("FD", "FD"), ("connectivity", "connectivity_BSI"),
                     ("connectivity", "connectivity_coh_mean"), ("connectivity", "connectivity_corr")]


@pytest.mark.parametrize("as_array", [False, True], ids=["list", "numpy array"])
@pytest.mark.parametrize("group, feature", ONE_BAND_FEATURES, ids=[f for _, f in ONE_BAND_FEATURES])
def test_one_band(group, feature, as_array):
    """A single band [[0.5, 4]] (a list or a numpy array) gives one column,
    whose values are the feature function's for that band. Before, the one
    row was taken for a flat [low, high] pair and generate_all_features
    failed with IndexError."""
    band = np.array([[0.5, 4]]) if as_array else [[0.5, 4]]
    params = change(**{group + ".freq_bands": band})
    out = run([feature], params)
    assert out[1] == [feature + "__05_4"]
    np.testing.assert_array_equal(per_epoch_values(feature, out), direct(feature, params))
    if feature != "FD":  # the first default band is also [0.5, 4]: the same values
        np.testing.assert_array_equal(per_epoch_values(feature, out)[..., 0],
                                      per_epoch_values(feature, run([feature]))[..., 0])


@pytest.mark.parametrize("group, feature, bands, suffixes", [
    ("spectral", "spectral_power", [[0.5, 4.1], [0.5, 4.9]], ["05_4p1", "05_4p9"]),
    ("amplitude", "amplitude_env_mean", [[1.2, 4], [1.7, 4]], ["1p2_4", "1p7_4"]),
    ("rEEG", "rEEG_median", np.array([[0.5, 3.5], [3.5, 8.25]]), ["05_3p5", "3p5_8p25"]),
    ("connectivity", "connectivity_BSI", [[0.5, 4.1], [0.5, 4.9]], ["05_4p1", "05_4p9"]),
], ids=["spectral", "amplitude", "rEEG", "connectivity"])
def test_fractional_bands_get_their_own_columns(group, feature, bands, suffixes):
    """Bands that differ only in a fraction of their edges: each its own
    column, with its own values. Before, both were named after the integer
    parts (e.g. '05_4'), and the summary held the second band's value twice."""
    params = change(**{group + ".freq_bands": bands})
    out = run([feature], params)
    assert out[1] == ["%s__%s" % (feature, s) for s in suffixes]
    values = per_epoch_values(feature, out)
    np.testing.assert_array_equal(values, direct(feature, params))
    assert not np.array_equal(values[..., 0], values[..., 1])
    summary = out[4].to_numpy(dtype=float)[0]
    assert summary[0] != summary[1]


@pytest.mark.parametrize("bands", [[[0.5, 4], [0.5, 4]], [[1, 4], [1.0, 4.0]], [[0.5, 4], [4, 7], [0.5, 4.0]]],
                         ids=["twice", "int and float", "first and third"])
def test_the_same_band_twice_raises_before_any_feature(bands, monkeypatch):
    calls = []
    monkeypatch.setattr(spectral_features, "main_spectral", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError, match=r"spectral_power: frequency bands \d \[.*\] and \d \[.*\] give the same "
                                         r"column name 'spectral_power__"):
        run(["spectral_power"], change(**{"spectral.freq_bands": bands}))
    assert calls == []


def test_feat_set_decides_the_features_and_columns():
    """A given feat_set decides what is computed and which columns there are,
    also for a feature missing from params['FEATURE_SET_ALL'] (before: it
    was computed, then generate_all_features failed for lack of a column).
    FEATURE_SET_ALL orders the columns, the others follow in feat_set order."""
    params = change(FEATURE_SET_ALL=["FD"])
    out = run(["spectral_power"], params)
    assert out[1] == ["spectral_power__05_4", "spectral_power__4_7", "spectral_power__7_13", "spectral_power__13_30"]
    assert_same_outputs(out, run(["spectral_power"]))
    params = change(FEATURE_SET_ALL=["rEEG_CV"])
    names = run(["spectral_power", "FD", "rEEG_CV"], params)[1]
    assert names == ["rEEG_CV__05_4", "rEEG_CV__4_7", "rEEG_CV__7_13", "rEEG_CV__13_30",
                     "spectral_power__05_4", "spectral_power__4_7", "spectral_power__7_13", "spectral_power__13_30",
                     "FD__05_30"]
    # with the defaults, as before: the order of FEATURE_SET_ALL, whatever the order of feat_set
    assert run(["FD", "spectral_power"])[1] == run(["spectral_power", "FD"])[1] == \
        ["spectral_power__05_4", "spectral_power__4_7", "spectral_power__7_13", "spectral_power__13_30", "FD__05_30"]


def test_supported_features_are_the_default_feature_set():
    assert list(NEURAL_parameters.SUPPORTED_FEATURES) == NEURAL_parameters.NEURAL_parameters()["FEATURE_SET_ALL"] \
        == neural_outputs.original_settings()["FEATURE_SET_ALL"]


@pytest.mark.parametrize("feat_set, channels, unknown", [
    (["IBI_burst_pct"], CHANNELS[:2], ["IBI_burst_pct"]),
    (["connectivity_bsi_typo"], CHANNELS[:1], ["connectivity_bsi_typo"]),
    (["spectral_power", "spectral_pwr", "FD", "IBI_burst_pct"], CHANNELS, ["spectral_pwr", "IBI_burst_pct"]),
], ids=["misspelt IBI name", "misspelt connectivity name, one channel", "valid and invalid names"])
@pytest.mark.parametrize("custom", [False, True], ids=["default params", "custom FEATURE_SET_ALL"])
def test_unknown_feature_names_raise_before_feature_computation(feat_set, channels, unknown, custom, monkeypatch):
    """Every requested name must be a supported feature (SUPPORTED_FEATURES,
    not the possibly shortened FEATURE_SET_ALL): ValueError naming the
    unknown ones, after the input is loaded and its channels screened, before
    any feature is computed. (Without this check, a
    misspelt name got a column of NaN on paths that return before the name
    is used, e.g. IBI without the burst detector or connectivity with one
    channel.)"""
    calls = []
    monkeypatch.setattr(IBI_features, "main_IBI", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(generate_all_features, "overlap_epochs", lambda *args, **kwargs: calls.append(args))
    data = {"eeg_data": DATA["eeg_data"][channels], "Fs": FS, "ch_labels": list(channels)}
    params = change(FEATURE_SET_ALL=["FD"]) if custom else None
    message = "Unknown feature name\\(s\\) %s; the supported features are" % ", ".join(repr(n) for n in unknown)
    with pytest.raises(ValueError, match=message):
        run(feat_set, params, data)
    assert calls == []


def test_unknown_name_in_a_custom_feature_set_all_raises():
    with pytest.raises(ValueError, match=r"Unknown feature name\(s\) 'spectral_pwr'"):
        run(None, change(FEATURE_SET_ALL=["spectral_power", "spectral_pwr"]))


def test_removed_names_keep_their_own_message():
    with pytest.raises(ValueError, match=r"Feature\(s\) 'rEEG_SD' removed to match neural_eeg_features 0.6.1"):
        run(["rEEG_SD", "spectral_pwr"])


def test_supported_names_outside_a_custom_feature_set_all_are_accepted(monkeypatch):
    """A supported feature missing from a custom FEATURE_SET_ALL is computed
    and gets its columns, IBI included (here main_IBI is replaced by a
    stand-in returning NaN, as it does without the burst detector)."""
    monkeypatch.setattr(IBI_features, "main_IBI", lambda *args, **kwargs: np.nan)
    params = change(FEATURE_SET_ALL=["FD"])
    names = run(["IBI_burst_prc", "connectivity_BSI"], params)[1]
    assert names == ["IBI_burst_prc__05_30"] + ["connectivity_BSI__" + band for band in FOUR]


def test_top_level_freq_bands():
    """Assigning a new list to the top-level FREQ_BANDS changes nothing: each
    group has its own 'freq_bands'. In NEURAL_parameters(), the spectral,
    amplitude, rEEG and connectivity 'freq_bands' are that same list object,
    so editing it in place changes those four groups (not FD's band or the
    spectral total band, which are separate lists). FILTER_REPLACE_ARTEFACTS
    is text and cannot be edited in place; assigning it changes nothing."""
    features = ["spectral_power", "amplitude_env_mean", "rEEG_median", "connectivity_BSI", "FD",
                "spectral_edge_frequency"]
    default = run(features)
    assigned = change(FREQ_BANDS=[[1, 3], [3, 20]], FILTER_REPLACE_ARTEFACTS="zeros")
    assert_same_outputs(run(features, assigned), default)
    edited = NEURAL_parameters.NEURAL_parameters()
    edited["FREQ_BANDS"][0][1] = 3  # [0.5, 4] becomes [0.5, 3] in place
    names = run(features, edited)[1]
    for feature in features[:4]:
        assert feature + "__05_3" in names and feature + "__05_4" not in names
    assert "FD__05_30" in names and "spectral_edge_frequency__05_30" in names


# ---------------------------------------------------------------------------
# params is not changed, and calls do not affect each other
# ---------------------------------------------------------------------------
def different_params():
    return change(EPOCH_LENGTH=32, **{"spectral.L_window": 4, "spectral.window_type": "hann",
                                      "amplitude.freq_bands": TWO_BANDS, "rEEG.L_window": 4,
                                      "FD.method": "katz", "connectivity.L_window": 4,
                                      "connectivity.coherence_zero_alpha": 0.5})


def test_params_are_not_changed():
    params = different_params()
    before = copy.deepcopy(params)
    run(neural_outputs.non_ibi_features(), params)
    assert params == before
    assert NEURAL_parameters.NEURAL_parameters() == PRISTINE_DEFAULTS


def test_calls_with_different_params_do_not_affect_each_other():
    features = neural_outputs.non_ibi_features()
    a1 = run(features, NEURAL_parameters.NEURAL_parameters())
    b1 = run(features, different_params())
    a2 = run(features, NEURAL_parameters.NEURAL_parameters())
    b2 = run(features, different_params())
    assert_same_outputs(a1, a2)
    assert_same_outputs(b1, b2)
    assert_same_outputs(run(features), a1)


def test_a_feature_call_does_not_change_the_next_ones_settings():
    """spectral_power sets 'method' to 'periodogram' in the settings it is
    given; spectral_flatness, computed after it in the same call, still uses
    the Welch PSD of params."""
    together = run(["spectral_power", "spectral_flatness"], NEURAL_parameters.NEURAL_parameters())
    alone = run(["spectral_flatness"], NEURAL_parameters.NEURAL_parameters())
    names = [n for n in together[1] if n.startswith("spectral_flatness")]
    assert np.array_equal(together[4][names].to_numpy(dtype=float), alone[4][names].to_numpy(dtype=float))


# ---------------------------------------------------------------------------
# params without the structure of NEURAL_parameters()
# ---------------------------------------------------------------------------
def without(params, *keys):
    node = params
    for key in keys[:-1]:
        node = node[key]
    del node[keys[-1]]
    return params


BAD_PARAMS = [
    ("missing", lambda p: without(p, "EPOCH_LENGTH"), r"params\['EPOCH_LENGTH'\] is missing"),
    ("missing in a group", lambda p: without(p, "spectral", "L_window"),
     r"params\['spectral'\]\['L_window'\] is missing"),
    ("missing group", lambda p: without(p, "connectivity"), r"params\['connectivity'\] is missing"),
    ("unknown", lambda p: dict(p, EPOCH_LENGHT=64),
     r"params\['EPOCH_LENGHT'\] is not a setting of NEURAL_parameters\(\)"),
    ("unknown in a group", lambda p: dict(p, spectral=dict(p["spectral"], Lwindow=4)),
     r"params\['spectral'\]\['Lwindow'\] is not a setting"),
    ("text for a number", lambda p: dict(p, EPOCH_LENGTH="64"),
     r"params\['EPOCH_LENGTH'\] must be a number, not a string \('64'\)"),
    ("True for a number", lambda p: dict(p, EPOCH_OVERLAP=True),
     r"params\['EPOCH_OVERLAP'\] must be a number, not True or False"),
    ("text for a list", lambda p: dict(p, spectral=dict(p["spectral"], freq_bands="0.5-4")),
     r"params\['spectral'\]\['freq_bands'\] must be a list, not a string"),
    ("None for a string", lambda p: dict(p, connectivity=dict(p["connectivity"], method=None)),
     r"params\['connectivity'\]\['method'\] must be a string, not None"),
    ("list for a group", lambda p: dict(p, rEEG=[1, 2]),
     r"params\['rEEG'\] must be a dictionary like NEURAL_parameters\(\)\['rEEG'\], not a list"),
    ("not a dictionary", lambda p: [p], r"params must be a dictionary like NEURAL_parameters\(\), not a list"),
    ("0-d array for a list", lambda p: dict(p, FEATURE_SET_ALL=np.array("spectral_power")),
     r"params\['FEATURE_SET_ALL'\] must be a list, not a zero-dimensional array"),
    ("0-d array for bands", lambda p: dict(p, spectral=dict(p["spectral"], freq_bands=np.array(4.0))),
     r"params\['spectral'\]\['freq_bands'\] must be a list, not a zero-dimensional array"),
    ("0-d array for a number", lambda p: dict(p, EPOCH_LENGTH=np.array(32)),
     r"params\['EPOCH_LENGTH'\] must be a number, not a zero-dimensional array"),
    ("a group instead of all settings", lambda p: p["spectral"], r"params\['LP_fc'\] is missing"),
]


@pytest.mark.parametrize("make, message", [(m, msg) for _, m, msg in BAD_PARAMS], ids=[i for i, _, _ in BAD_PARAMS])
def test_bad_params_raise_before_any_feature(make, message, monkeypatch):
    calls = []
    monkeypatch.setattr(spectral_features, "main_spectral", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(generate_all_features, "overlap_epochs", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError, match=message):
        run(["spectral_power"], make(NEURAL_parameters.NEURAL_parameters()))
    assert calls == []


def test_every_problem_is_named():
    params = without(dict(NEURAL_parameters.NEURAL_parameters(), EPOCH_LENGHT=64), "spectral", "SEF")
    with pytest.raises(ValueError) as error:
        NEURAL_parameters.check_parameters(params)
    assert "params['spectral']['SEF'] is missing" in str(error.value)
    assert "params['EPOCH_LENGHT'] is not a setting" in str(error.value)


@pytest.mark.parametrize("settings", [
    {"FD.method": None},  # main_fd: None means 'higuchi'
    {"REMOVE_ART": False, "rEEG.APPLY_LOG_LINEAR_SCALE": True},  # 0/1 switches
    {"EPOCH_LENGTH": 32.5, "EPOCH_OVERLAP": np.int64(25), "spectral.SEF": np.float32(0.9)},
    {"spectral.freq_bands": ((0.5, 4), (4, 30)), "amplitude.freq_bands": np.array(TWO_BANDS)},
    {"rEEG.freq_bands": []},
], ids=["FD method None", "switches as True/False", "int, float and numpy numbers", "tuples and arrays",
        "empty band list"])
def test_values_of_the_right_kind_are_accepted(settings):
    NEURAL_parameters.check_parameters(change(**settings))
