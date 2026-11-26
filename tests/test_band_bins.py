"""spectral_features.band_bins: the FFT bins of a frequency band, as in
neural_eeg_features 0.6.1 (the reference package; its spectral.band_slice and
docs/definitions.md, "Feature conventions retained from version 0.1"):

each band uses the bins ceil(low * N / Fs) to floor(high * N / Fs), inclusive,
independently of the other bands, with two floating-point steps allowed at
each edge for roundoff, and at most the Nyquist bin N // 2.

Before, as in MATLAB NEURAL, each later band started at the previous band's
last bin (chained_bins below, copied from the old code). For non-empty,
unclipped band selections whose edges are not within about two
floating-point steps of a bin, the two rules select the same bins exactly
when, for every band after the first, its first bin ceil(low * N / Fs) is
the previous band's last bin floor(high * N / Fs), i.e.
the two edges fall within the same bin step (usually: the same edge, exactly
on a bin); the first band's lower edge and the last band's upper edge do not
matter. A band left empty under both rules can agree although the equation
fails, and edges within about two floating-point steps of a bin can agree or
differ (test_edges_near_a_bin_can_round_differently).

Bands are checked as in the reference package: a band whose upper edge is not
above its lower edge, or not below the Nyquist frequency, raises ValueError
naming the band; a valid band with no bins gives NaN, without warnings.

The settings are those of the original NEURAL (commit 78c9425), passed
explicitly (neural_outputs.original_settings()): the recorded values below
and the stored reference files were made with them.

Synthetic values only.
"""
import json
import math
import re
import warnings
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

import neural_outputs
from NEURAL_py_EEG import NEURAL_parameters, connectivity_features, generate_all_features, spectral_features

DATA = Path(__file__).parent / "data"
DEFAULT_BANDS = [[0.5, 4], [4, 7], [7, 13], [13, 30]]
FS = 64
BIN_FEATURES = ["spectral_flatness", "spectral_entropy", "spectral_diff", "spectral_edge_frequency",
                "connectivity_BSI", "connectivity_coh_mean"]
SPECTRAL_FEATURES = ["spectral_power", "spectral_relative_power", "spectral_flatness", "spectral_entropy",
                     "spectral_diff", "spectral_edge_frequency"]
CONNECTIVITY_FEATURES = ["connectivity_BSI", "connectivity_coh_mean"]
LABELS = np.array(["C3_O1", "C4_O2"])


def chained_bins(freq_bands, n_fft, Fs):
    """The previous rule (MATLAB NEURAL and the original Python port), as in
    the old spectral_features.spectral_flatness: the first band from
    ceil(low * f_scale), each later band from the previous band's last bin."""
    f_scale = n_fft / Fs
    n_bins = n_fft // 2 + 1
    result, ibandpass = [], []
    for p in range(len(freq_bands)):
        if p == 0:
            istart = np.ceil(freq_bands[p][0] * f_scale).astype(int) - 1
        else:
            istart = ibandpass[-1] - 1
        ibandpass = np.array(range(istart, np.floor(freq_bands[p][1] * f_scale).astype(int))) + 1
        ibandpass[ibandpass < 0] = 0
        ibandpass[ibandpass > n_bins - 1] = n_bins - 1
        result.append(ibandpass.tolist())
    return result


def bins(freq_bands, n_fft, Fs):
    return [spectral_features.band_bins(low, high, n_fft, Fs).tolist() for low, high in freq_bands]


def span(first, last):
    return list(range(first, last + 1))


def signals(seconds=64, with_nan=False):
    """Two seeded synthetic channels at 64 Hz (a left/right pair)."""
    rng = np.random.default_rng(11)
    t = np.arange(seconds * FS) / FS
    x = np.vstack([np.sin(2 * np.pi * 3 * t) + 0.5 * np.sin(2 * np.pi * 10 * t) + rng.normal(size=t.size),
                   np.sin(2 * np.pi * 3 * t + 0.4) + 0.3 * np.sin(2 * np.pi * 21 * t) + rng.normal(size=t.size)])
    if with_nan:
        x[:, 1000:1033] = np.nan  # 33 samples: shortens a NaN-removed spectrum to an off-grid length
    return x


