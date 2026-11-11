"""Building blocks for the numerical sensitivity experiment (run_sensitivity.py).

Nothing here changes NEURAL's source code. To try another filter form, the
experiment temporarily replaces, inside NEURAL's `utils` module only, the two
primitives that `utils.filter_butterworth_withnans` uses:

    scipy.signal.butter      designs the (b, a) coefficients
    mfiltfilt.mat_filtfilt   filters forwards and then backwards

NEURAL's own code (NaN handling, edge padding, every calling function) then runs
unchanged, with either
  * second-order sections (SOS): the same Butterworth filter, designed with
    scipy.signal.butter(..., output="sos") and applied forwards-backwards with
    the same padding and initial conditions as mat_filtfilt; or
  * (b, a) coefficients moved by one unit in the last place (ULP).
All other filters (for example the 30 Hz FIR low-pass) are passed through untouched.
"""
import contextlib
import copy
import io
import warnings

import numpy as np
import pandas as pd
from scipy import signal as scipy_signal

from NEURAL_py_EEG import (
    NEURAL_parameters,
    generate_all_features,
    mfiltfilt,
    preprocessing_EEG,
    rEEG,
    utils,
)
from NEURAL_py_EEG.connectivity_features import channel_hemispheres

PARAMS = NEURAL_parameters.NEURAL_parameters()
BANDS = [tuple(band) for band in PARAMS["FREQ_BANDS"]]  # (low, high) cut-offs in Hz
FD_BAND = tuple(PARAMS["FD"]["freq_bands"])  # (0.5, 30)
FS_NEW = 64  # output rate of preprocessing_EEG.main_preprocessing (its default)
FEATURES = [f for f in PARAMS["FEATURE_SET_ALL"] if not f.startswith("IBI")]  # 26 features
GROUPS = ("spectral", "amplitude", "connectivity", "rEEG", "FD")


def group_of(feature):
    """NEURAL's own rule: the feature group is the part of the name before the first '_'."""
    return feature.split("_")[0]


def band_name(band):
    return "%g-%g Hz" % band


def quiet():
    """NEURAL prints progress messages and some warnings; keep the console readable."""
    stack = contextlib.ExitStack()
    stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
    stack.enter_context(warnings.catch_warnings())
    warnings.simplefilter("ignore")
    return stack


# ---------------------------------------------------------------------------
# Perturbations
# ---------------------------------------------------------------------------
def perturb_ulps(x, rng, max_ulps=4):
    """A copy of x with every finite, non-zero value moved by 1 to max_ulps ULP
    (chosen at random) in a random direction, using np.nextafter.

    One ULP is the gap between a number and the next representable double; for
    a value v it is about 2.2e-16 * |v|. Exact zeros are left unchanged: moving
    0 by one ULP gives a subnormal number (about 5e-324) that no rounding of a
    real computation would produce, and the synthetic artefacts contain exact
    zeros that NEURAL's flat-signal checks look for."""
    x = np.asarray(x, dtype=float)
    steps = rng.integers(1, max_ulps + 1, size=x.shape)
    direction = np.where(rng.random(x.shape) < 0.5, -np.inf, np.inf)
    movable = np.isfinite(x) & (x != 0)
    y = x.copy()
    for step in range(max_ulps):
        move = movable & (steps > step)
        y[move] = np.nextafter(y[move], direction[move])
    return y


def perturb_coefficients(b, a, rng):
    """(b, a) with every coefficient moved by exactly 1 ULP in a random
    direction, except a[0], which stays 1."""
    b = np.array(b, dtype=float)
    a = np.array(a, dtype=float)
    b_new = np.nextafter(b, np.where(rng.random(b.shape) < 0.5, -np.inf, np.inf))
    a_new = a.copy()
    a_new[1:] = np.nextafter(a[1:], np.where(rng.random(a.shape[0] - 1) < 0.5, -np.inf, np.inf))
    return b_new, a_new


def _design_seed(seed, N, Wn, btype):
    """A fixed random-number seed for one filter design, so that a given design
    always gets the same perturbed coefficients within one run."""
    bits = int(np.float64(Wn).view(np.uint64))
    return [int(seed), int(N), bits & 0xFFFFFFFF, bits >> 32, 0 if str(btype).startswith("low") else 1]


