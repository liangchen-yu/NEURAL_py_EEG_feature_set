"""Inputs and runners for the edge-case regression tests
(tests/test_edge_cases.py): pre-existing NaN, +/-inf, EDF export, and the
window types SciPy removed.

An EDF file stores whole numbers, so it can never contain NaN or infinity.
These cases therefore call NEURAL's functions directly with DataFrames, the
way NEURAL's own main_preprocessing calls them.

Every input is built from the whole-number signals of synthetic_edf.py, so it
is identical on every computer. make_reference.py (with the original NEURAL)
and the tests (with this repository's NEURAL) both use the *_results()
functions below, so both run exactly the same steps. This file must also run
on Python 3.7 (the window reference comes from the 2020 environment).
"""
import contextlib
import io
import math
import os
import traceback

import numpy as np
import pandas as pd

import neural_outputs
import synthetic_edf

FS = 256  # sampling rate of the synthetic recordings (Hz)
SECONDS = 120  # length used for the NaN and inf cases
# the order in which NEURAL's EDF reader (load_edf_EEG_file) adds the electrodes
EDF_READER_ORDER = ["F3", "F4", "C3", "C4", "O1", "O2", "T3", "T4", "Cz"]
# the bipolar channels NEURAL makes from them (utils.set_bi_montage), in order
BIPOLAR_ORDER = ["C3_O1", "C4_O2", "Cz_C3", "C4_Cz", "C3_T3", "C4_T4", "F3_C3", "F4_C4"]

# Pre-existing NaN runs in the referential data: electrode -> (first sample, last sample + 1)
NAN_RUNS = {
    "Cz": (30 * FS, 30 * FS + 384),  # in the middle (1.5 s)
    "O2": (0, FS),  # at the start (1 s)
    "T3": (SECONDS * FS - 2 * FS, SECONDS * FS),  # at the end (2 s)
    "F3": (45 * FS, 45 * FS + 1),  # a single sample
}
# ... and one run that is only in the bipolar data
BIPOLAR_NAN_RUN = ("C3_O1", 50 * FS, 50 * FS + 128)

# Infinite values that the art_per_channel stand-in adds (see inf_line_results)
INF_RUNS = [("F3_C3", 1000, 1010, np.inf), ("F3_C3", 2000, 2005, -np.inf), ("C4_T4", 7000, 7003, np.inf)]

WINDOW_TYPES = ["tuke", "bart", "blackmanharris"]
# The features whose result depends on the window type (see window_results)
SPECTRAL_WINDOW_FEATURES = ["spectral_flatness", "spectral_entropy", "spectral_diff", "spectral_edge_frequency"]
REEG_FEATURES = ["rEEG_mean", "rEEG_median", "rEEG_lower_margin", "rEEG_upper_margin", "rEEG_width",
                 "rEEG_SD", "rEEG_CV", "rEEG_asymmetry"]


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def referential(seconds=SECONDS):
    """Referential EEG in microvolts, built column by column like NEURAL's EDF reader."""
    units = synthetic_edf.make_signals("clean")[:, :seconds * FS]
    frame = pd.DataFrame()
    for i, name in enumerate(EDF_READER_ORDER):
        frame.insert(i, name, units[synthetic_edf.ELECTRODES.index(name)] / 10.0)
    return frame


def set_values(frame, column, start, stop, value):
    frame.iloc[start:stop, frame.columns.get_loc(column)] = value


def bipolar(ref):
    from NEURAL_py_EEG import utils

    return utils.set_bi_montage(ref, FS)[0]


def nan_inputs():
    """Referential and bipolar EEG with the NaN runs above."""
    ref = referential()
    for name, (start, stop) in NAN_RUNS.items():
        set_values(ref, name, start, stop, np.nan)
    bip = bipolar(ref)
    column, start, stop = BIPOLAR_NAN_RUN
    set_values(bip, column, start, stop, np.nan)
    return ref, bip


def inf_inputs():
    """Real +/-inf input: a run of +inf in F3 and of -inf in F4."""
    ref = referential()
    set_values(ref, "F3", 20 * FS, 23 * FS, np.inf)
    set_values(ref, "F4", 40 * FS, 43 * FS, -np.inf)
    return ref, bipolar(ref)