def feature(name, x, bands=None, total=None, Fs=FS, **settings):
    """One feature through NEURAL's own entry points (main_spectral or
    main_connectivity), with a fresh copy of the original settings."""
    group = "connectivity" if name.startswith("connectivity") else "spectral"
    params = neural_outputs.original_settings()[group]
    if bands is not None:
        params["freq_bands"] = [list(b) for b in bands]
    if total is not None:
        params["total_freq_bands"] = list(total)
    params.update(settings)
    if group == "spectral":
        return np.atleast_1d(np.asarray(spectral_features.main_spectral(x[0].copy(), Fs, name, params), float))
    return np.atleast_1d(np.asarray(connectivity_features.main_connectivity(x.copy(), Fs, name, LABELS, params),
                                    float))


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------
def test_docstring_example():
    assert spectral_features.band_bins(4, 7, 128, 64).tolist() == span(8, 14)


@pytest.mark.parametrize("n_fft", [64, 128, 512, 4096], ids=["1 bin/Hz", "2 bins/Hz", "8 bins/Hz", "64 bins/Hz"])
def test_default_bands_on_the_bin_grid_are_unchanged(n_fft):
    """At 64 Hz with whole-second windows every default band edge is a bin,
    so both rules give the same bins (the shared boundary bin included)."""
    assert bins(DEFAULT_BANDS, n_fft, 64) == chained_bins(DEFAULT_BANDS, n_fft, 64)


def test_shared_boundary_bin_on_the_grid():
    delta, theta = bins(DEFAULT_BANDS[:2], 128, 64)
    assert delta[-1] == theta[0] == 8  # 4 Hz is bin 8 at 2 bins per Hz: in both bands


def test_reference_package_example():
    """docs/definitions.md of the reference package: a 4 Hz tone in a
    16-second epoch at 98 Hz contributes bin 64 to both delta and theta."""
    n_fft = 16 * 98
    delta, theta = bins(DEFAULT_BANDS[:2], n_fft, 98)
    assert delta[-1] == theta[0] == 64


@pytest.mark.parametrize("n_fft, expected, extra_bins_before", [
    # 4000 samples at 64 Hz: 62.5 bins per Hz; 7 Hz and 13 Hz lie between bins.
    (4000, [span(32, 250), span(250, 437), span(438, 812), span(813, 1875)], [[], [], [437], [812]]),
    # 3999 samples: 4, 7 and 13 Hz all lie between bins.
    (3999, [span(32, 249), span(250, 437), span(438, 812), span(813, 1874)], [[], [249], [437], [812]]),
])
def test_off_grid_edges(n_fft, expected, extra_bins_before):
    """Each band starts at its own lower edge. The previous rule also took
    the bin just below the edge (the previous band's last bin)."""
    assert bins(DEFAULT_BANDS, n_fft, 64) == expected
    old = chained_bins(DEFAULT_BANDS, n_fft, 64)
    for new_band, old_band, extra in zip(expected, old, extra_bins_before):
        assert sorted(set(old_band) - set(new_band)) == extra
        assert set(new_band) <= set(old_band)


def test_non_integer_rate_moves_default_bands_off_the_grid():
    """At 63.93 Hz a 2 s window has 127 samples (1.987 bins per Hz): theta's
    lower edge (4 Hz = bin 7.95) is between bins. The previous rule started
    theta at bin 7 (delta's last bin); now it starts at bin 8."""
    n_fft = math.floor(2 * 63.93)
    assert n_fft == 127
    assert chained_bins(DEFAULT_BANDS, n_fft, 63.93)[1][0] == 7
    assert bins(DEFAULT_BANDS, n_fft, 63.93)[1][0] == 8


def same_bins_condition(freq_bands, n_fft, Fs):
    """In exact arithmetic: for every band after the first, ceil(low * N / Fs)
    equals floor(high_previous * N / Fs)."""
    def position(x):
        return Fraction(x) * n_fft / Fraction(Fs)
    return all(math.ceil(position(freq_bands[i][0])) == math.floor(position(freq_bands[i - 1][1]))
               for i in range(1, len(freq_bands)))