# ---------------------------------------------------------------------------
# Butterworth filter variants (SOS form, or perturbed (b, a) coefficients)
# ---------------------------------------------------------------------------
def sos_filtfilt_like_neural(sos, x, L_pad):
    """Forwards-backwards filtering in second-order sections with the edge
    handling of NEURAL's mfiltfilt.mat_filtfilt: L_pad samples of odd
    reflection at each end, steady-state initial conditions (from
    scipy.signal.sosfilt_zi) scaled by the first sample of each pass, and the
    padding removed at the end."""
    x = np.asarray(x, dtype=float)
    x_pad = np.concatenate((2 * x[0] - x[1:(L_pad + 1)][::-1],
                            x,
                            2 * x[-1] - x[len(x) - L_pad - 1:-1][::-1]))
    zi = scipy_signal.sosfilt_zi(sos)
    y, _ = scipy_signal.sosfilt(sos, x_pad, zi=zi * x_pad[0])
    y = y[::-1]
    y, _ = scipy_signal.sosfilt(sos, y, zi=zi * y[0])
    y = y[::-1]
    return y[L_pad:len(x) + L_pad]


class ButterworthVariant:
    """What NEURAL's Butterworth filters do inside a `butterworth_variant` block.

    form "ba":  NEURAL as it is: (b, a) coefficients, mfiltfilt.mat_filtfilt.
    form "sos": every Butterworth design is also made in SOS form and applied
                with sos_filtfilt_like_neural (same padding length L_pad).
    coefficient_seed: if not None (form "ba" only), every (b, a) design gets
                its coefficients moved by 1 ULP (fixed per design and seed)."""

    def __init__(self, form="ba", coefficient_seed=None):
        if form not in ("ba", "sos"):
            raise ValueError("form must be 'ba' or 'sos'")
        if form == "sos" and coefficient_seed is not None:
            raise ValueError("coefficient perturbation is only defined for the (b, a) form")
        self.form = form
        self.coefficient_seed = coefficient_seed
        self.counts = {"butterworth designs": 0, "filtered in SOS form": 0,
                       "filtered in (b, a) form": 0, "other filters passed through": 0}
        self._sos_by_coefficients = {}
        self._original_mat_filtfilt = mfiltfilt.mat_filtfilt

    def design(self, N, Wn, btype="low", analog=False, output="ba", fs=None):
        if analog or output != "ba" or fs is not None:
            raise ValueError("unexpected scipy.signal.butter call: %r" % ((N, Wn, btype, analog, output, fs),))
        b, a = scipy_signal.butter(N, Wn, btype)
        self.counts["butterworth designs"] += 1
        if self.coefficient_seed is not None:
            b, a = perturb_coefficients(b, a, np.random.default_rng(_design_seed(self.coefficient_seed, N, Wn, btype)))
        if self.form == "sos":
            sos = scipy_signal.butter(N, Wn, btype, output="sos")
            self._sos_by_coefficients[(np.asarray(b, float).tobytes(), np.asarray(a, float).tobytes())] = sos
        return b, a

    def filtfilt(self, b, a, x):
        sos = self._sos_by_coefficients.get((np.asarray(b, float).tobytes(), np.asarray(a, float).tobytes()))
        if sos is not None:
            self.counts["filtered in SOS form"] += 1
            L_pad = 3 * (max(len(b), len(a)) - 1)  # the padding mat_filtfilt uses for this (b, a) design
            return sos_filtfilt_like_neural(sos, x, L_pad)
        if len(a) > 1:
            self.counts["filtered in (b, a) form"] += 1
        else:
            self.counts["other filters passed through"] += 1  # FIR filters, e.g. the 30 Hz low-pass
        return self._original_mat_filtfilt(b, a, x)


class _SignalModule:
    """Stands in for scipy.signal inside NEURAL's utils module; only butter() differs."""

    def __init__(self, variant):
        self._variant = variant

    def __getattr__(self, name):
        return getattr(scipy_signal, name)

    def butter(self, *args, **kwargs):
        return self._variant.design(*args, **kwargs)


class _MfiltfiltModule:
    """Stands in for NEURAL's mfiltfilt module inside utils; only mat_filtfilt() differs."""

    def __init__(self, variant):
        self._variant = variant

    def __getattr__(self, name):
        return getattr(mfiltfilt, name)

    def mat_filtfilt(self, b, a, x):
        return self._variant.filtfilt(b, a, x)


@contextlib.contextmanager
def butterworth_variant(form="ba", coefficient_seed=None):
    """Within this block, every call of NEURAL's utils.filter_butterworth_withnans
    (artefact checks and features alike) uses the chosen variant."""
    variant = ButterworthVariant(form, coefficient_seed)
    saved = (utils.signal, utils.mfiltfilt)
    utils.signal = _SignalModule(variant)
    utils.mfiltfilt = _MfiltfiltModule(variant)
    try:
        yield variant
    finally:
        utils.signal, utils.mfiltfilt = saved


