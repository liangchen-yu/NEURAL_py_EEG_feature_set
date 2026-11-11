#!/usr/bin/env python
"""Numerical sensitivity of NEURAL_py's Butterworth band filters, on one machine.

Question. Between computing environments the original NEURAL code gives
features that differ by up to about 3e-7 (relative), while its preprocessed EEG
differs by only about 1e-14. Only features computed with
utils.filter_butterworth_withnans (order-5 Butterworth filters in (b, a) form,
applied with mfiltfilt.mat_filtfilt) show the larger differences. Hypothesis:
these (b, a) filters amplify last-digit rounding differences. This script tests
where a tiny difference grows, by how much, and whether second-order sections
(SOS) reduce it:

  A  stage by stage: every sample of the referential EEG moved by 1-4 units in
     the last place (ULP), then NEURAL's whole pipeline, compared after each stage;
  B  filter only: the same kind of change fed straight into each Butterworth filter;
  C  coefficients: the (b, a) coefficients moved by 1 ULP instead of the signal;
  D  SOS: the same filters in second-order sections, and what switching changes.

Run from the repository's top folder (details in README.md next to this file):

    python experiments/sensitivity/run_sensitivity.py --work-dir <folder outside the repository>

It writes the tables into results.md (between the GENERATED markers), the
figure stage_differences.png, and all per-seed numbers as JSON files into the
work folder. Only synthetic recordings (tests/synthetic_edf.py) are used.
"""
import argparse
import hashlib
import json
import platform
import re
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.append(str(REPO / "tests"))  # the regression tests' synthetic inputs (tests/synthetic_edf.py)

import sensitivity_tools as st  # noqa: E402
import synthetic_edf  # noqa: E402
from scipy import signal as scipy_signal  # noqa: E402

from NEURAL_py_EEG import preprocessing_EEG  # noqa: E402

FORMS = ("ba", "sos")
FORM_LABEL = {"ba": "(b, a)", "sos": "SOS"}
CASES = synthetic_edf.CASES  # ("clean", "artefacts")
CASE_LABEL = {"clean": "Clean recording", "artefacts": "Recording with artefacts"}
DOSE_LEVELS = (1e-15, 1e-14, 1e-13, 1e-12, 1e-11, 1e-10, 1e-9, 1e-8)
RESULTS_MD = HERE / "results.md"
FIGURE = HERE / "stage_differences.png"
BEGIN = "<!-- BEGIN GENERATED (written by run_sensitivity.py; edit the script, not this part) -->"
END = "<!-- END GENERATED -->"

# Separate random-number streams for the separate perturbations.
STREAM_SIGNAL, STREAM_FILTER_INPUT, STREAM_DOSE, STREAM_TEST_SIGNAL = 1, 2, 4, 5

# Every Butterworth filter in NEURAL's default pipeline, as called by its code:
# (label, low-pass cut-off, high-pass cut-off, order, NaN mode, input, sample rate).
# [] means "no such cut-off". Band filters are a low-pass followed by a high-pass.
FS_RECORDING = synthetic_edf.FS
FILTER_SPECS = [
    ("Low-pass 4 Hz", 4, [], 5, "nans", "epochs", 64),
    ("Low-pass 7 Hz", 7, [], 5, "nans", "epochs", 64),
    ("Low-pass 13 Hz", 13, [], 5, "nans", "epochs", 64),
    ("Low-pass 30 Hz", 30, [], 5, "nans", "epochs", 64),
    ("High-pass 0.5 Hz", [], 0.5, 5, "nans", "epochs", 64),
    ("High-pass 4 Hz", [], 4, 5, "nans", "epochs", 64),
    ("High-pass 7 Hz", [], 7, 5, "nans", "epochs", 64),
    ("High-pass 13 Hz", [], 13, 5, "nans", "epochs", 64),
    ("Band 0.5-4 Hz", 4, 0.5, 5, "nans", "epochs", 64),
    ("Band 4-7 Hz", 7, 4, 5, "nans", "epochs", 64),
    ("Band 7-13 Hz", 13, 7, 5, "nans", "epochs", 64),
    ("Band 13-30 Hz", 30, 13, 5, "nans", "epochs", 64),
    ("FD band 0.5-30 Hz", 30, 0.5, 5, "nans", "epochs", 64),
    ("Artefact check 0.5-20 Hz", 20, 0.5, 5, "linear_interp", "referential", FS_RECORDING),
    ("High-pass 0.5 Hz (256 Hz)", [], 0.5, 5, "linear_interp", "referential", FS_RECORDING),
    ("Low-pass 20 Hz (256 Hz)", 20, [], 5, "linear_interp", "referential", FS_RECORDING),
    ("Artefact check 0.1-40 Hz", 40, 0.1, [5, 2], "linear_interp", "bipolar", FS_RECORDING),
    ("High-pass 0.1 Hz, order 2 (256 Hz)", [], 0.1, 2, "linear_interp", "bipolar", FS_RECORDING),
    ("Low-pass 40 Hz (256 Hz)", 40, [], 5, "linear_interp", "bipolar", FS_RECORDING),
]
FILTER_USE = {
    "Band 0.5-4 Hz": "amplitude, rEEG, connectivity_corr",
    "Band 4-7 Hz": "amplitude, rEEG, connectivity_corr",
    "Band 7-13 Hz": "amplitude, rEEG, connectivity_corr",
    "Band 13-30 Hz": "amplitude, rEEG, connectivity_corr",
    "FD band 0.5-30 Hz": "FD",
    "Artefact check 0.5-20 Hz": "low-correlation and coupling checks",
    "Artefact check 0.1-40 Hz": "high-amplitude check",
}
DOSE_FILTERS = ("Band 0.5-4 Hz", "Band 13-30 Hz", "FD band 0.5-30 Hz", "Artefact check 0.5-20 Hz")

SIGNAL_STAGES = ["referential", "bipolar", "after_artefact_removal", "lowpass", "downsampled"]
STAGE_LABEL = {
    "referential": "Referential EEG (the input change)",
    "bipolar": "Bipolar montage",
    "after_artefact_removal": "After artefact removal",
    "lowpass": "30 Hz FIR low-pass (256 Hz)",
    "downsampled": "Downsampled to 64 Hz (preprocessed EEG)",
}
for _band in st.BANDS:
    STAGE_LABEL["band " + st.band_name(_band)] = "Band filter " + st.band_name(_band)
STAGE_LABEL["band " + st.band_name(st.FD_BAND) + " (FD)"] = "FD band filter " + st.band_name(st.FD_BAND)
for _band in st.BANDS:
    STAGE_LABEL["envelope " + st.band_name(_band)] = "Squared envelope, " + st.band_name(_band)
for _band in st.BANDS:
    STAGE_LABEL["rEEG " + st.band_name(_band)] = "rEEG (2 s ranges), " + st.band_name(_band)
FEATURE_STAGES = [k for k in STAGE_LABEL if k not in SIGNAL_STAGES]


def log(message):
    print(message, flush=True)


# ---------------------------------------------------------------------------
# Inputs, environment and small helpers
# ---------------------------------------------------------------------------
def write_inputs(work_dir):
    """The regression tests' two synthetic recordings, written as EDF files,
    with their checksums compared to the ones stored in tests/data/."""
    paths, same = {}, {}
    for case in CASES:
        data = synthetic_edf.make_edf(case)
        path = work_dir / f"synthetic_{case}.edf"
        path.write_bytes(data)
        stored = json.loads((REPO / "tests" / "data" / f"reference_{case}.json").read_text(encoding="utf-8"))
        same[case] = synthetic_edf.sha256(data) == stored["input"]["sha256"]
        paths[case] = path
    return paths, same