@pytest.mark.parametrize("bands, same", [
    ([[1.1, 2], [2, 3.1]], True),   # shared edge on a bin; first and last edges anywhere
    ([[1, 2], [5, 6]], False),      # disjoint
    ([[1, 2.25], [2.25, 3]], False),  # shared edge between bins
    ([[1.5, 9.0], [8.535, 25.0]], True),  # overlapping, but both edges in the same bin step
    ([[1.5, 9.0], [8.4, 25.0]], False),   # overlapping by more than that
])
def test_rules_agree_examples(bands, same):
    """64 Hz, 128-point FFT (2 bins per Hz)."""
    assert (bins(bands, 128, 64) == chained_bins(bands, 128, 64)) is same
    assert same_bins_condition(bands, 128, 64) is same


def test_rules_agree_exactly_when_the_condition_holds():
    """Seeded random band sets (2 to 4 bands) whose edges are on bins, between
    bins (at least 1 % of a bin away), disjoint or overlapping, on grids where
    the bins are exact binary fractions (so no edge is within a few
    floating-point steps of a bin): the two rules select the same bins if and
    only if same_bins_condition holds.

    The draws leave out edges within about two floating-point steps of a bin
    (the grids are exact and off-bin edges are at least 1 % of a bin away),
    clipped selections (every edge is at least 1.5 bins from bin 0 and from
    the Nyquist bin) and band sets the old rule cannot process after an empty
    band (skipped below). Empty selections are not excluded: a few draws keep
    a band that is empty under the new rule, and the equivalence assertion
    passed for them.
    """
    
    rng = np.random.default_rng(2026)
    grids = [(64, 128), (64, 512), (64, 4096), (256, 512), (100, 200), (128, 1024)]
    agree = differ = 0
    for _ in range(3000):
        Fs, n_fft = grids[rng.integers(len(grids))]
        step = Fraction(Fs, n_fft)  # Hz per bin, an exact binary fraction
        count = int(rng.integers(2, 5))
        cuts = np.sort(rng.choice(np.arange(3, n_fft // 2 - 3), size=count + 1, replace=False)).tolist()
        edges = [[Fraction(cuts[i]), Fraction(cuts[i + 1])] for i in range(count)]
        for i in range(1, count):
            # in bins; 0 (a third of the time) keeps a shared edge on a bin
            shift = Fraction(0) if rng.integers(3) == 0 else Fraction(int(rng.integers(-150, 151)), 100)
            if rng.integers(2):
                edges[i][0] += shift  # gap or overlap
            else:
                edges[i][0] = edges[i - 1][1] = edges[i][0] + shift  # shared edge, on or off a bin
        bands = [[float(lo * step), float(hi * step)] for lo, hi in edges]
        if not all(0 < lo < hi < Fs / 2 for lo, hi in bands):
            continue
        try:
            old = chained_bins(bands, n_fft, Fs)
        except IndexError:  # the old rule cannot continue after an empty band
            continue
        same = bins(bands, n_fft, Fs) == old
        assert same == same_bins_condition(bands, n_fft, Fs), (bands, n_fft, Fs)
        agree += same
        differ += not same
    assert agree > 300 and differ > 300  # both outcomes were exercised


def test_edges_near_a_bin_can_round_differently():
    """Edges meant to lie on a bin but not exact in binary floating point:
    at 63.93 Hz with a 127-point FFT, bins k * 63.93 / 127 Hz. With the shared
    edges of these bands on bins 10, 20 and 30, the old rule (high * (N / Fs),
    no roundoff allowance) and band_bins can still disagree."""
    edges = [k * 63.93 / 127 for k in (5, 10, 20, 30, 50)]
    bands = [[lo, hi] for lo, hi in zip(edges[:-1], edges[1:])]
    new = bins(bands, 127, 63.93)
    assert [b[0] for b in new[1:]] == [10, 20, 30]  # band_bins: each later band starts on its edge's bin
    assert new != chained_bins(bands, 127, 63.93)


def test_disjoint_bands_keep_their_own_edges():
    """The previous rule filled the gap between disjoint bands."""
    bands = [[1, 2], [5, 6]]
    assert bins(bands, 128, 64) == [span(2, 4), span(10, 12)]
    assert chained_bins(bands, 128, 64)[1] == span(4, 12)


def test_two_floating_point_steps_allowed_at_each_edge():
    """low * n_fft / Fs a little above a bin (high: a little below) still
    includes that bin if within two floating-point steps; three steps do not."""
    def up(x, steps):
        for _ in range(steps):
            x = math.nextafter(x, math.inf)
        return x

    def down(x, steps):
        for _ in range(steps):
            x = math.nextafter(x, -math.inf)
        return x

    # 4 Hz * 128 / 64 = bin 8; one step of 4.0, times 2, is one step of 8.0.
    assert spectral_features.band_bins(up(4.0, 1), 7, 128, 64)[0] == 8
    assert spectral_features.band_bins(up(4.0, 2), 7, 128, 64)[0] == 8
    assert spectral_features.band_bins(up(4.0, 3), 7, 128, 64)[0] == 9
    assert spectral_features.band_bins(4, down(7.0, 2), 128, 64)[-1] == 14
    assert spectral_features.band_bins(4, down(7.0, 3), 128, 64)[-1] == 13


def test_band_with_no_bins_is_empty():
    assert spectral_features.band_bins(4.101, 4.102, 128, 64).tolist() == []


# ---------------------------------------------------------------------------
# Unusable bands: ValueError naming the band (as the reference package)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("low, high, message", [
    (7, 4, "above the lower edge"),
    (4, 4, "above the lower edge"),
    (40, 50, "below the Nyquist frequency"),
    (30, 40, "below the Nyquist frequency"),
    (13, 32, "below the Nyquist frequency"),  # the Nyquist frequency itself is not allowed
])
def test_band_bins_rejects_unusable_bands(low, high, message):
    with pytest.raises(ValueError, match=message):
        spectral_features.band_bins(low, high, 128, 64)


@pytest.mark.parametrize("name", SPECTRAL_FEATURES + CONNECTIVITY_FEATURES)
@pytest.mark.parametrize("band, message", [
    ([7, 4], r"freq_bands\[1\] \[7, 4\] Hz: the upper edge must be above the lower edge"),
    ([40, 50], r"freq_bands\[1\] \[40, 50\] Hz: the upper edge must be below the Nyquist frequency \(32 Hz\)"),
    ([30, 40], r"freq_bands\[1\] \[30, 40\] Hz: the upper edge must be below the Nyquist frequency \(32 Hz\)"),
], ids=["inverted", "above Nyquist", "partly above Nyquist"])
def test_features_reject_unusable_bands(name, band, message):
    """Raised before any computation, not hidden as "Feature function not
    found". The spectral edge frequency uses only the total band, so it
    ignores freq_bands (as before)."""
    if name == "spectral_edge_frequency":
        np.testing.assert_array_equal(feature(name, signals(), bands=[[1, 2], band], total=[1, 2]),
                                      feature(name, signals(), total=[1, 2]))
        return
    with pytest.raises(ValueError, match=message):
        feature(name, signals(), bands=[[1, 2], band], total=[1, 2])


@pytest.mark.parametrize("name", SPECTRAL_FEATURES)
def test_total_band_above_nyquist_rejected_only_where_used(name):
    """Only relative power and the spectral edge frequency use the total
    band; they raise. The other spectral features ignore it, as before."""
    if name in spectral_features.TOTAL_BAND_FEATURES:
        with pytest.raises(ValueError, match=r"total_freq_bands \[40, 50\] Hz: the upper edge must be below"):
            feature(name, signals(), total=[40, 50])
    else:
        np.testing.assert_array_equal(feature(name, signals(), total=[40, 50]), feature(name, signals()))


# The values of the code before this change (commit bac1c62) for signals()[0]
# with its default parameters (the original settings); it gave the same with
# total_freq_bands = [NaN, NaN].
BEFORE_VALUES = {
    "spectral_power": [0.6221482651, 0.0918949363, 0.3101098395, 0.5362514695],
    "spectral_flatness": [0.4701422782, 0.9946928675, 0.7978572608, 0.9916814088],
    "spectral_entropy": [0.6393849352, 0.9973190394, 0.883004041, 0.9975547161],
}


@pytest.mark.parametrize("name", sorted(BEFORE_VALUES))
def test_unused_total_band_does_not_affect_other_features(name):
    """Absolute power, flatness and entropy do not use the total band: even
    total_freq_bands = [NaN, NaN] leaves their values (those of the code
    before this change), through main_spectral and called directly, and
    gives no warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        through_main = feature(name, signals(), total=[float("nan"), float("nan")])
        params = neural_outputs.original_settings()["spectral"]
        params["total_freq_bands"] = [float("nan"), float("nan")]
        function = getattr(spectral_features, name)
        direct = np.asarray(function(signals()[0].copy(), FS, name, params), float)
    np.testing.assert_array_equal(through_main, feature(name, signals()))
    np.testing.assert_array_equal(direct, through_main)
    np.testing.assert_allclose(through_main, BEFORE_VALUES[name], rtol=0, atol=5e-11)


@pytest.mark.parametrize("total", [[1, float("inf")], [float("nan"), float("nan")], [float("-inf"), 30]],
                         ids=["[1, inf]", "[NaN, NaN]", "[-inf, 30]"])
@pytest.mark.parametrize("name", ["spectral_relative_power", "spectral_edge_frequency"])
def test_total_band_must_be_finite(name, total):
    """Relative power and the spectral edge frequency check the total band
    before any bin arithmetic: a clear ValueError, through main_spectral and
    called directly (not an OverflowError or IndexError)."""
    message = r"spectral total_freq_bands \[.*\] Hz: the edges must be finite numbers"
    with pytest.raises(ValueError, match=message):
        feature(name, signals(), total=total)
    params = neural_outputs.original_settings()["spectral"]
    params["total_freq_bands"] = total
    function = spectral_features.spectral_power if name == "spectral_relative_power" else \
        spectral_features.spectral_edge_frequency
    with pytest.raises(ValueError, match=message):
        function(signals()[0].copy(), FS, name, params)


@pytest.mark.parametrize("low, high", [(float("nan"), 4), (1, float("nan")), (1, float("inf"))])
def test_check_band_rejects_non_finite_edges(low, high):
    with pytest.raises(ValueError, match="the edges must be finite numbers"):
        spectral_features.check_band(low, high, 64)
    with pytest.raises(ValueError, match="the edges must be finite numbers"):
        spectral_features.band_bins(low, high, 128, 64)


def test_edge_frequency_needs_no_freq_bands():
    """The spectral edge frequency uses only the total band: without a
    'freq_bands' key it gives the value of the code before this change
    (commit bac1c62: 27.5 Hz for this signal)."""
    params = neural_outputs.original_settings()["spectral"]
    del params["freq_bands"]
    value = spectral_features.main_spectral(signals()[0].copy(), FS, "spectral_edge_frequency", params)
    assert value == 27.5
    assert value == feature("spectral_edge_frequency", signals())[0]


@pytest.mark.parametrize("name", [f for f in SPECTRAL_FEATURES if f in spectral_features.BAND_FEATURES])
def test_band_features_need_freq_bands(name):
    params = neural_outputs.original_settings()["spectral"]
    del params["freq_bands"]
    with pytest.raises(KeyError):
        spectral_features.main_spectral(signals()[0].copy(), FS, name, params)


def test_generate_all_features_reports_the_band():
    """Through the usual pipeline the error names the band too."""
    data = {"eeg_data": __import__("pandas").DataFrame(signals().T, columns=LABELS), "Fs": FS,
            "ch_labels": list(LABELS)}
    original = NEURAL_parameters.NEURAL_parameters

    def params_with_bad_band():
        params = original()
        params["spectral"]["freq_bands"] = [[0.5, 4], [40, 50]]
        return params

    NEURAL_parameters.NEURAL_parameters = params_with_bad_band
    try:
        with pytest.raises(ValueError, match=r"spectral freq_bands\[1\] \[40, 50\] Hz"):
            generate_all_features.generate_all_features(data, feat_set=["spectral_flatness"])
    finally:
        NEURAL_parameters.NEURAL_parameters = original


# ---------------------------------------------------------------------------
# Bands with no bins: NaN without warnings (as the reference package)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", [f for f in SPECTRAL_FEATURES + CONNECTIVITY_FEATURES
                                  if f != "spectral_edge_frequency"])
def test_band_with_no_bins_gives_nan_without_warnings(name):
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning fails the test
        result = feature(name, signals(), bands=[[1, 2], [4.101, 4.102]], total=[1, 4.102])
    assert result.shape == (2,)
    assert np.isfinite(result[0]) and np.isnan(result[1])


@pytest.mark.parametrize("name", ["spectral_relative_power", "spectral_edge_frequency"])
def test_total_band_with_no_bins_gives_nan_without_warnings(name):
    """The default bands have bins, the total band has none: relative power
    (every band) and the spectral edge frequency are NaN."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = feature(name, signals(), total=[4.101, 4.102])
    assert np.isnan(result).all()


@pytest.mark.parametrize("seconds", [8, 64], ids=["8 s input (one window)", "64 s input"])
def test_coherence_sole_band_with_no_bins_is_quiet(seconds):
    """No band has a bin: NaN, without computing the coherence threshold
    (with one 8 s window the analytic threshold divides by zero)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = feature("connectivity_coh_mean", signals()[:, :seconds * FS], bands=[[4.101, 4.102]])
    assert result.shape == (1,) and np.isnan(result).all()


def test_coherence_of_zero_input_is_quiet():
    """An all-zero input: NaN for every band, without warnings (0 / 0 in the
    coherence, empty means and medians)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = feature("connectivity_coh_mean", np.zeros((2, 64 * FS)))
    assert result.shape == (4,) and np.isnan(result).all()


def test_total_band_with_no_bins_leaves_absolute_power():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = feature("spectral_power", signals(), total=[4.101, 4.102])
    assert np.isfinite(result).all()


# ---------------------------------------------------------------------------
# Coherence: the FFT length is the exact one
# ---------------------------------------------------------------------------
def test_coherence_uses_the_exact_fft_length(monkeypatch):
    """With a float16 sampling rate (278.75 Hz, exactly representable) and a
    2.1 s window the FFT has 585 samples; f_scale * Fs in float16 rounds to
    586, which used to shift the bins. Every band must use 585, and the
    result must equal the one with the same rate as float64."""
    rng = np.random.default_rng(3)
    x = rng.normal(size=(2, int(60 * 278.75)))
    seen = []
    real = spectral_features.band_bins

    def recording(low, high, n_fft, Fs):
        seen.append(int(n_fft))
        return real(low, high, n_fft, Fs)

    def coherence(Fs):
        params = neural_outputs.original_settings()["connectivity"]
        params["L_window"] = 2.1
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)  # NEURAL's own channel warnings
            return connectivity_features.main_connectivity(x, Fs, "connectivity_coh_mean", LABELS, params)

    fs16 = np.float16(278.75)
    assert float(fs16) == 278.75
    f_scale = 585 / fs16
    assert int(round(f_scale * fs16)) == 586  # the recovery that was off by one
    monkeypatch.setattr(spectral_features, "band_bins", recording)
    result16 = coherence(fs16)
    assert seen and set(seen) == {585}
    monkeypatch.setattr(spectral_features, "band_bins", real)
    np.testing.assert_array_equal(result16, coherence(278.75))