def export_frame():
    """A small DataFrame to export as EDF: 3 channels, 4 s, with NaN (which
    NEURAL writes as 0)."""
    frame = referential(seconds=4)[["F3", "F4", "C3"]].copy()
    set_values(frame, "F4", 100, 150, np.nan)
    set_values(frame, "C3", 500, 501, np.nan)
    return frame


# ---------------------------------------------------------------------------
# Running NEURAL
# ---------------------------------------------------------------------------
def remove_artefacts(ref, bip):
    """NEURAL's remove_artefacts, called as main_preprocessing calls it.
    Returns (cleaned bipolar data, artefact report). ref may be changed."""
    from NEURAL_py_EEG import preprocessing_EEG

    with contextlib.redirect_stdout(io.StringIO()):
        return preprocessing_EEG.remove_artefacts(
            bip.copy(), np.array(list(bip.columns)), FS, ref, np.array(list(ref.columns)))


def downstream(cleaned):
    """The rest of main_preprocessing (low-pass filter, downsample to 64 Hz)
    and all 26 non-IBI features in one generate_all_features call. Returns the
    64 Hz data and each feature's summary (median over channels and epochs,
    one value per frequency band); fingerprints of the data check the rest."""
    from NEURAL_py_EEG import preprocessing_EEG

    with contextlib.redirect_stdout(io.StringIO()):
        filtered = preprocessing_EEG.LPF_zero_phase(cleaned.copy(), FS)
        down, fs = preprocessing_EEG.signal_downsample(filtered.copy(), FS, 64)
        data = {"eeg_data": down, "Fs": fs, "ch_labels": list(down.columns)}
        features = neural_outputs.compute_features(data, neural_outputs.non_ibi_features())
    return down, {f: out["feats_median_all"] for f, out in features.items()}


def fingerprint(frame, step=997):
    """A small, sampled check of every column (not a copy of all its values):
    exactly where it is NaN, how many +inf and -inf it has, the sum and sum of
    squares of its finite values, its min and max, and every 997th sample.
    A change to the NaN places, to the infinities, or to the values themselves
    almost always shows up here, but a change to a few unsampled values that
    happened to leave the sums unchanged would not."""
    result = {}
    for name in frame.columns:
        x = np.array(frame[name], dtype=float)
        finite = x[np.isfinite(x)]
        result[str(name)] = {
            "nan_runs": neural_outputs.nan_runs(np.isnan(x)),
            "posinf": int(np.isposinf(x).sum()),
            "neginf": int(np.isneginf(x).sum()),
            "sum": float(finite.sum()) if finite.size else math.nan,
            "sum_of_squares": float((finite ** 2).sum()) if finite.size else math.nan,
            "min": float(finite.min()) if finite.size else math.nan,
            "max": float(finite.max()) if finite.size else math.nan,
            "every_997th_sample": x[::step],
        }
    return result