def environment():
    import matplotlib
    import mne
    import scipy

    import make_reference  # tests/make_reference.py holds the SHA-256 of the original 78c9425 modules
    import NEURAL_py_EEG

    folder = Path(NEURAL_py_EEG.__file__).resolve().parent
    original = make_reference.ORIGINAL_SHA256
    same = [name for name, digest in sorted(original.items()) if (folder / name).exists() and
            hashlib.sha256((folder / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest]
    return {
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "pandas": pd.__version__,
        "mne": mne.__version__,
        "matplotlib": matplotlib.__version__,
        "neural_from_this_repository": folder.is_relative_to(REPO),
        "neural_modules_identical_to_78c9425": len(same),
        "neural_modules": len(original),
        "neural_modules_changed": sorted(set(original) - set(same)),
    }


def report_channels(report):
    """The removed channels in NEURAL's artefact report, as a sorted list."""
    return [] if isinstance(report[4], str) else sorted(str(c) for c in report[4])


def reports_equal(a, b):
    return [float(v) for v in a[:4]] == [float(v) for v in b[:4]] and report_channels(a) == report_channels(b)


def pooled(refs, news):
    if len(refs) == 0:
        return None
    return st.signal_difference(np.concatenate(refs), np.concatenate(news))


def rms_of(arrays):
    v = np.concatenate([np.ravel(a) for a in arrays])
    v = v[np.isfinite(v)]
    return float(np.sqrt(np.mean(v ** 2))) if v.size else 0.0


def median(values):
    values = [v for v in values if v is not None]
    return float(np.median(values)) if values else None


def largest(values):
    values = [v for v in values if v is not None]
    return float(np.max(values)) if values else None


def to_json(value):
    if isinstance(value, dict):
        return {str(k): to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json(v) for v in value]
    if isinstance(value, np.ndarray):
        return to_json(value.tolist())
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else str(float(value))
    return value


def write_json(value, path):
    path.write_text(json.dumps(to_json(value), indent=1, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# One run of the whole pipeline, and comparisons between runs
# ---------------------------------------------------------------------------
def stage_arrays(pre, stages):
    out = {k: pre[k] for k in SIGNAL_STAGES}
    for band in st.BANDS:
        out["band " + st.band_name(band)] = stages["band"][band]
    out["band " + st.band_name(st.FD_BAND) + " (FD)"] = stages["fd_band"]
    for band in st.BANDS:
        out["envelope " + st.band_name(band)] = stages["envelope"][band]
    for band in st.BANDS:
        out["rEEG " + st.band_name(band)] = stages["reeg"][band]
    return out


def full_run(ref, Fs, artefact_mask=None):
    pre = st.run_preprocessing(ref, Fs, artefact_mask)
    stages = st.run_feature_stages(pre["downsampled_frame"], pre["Fs_new"])
    features = st.run_features(pre["downsampled_frame"], pre["Fs_new"])
    return {"pre": pre, "stages": stage_arrays(pre, stages), "features": features}


def perturbed_referential(ref, seed):
    values = st.perturb_ulps(ref.to_numpy(dtype=float), np.random.default_rng([STREAM_SIGNAL, seed]))
    return pd.DataFrame(values, columns=ref.columns, index=ref.index)


def compare_stages(base, run, keys=None):
    keys = keys or list(base["stages"])
    return {k: st.signal_difference(base["stages"][k], run["stages"][k]) for k in keys}


def compare_features(base, run):
    return {f: {level: st.feature_difference(base["features"][f][level], run["features"][f][level])
                for level in base["features"][f]} for f in base["features"]}


def compare_decisions(base_pre, pre):
    b, o = base_pre["decisions"], pre["decisions"]

    def max_abs_change(x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        if x.shape != y.shape or x.size == 0:
            return None
        finite = np.isfinite(x) & np.isfinite(y)
        return float(np.max(np.abs(x[finite] - y[finite]))) if finite.any() else 0.0

    return {
        "same_mask": bool(np.array_equal(base_pre["mask"], pre["mask"])),
        "same_report": reports_equal(base_pre["report"], pre["report"]),
        "mask_samples_changed": int(np.count_nonzero(base_pre["mask"] != pre["mask"])),
        "removed_base": report_channels(base_pre["report"]),
        "removed_run": report_channels(pre["report"]),
        "change_ref_correlation": max_abs_change(b["ref_correlation"], o["ref_correlation"]),
        "change_coupling_ratio": max_abs_change(b["coupling_ratio"], o["coupling_ratio"]),
        "change_envelope_uV": max_abs_change(b["envelopes"], o["envelopes"]),
    }


def decision_margins(pre):
    """How far the unperturbed values are from NEURAL's thresholds."""
    d = pre["decisions"]
    r = np.abs(d["ref_correlation"])
    i = int(np.argmin(np.abs(r - st.PARAMS["ART_REF_LOW_CORR"])))
    env = d["envelopes"]
    return {
        "ref_correlation": float(abs(r[i] - st.PARAMS["ART_REF_LOW_CORR"])),
        "ref_correlation_closest": float(r[i]),
        "coupling_ratio": float(np.min(np.abs(d["coupling_ratio"] - 1))) if d["coupling_ratio"].size else None,
        "envelope_uV": float(np.nanmin(np.abs(env - st.PARAMS["ART_HIGH_VOLT"]))) if env.size else None,
    }


def largest_difference(base, run):
    """The largest absolute difference anywhere (stages, decisions, features); 0 if identical."""
    values = [d.get("max_abs", np.inf) if d.get("same_nan", False) else np.inf
              for d in compare_stages(base, run).values()]
    for f in compare_features(base, run).values():
        values += [lvl["max_abs"] if lvl["same_nan"] else np.inf for lvl in f.values()]
    dec = compare_decisions(base["pre"], run["pre"])
    values += [0.0 if (dec["same_mask"] and dec["same_report"]) else np.inf]
    values += [v for k, v in dec.items() if k.startswith("change_") and v is not None]
    return float(max(values))


def fingerprint(run):
    """SHA-256 of the preprocessed EEG and every feature value, to compare runs exactly."""
    h = hashlib.sha256(np.ascontiguousarray(run["pre"]["downsampled"]).tobytes())
    for f in sorted(run["features"]):
        for level in sorted(run["features"][f]):
            h.update(np.ascontiguousarray(run["features"][f][level]).tobytes())
    return h.hexdigest()


def features_identical(a, b):
    return all(np.array_equal(a[f][level], b[f][level], equal_nan=True) for f in a for level in a[f])


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------
def experiment_A(case, ref, Fs, seeds, forms, edf_path):
    """Stage by stage: perturbed referential EEG through the whole pipeline."""
    result = {"forms": {}, "checks": {}}
    bases = {}
    for form in forms:
        with st.butterworth_variant(form) as variant:
            t = time.perf_counter()
            base = full_run(ref, Fs)
            control = largest_difference(base, full_run(ref, Fs))
            runs = []
            for seed in seeds:
                pert = perturbed_referential(ref, seed)
                run = full_run(pert, Fs)
                decisions = compare_decisions(base["pre"], run["pre"])
                entry = {"seed": seed, "decisions": decisions}
                if not (decisions["same_mask"] and decisions["same_report"]):
                    # A changed artefact decision is a separate effect from rounding:
                    # record its effect, then redo the run with the unperturbed decisions.
                    entry["effect_of_changed_decisions"] = compare_features(base, run)
                    run = full_run(pert, Fs, artefact_mask=base["pre"]["mask"])
                entry["stages"] = compare_stages(base, run)
                entry["features"] = compare_features(base, run)
                runs.append(entry)
            counts = dict(variant.counts)
        log(f"  A  {case:9s} {FORM_LABEL[form]:6s} base + control + {len(seeds)} seeds: {time.perf_counter() - t:.0f} s")
        result["forms"][form] = {"runs": runs, "control_largest_difference": control,
                                 "filter_calls": counts, "margins": decision_margins(base["pre"]),
                                 "fingerprint": fingerprint(base)}
        bases[form] = base

    checks = result["checks"]
    if "ba" in bases:
        base = bases["ba"]
        with st.quiet():
            import mne

            with mne.utils.use_log_level("WARNING"):
                packaged, report = preprocessing_EEG.main_preprocessing(str(edf_path))
        checks["staged_preprocessing_equals_main_preprocessing"] = bool(
            np.array_equal(packaged["eeg_data"].to_numpy(dtype=float), base["pre"]["downsampled"], equal_nan=True)
            and reports_equal(report, base["pre"]["report"]))
        expected = np.where(base["pre"]["mask"], np.nan, base["pre"]["bipolar"])
        checks["artefact_removal_only_inserts_nan"] = bool(
            np.array_equal(expected, base["pre"]["cleaned_by_neural"], equal_nan=True))
        checks["decision_replica_matches_neural"] = bool(
            base["pre"]["decisions"]["predicted_removed"] == report_channels(base["pre"]["report"])
            and base["pre"]["decisions"]["predicted_high_amplitude_percent"] == float(base["pre"]["report"][1]))
        plain = st.run_features(base["pre"]["downsampled_frame"], base["pre"]["Fs_new"])  # no variant installed
        checks["ba_variant_is_transparent"] = features_identical(plain, base["features"])
        checks["removed_channels"] = report_channels(base["pre"]["report"])
    if "sos" in bases:
        counts = result["forms"]["sos"]["filter_calls"]
        checks["sos_used_for_every_butterworth_filter"] = bool(
            counts["filtered in (b, a) form"] == 0 and counts["filtered in SOS form"] > 0)
    if "ba" in bases and "sos" in bases:
        checks["sos_same_artefact_decisions"] = bool(
            np.array_equal(bases["ba"]["pre"]["mask"], bases["sos"]["pre"]["mask"])
            and reports_equal(bases["ba"]["pre"]["report"], bases["sos"]["pre"]["report"]))
        checks["sos_same_preprocessed_eeg"] = bool(
            np.array_equal(bases["ba"]["pre"]["downsampled"], bases["sos"]["pre"]["downsampled"], equal_nan=True))
    return result, bases


def filter_inputs(base_pre, ref):
    """Realistic filter inputs: the 64 s epochs the feature functions filter
    (unperturbed preprocessed EEG, epochs NEURAL skips left out), and the whole
    referential and bipolar channels the artefact checks filter at 256 Hz."""
    eeg = base_pre["downsampled_frame"]
    with st.quiet():
        epochs = [x.copy() for c in st.used_channels(eeg) for x in st.epochs_of(eeg[c], base_pre["Fs_new"])
                  if st.epoch_is_used(x)]
    return {"epochs": epochs,
            "referential": [ref[c].to_numpy(dtype=float, copy=True) for c in ref.columns],
            "bipolar": [base_pre["bipolar"][:, i].copy() for i in range(base_pre["bipolar"].shape[1])]}


def make_filter(lowpass, highpass, order, mode, rate):
    return lambda x: st.butterworth(x, rate, lowpass, highpass, order, mode)


def experiment_B(inputs, seeds):
    """Filter only: 1-4 ULP changes of each filter's input; plus 1-ULP changes of
    the (b, a) coefficients (experiment C at filter level) and the unperturbed
    (b, a) versus SOS outputs (experiment D on real EEG)."""
    rows = {}
    for label, lowpass, highpass, order, mode, source, rate in FILTER_SPECS:
        xs = inputs[source]
        f = make_filter(lowpass, highpass, order, mode, rate)
        nan_free = [i for i, x in enumerate(xs) if not np.isnan(x).any()]
        with st.quiet():
            base = {}
            for form in FORMS:
                with st.butterworth_variant(form):
                    base[form] = [f(x) for x in xs]
            per_seed = []
            for seed in seeds:
                rng = np.random.default_rng([STREAM_FILTER_INPUT, seed])
                xps = [st.perturb_ulps(x, rng) for x in xs]
                entry = {"input": pooled(xs, xps), "input_nan_free": pooled([xs[i] for i in nan_free],
                                                                            [xps[i] for i in nan_free])}
                for form in FORMS:
                    with st.butterworth_variant(form):
                        out = [f(x) for x in xps]
                    entry[form] = pooled(base[form], out)
                    entry[form + "_nan_free"] = pooled([base[form][i] for i in nan_free], [out[i] for i in nan_free])
                # Exact (linear) response to the input change, computed accurately in SOS form.
                # Only for inputs without NaN: the PCHIP filling of NaN gaps is not linear.
                entry["linear_rms_rel"] = None
                if nan_free:
                    with st.butterworth_variant("sos"):
                        linear = [f(xps[i] - xs[i]) for i in nan_free]
                    entry["linear_rms_rel"] = rms_of(linear) / rms_of([base["ba"][i] for i in nan_free])
                with st.butterworth_variant("ba", coefficient_seed=seed):
                    entry["coefficients"] = pooled(base["ba"], [f(x) for x in xs])
                per_seed.append(entry)
        rows[label] = {"per_seed": per_seed, "ba_vs_sos": pooled(base["ba"], base["sos"]),
                       "inputs": len(xs), "inputs_nan_free": len(nan_free), "rate": rate}
    return rows


def dose_response(inputs, dose_seeds):
    """Output difference versus the size of a random input change (clean recording)."""
    out = {}
    for label, lowpass, highpass, order, mode, source, rate in FILTER_SPECS:
        if label not in DOSE_FILTERS:
            continue
        xs = [x for x in inputs[source] if not np.isnan(x).any()]
        f = make_filter(lowpass, highpass, order, mode, rate)
        levels = []
        with st.quiet():
            base = {}
            for form in FORMS:
                with st.butterworth_variant(form):
                    base[form] = [f(x) for x in xs]
            for li, size in enumerate(DOSE_LEVELS):
                entries = []
                for seed in range(1, dose_seeds + 1):
                    rng = np.random.default_rng([STREAM_DOSE, seed, li])
                    xps = [x + size * np.sqrt(np.mean(x ** 2)) * rng.standard_normal(x.shape) for x in xs]
                    entry = {"input": pooled(xs, xps)["rms_rel"]}
                    for form in FORMS:
                        with st.butterworth_variant(form):
                            entry[form] = pooled(base[form], [f(x) for x in xps])["rms_rel"]
                    with st.butterworth_variant("sos"):
                        entry["linear"] = rms_of([f(xp - x) for x, xp in zip(xs, xps)]) / rms_of(base["ba"])
                    entries.append(entry)
                levels.append({"nominal": size, **{k: median([e[k] for e in entries]) for k in entries[0]}})
        out[label] = levels
    return out


def experiment_C(base_ba, seeds):
    """Coefficients: every (b, a) coefficient of the feature band filters moved
    by 1 ULP; same (unperturbed) preprocessed EEG."""
    eeg, Fs = base_ba["pre"]["downsampled_frame"], base_ba["pre"]["Fs_new"]
    runs = []
    for seed in seeds:
        with st.butterworth_variant("ba", coefficient_seed=seed) as variant:
            stages = st.run_feature_stages(eeg, Fs)
            features = st.run_features(eeg, Fs)
            designs = variant.counts["butterworth designs"]
        other = {"pre": base_ba["pre"], "stages": stage_arrays(base_ba["pre"], stages), "features": features}
        runs.append({"seed": seed, "stages": compare_stages(base_ba, other, FEATURE_STAGES),
                     "features": compare_features(base_ba, other), "designs": designs})
    return runs


def test_signal(rate, seconds, seed):
    """Sum of sine waves (some below 0.5 Hz, some near the top of the band) plus
    white noise and an offset; fixed seed."""
    rng = np.random.default_rng([STREAM_TEST_SIGNAL, seed])
    t = np.arange(int(round(seconds * rate))) / rate
    x = 20.0 + 5.0 * rng.standard_normal(t.size)
    for freq in (0.1, 0.3, 0.7, 1.5, 3, 5.5, 9, 12, 18, 25, 29, 31, 40, 60, 90):
        if freq < 0.49 * rate:
            x = x + 10.0 * np.sin(2 * np.pi * freq * t + rng.uniform(0, 2 * np.pi))
    return x


def experiment_D_test_signal():
    """(b, a) versus SOS on a test signal, unperturbed; and the SOS
    forwards-backwards implementation versus scipy.signal.sosfiltfilt."""
    signals = {64: test_signal(64, 64, 1), FS_RECORDING: test_signal(FS_RECORDING, 300, 2)}
    rows, identical = {}, True
    with st.quiet():
        for label, lowpass, highpass, order, mode, source, rate in FILTER_SPECS:
            f = make_filter(lowpass, highpass, order, mode, rate)
            outputs = {}
            for form in FORMS:
                with st.butterworth_variant(form):
                    outputs[form] = f(signals[rate])
            rows[label] = st.signal_difference(outputs["ba"], outputs["sos"])
            for cutoff, btype, n in ((lowpass, "lowpass", order if not isinstance(order, list) else order[0]),
                                     (highpass, "highpass", order if not isinstance(order, list) else order[1])):
                if cutoff:
                    b, a = scipy_signal.butter(n, cutoff / (rate / 2), btype)
                    sos = scipy_signal.butter(n, cutoff / (rate / 2), btype, output="sos")
                    L_pad = 3 * (max(len(b), len(a)) - 1)
                    own = st.sos_filtfilt_like_neural(sos, signals[rate], L_pad)
                    reference = scipy_signal.sosfiltfilt(sos, signals[rate], padtype="odd", padlen=L_pad)
                    identical = identical and bool(np.array_equal(own, reference))
    return rows, identical


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------
def stage_summary(runs, key, measure):
    values = [r["stages"][key][measure] for r in runs if r["stages"][key].get("comparable", True)]
    return median(values), largest(values)


def feature_level_values(runs, feature, level, measure):
    """Per seed: one feature's difference at one output level."""
    return [r["features"][feature][level][measure] for r in runs if level in r["features"][feature]]


def group_values(runs, features, level, measure):
    """Per seed: the largest difference over the given features at one output level."""
    out = []
    for r in runs:
        values = [r["features"][f][level][measure] for f in features if level in r["features"][f]]
        out.append(max(values) if values else None)
    return out


def each_epoch_level(feature_or_group):
    """NEURAL's per-epoch output: each channel and epoch, or for connectivity
    (which compares channel pairs) the value of each epoch."""
    return "median_over_channels" if st.group_of(feature_or_group) == "connectivity" else "each_epoch_and_channel"


def worst_feature(runs, features, level, measure="max_rel"):
    """The feature (and the value) with the largest difference over seeds."""
    best = (None, -1.0, None)
    for f in features:
        for r in runs:
            d = r["features"][f].get(level)
            if d is not None and d[measure] > best[1]:
                best = (f, d[measure], d.get("value_at_max_rel"))
    return best


def figure_values(runs):
    """Per seed: the largest difference relative to the largest value at each
    figure stage (worst band or feature)."""
    groups = [
        ("Input change\n(referential EEG)", ["referential"]),
        ("Bipolar\nmontage", ["bipolar"]),
        ("Artefact\nremoval", ["after_artefact_removal"]),
        ("30 Hz FIR\nlow-pass", ["lowpass"]),
        ("Downsampled\nto 64 Hz", ["downsampled"]),
        ("Band filters\n(worst band)", [k for k in FEATURE_STAGES if k.startswith("band")]),
        ("Squared\nenvelope", [k for k in FEATURE_STAGES if k.startswith("envelope")]),
        ("rEEG\n(2 s ranges)", [k for k in FEATURE_STAGES if k.startswith("rEEG")]),
    ]
    out = []
    for label, keys in groups:
        out.append((label, [max(r["stages"][k]["max_rel"] for k in keys) for r in runs]))
    for label, level in (("Features:\neach epoch", "each_epoch"), ("Features:\nsummary", "summary")):
        values = []
        for r in runs:
            v = 0.0
            for f, levels in r["features"].items():
                key = level if level == "summary" else (
                    "each_epoch_and_channel" if "each_epoch_and_channel" in levels else "median_over_channels")
                v = max(v, levels[key]["scale_rel"])
            values.append(v)
        out.append((label, values))
    return out


# ---------------------------------------------------------------------------
# Report (Markdown) and figure
# ---------------------------------------------------------------------------
def fmt(x):
    if x is None:
        return "-"
    if x == 0:
        return "0"
    mantissa, exponent = f"{x:.1e}".split("e")
    return f"{mantissa}e{int(exponent)}"


def med_max(values):
    return f"{fmt(median(values))} ({fmt(largest(values))})"


def table(header, rows):
    """A Markdown table; '|' inside a cell is escaped so that it does not split the cell."""
    def cell(c):
        return str(c).replace("|", "\\|")

    lines = ["| " + " | ".join(cell(h) for h in header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def roundoff_rule_of_thumb(lowpass, highpass, order, rate):
    """Double-precision resolution (2.2e-16) times the largest gain of the feedback
    part 1/A of each (b, a) stage, max over frequency of 1/|A(e^jw)|; for a band
    filter the larger of its two stages."""
    estimates = []
    orders = order if isinstance(order, list) else [order, order]
    for cutoff, btype, n in ((lowpass, "lowpass", orders[0]), (highpass, "highpass", orders[1])):
        if cutoff:
            _, a = scipy_signal.butter(n, cutoff / (rate / 2), btype)
            _, A = scipy_signal.freqz(a, [1.0], worN=np.linspace(0, np.pi, 2 ** 16))
            estimates.append(np.finfo(float).eps * float(np.max(1 / np.abs(A))))
    return max(estimates)


def nice(label):
    """Ranges such as 0.5-4 Hz with an en dash."""
    return re.sub(r"(?<=\d)-(?=\d)", "–", label)


def build_report(res):
    env, settings, cases = res["environment"], res["settings"], res["cases"]
    n_seeds = len(settings["seeds"])
    md = [BEGIN, "", "## How this run was made", ""]
    md += [
        "- **Inputs:** the two synthetic recordings of the regression tests (`tests/synthetic_edf.py`), "
        "\"clean\" and \"artefacts\": 300 s, 256 Hz, 9 electrodes, whole-number samples. "
        f"Checksums identical to the regression tests' inputs: {'yes' if all(res['inputs_identical'].values()) else 'NO'}. "
        "No real recordings were used.",
        f"- **Perturbation (A):** every non-zero sample of the referential EEG moved by 1 to 4 ULP (random number "
        f"and direction; `np.nextafter`); exact zeros left unchanged. {n_seeds} seeds per recording; the same "
        "perturbed inputs are used for (b, a) and SOS. One ULP (unit in the last place) is the smallest possible "
        "change of a stored number, about 2.2e-16 of its size.",
        "- **Measures:** for signals, max|d| / max|x| (largest difference relative to the largest value) and "
        "RMS(d) / RMS(x); for features, the largest relative difference |d| / |x| over all values that are not zero, "
        "the largest absolute difference |d|, and max|d| / max|x| per feature. NaN positions are compared separately. "
        "\"Median (largest)\" means the median and the largest value over the seeds.",
        f"- **Environment:** {env['os']} ({env['machine']}), Python {env['python']}, numpy {env['numpy']}, "
        f"SciPy {env['scipy']}, pandas {env['pandas']}, MNE {env['mne']}, matplotlib {env['matplotlib']}.",
        f"- **NEURAL code:** {'this repository (`src/`)' if env['neural_from_this_repository'] else 'an installed copy outside this repository'}; "
        f"{env['neural_modules_identical_to_78c9425']} of {env['neural_modules']} modules are identical to the "
        "original commit 78c9425" + (f" (changed: {', '.join('`' + m + '`' for m in env['neural_modules_changed'])}, "
                                     "the pandas 3 compatibility changes)." if env["neural_modules_changed"] else "."),
        "",
    ]

    # checks
    md += ["## Checks", ""]
    rows = []
    check_text = {
        "staged_preprocessing_equals_main_preprocessing":
            "The stage-by-stage pipeline gives exactly the output of `preprocessing_EEG.main_preprocessing`",
        "artefact_removal_only_inserts_nan":
            "Artefact removal only inserts NaN: its output equals the bipolar signal with NaN at the removed samples",
        "decision_replica_matches_neural":
            "The recomputed decision quantities (correlations, coupling powers, envelopes) predict NEURAL's removed "
            "channels and high-amplitude percentage",
        "ba_variant_is_transparent":
            "The filter switch in (b, a) mode changes nothing: features identical to plain NEURAL",
        "sos_used_for_every_butterworth_filter":
            "In SOS mode every Butterworth filter ran in SOS form (no (b, a) filtering left)",
        "sos_same_artefact_decisions": "SOS gives the same artefact decisions as (b, a)",
        "sos_same_preprocessed_eeg": "SOS gives exactly the same preprocessed EEG as (b, a)",
    }
    for key, text in check_text.items():
        vals = [cases[c]["A"]["checks"].get(key) for c in CASES if key in cases[c]["A"]["checks"]]
        if vals:
            rows.append([text, "yes" if all(vals) else "NO"])
    controls = [cases[c]["A"]["forms"][f]["control_largest_difference"] for c in CASES for f in cases[c]["A"]["forms"]]
    rows.append(["Control: the same input run twice gives differences of exactly 0 everywhere",
                 "yes" if all(v == 0 for v in controls) else f"NO (largest {fmt(max(controls))})"])
    if "sos_implementation_identical_to_scipy" in res:
        rows.append(["The SOS forwards-backwards code gives exactly the output of `scipy.signal.sosfiltfilt` "
                     "(odd padding, same padding length)",
                     "yes" if res["sos_implementation_identical_to_scipy"] else "NO"])
    if "original_code" in res:
        oc = res["original_code"]
        where = (f" (all {oc['neural_modules']} modules identical to 78c9425, pandas {oc['pandas']}, numpy "
                 f"{oc['numpy']}, SciPy {oc['scipy']})" if oc.get("neural_modules_identical_to_78c9425") ==
                 oc.get("neural_modules") and "pandas" in oc else "")
        rows.append(["Part A in (b, a) form run with the original NEURAL code" + where + ": every number, the "
                     "fingerprint of the unperturbed outputs and every per-seed difference byte for byte identical",
                     "yes" if oc["identical"] else "NO"])
    md += [table(["Check", "Result"], rows), ""]
    removed = {c: cases[c]["A"]["checks"].get("removed_channels") for c in CASES}
    md += [f"Channels removed by NEURAL: clean {', '.join(removed['clean']) or 'none'}; "
           f"artefacts {', '.join(removed['artefacts']) or 'none'}.", ""]

    # ---- A
    md += ["## A. Where the difference grows: stage by stage", "",
           f"Table A1. RMS(d) / RMS(x) after each stage, median (largest) over {n_seeds} seeds. The input change is "
           "the first row. Rows from \"Band filter\" on are computed inside the feature functions, epoch by epoch.", ""]
    header = ["Stage"] + [f"{c}, {FORM_LABEL[f]}" for c in CASES for f in FORMS if f in cases[c]["A"]["forms"]]
    rows = []
    for key in STAGE_LABEL:
        row = [nice(STAGE_LABEL[key])]
        for c in CASES:
            for f in FORMS:
                if f in cases[c]["A"]["forms"]:
                    runs = cases[c]["A"]["forms"][f]["runs"]
                    m, x = stage_summary(runs, key, "rms_rel")
                    row.append(f"{fmt(m)} ({fmt(x)})")
        rows.append(row)
    md += [table(header, rows), ""]
    md += ["<details>", "<summary>Table A1b. The same with max|d| / max|x|</summary>", ""]
    rows = []
    for key in STAGE_LABEL:
        row = [nice(STAGE_LABEL[key])]
        for c in CASES:
            for f in FORMS:
                if f in cases[c]["A"]["forms"]:
                    m, x = stage_summary(cases[c]["A"]["forms"][f]["runs"], key, "max_rel")
                    row.append(f"{fmt(m)} ({fmt(x)})")
        rows.append(row)
    md += [table(header, rows), "", "</details>", ""]
    md += ["![Largest difference after each stage, (b, a) versus SOS](stage_differences.png)", "",
           f"Figure. Largest difference relative to the largest value after each stage (median over {n_seeds} seeds; "
           "vertical bars: smallest to largest seed). For band filters, envelopes and rEEG the worst band is shown; "
           "for features the worst feature, with max|d| / max|x| per feature. The grey line marks one ULP "
           "relative to the largest value (2.2e-16).", ""]

    # decisions
    md += ["### Artefact decisions", ""]
    lines = []
    for c in CASES:
        for f in FORMS:
            if f in cases[c]["A"]["forms"]:
                runs = cases[c]["A"]["forms"][f]["runs"]
                same = sum(1 for r in runs if r["decisions"]["same_mask"] and r["decisions"]["same_report"])
                lines.append(f"{c}, {FORM_LABEL[f]}: {same} of {len(runs)}")
    md += ["Runs in which the NaN mask, the removed channels and the percentages removed were all identical to the "
           "unperturbed run: " + "; ".join(lines) + ".", ""]
    changed = [(c, f, r) for c in CASES for f in cases[c]["A"]["forms"] for r in cases[c]["A"]["forms"][f]["runs"]
               if not (r["decisions"]["same_mask"] and r["decisions"]["same_report"])]
    if changed:
        md += ["Runs with changed decisions (reported separately; their rounding differences above were measured "
               "with the unperturbed decisions):", ""]
        for c, f, r in changed:
            worst = max((lvl["max_rel"], feat) for feat, levels in r["effect_of_changed_decisions"].items()
                        for lvl in levels.values())
            md.append(f"- {c}, {FORM_LABEL[f]}, seed {r['seed']}: {r['decisions']['mask_samples_changed']} mask entries "
                      f"changed; removed channels {r['decisions']['removed_base']} -> {r['decisions']['removed_run']}; "
                      f"largest feature change {fmt(worst[0])} ({worst[1]}).")
        md.append("")
    md += ["Table A2. Distance of the unperturbed decision quantities from NEURAL's thresholds, and the largest "
           f"change any of the {n_seeds} perturbations caused.", ""]
    rows = []
    specs = [("Referential correlation (0.5–20 Hz filter)", "|r| < 0.15", "ref_correlation", "change_ref_correlation", ""),
             ("Electrode coupling (0.5–20 Hz filter)", "power < 1/4 of hemisphere median", "coupling_ratio",
              "change_coupling_ratio", " (ratio)"),
             ("High amplitude (0.1–40 Hz filter)", "envelope > 1500 µV", "envelope_uV", "change_envelope_uV", " µV")]
    for c in CASES:
        for name, threshold, mkey, ckey, unit in specs:
            row = [c, name, threshold]
            margin = cases[c]["A"]["forms"].get("ba", cases[c]["A"]["forms"][next(iter(cases[c]["A"]["forms"]))])["margins"][mkey]
            row.append(fmt(margin) + unit if margin is not None else "-")
            for f in FORMS:
                if f in cases[c]["A"]["forms"]:
                    row.append(fmt(largest([r["decisions"][ckey] for r in cases[c]["A"]["forms"][f]["runs"]])) + unit)
            rows.append(row)
    md += [table(["Recording", "Decision", "Threshold", "Closest value's distance from threshold"]
                 + [f"Largest change, {FORM_LABEL[f]}" for f in FORMS if f in cases[CASES[0]]["A"]["forms"]], rows), ""]

    # features
    md += ["### Features", "",
           "Tables A3. For each seed, the largest difference over all values and features of a group; shown as "
           f"median (largest) over the {n_seeds} seeds. \"Each epoch\" is every channel and epoch (for connectivity, "
           "which compares channel pairs, every epoch); \"summary\" is NEURAL's `feats_median_all`. \"Relative\" "
           "is |d| / |x|, \"absolute\" is |d| in the feature's own unit. The last column names the feature with the "
           "largest (b, a) relative difference and the feature value where it occurred: relative differences are "
           "largest where values are close to zero.", ""]
    for c in CASES:
        forms = [f for f in FORMS if f in cases[c]["A"]["forms"]]
        md += [f"**{CASE_LABEL[c]}**", ""]
        header = ["Group", "Level"]
        for f in forms:
            header += [f"{FORM_LABEL[f]} relative", f"{FORM_LABEL[f]} absolute"]
        header.append("Largest (b, a) relative difference in")
        rows = []
        for group in st.GROUPS:
            feats = [x for x in st.FEATURES if st.group_of(x) == group]
            for level, level_name in ((each_epoch_level(group), "each epoch"), ("summary", "summary")):
                row = [group if level_name == "each epoch" else "", level_name]
                for f in forms:
                    runs = cases[c]["A"]["forms"][f]["runs"]
                    row += [med_max(group_values(runs, feats, level, "max_rel")),
                            med_max(group_values(runs, feats, level, "max_abs"))]
                if "ba" in forms:
                    name, val, at = worst_feature(cases[c]["A"]["forms"]["ba"]["runs"], feats, level)
                    row.append(f"`{name}` (at {at:.3g})" if name and at is not None and val > 0 else "-")
                else:
                    row.append("-")
                rows.append(row)
        md += [table(header, rows), ""]
    md += ["<details>", f"<summary>Tables A4. Every feature, median (largest) over {n_seeds} seeds</summary>", ""]
    for c in CASES:
        for f in [f for f in FORMS if f in cases[c]["A"]["forms"]]:
            runs = cases[c]["A"]["forms"][f]["runs"]
            rows = []
            for feat in st.FEATURES:
                each = each_epoch_level(feat)
                rows.append([f"`{feat}`",
                             med_max(feature_level_values(runs, feat, each, "max_rel")),
                             med_max(feature_level_values(runs, feat, each, "max_abs")),
                             med_max(feature_level_values(runs, feat, "median_over_channels", "max_rel"))
                             if st.group_of(feat) != "connectivity" else "(as each epoch)",
                             med_max(feature_level_values(runs, feat, "summary", "max_rel")),
                             med_max(feature_level_values(runs, feat, "summary", "max_abs"))])
            md += [f"**{CASE_LABEL[c]}, {FORM_LABEL[f]}**", "",
                   table(["Feature", "Each epoch: relative", "Each epoch: absolute",
                          "Each epoch, median over channels: relative", "Summary: relative", "Summary: absolute"],
                         rows), ""]
    md += ["</details>", ""]

    # ---- B
    if any("B" in cases[c] for c in CASES):
        md += ["## B. Filter only: how much each filter magnifies a tiny input change", "",
               "Each filter was given its realistic input (unperturbed: the 64 s epochs of preprocessed EEG that the "
               "feature functions filter; at 256 Hz, the whole referential or bipolar channels) and the same input "
               f"with every non-zero sample moved by 1–4 ULP ({n_seeds} seeds). \"Gain\" is the output change "
               "divided by the input change (both RMS(d) / RMS(x)). \"Exact response\" is the output change that "
               "exact arithmetic would give: the filter applied to the input change itself (a linear filter's "
               "response to a sum is the sum of the responses), computed in SOS form; \"(b, a) / exact\" above 1 "
               "means the extra difference comes from rounding inside the filter, not from the input change. "
               "\"Rule of thumb\" is a size for that rounding: double-precision resolution (2.2e-16) times the "
               "largest gain of the filter's feedback part, max over frequency of 1/|A(e^jω)| (for band filters "
               "the larger of the two stages); it is computed from the coefficients alone, not measured. "
               "Output changes are median (largest) over the seeds; the other columns are medians.", ""]
        for c in CASES:
            if "B" not in cases[c]:
                continue
            B = cases[c]["B"]
            rows = []
            for label, lowpass, highpass, order, _mode, _source, rate in FILTER_SPECS:
                runs = B[label]["per_seed"]
                rule = roundoff_rule_of_thumb(lowpass, highpass, order, rate)
                in_rel = median([r["input"]["rms_rel"] for r in runs])
                ba = med_max([r["ba"]["rms_rel"] for r in runs])
                sos = med_max([r["sos"]["rms_rel"] for r in runs])
                gain_ba = median([r["ba"]["rms_rel"] / r["input"]["rms_rel"] for r in runs])
                gain_sos = median([r["sos"]["rms_rel"] / r["input"]["rms_rel"] for r in runs])
                exact = median([r["linear_rms_rel"] for r in runs])
                excess = median([r["ba_nan_free"]["rms_rel"] / r["linear_rms_rel"] for r in runs
                                 if r["linear_rms_rel"] and r["ba_nan_free"] is not None])
                reduction = median([r["ba"]["rms_rel"] / r["sos"]["rms_rel"] for r in runs if r["sos"]["rms_rel"] > 0])
                rows.append([nice(label) + (f" ({FILTER_USE[label]})" if label in FILTER_USE else ""),
                             fmt(in_rel), ba, fmt(gain_ba), fmt(exact), fmt(excess), fmt(rule), sos, fmt(gain_sos),
                             fmt(reduction)])
            text = (f"Table B1 ({CASE_LABEL[c].lower()}). Inputs that contain NaN are left out of the two "
                    "\"exact\" columns, because NEURAL fills NaN gaps by PCHIP interpolation, which is not linear: "
                    + ("here every 64 s epoch contains NaN, so those columns exist only for the 256 Hz filters."
                       if c == "artefacts" else "here the last epoch of each channel, which runs past the end of "
                       "the recording and is padded with NaN."))
            block = [text, "", table(["Filter", "Input change", "(b, a) output change", "(b, a) gain", "Exact response",
                                      "(b, a) / exact", "Rule of thumb 2.2e-16 × max 1/|A|", "SOS output change",
                                      "SOS gain", "(b, a) / SOS"], rows), ""]
            if c == "clean":
                md += block
            else:
                md += ["<details>", f"<summary>Table B1 for the {CASE_LABEL[c].lower()}</summary>", ""] + block + ["</details>", ""]
        if "dose" in res:
            md += ["Table B2. Output change (RMS(d) / RMS(x)) for random input changes of increasing size (clean "
                   "recording, Gaussian noise of the given size relative to each input's RMS; median of "
                   f"{settings['dose_seeds']} seeds). For a linear filter computed exactly, the output change "
                   "would grow in proportion to the input change.", ""]
            header = ["Input change"]
            for label in DOSE_FILTERS:
                header += [f"{nice(label)}: (b, a)", "SOS", "exact"]
            rows = []
            for li in range(len(DOSE_LEVELS)):
                row = [fmt(res["dose"][DOSE_FILTERS[0]][li]["input"])]
                for label in DOSE_FILTERS:
                    lv = res["dose"][label][li]
                    row += [fmt(lv["ba"]), fmt(lv["sos"]), fmt(lv["linear"])]
                rows.append(row)
            md += [table(header, rows), ""]

    # ---- C
    if any("C" in cases[c] for c in CASES):
        md += ["## C. Coefficients: does a 1-ULP change of the (b, a) coefficients matter as much?", "",
               "Every coefficient of b and a (except a[0] = 1) was moved by exactly 1 ULP in a random direction, "
               f"the same for every use of a given filter design ({n_seeds} seeds). At filter level (Table C1) the "
               "input is unperturbed; in Table C2 the preprocessed EEG is unperturbed and only the feature band "
               "filters' coefficients change. The artefact-check filters keep their coefficients in Table C2.", ""]
        rows = []
        B = cases["clean"].get("B")
        if B:
            for label, *_ in FILTER_SPECS:
                runs = B[label]["per_seed"]
                rows.append([nice(label), med_max([r["coefficients"]["rms_rel"] for r in runs]),
                             med_max([r["ba"]["rms_rel"] for r in runs])])
            md += ["Table C1 (clean recording, (b, a) form). Output change, RMS(d) / RMS(x), median (largest).", "",
                   table(["Filter", "From 1-ULP coefficient change", "From 1–4 ULP input change (Table B1)"], rows), ""]
        md += ["Table C2. Coefficient change versus the input change of experiment A, both in (b, a) form: band "
               "filter outputs (RMS(d) / RMS(x)) and features (per seed the largest difference over the values and "
               "features of a group), median (largest) over the seeds.", ""]
        for c in CASES:
            if "C" not in cases[c] or "ba" not in cases[c]["A"]["forms"]:
                continue
            C, A = cases[c]["C"], cases[c]["A"]["forms"]["ba"]["runs"]
            rows = []
            for key in FEATURE_STAGES:
                if key.startswith("band"):
                    rows.append([nice(STAGE_LABEL[key]) + " output",
                                 med_max([r["stages"][key]["rms_rel"] for r in C]),
                                 med_max([r["stages"][key]["rms_rel"] for r in A]), "", ""])
            for group in st.GROUPS:
                feats = [x for x in st.FEATURES if st.group_of(x) == group]
                for level, level_name in ((each_epoch_level(group), "each epoch"), ("summary", "summary")):
                    rows.append([f"{group}, {level_name}",
                                 med_max(group_values(C, feats, level, "max_rel")),
                                 med_max(group_values(A, feats, level, "max_rel")),
                                 med_max(group_values(C, feats, level, "max_abs")),
                                 med_max(group_values(A, feats, level, "max_abs"))])
            md += [f"**{CASE_LABEL[c]}**", "",
                   table(["Output", "Coefficient change: relative", "Input change: relative",
                          "Coefficient change: absolute", "Input change: absolute"], rows), ""]

    # ---- D
    if any("D" in cases[c] for c in CASES) or "test_signal" in res:
        md += ["## D. Second-order sections (SOS)", "",
               "The SOS filters are designed with `scipy.signal.butter(..., output='sos')` and applied forwards and "
               "backwards with mat_filtfilt's edge handling (same padding length, odd reflection, steady-state "
               "initial conditions from `scipy.signal.sosfilt_zi`). They replace every Butterworth filter in "
               "NEURAL's pipeline (artefact checks and features). The amplification with SOS is in the SOS columns "
               "of Tables A1, A3 and B1.", "",
               "Table D1. (b, a) versus SOS without any perturbation: how closely the two forms agree.", ""]
        rows = []
        for label, *_ in FILTER_SPECS:
            t = res.get("test_signal", {}).get(label)
            real = cases["clean"].get("B", {}).get(label, {}).get("ba_vs_sos")
            rows.append([nice(label), fmt(t["max_rel"]) if t else "-", fmt(t["rms_rel"]) if t else "-",
                         fmt(real["max_rel"]) if real else "-", fmt(real["rms_rel"]) if real else "-"])
        md += [table(["Filter", "Test signal max|d| / max|x|", "Test signal RMS(d) / RMS(x)",
                      "Clean EEG max|d| / max|x|", "Clean EEG RMS(d) / RMS(x)"], rows), "",
               "Test signal: sine waves from 0.1 Hz to just below half the sample rate, plus white noise and an "
               "offset (64 s at 64 Hz; 300 s at 256 Hz).", ""]
        md += ["Table D2. What switching to SOS changes, without any perturbation: unperturbed SOS versus "
               "unperturbed (b, a) outputs (one comparison, so one number), next to the difference that a 1–4 ULP "
               "input change caused within the (b, a) form (experiment A, median (largest) over the seeds). "
               "Band filter outputs: RMS(d) / RMS(x); features: largest difference over the values and features of "
               "a group.", ""]
        for c in CASES:
            if "D" not in cases[c]:
                continue
            D = cases[c]["D"]
            A = cases[c]["A"]["forms"].get("ba", {}).get("runs", [])
            rows = []
            for key in FEATURE_STAGES:
                if key.startswith("band"):
                    rows.append([nice(STAGE_LABEL[key]) + " output", fmt(D["stages"][key]["rms_rel"]),
                                 med_max([r["stages"][key]["rms_rel"] for r in A]), "", ""])
            for group in st.GROUPS:
                feats = [x for x in st.FEATURES if st.group_of(x) == group]
                for level, level_name in ((each_epoch_level(group), "each epoch"), ("summary", "summary")):
                    rows.append([f"{group}, {level_name}",
                                 fmt(largest([D["features"][x][level]["max_rel"] for x in feats])),
                                 med_max(group_values(A, feats, level, "max_rel")),
                                 fmt(largest([D["features"][x][level]["max_abs"] for x in feats])),
                                 med_max(group_values(A, feats, level, "max_abs"))])
            md += [f"**{CASE_LABEL[c]}**", "",
                   table(["Output", "SOS vs (b, a): relative", "(b, a) input change: relative",
                          "SOS vs (b, a): absolute", "(b, a) input change: absolute"], rows), ""]
        md += ["<details>", "<summary>Table D3. What switching to SOS changes, every feature</summary>", ""]
        for c in CASES:
            if "D" not in cases[c]:
                continue
            D = cases[c]["D"]
            rows = []
            for feat in st.FEATURES:
                each = "median_over_channels" if st.group_of(feat) == "connectivity" else "each_epoch_and_channel"
                d_each, d_sum = D["features"][feat][each], D["features"][feat]["summary"]
                rows.append([f"`{feat}`", fmt(d_each["max_rel"]), fmt(d_each["max_abs"]), fmt(d_each["scale_rel"]),
                             fmt(d_sum["max_rel"]), fmt(d_sum["max_abs"])])
            md += [f"**{CASE_LABEL[c]}**", "",
                   table(["Feature", "Each epoch: relative", "Each epoch: absolute", "Each epoch: max|d| / max|x|",
                          "Summary: relative", "Summary: absolute"], rows), ""]
        md += ["</details>", ""]
    md += [END]
    return "\n".join(md)


def write_report(res):
    text = RESULTS_MD.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise SystemExit(f"{RESULTS_MD.name} has no GENERATED markers; not writing the report.")
    before, rest = text.split(BEGIN, 1)
    after = rest.split(END, 1)[1]
    RESULTS_MD.write_text(before + build_report(res) + after, encoding="utf-8", newline="\n")


def make_figure(res, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    surface, ink, ink2, muted, grid, axis = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
    color = {"ba": "#2a78d6", "sos": "#eb6834"}  # categorical slots 1 and 2 (validated)
    marker = {"ba": "o", "sos": "s"}
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "axes.edgecolor": axis,
                         "axes.labelcolor": ink2, "xtick.color": ink2, "ytick.color": ink2})
    fig, axes = plt.subplots(2, 1, figsize=(11, 8.6), sharex=True, sharey=True, facecolor=surface)
    n_seeds = len(res["settings"]["seeds"])
    labels = []
    for ax, case in zip(axes, CASES):
        ax.set_facecolor(surface)
        forms = [f for f in FORMS if f in res["cases"][case]["A"]["forms"]]
        for k, form in enumerate(forms):
            values = figure_values(res["cases"][case]["A"]["forms"][form]["runs"])
            labels = [v[0] for v in values]
            x = np.arange(len(values)) + (k - (len(forms) - 1) / 2) * 0.12
            med = np.array([np.median(v[1]) for v in values])
            lo = np.array([np.min(v[1]) for v in values])
            hi = np.array([np.max(v[1]) for v in values])
            med = np.where(med > 0, med, np.nan)
            ax.vlines(x, np.where(lo > 0, lo, np.nan), np.where(hi > 0, hi, np.nan), color=color[form], lw=1.2,
                      zorder=2)
            ax.plot(x, med, color=color[form], lw=2, marker=marker[form], ms=8, mec=surface, mew=2,
                    solid_joinstyle="round", solid_capstyle="round", label=FORM_LABEL[form], zorder=3)
            ax.annotate(FORM_LABEL[form], (x[-1], med[-1]), xytext=(12, 0), textcoords="offset points",
                        va="center", color=ink, fontsize=10)  # direct label at the end of each line
        ax.axhline(2.22e-16, color=muted, lw=1, zorder=1)
        ax.annotate("one ULP relative to the largest value (2.2e-16)", (len(labels) - 0.5, 2.22e-16),
                    xytext=(0, 3), textcoords="offset points", ha="right", va="bottom", color=muted, fontsize=8.5)
        ax.set_yscale("log")
        ax.set_ylim(5e-17, 3e-8)
        ax.set_xlim(-0.5, len(labels) - 0.5 + 0.7)
        ax.grid(axis="y", color=grid, lw=0.8, which="major")
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.set_title(CASE_LABEL[case], color=ink, fontsize=11, loc="left")
        ax.set_ylabel("Largest difference / largest value")
    axes[-1].set_xticks(np.arange(len(labels)))
    axes[-1].set_xticklabels(labels, fontsize=9)
    axes[0].legend(frameon=False, loc="upper left", labelcolor=ink)
    fig.suptitle("How a 1–4 ULP change of the input grows through NEURAL's pipeline: "
                 "Butterworth filters in (b, a) form versus second-order sections (SOS)\n"
                 f"Median of {n_seeds} seeds; vertical bars: smallest to largest seed",
                 x=0.01, ha="left", color=ink, fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=150, facecolor=surface, metadata={"Software": None})
    plt.close(fig)


# ---------------------------------------------------------------------------
def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--seeds", type=int, default=10, help="perturbation seeds per condition (default 10)")
    p.add_argument("--dose-seeds", type=int, default=3, help="seeds per level in Table B2 (default 3)")
    p.add_argument("--work-dir", default=str(Path(tempfile.gettempdir()) / "neural_sensitivity"),
                   help="folder for the EDF inputs and the JSON results (outside the repository)")
    p.add_argument("--forms", default="ba,sos", help="filter forms to run: ba, sos or ba,sos")
    p.add_argument("--parts", default="A,B,C,D", help="experiments to run (A is always needed)")
    p.add_argument("--no-report", action="store_true", help="do not write results.md or the figure")
    p.add_argument("--report-from-json", action="store_true",
                   help="do not compute; rebuild results.md and the figure from the JSON files in --work-dir")
    p.add_argument("--original-json", default=None,
                   help="A_ba.json from a run with the original NEURAL (78c9425): reported as identical or not")
    return p.parse_args(argv)


def compare_with_original(res, work, original_json):
    """Is the (b, a) part byte for byte the same as in a run with the original code?"""
    original = Path(original_json).resolve()
    info = {"identical": (work / "A_ba.json").read_bytes() == original.read_bytes()}
    other = original.parent / "other_results.json"
    if other.exists():
        env = json.loads(other.read_text(encoding="utf-8"))["environment"]
        info.update({k: env[k] for k in ("neural_modules_identical_to_78c9425", "neural_modules", "pandas",
                                         "numpy", "scipy", "neural_from_this_repository")})
    res["original_code"] = info


def load_results(work):
    """Rebuild the results from the JSON files written by a full run."""
    other = json.loads((work / "other_results.json").read_text(encoding="utf-8"))
    res = {k: other[k] for k in ("settings", "environment", "inputs_identical")}
    res.update({k: other[k] for k in ("test_signal", "sos_implementation_identical_to_scipy", "dose") if k in other})
    res["cases"] = {case: {"A": {"forms": {}, "checks": other["checks"][case]}} for case in CASES}
    for form in res["settings"]["forms"]:
        a = json.loads((work / f"A_{form}.json").read_text(encoding="utf-8"))
        for case in CASES:
            res["cases"][case]["A"]["forms"][form] = a[case]
    for case in CASES:
        for part in ("B", "C", "D"):
            if f"{part}_{case}" in other:
                res["cases"][case][part] = other[f"{part}_{case}"]
    return res


def main(argv=None):
    args = parse_args(argv)
    seeds = list(range(1, args.seeds + 1))
    forms = [f for f in FORMS if f in args.forms.split(",")]
    parts = set(args.parts.split(",")) | {"A"}
    work = Path(args.work_dir).resolve()
    if work.is_relative_to(REPO):
        raise SystemExit("--work-dir must be outside the repository")
    if args.report_from_json:
        res = load_results(work)
        if args.original_json:
            compare_with_original(res, work, args.original_json)
        write_report(res)
        make_figure(res, FIGURE)
        log(f"Rebuilt {RESULTS_MD.name} and {FIGURE.name} from the JSON files")
        return
    work.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    res = {"settings": {"seeds": seeds, "dose_seeds": args.dose_seeds, "forms": forms, "parts": sorted(parts),
                        "max_ulps": 4, "dose_levels": DOSE_LEVELS},
           "environment": environment(), "cases": {}}
    paths, res["inputs_identical"] = write_inputs(work)
    log(f"NEURAL modules identical to 78c9425: {res['environment']['neural_modules_identical_to_78c9425']} of "
        f"{res['environment']['neural_modules']}; seeds {len(seeds)}; forms {forms}; parts {sorted(parts)}")
    if "D" in parts and set(forms) == set(FORMS):
        res["test_signal"], res["sos_implementation_identical_to_scipy"] = experiment_D_test_signal()

    for case in CASES:
        ref, Fs = st.load_referential(paths[case])
        A, bases = experiment_A(case, ref, Fs, seeds, forms, paths[case])
        res["cases"][case] = {"A": A}
        if "B" in parts and set(forms) == set(FORMS):
            t = time.perf_counter()
            inputs = filter_inputs(bases["ba"]["pre"], ref)
            res["cases"][case]["B"] = experiment_B(inputs, seeds)
            if case == "clean":
                res["dose"] = dose_response(inputs, args.dose_seeds)
            log(f"  B  {case:9s} filter only{' + dose-response' if case == 'clean' else ''}: "
                f"{time.perf_counter() - t:.0f} s")
        if "C" in parts and "ba" in bases:
            t = time.perf_counter()
            res["cases"][case]["C"] = experiment_C(bases["ba"], seeds)
            log(f"  C  {case:9s} coefficients: {time.perf_counter() - t:.0f} s")
        if "D" in parts and set(forms) == set(FORMS):
            res["cases"][case]["D"] = {"stages": compare_stages(bases["ba"], bases["sos"]),
                                       "features": compare_features(bases["ba"], bases["sos"]),
                                       "decisions": compare_decisions(bases["ba"]["pre"], bases["sos"]["pre"])}
        del bases

    # JSON: per-part files (A_ba.json can be compared byte for byte between environments)
    for form in forms:
        write_json({case: res["cases"][case]["A"]["forms"][form] for case in CASES}, work / f"A_{form}.json")
    write_json({"settings": res["settings"], "environment": res["environment"],
                "inputs_identical": res["inputs_identical"],
                "checks": {case: res["cases"][case]["A"]["checks"] for case in CASES},
                **{k: res[k] for k in ("test_signal", "sos_implementation_identical_to_scipy", "dose") if k in res},
                **{f"{part}_{case}": res["cases"][case][part] for case in CASES for part in ("B", "C", "D")
                   if part in res["cases"][case]}}, work / "other_results.json")
    if args.original_json:
        compare_with_original(res, work, args.original_json)
    if not args.no_report:
        write_report(res)
        make_figure(res, FIGURE)
        log(f"Wrote {RESULTS_MD.name} and {FIGURE.name}")
    log(f"JSON results in the work folder; total time {(time.perf_counter() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