def test_gen_coherence_still_returns_five_values():
    x = signals()
    params = neural_outputs.original_settings()["connectivity"]
    assert len(connectivity_features.gen_coherence(x[0], x[1], FS, params)) == 5


# ---------------------------------------------------------------------------
# Guard for the stored data: the six other bin-based features
# ---------------------------------------------------------------------------
def stored_settings():
    """Sampling rates, bands, total band and window settings read from the
    stored reference files (tests/data). The main files store the rate
    (preprocessed.Fs) and the band edges in their column names (e.g.
    "spectral_power__05_4", total band "spectral_edge_frequency__05_30"); the
    edge-case and input-type files state the rate in their "about" text; the
    windows file names its window types and lengths in its keys."""
    def edge(text):
        return float(text.replace("05", "0.5")) if text == "05" else float(text)

    rates, bands, totals, window_types, lengths = set(), set(), set(), set(), set()
    for name in ("clean", "artefacts"):
        reference = json.loads((DATA / ("reference_%s.json" % name)).read_text(encoding="utf-8"))
        rates.add(reference["preprocessed"]["Fs"])
        for entry in reference["features"].values():
            for column in entry["columns"]:
                feature_name, suffix = column.split("__")
                if not feature_name.startswith(("spectral_", "connectivity_")):
                    continue  # FD, amplitude and rEEG use filters, not FFT bins
                low, high = (edge(part) for part in suffix.split("_"))
                (totals if feature_name == "spectral_edge_frequency" else bands).add((low, high))
    for name, key in (("edge_cases", "nan_input"), ("input_types", "index_types")):
        about = json.loads((DATA / ("reference_%s.json" % name)).read_text(encoding="utf-8"))["about"][key]
        rates.update(int(hz) for hz in re.findall(r"(\d+) Hz", about))
    windows = json.loads((DATA / "reference_windows.json").read_text(encoding="utf-8"))["windows"]
    for key in windows["windows"]:
        match = re.match(r"get_window (\S+) (\d+)", key)
        if match:
            window_types.add(match.group(1))
            lengths.add(int(match.group(2)))
    return rates, sorted(bands), sorted(totals), sorted(window_types), sorted(lengths)