def values_at_runs(frame, runs):
    """The values just before, at the start, middle and end of, and just after
    each run: shows exactly how the NaN were filled."""
    result = {}
    for name, (start, stop) in runs.items():
        x = np.array(frame[name], dtype=float)
        positions = sorted({p for p in (start - 1, start, start + 1, (start + stop) // 2, stop - 1, stop)
                            if 0 <= p < len(x)})
        result[name] = {"positions": positions, "values": x[positions]}
    return result


@contextlib.contextmanager
def inf_stand_in():
    """No input reaches the +inf line of remove_artefacts (~line 419): an
    infinity either makes one of NEURAL's Butterworth filters stop with an
    error first (see inf_input_failure), or, right next to a run of zeros of
    1 s or more, is turned into NaN by the flat-zero check before that line.
    To test the line itself, temporarily replace art_per_channel by a
    stand-in that calls the real one and then adds the values in INF_RUNS."""
    from NEURAL_py_EEG import preprocessing_EEG

    real = preprocessing_EEG.art_per_channel
    calls = []

    def stand_in(x, fs, verbose):
        cleaned, removed = real(x, fs, verbose)
        name = BIPOLAR_ORDER[len(calls)]  # NEURAL processes the channels in this order
        calls.append(name)
        for column, start, stop, value in INF_RUNS:
            if column == name:
                cleaned[start:stop] = value
        return cleaned, removed

    preprocessing_EEG.art_per_channel = stand_in
    try:
        yield calls
    finally:
        preprocessing_EEG.art_per_channel = real


# ---------------------------------------------------------------------------
# The cases: each returns plain values, saved as JSON by make_reference.py
# ---------------------------------------------------------------------------
def nan_case_results():
    ref, bip = nan_inputs()
    cleaned, removed = remove_artefacts(ref, bip)  # changes ref, as the original did
    down, features = downstream(cleaned)
    return {
        "artefact_report": neural_outputs.artefact_report(removed),
        "cleaned": fingerprint(cleaned),
        "data_ref_after": {"fingerprint": fingerprint(ref), "values_at_runs": values_at_runs(ref, NAN_RUNS)},
        "preprocessed": fingerprint(down),
        "features": features,
    }


def inf_line_results():
    ref = referential()
    with inf_stand_in() as calls:
        cleaned, removed = remove_artefacts(ref, bipolar(ref))
    if calls != BIPOLAR_ORDER:
        raise RuntimeError("art_per_channel was not called once per channel in the expected order")
    down, features = downstream(cleaned)
    return {
        "artefact_report": neural_outputs.artefact_report(removed),
        "cleaned": fingerprint(cleaned),
        "preprocessed": fingerprint(down),
        "features": features,
    }


def inf_input_failure():
    """What happens with real +/-inf input: the original fails with an error."""
    try:
        remove_artefacts(*inf_inputs())
    except Exception as error:  # noqa: BLE001 - recording the original's failure
        return {"error": type(error).__name__, "in_function": traceback.extract_tb(error.__traceback__)[-1].name}
    return {"error": None, "in_function": None}


def read_edf(path):
    """What an EDF file contains, read back with pyedflib: per signal its
    header values and its stored whole numbers (digital samples)."""
    import hashlib
    import pyedflib

    reader = pyedflib.EdfReader(path)
    try:
        signals = []
        for i in range(reader.signals_in_file):
            digital = reader.readSignal(i, digital=True).astype("<i4")
            signals.append({
                "label": reader.getLabel(i), "dimension": reader.getPhysicalDimension(i),
                "sample_frequency": float(reader.getSampleFrequency(i)),
                "physical_min": float(reader.getPhysicalMinimum(i)),
                "physical_max": float(reader.getPhysicalMaximum(i)),
                "digital_min": int(reader.getDigitalMinimum(i)),
                "digital_max": int(reader.getDigitalMaximum(i)),
                "samples": int(digital.size), "digital_sum": int(digital.sum()),
                "digital_sha256": hashlib.sha256(digital.tobytes()).hexdigest(),
                "first_digital_values": [int(v) for v in digital[:5]],
            })
        return {"signals": signals, "duration_s": float(reader.getFileDuration())}
    finally:
        reader.close()


def export_results(folder):
    """utils.save_pd_as_edf with NEURAL's own header values and with the header
    copied from an existing EDF file; then what the files contain and what
    happened to the caller's DataFrame (the original also set its NaN to 0)."""
    from NEURAL_py_EEG import utils

    template = os.path.join(str(folder), "synthetic_clean.edf")
    with open(template, "wb") as f:
        f.write(synthetic_edf.make_edf("clean"))
    results = {}
    for label, kwargs in (("default_header", {}), ("header_from_edf", {"original_edf_file": template})):
        frame = export_frame()
        nan_positions = {c: np.flatnonzero(np.isnan(frame[c].to_numpy())) for c in frame.columns}
        path = os.path.join(str(folder), label + ".edf")
        with contextlib.redirect_stdout(io.StringIO()):
            utils.save_pd_as_edf(frame, path, Fs=FS, **kwargs)
        results[label] = {
            "file": read_edf(path),
            "caller_dataframe_after": {c: {"nan_left": int(frame[c].isna().sum()),
                                           "values_where_nan_was": frame[c].to_numpy()[pos]}
                                       for c, pos in nan_positions.items() if pos.size},
        }
    return results


def window_results():
    """NEURAL's window functions for the types SciPy 1.13 removed from
    scipy.signal, at NEURAL's default lengths (64 Hz: 2 s = 128 samples for
    spectral and rEEG, 8 s = 512 for connectivity; every 4th value of the
    longer ones), and every feature whose result depends on the window type,
    computed with each of these windows:
      - spectral_flatness, spectral_entropy, spectral_diff and
        spectral_edge_frequency (spectral_power and spectral_relative_power
        use a periodogram, which has no window, so they are left out);
      - the 8 rEEG features, without the frequency-band filter
        (freq_bands = [], a path NEURAL supports): the window is then the
        only thing that matters, so the comparison with the 2020 environment
        is not blurred by the band filter's last-digit rounding;
      - connectivity_BSI with method "PSD" (the default "bartlett-PSD"
        always uses a rectangular window).
    Each computation gets its own fresh parameters (spectral_power, for
    example, changes the dictionary it is given), and must really have asked
    utils.get_window for its window type; "window_calls" records how often."""
    from NEURAL_py_EEG import NEURAL_parameters, connectivity_features, rEEG, spectral_features, utils

    windows = {}
    for kind in WINDOW_TYPES:
        windows["get_window %s 128" % kind] = utils.get_window(128, kind)
        windows["get_window %s 512, every 4th" % kind] = utils.get_window(512, kind)[::4]
        windows["gen_epoch_window %s, 2 s at 64 Hz" % kind] = utils.gen_epoch_window(50, 2, kind, 64)[2]
    windows["gen_window blackmanharris 128"] = utils.gen_window("blackmanharris", 128)

    x = synthetic_edf.make_signals("clean")[2, :64 * 256:4] / 10.0  # C3, every 4th sample: 64 s at 64 Hz
    bip = bipolar(referential(seconds=64))
    x_bipolar = bip.to_numpy().T[:, ::4].copy()  # 8 bipolar channels, 64 s at 64 Hz
    labels = np.array(list(bip.columns))

    def fresh(group, kind):
        params = NEURAL_parameters.NEURAL_parameters()[group]
        params["window_type"] = kind
        return params

    features = {}
    for kind in WINDOW_TYPES:
        for feature in SPECTRAL_WINDOW_FEATURES:
            params = fresh("spectral", kind)
            features["%s, %s window" % (feature, kind)] = windowed(
                kind, lambda: spectral_features.main_spectral(x.copy(), 64, feature, params))
        for feature in REEG_FEATURES:
            params = fresh("rEEG", kind)
            params["freq_bands"] = []
            features["%s, %s window" % (feature, kind)] = windowed(
                kind, lambda: rEEG.main_rEEG(x.copy(), 64, feature, params))
        params = fresh("connectivity", kind)
        params["method"] = "PSD"
        features["connectivity_BSI, %s window" % kind] = windowed(
            kind, lambda: connectivity_features.main_connectivity(
                x_bipolar.copy(), 64, "connectivity_BSI", labels, params))
    return {"windows": windows, "features": features}


@contextlib.contextmanager
def recorded_window_calls():
    """Record the window type of every call to utils.get_window, through
    which all of NEURAL's windows are made."""
    from NEURAL_py_EEG import utils

    real = utils.get_window
    calls = []

    def recording(win_length, win_type, Npad=0):
        calls.append(win_type)
        return real(win_length, win_type, Npad)

    utils.get_window = recording
    try:
        yield calls
    finally:
        utils.get_window = real


INDEX_KINDS = ["default 0, 1, 2, ...", "datetime", "text", "integers in reverse order", "integers from 1000"]


def with_index(frame, kind, fs):
    """A copy of frame with another kind of row index (same values, same order)."""
    frame = frame.copy()
    n = len(frame)
    if kind == "datetime":
        frame.index = pd.date_range("2020-01-01", periods=n, freq=pd.to_timedelta(1.0 / fs, unit="s"))
    elif kind == "text":
        frame.index = ["sample %d" % i for i in range(n)]
    elif kind == "integers in reverse order":
        frame.index = np.arange(n)[::-1]
    elif kind == "integers from 1000":
        frame.index = np.arange(1000, 1000 + n)
    return frame


def outcome(compute):
    """compute()'s result, or the error it stopped with (the original also
    stops with an error for some inputs; the fork must do the same)."""
    try:
        return compute()
    except Exception as error:  # noqa: BLE001 - recording the failure itself
        frames = traceback.extract_tb(error.__traceback__)
        in_neural = [f for f in frames if os.path.basename(os.path.dirname(f.filename)) == "NEURAL_py_EEG"]
        return {"error": type(error).__name__, "in_neural_function": (in_neural or frames)[-1].name}


def epochs_fingerprint(x_epochs, x_epochs_inds):
    flat = np.asarray(x_epochs, dtype=float).ravel()
    finite = flat[np.isfinite(flat)]
    return {"shape": list(np.shape(x_epochs)), "nan": int(np.isnan(flat).sum()), "sum": float(finite.sum()),
            "sum_of_squares": float((finite ** 2).sum()), "every_997th_value": flat[::997],
            "index_sum": int(np.sum(x_epochs_inds))}


def index_type_results():
    """The same EEG with other kinds of row index (datetime, text, integers in
    another order), through generate_all_features (all 26 non-IBI features),
    the preprocessing steps (remove_artefacts, low-pass filter, downsampling;
    clean data, so nothing is removed) and preprocessing_EEG.overlap_epochs.
    pandas < 3 picked samples by position for a datetime or text index and by
    label for an integer index; the fork must give the same results, and fail
    where the original failed."""
    from NEURAL_py_EEG import preprocessing_EEG

    ref = referential()
    bip = bipolar(ref)
    bip64 = bip.iloc[::4].reset_index(drop=True)  # 64 Hz, as after NEURAL's downsampling
    labels = list(bip64.columns)
    result = {"generate_all_features": {}, "preprocessing": {}, "overlap_epochs": {}}
    for kind in INDEX_KINDS:
        data = {"eeg_data": with_index(bip64, kind, 64), "Fs": 64, "ch_labels": labels}

        def features():
            with contextlib.redirect_stdout(io.StringIO()):
                out = neural_outputs.compute_features(data, neural_outputs.non_ibi_features())
            return {f: values["feats_median_all"] for f, values in out.items()}

        result["generate_all_features"][kind] = outcome(features)
        series = with_index(bip64, kind, 64)["C3_O1"]
        result["overlap_epochs"][kind] = outcome(
            lambda: epochs_fingerprint(*preprocessing_EEG.overlap_epochs(series, 64, 8, 50, "hamm")))
    for kind in INDEX_KINDS[:3]:
        def preprocessing():
            cleaned, removed = remove_artefacts(with_index(ref, kind, FS), with_index(bip, kind, FS))
            with contextlib.redirect_stdout(io.StringIO()):
                filtered = preprocessing_EEG.LPF_zero_phase(cleaned.copy(), FS)
                down, _ = preprocessing_EEG.signal_downsample(filtered.copy(), FS, 64)
            return {"artefact_report": neural_outputs.artefact_report(removed), "preprocessed": fingerprint(down)}

        result["preprocessing"][kind] = outcome(preprocessing)
    return result


def read_only_results(read_only=True):
    """connectivity_features.gen_coherence (and gen_cross_spectrum inside it)
    with two bipolar channels at 64 Hz. With read_only=True the arrays cannot
    be written to, like the arrays pandas 3 gives; the original needs
    writable ones, so its reference values were made with read_only=False.
    Also records whether the function left its input arrays unchanged."""
    from NEURAL_py_EEG import NEURAL_parameters, connectivity_features

    bip64 = bipolar(referential(seconds=64)).iloc[::4]
    x = bip64["F3_C3"].to_numpy(dtype=float).copy()
    y = bip64["F4_C4"].to_numpy(dtype=float).copy()
    x_before, y_before = x.copy(), y.copy()
    if read_only:
        x.setflags(write=False)
        y.setflags(write=False)
    params = NEURAL_parameters.NEURAL_parameters()["connectivity"]
    c, pxx, pyy, f_scale, fp = connectivity_features.gen_coherence(x, y, 64, params)
    return {"coherence": c,
            "pxx": {"sum": float(np.sum(pxx)), "every_8th_value": pxx[::8]},
            "pyy": {"sum": float(np.sum(pyy)), "every_8th_value": pyy[::8]},
            "f_scale": float(f_scale), "fp_sum": float(np.sum(fp)),
            "inputs_unchanged": bool(np.array_equal(x, x_before) and np.array_equal(y, y_before))}


def windowed(kind, compute):
    """Run compute() and check it really used the window type `kind`;
    otherwise the comparison would prove nothing."""
    with recorded_window_calls() as calls:
        values = np.atleast_1d(compute())
    if kind not in calls:
        raise RuntimeError("the %r window was never used, so this comparison would prove nothing" % kind)
    return {"values": values, "window_calls": calls.count(kind)}