def butterworth(x, Fs, lowpass, highpass, order=5, mode="nans"):
    """NEURAL's utils.filter_butterworth_withnans on a copy of x ([] = no such cut-off)."""
    return utils.filter_butterworth_withnans(np.array(x, dtype=float), Fs, lowpass, highpass, order, mode)[0]


# ---------------------------------------------------------------------------
# NEURAL's pipeline, stage by stage
# ---------------------------------------------------------------------------
def load_referential(edf_path):
    """Read an EDF file as NEURAL does (preprocessing_EEG.load_edf_EEG_file)."""
    import mne

    with mne.utils.use_log_level("WARNING"), quiet():
        data, ch_fs = preprocessing_EEG.load_edf_EEG_file(str(edf_path))
    return data, ch_fs[0]


def run_preprocessing(ref, Fs, artefact_mask=None):
    """preprocessing_EEG.main_preprocessing, step by step (same calls, same
    order), keeping every intermediate result.

    artefact_mask (optional, True = removed; samples x bipolar channels): use
    these artefact decisions instead of this run's own. remove_artefacts only
    inserts NaN into the bipolar signal (checked in run_sensitivity.py), so this
    equals its output whenever the decisions are the same. It lets a change in
    the decisions be separated from rounding differences."""
    ref = ref.copy()
    with quiet():
        montage, _ = utils.set_bi_montage(ref, Fs)
        cleaned, report = preprocessing_EEG.remove_artefacts(
            montage.copy(), np.array(list(montage.columns)), Fs, ref, np.array(list(ref.columns))
        )
        decisions = decision_quantities(ref, montage, Fs)
        mask = np.isnan(cleaned.to_numpy(dtype=float))
        if artefact_mask is None:
            used = cleaned
        else:
            values = montage.to_numpy(dtype=float, copy=True)
            values[artefact_mask] = np.nan
            used = pd.DataFrame(values, columns=montage.columns, index=montage.index)
        lowpassed = preprocessing_EEG.LPF_zero_phase(used.copy(), Fs)
        downsampled, Fs_new = preprocessing_EEG.signal_downsample(lowpassed.copy(), Fs, FS_NEW)
    return {
        "Fs": Fs,
        "Fs_new": Fs_new,
        "referential": ref.to_numpy(dtype=float, copy=True),
        "bipolar": montage.to_numpy(dtype=float, copy=True),
        "cleaned_by_neural": cleaned.to_numpy(dtype=float, copy=True),
        "after_artefact_removal": used.to_numpy(dtype=float, copy=True),
        "lowpass": lowpassed.to_numpy(dtype=float, copy=True),
        "downsampled_frame": downsampled,
        "downsampled": downsampled.to_numpy(dtype=float, copy=True),
        "mask": mask,
        "report": report,
        "decisions": decisions,
    }