def chained_rule(freq_bands):
    """band_bins replaced by the previous rule for these bands: a band of
    freq_bands gets its chained bins; any other band (the total band) the old
    single-interval rule ceil(low * f) to floor(high * f)."""
    def band_bins(low, high, n_fft, Fs):
        for index, band in enumerate(freq_bands):
            if (float(low), float(high)) == (float(band[0]), float(band[1])):
                return np.array(chained_bins(freq_bands, n_fft, Fs)[index])
        f_scale = n_fft / Fs
        first, last = int(np.ceil(low * f_scale)), int(np.floor(high * f_scale))
        return np.arange(max(first, 0), min(last, n_fft // 2) + 1)
    return band_bins


def test_other_bin_features_are_unchanged_for_every_stored_setting(monkeypatch):
    """The reference section with_neural_eeg_features_0.6.1_band_bins holds
    only spectral_power and spectral_relative_power. For the settings of the
    stored data (read from tests/data), the six other bin-based features
    must give exactly the same values under the previous rule, with and
    without NaN in the epoch, for every stored window type."""
    rates, bands, totals, window_types, lengths = stored_settings()
    assert rates == {64}
    assert bands == [(0.5, 4.0), (4.0, 7.0), (7.0, 13.0), (13.0, 30.0)]
    assert totals == [(0.5, 30.0)]
    assert window_types == ["bart", "blackmanharris", "tuke"] and lengths == [128, 512]
    params = neural_outputs.original_settings()
    # the stored data were made with these windows: 2 s (128) and 8 s (512) at 64 Hz
    assert {int(params["spectral"]["L_window"] * 64), int(params["connectivity"]["L_window"] * 64)} == set(lengths)

    freq_bands = [list(b) for b in bands]
    real = spectral_features.band_bins
    for with_nan in (False, True):
        x = signals(with_nan=with_nan)
        for window_type in [None] + window_types:
            settings = {} if window_type is None else {"window_type": window_type}
            for name in BIN_FEATURES:
                if name == "connectivity_BSI" and window_type is not None:
                    settings = dict(settings, method="PSD")  # as window_results: bartlett-PSD has no window
                kwargs = dict(bands=freq_bands, total=list(totals[0]), Fs=list(rates)[0], **settings)
                monkeypatch.setattr(spectral_features, "band_bins", real)
                new = feature(name, x, **kwargs)
                monkeypatch.setattr(spectral_features, "band_bins", chained_rule(freq_bands))
                old = feature(name, x, **kwargs)
                assert np.array_equal(new, old, equal_nan=True), (name, with_nan, window_type)
                settings = {} if window_type is None else {"window_type": window_type}
    monkeypatch.setattr(spectral_features, "band_bins", real)

    # The monkeypatch is effective: spectral_power, whose periodogram is
    # shortened by NaN removal, differs under the previous rule.
    x = signals(with_nan=True)
    new = feature("spectral_power", x, bands=freq_bands)
    monkeypatch.setattr(spectral_features, "band_bins", chained_rule(freq_bands))
    old = feature("spectral_power", x, bands=freq_bands)
    assert not np.array_equal(new, old)