def decision_quantities(ref, montage, Fs):
    """The filtered quantities behind NEURAL's artefact decisions, recomputed
    with the same calls as preprocessing_EEG.remove_artefacts (referential
    low-correlation and electrode-coupling checks, 0.5-20 Hz filter) and
    art_per_channel (high-amplitude check, 0.1-40 Hz filter), so that their
    distance from the thresholds can be reported. The channels this predicts
    to be removed are compared with NEURAL's own report in run_sensitivity.py."""
    labels_ref = list(ref.columns)
    labels_bi = np.array(list(montage.columns))
    N = len(montage)

    # remove_artefacts, step 0: referential low-correlation check
    x_filt = np.zeros([len(labels_ref), N])
    for ch, name in enumerate(labels_ref):
        x_filt[ch, :] = butterworth(ref[name].to_numpy(dtype=float, copy=True), Fs, 20, 0.5, 5, "linear_interp")
    r = np.corrcoef(x_filt)
    np.fill_diagonal(r, np.nan)
    r_channel = np.nanmean(r, axis=0)
    removed = []
    for idx in np.where(np.abs(r_channel) < PARAMS["ART_REF_LOW_CORR"])[0]:
        removed += [i for i, label in enumerate(labels_bi) if labels_ref[idx] in label]

    # remove_artefacts, step 1: electrode coupling. NEURAL removes every channel
    # in this list (its index array is two-dimensional), so do the same here.
    keep = np.delete(np.arange(len(labels_bi)), removed)
    coupling_ratio = np.array([])
    if len(keep) > 4:
        ileft, iright = channel_hemispheres(labels_bi[keep])
        if len(ileft) > 1 and len(iright) > 1:
            power = np.array([
                np.nanmean(np.abs(butterworth(montage[labels_bi[i]].to_numpy(dtype=float, copy=True),
                                              Fs, 20, 0.5, 5, "linear_interp")) ** 2)
                for i in keep
            ])
            cut_left, cut_right = np.median(power[ileft]) / 4, np.median(power[iright]) / 4
            coupling_ratio = np.concatenate([power[ileft] / cut_left, power[iright] / cut_right])
            short = np.concatenate([keep[ileft][power[ileft] < cut_left], keep[iright][power[iright] < cut_right]])
            removed += [int(i) for i in short]

    # art_per_channel, check 2: high-amplitude envelope of the 0.1-40 Hz filtered channel
    keep = np.delete(np.arange(len(labels_bi)), removed)
    envelopes = np.full([len(keep), N], np.nan)
    percent = []
    collar = int(PARAMS["ART_TIME_COLLAR"] * Fs)
    for row, i in enumerate(keep):
        x = montage[labels_bi[i]].to_numpy(dtype=float, copy=True)
        x_channel = x.copy()
        x_channel[np.where(x_channel != 0)] = 1
        lens, istart, iend = utils.len_cont_zeros(x_channel, 0)
        for m in np.where(lens >= PARAMS["ART_ELEC_CHECK"] * Fs)[0]:
            x[np.clip(np.arange(istart[m] - 1, iend[m] + 2), 0, N - 1)] = np.nan
        envelope = np.abs(scipy_signal.hilbert(butterworth(x, Fs, 40, 0.1, [5, 2], "linear_interp")))
        envelopes[row, :] = envelope
        removed_samples = np.zeros(N)
        for p in np.where(envelope > PARAMS["ART_HIGH_VOLT"])[0]:
            removed_samples[np.clip(np.arange(p - collar, p + collar + 1), 0, N - 1)] = 1
        percent.append(100 * np.sum(removed_samples) / N)

    return {
        "ref_correlation": r_channel,
        "coupling_ratio": coupling_ratio,  # channel power / (median power of its hemisphere / 4)
        "envelopes": envelopes,
        "predicted_removed": sorted(set(str(labels_bi[i]) for i in removed)),
        "predicted_high_amplitude_percent": max(percent) if percent else 0.0,
    }


def epochs_of(eeg_column, Fs):
    """The 64 s epochs (50 % overlap) generate_all_features makes from one channel."""
    return generate_all_features.overlap_epochs(eeg_column, Fs, PARAMS["EPOCH_LENGTH"], PARAMS["EPOCH_OVERLAP"])


def epoch_is_used(x):
    """generate_all_features skips an epoch with EPOCH_IGNORE_PRC_NANS % or more NaN."""
    return 100 * np.count_nonzero(np.isnan(x)) / len(x) < PARAMS["EPOCH_IGNORE_PRC_NANS"]


def used_channels(eeg):
    """generate_all_features drops channels that are entirely NaN (removed as artefact)."""
    return [c for c in eeg.columns if not np.all(np.isnan(eeg[c].to_numpy(dtype=float)))]


def run_feature_stages(eeg, Fs):
    """The filtered signals inside NEURAL's feature functions, epoch by epoch,
    made with the same calls: the band filter of main_amplitude, main_rEEG and
    connectivity_corr (each band), the squared Hilbert envelope of
    amplitude_env_mean / _SD, the 2 s ranges of rEEG.gen_rEEG, and main_fd's
    0.5-30 Hz filter. Skipped epochs are left as NaN."""
    mode = PARAMS["amplitude"]["FILTER_REPLACE_ARTEFACTS"]  # 'nans', as for rEEG, FD and connectivity
    p = PARAMS["rEEG"]
    out = {"band": {b: [] for b in BANDS}, "envelope": {b: [] for b in BANDS},
           "reeg": {b: [] for b in BANDS}, "fd_band": []}
    with quiet():
        for channel in used_channels(eeg):
            x_epochs = epochs_of(eeg[channel], Fs)
            for x in x_epochs:
                used = epoch_is_used(x)
                for band in BANDS:
                    if used:
                        y = butterworth(x, Fs, band[1], band[0], 5, mode)
                        envelope = np.abs(scipy_signal.hilbert(y[~np.isnan(y)])) ** 2
                        reeg = np.asarray(rEEG.gen_rEEG(y, p["overlap"], p["L_window"], p["window_type"], Fs,
                                                        p["APPLY_LOG_LINEAR_SCALE"]), dtype=float)
                    else:
                        y = np.full(len(x), np.nan)
                        envelope = np.array([])
                        reeg = np.full(int(len(x) / (p["L_window"] * Fs)), np.nan)
                    out["band"][band].append(y)
                    out["envelope"][band].append(envelope)
                    out["reeg"][band].append(reeg)
                out["fd_band"].append(butterworth(x, Fs, FD_BAND[1], FD_BAND[0], 5, mode) if used
                                      else np.full(len(x), np.nan))
    return {
        "band": {b: np.vstack(v) for b, v in out["band"].items()},
        "envelope": {b: np.concatenate(v) for b, v in out["envelope"].items()},
        "reeg": {b: np.vstack(v) for b, v in out["reeg"].items()},
        "fd_band": np.vstack(out["fd_band"]),
    }


def run_features(eeg, Fs, features=FEATURES):
    """NEURAL's generate_all_features, one feature per call (as the regression
    tests do), so that the per-epoch, per-channel values of every feature are
    kept (NEURAL returns them only for the last feature of a call)."""
    data = {"eeg_data": eeg, "Fs": Fs, "ch_labels": list(eeg.columns)}
    out = {}
    with quiet():
        for feature in features:
            per_epochs, names, feat_st, median_ch, median_all = generate_all_features.generate_all_features(
                copy.deepcopy(data), feat_set=[feature]
            )
            columns = [n for n in names if n.startswith(feature + "__")]
            result = {
                "summary": median_all[columns].to_numpy(dtype=float)[0],
                "median_over_channels": median_ch[columns].to_numpy(dtype=float),
            }
            if group_of(feature) != "connectivity":
                result["each_epoch_and_channel"] = np.asarray(per_epochs, dtype=float)
            out[feature] = result
    return out


# ---------------------------------------------------------------------------
# Difference measures
# ---------------------------------------------------------------------------
def _rms(v):
    return float(np.sqrt(np.mean(np.square(v)))) if v.size else 0.0


def signal_difference(ref, new):
    """Scale-aware difference between two signals (NaN ignored): the largest
    difference relative to the largest value, max|d| / max|x|, and the RMS of
    the difference relative to the RMS of the signal, RMS(d) / RMS(x)."""
    ref = np.asarray(ref, dtype=float)
    new = np.asarray(new, dtype=float)
    if ref.shape != new.shape:
        return {"same_nan": False, "comparable": False}
    finite = np.isfinite(ref) & np.isfinite(new)
    d = new[finite] - ref[finite]
    r = ref[finite]
    max_ref, rms_ref = (float(np.max(np.abs(r))), _rms(r)) if r.size else (0.0, 0.0)
    return {
        "same_nan": bool(np.array_equal(np.isnan(ref), np.isnan(new))),
        "comparable": True,
        "max_abs": float(np.max(np.abs(d))) if d.size else 0.0,
        "max_rel": float(np.max(np.abs(d))) / max_ref if d.size and max_ref > 0 else 0.0,
        "rms_rel": _rms(d) / rms_ref if rms_ref > 0 else 0.0,
    }


def feature_difference(ref, new):
    """For feature values: the largest relative difference |d| / |x| (over
    values that are not zero), the largest absolute difference |d|, and the
    largest difference relative to the largest value of that feature,
    max|d| / max|x| (not inflated by values near zero)."""
    ref = np.asarray(ref, dtype=float)
    new = np.asarray(new, dtype=float)
    finite = np.isfinite(ref) & np.isfinite(new)
    d = np.abs(new[finite] - ref[finite])
    r = np.abs(ref[finite])
    out = {"same_nan": bool(ref.shape == new.shape and np.array_equal(np.isnan(ref), np.isnan(new))),
           "max_abs": float(d.max()) if d.size else 0.0,
           "max_rel": 0.0, "value_at_max_rel": None,
           "scale_rel": float(d.max() / r.max()) if d.size and r.max() > 0 else 0.0}
    nonzero = r > 0
    if nonzero.any():
        rel = d[nonzero] / r[nonzero]
        i = int(np.argmax(rel))
        out["max_rel"] = float(rel[i])
        out["value_at_max_rel"] = float(ref[finite][nonzero][i])
    return out
