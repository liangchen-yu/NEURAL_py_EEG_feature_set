# Changes to match neural_eeg_features 0.6.1

The reference package neural_eeg_features 0.6.1 revises the NEURAL feature set
and its filters. This file lists every change made to this NEURAL_py to match
it, one row per change, in the order they were made. Section names refer to
the reference package's `docs/definitions.md`.

| # | Change | Before | After | Reason (reference `docs/definitions.md`) | Verification |
| --- | --- | --- | --- | --- | --- |
| 1 | Remove 7 features: `amplitude_total_power`, `amplitude_SD`, `rEEG_mean`, `rEEG_width`, `rEEG_SD`, `connectivity_coh_max`, `connectivity_coh_freqmax` | `FEATURE_SET_ALL` has 30 names (26 non-IBI); with the default bands, 102 feature columns; a default call's `feats_median_ch` has 98 columns (the non-IBI ones) | `FEATURE_SET_ALL` has the reference package's 23 names in the same order (19 non-IBI); 74 columns. `feats_median_ch` still keeps the first 98 columns (`[:98]` unchanged): the same explicit feature list gives the same columns; a default call gives 74 (28 removed-feature columns gone, the 4 always-NaN IBI columns now included). Requesting a removed name raises `ValueError` naming it, in `generate_all_features`, `main_amplitude`, `main_rEEG` and `main_connectivity`. Public functions `amplitude_total_power`, `amplitude_SD`, `rEEG_mean`, `rEEG_width`, `rEEG_SD` deleted; coherence max and max-frequency branches removed | "Version changes and validation limits" (0.2 removes the two coherence features, 0.3 the two amplitude features, 0.4 `rEEG_mean`, 0.5 `rEEG_width` and `rEEG_SD`; requesting a removed name raises `ValueError`); "Deliberate settings and feature-selection differences" (the seven names deliberately removed; 23 remain); "Feature catalogue" (the amplitude pair removed as largely redundant measures of band energy) | Exact comparison with the previous code (commit dc272ea) on all test cases, with the same explicit feature lists: 16,299 values, 0 differ, same columns (details below). Regression tests against `tests/data/` (removed features skipped): all pass, 0 values outside tolerance. New `tests/test_removed_features.py`: each removed name raises `ValueError`; `FEATURE_SET_ALL` equals the reference package's `ALL_FEATURES` and the removed names equal those in its `docs/definitions.md`; `feats_median_ch` keeps all columns of a request with fewer than 98 columns, as before (73 for all features except FD; 4 with empty rEEG bands and `spectral_power` only; 74 for the default call, including the 4 always-NaN IBI columns) |
| 2 | `amplitude_skew` and `amplitude_kurtosis`: bias-corrected moments, as in the reference package | Biased moments: `abs(scipy.stats.skew(x, nan_policy="omit"))` and `scipy.stats.kurtosis(x, fisher=False)` (Pearson). `main_amplitude` removed NaN first; called directly, kurtosis gave NaN for NaN and both gave NaN for +/-inf. No explicit rule for short input: 2 values gave skewness 0 and kurtosis 1, 3 values gave a kurtosis. Constant input: NaN from scipy's own check | `abs(scipy.stats.skew(x, bias=False))` and `scipy.stats.kurtosis(x, fisher=False, bias=False)` (Pearson) on the finite values only (NaN and +/-inf ignored). NaN for fewer than 3 (skewness) or 4 (kurtosis) values, and for constant values (range not above eps * max(1, max abs value)), as in the reference package's `amplitude.py`. In the test data every value rose slightly (skewness +0.04-0.06 %, kurtosis +0.04-0.16 %). The skewness magnitude always increases with the correction (factor sqrt(n(n-1))/(n-2), +0.037 % for a full 64 s epoch, n = 4096), unless it is 0; the kurtosis usually does for EEG-like data but can decrease for very flat signals (4096 alternating -1/+1 values: 1.0 becomes 0.99902). No other output changes | "Skewness and kurtosis: correction to the earlier audit" (the reference package uses `bias=False`, and `fisher=False` for Pearson kurtosis; the older NEURAL Python port uses biased moments; example `[-2, -1, 0, 1, 2]`: kurtosis 1.8, original 1.7); "Feature catalogue" (absolute bias-corrected skewness; bias-corrected Pearson kurtosis, not excess kurtosis) | Same arrays through the reference package's `amplitude_features()` (in its own environment) and this repository's functions: 488 arrays (456 real band-filtered epochs of the synthetic test recordings, 32 synthetic edge cases), every finite value exactly equal (max abs and rel difference 0), NaN in the same places (skewness 10, kurtosis 12). Exact comparison with the previous code (commit 2bd0742) on all test cases: 15,070 values of other features, 0 differ; of each moment's 748 values, 684 changed, 64 NaN in both. Regression tests against the new reference section `with_neural_eeg_features_0.6.1_moments` and the original: all pass, difference 0. New `tests/test_amplitude_moments.py` (closed-form formulas, the reference package's example, short, constant, NaN and +/-inf inputs) |
| 3 | Band bins: each frequency band an independent closed interval (new `spectral_features.band_bins`), in all six band loops (`spectral_power`, `spectral_flatness`, `spectral_entropy`, `spectral_diff`, `connectivity_BSI`, `connectivity_coh`) and the total band of `gen_spectrum` (relative power, `spectral_edge_frequency`) | Chained rule, as in MATLAB NEURAL: the first band from `ceil(low * f)` to `floor(high * f)` (f = FFT bins per Hz); each later band from the previous band's last bin to `floor(high * f)`; indices clipped to [0, Nyquist], so a band above Nyquist repeated the Nyquist bin; no roundoff allowance. When an edge lay between bins, the later band also took the bin below its lower edge; gaps between disjoint bands were filled | Each band: bins `ceil(low * N / Fs)` to `floor(high * N / Fs)`, inclusive, independently of the other bands, with two floating-point steps allowed at each edge, at most the Nyquist bin (the reference package's `spectral.band_slice`). **This departs from MATLAB NEURAL's chained rule.** For bands that are not empty and not clipped at 0 or Nyquist, with no edge within about two floating-point steps of a bin, the two rules select the same bins exactly when, for every band after the first, `ceil(low * N / Fs)` equals the previous band's `floor(high * N / Fs)` (the two edges fall within the same bin step; usually one shared edge exactly on a bin); the first band's lower edge and the last band's upper edge do not matter. Exceptions: a band left empty under both rules can agree although the equation fails, and an edge within about two floating-point steps of a bin can agree or differ because of the two-step allowance. At 64 Hz with the default bands and windows this holds for every window-based spectrum; disjoint bands never satisfy it, and a non-integer sampling rate can break it for the default bands (63.93 Hz, 2 s window: theta started at bin 7, now 8). A band that a feature uses whose upper edge is not above its lower edge, or not below the Nyquist frequency, raises `ValueError` naming the band; a band with no bin gives NaN without warnings (details below). In the test data only `spectral_power` and `spectral_relative_power` change, and only in epochs that contain NaN (the periodogram is shortened by NaN removal): in the artefacts recording 108 of 168 values per feature, by up to 3.5 % (median 0.15 %), all lower; summary per band up to -0.42 % (`spectral_power`, theta) and -2.4 % (`spectral_relative_power`, theta); delta unchanged. The clean recording is unchanged | The reference package's `docs/definitions.md` documents independent closed intervals as the intended definition: "Feature conventions retained from version 0.1" (each band uses bins from `ceil(low * N / fs)` through `floor(high * N / fs)`, inclusive, with two floating-point steps for roundoff; shared boundary bins; a 4 Hz tone in a 16-second epoch at 98 Hz contributes bin 64 to both delta and theta). "NEURAL Python and MATLAB spectral comparison" (band bins: independent closed intervals in the reference package, chained in NEURAL Python and MATLAB; the chained loops can include a bin below the band's lower limit and fill gaps between disjoint bands). "Spectral details beyond the equations" (the paper's band sums include both endpoints; independent closed intervals follow that interpretation) | (a) `band_bins` against the reference package's `band_slice`: 61,864 band/length/rate cases (3,864 on and off the bin grid, 4,000 random off-grid bands, 54,000 edges within 4 floating-point steps of a bin; the two-step allowance changes the bins in over 21,000 of them): 0 differences. (b) `spectral_power` and `spectral_relative_power` against its `spectral_features()` on 38 NaN-free arrays (off-grid and on-grid lengths at 64 and 100 Hz; default, preterm, off-grid and disjoint bands; 1,140 values): max abs difference 1.7e-13, max rel 3.2e-15, 422 exactly equal (the previous rule: up to 6 % with preterm bands, and far more where an edge bin carried a strong component). (c) Exact comparison with the previous code (commit bac1c62) on all test cases: only `spectral_power` and `spectral_relative_power` change (342 of the 16,566 values compared, all lower; every other value is identical), only in epochs that contain NaN; the clean recording's 21 outputs are byte-identical. Regression tests against the new reference section `with_neural_eeg_features_0.6.1_band_bins` and the original: all pass, difference 0. New `tests/test_band_bins.py`: the rule; `ValueError` for inverted, above-Nyquist and partly above-Nyquist bands and total bands, in each feature that uses the band; NaN without warnings for bands and total bands with no bin, and for coherence also with one 8 s window or an all-zero input; each feature checks only the bands it uses (the edge frequency needs no `freq_bands`, 27.5 Hz as before on the test signal); the exact FFT length in coherence (float16 sampling rate); the condition under which the two rules agree (3,000 seeded random draws); and, for every setting read from the stored reference files, identical values of the six other bin-based features under both rules |
| 4 | Complete epochs only (`generate_all_features.overlap_epochs`, `epoch_count`, `get_max_num_epochs`) | `ceil((N - (L_epoch - L_hop)) / L_hop)` epochs, at least 1: a final epoch padded with NaN whenever the recording did not end on an epoch boundary (at 50 % overlap the padding alone stayed below the 50 % NaN threshold, so it was kept unless NaN already in the signal brought its NaN share to 50 % or more: the rule skipped an epoch whose NaN share reached or exceeded 50 %); a recording shorter than one epoch gave one padded epoch (values if more than half of it was data, else NaN) | `(N - L_epoch) // L_hop + 1` complete epochs, no padding; the rows of `feats_median_ch` always equal the epochs. A recording shorter than one epoch raises `ValueError` naming both lengths when an epoch-based feature is requested, before any feature is computed; IBI-only and empty requests return (0 rows). The hop, the 50 % NaN rule and the windows within an epoch are unchanged. In the test data the complete epochs are bit-identical and only the padded epoch is dropped (300 s: 9 to 8 epochs); the summaries of 18 of 19 features change, by up to 15.7 % (clean) and 42.9 % (artefacts) at 300 s, because there are only 9 epochs; with the same generator up to 3.9 % / 3.7 % at 30 min and 1.4 % / 2.1 % at 60 min | The reference package's `docs/definitions.md`, "Missing data and recording boundaries": "Ordinary epochs are complete windows only: trailing incomplete data do not create an additional epoch. A recording shorter than one ordinary epoch raises `ValueError` when ordinary features are requested." "Version changes and validation limits": version 0.1's "... padded ordinary final epochs are replaced by the processing defaults above". Its README: "Shorter recordings raise `ValueError`; incomplete trailing windows are discarded." | (a) The reference package on identical preprocessed arrays (clean 300 s test recording) at NEURAL_py-like settings: `spectral_diff` agrees to 4.7e-16 relative per band, 1.1e-15 per channel and 2.2e-15 per channel and epoch (256 values); before, -8.4 % to +10.1 % per band. (b) Exact comparison with commit 90543fc on all test cases: 80 per-epoch arrays lose exactly the final epoch, every kept epoch bit-identical; the window, read-only and few-channel connectivity outputs are unchanged; IBI outputs unchanged (NaN on these signals). (c) Recording lengths L - 1, L, L + H - 1, L + H and L + 3H at 64, 256 and 63.93 Hz. Regression tests against the new section `with_neural_eeg_features_0.6.1_complete_epochs` and the original: all pass; a guard checks that the section equals the earlier values on the complete epochs. New `tests/test_complete_epochs.py` |
| 5 | Settings can be passed to `generate_all_features` (`params`), and the tests pass the original NEURAL's settings explicitly; prepares the adoption of the reference package's default settings. No output change | `generate_all_features` took no settings: it and every feature function it called made their own `NEURAL_parameters()`, so other settings needed an edited `NEURAL_parameters.py` (or a replaced function). The tests used the defaults, which equal the original's settings | `generate_all_features(data, save_p_l=None, channel_names=None, feat_set=None, params=None)`: `None` as before; otherwise `params` is checked (`NEURAL_parameters.check_parameters`: the structure of `NEURAL_parameters()`, `ValueError` naming each problem, before anything is computed), copied and never changed, and every feature call gets its own copy of its group's settings. `size_feature` also takes `params`. Not read from `params` (as before, not read by `generate_all_features`): the preprocessing settings, and the top-level `FREQ_BANDS` and `FILTER_REPLACE_ARTEFACTS` (each group has its own). Column names: a single band `[[low, high]]` now works (it failed with `IndexError`), distinct bands get distinct names (fractional edges were cut to integers, so `[0.5, 4.1]` and `[0.5, 4.9]` shared one name and value), the same band twice raises `ValueError`, and a given `feat_set` decides the columns (a feature missing from `FEATURE_SET_ALL` failed), while a name that is not one of the 23 supported features raises `ValueError` before any work (`check_requested_features`); every default column name is unchanged, and all three faults also occur on the previous code with an edited `NEURAL_parameters()` (section 5). `tests/neural_outputs.py` writes out the original's settings (`original_settings()`), which the regression tests, the edge cases, the sensitivity experiment and the unit tests with recorded values pass explicitly | The reference package's configuration is explicit too (`FeatureConfig`, passed as `config` to `extract_features`); the regression tests must keep checking the original's settings once the defaults are the reference package's (step 3, settings) | (a) Exact comparison with commit c205097 on every stored case (52, incl. the default call with IBI): every output of all 48 `generate_all_features` calls (336,614 numbers, 2,451 other values), the helpers' results, the printed text (31,495 characters) and the 130 warnings are identical with `params=None` and with the original settings passed; only the line numbers of 16 warnings raised in `generate_all_features.py` moved (+51 lines: the new docstrings and helpers). (b) `original_settings()` equals the original's `NEURAL_parameters()` (its `FEATURE_SET_ALL` less the 7 removed names), in its own environment and in the 2020 environment. (c) `make_reference.py`, unchanged, run with the original through the changed test helpers: all five reference files byte-identical to the committed ones. New `tests/test_params.py` (114 tests, one a strict expected failure): each setting read by `generate_all_features` and the five feature groups reaches its feature (values equal to the feature function's with the same settings, and different from the defaults); `params` unchanged by a call; calls with different settings independent; bad `params` raise `ValueError` naming the setting; the 74 default column names, one-band lists and arrays, fractional and repeated bands, `feat_set` against `FEATURE_SET_ALL`, and unknown feature names |

## 1. Removal of 7 features

**Kept internally.** As in the reference package, calculations that remaining
features need are kept:

- `rEEG_CV` still computes the sample SD and the mean of the range trace
  itself (`SD / mean`); it never called `rEEG_SD` or `rEEG_mean`.
- `rEEG_asymmetry` still uses the lower and upper margins and the median; it
  never called `rEEG_width`.
- `connectivity_coh_mean` still uses the shared coherence calculation in
  `connectivity_features.connectivity_coh` (coherence estimate, zero-level
  threshold, frequency-band indices); only the max and max-frequency branches
  were removed.
- No remaining amplitude feature used `amplitude_total_power` or
  `amplitude_SD`.

**Error message.** Requesting a removed name raises `ValueError` with a message
that names the feature, e.g. `Feature(s) 'rEEG_SD' removed to match
neural_eeg_features 0.6.1; ...`. The reference package also raises
`ValueError`, but its message ("Feature names must be unique members of
ALL_FEATURES") does not name the feature. Names that never existed behave as
before (no new check).

**Reference values.** The original's values in the regression reference files
in `tests/data/` are unchanged: they were made by the original NEURAL and still
hold the 7 removed features. The tests skip them when loading the files
(`tests/neural_outputs.py`, `without_removed_features`), and check that the
reference holds the original's 26 non-IBI features and this repository the
same 19 others, in the same order.

**Exact comparison.** The previous code (commit dc272ea) and the changed code
were run on the same inputs, and every output was compared exactly (NaN equal
to NaN): the two synthetic EDF recordings of the regression tests (each
remaining feature in its own `generate_all_features` call and all 19 in one
call; `feats_median_all`, `feat_st`, `feats_median_ch` and
`feats_per_epochs`), a subset call with an IBI feature, NEURAL's
`gen_test_EEGdata` (fixed seed) with the 23 features, the edge-case inputs
(pre-existing NaN, the +inf line, row-index types, read-only arrays, window
types) and the connectivity features with 2, 3 and 8 channels. Both versions
were given the same explicit feature lists. 16,299 values were compared; none
differ, and every output has the same columns. Entries present only in the
previous code were those of the 7 removed features.

**`feats_median_ch` columns.** `generate_all_features` still keeps the first
98 columns of `feats_median_ch` (the hard-coded `[:98]`, unchanged).

- The same explicit feature list gives the same `feats_median_ch` columns as
  before (for example 73 for all features except FD, 4 for `spectral_power`).
- A default call (`feat_set=None`) changes from 98 to 74 columns. Before, the
  full set had 102 columns, and `[:98]` kept its 98 non-IBI columns. Now the
  28 columns of the removed features (7 features x 4 bands) are gone, leaving
  70 non-IBI columns, and as the full set has only 74 columns, the 4 IBI
  columns (always NaN in `feats_median_ch`) now fall inside `[:98]` too.

**Not changed here (possible later, separate change).** Whenever a request has
fewer than 98 columns, which now includes the full 23-name set,
`feats_median_ch` keeps the IBI columns, which are always NaN there because
IBI features are computed for the whole recording, not per epoch. Before, this
happened for every call with fewer than 98 columns, but not for the full set,
which had 102 columns (the first 98 are the non-IBI ones).
Keeping only the non-IBI columns would remove them; that change must work out
the column names from the requested features only, as a feature group that is
not requested may have an unusable band setting.

## 2. Bias-corrected skewness and kurtosis

**Definitions.** As in the reference package's `amplitude.py`:

- `amplitude_skew`: `abs(scipy.stats.skew(x, bias=False))`, the absolute
  bias-corrected sample skewness G1 = sqrt(n(n-1))/(n-2) * g1;
- `amplitude_kurtosis`: `scipy.stats.kurtosis(x, fisher=False, bias=False)`,
  the bias-corrected Pearson kurtosis (excess kurtosis G2 plus 3);
- only the finite values of `x` are used;
- NaN for fewer than 3 (skewness) or 4 (kurtosis) values, and for constant
  values: range not above eps * max(1, max abs value).

Differences from before: the bias correction (`bias=False`); +/-inf now
ignored, and NaN ignored by kurtosis when it is called directly (the pipeline
already removed NaN); the explicit short and constant input rules. The
absolute value (of the signed skewness, after summation) and the Pearson
convention are unchanged. Both functions now return a Python `float`. The
filters and the other amplitude features are unchanged.

**Size of the change.** With the default settings every epoch has 4096
samples, unless NaN samples (artefacts) were removed. The skewness factor is
then 1.000366, and the kurtosis change depends on the data. In the test data
(the synthetic test recordings) every value rose slightly, per channel and
epoch: skewness +0.037 % to +0.057 %, kurtosis +0.039 % to +0.159 %. The
summary per band (median over channels and epochs) rose by 0.037-0.048 %
(skewness) and 0.052-0.081 % (kurtosis). This direction is not general. The
skewness magnitude always increases with the correction (unless it is 0), as
the factor sqrt(n(n-1))/(n-2) is above 1. The kurtosis usually increases for
EEG-like (peaked) data but can decrease for very flat signals: for 4096
alternating -1/+1 values the biased Pearson kurtosis is 1.0 and the corrected
one 0.99902 (`tests/test_amplitude_moments.py`).

**Comparison with the reference package.** The same arrays were given to the
reference package's `amplitude_features()`, run in its own environment, and to
this repository's `amplitude_skew` and `amplitude_kurtosis`: the 456
band-filtered amplitude epochs (4 bands) of the two synthetic test recordings,
as `main_amplitude` filters them, with their NaN kept; and 32 synthetic cases
(0 to 6 values, the docstring example, `[-2, -1, 0, 1, 2]`, constant and
nearly constant values at amplitudes 1 and 1e6, tiny and large amplitudes,
NaN and +/-inf inside, only NaN and +/-inf, and noise, gamma and sine signals
of 64 to 16384 values). Every finite value is exactly equal (largest absolute
and relative difference 0; skewness 478, kurtosis 476 values), and NaN is in
the same places (skewness 10, kurtosis 12 arrays). The two environments differ
slightly (numpy 2.4.6 and 2.5.4, scipy 1.18.1 in both).

**Reference values.** `tests/make_reference.py` also runs the original NEURAL
with only these two functions replaced, in memory, by the reference package's
definitions (written out independently in that script), and stores their
values in a new section, `with_neural_eeg_features_0.6.1_moments`, at the same
places as in the rest of each file: clean and artefacts (each feature in its
own call), edge cases (pre-existing NaN, +inf line) and input types (row-index
types). `reference_windows.json` has no amplitude features, so it has no such
section and was not remade. The four files were remade with the original
NEURAL (commit 78c9425) and the library versions in the script's header.
Without the new section (and its description in `about`), each is
byte-identical to the committed file; the only other change is the comma that
JSON needs after the former last `about` entry. `neural_outputs.with_fixes`
applies the fix sections in order: first the MATLAB `spectral_diff` fix
(`with_matlab_fix_a279ddd`), then the 0.6.1 moments section
(`with_neural_eeg_features_0.6.1_moments`). The tests therefore compare
`spectral_diff` with the first, `amplitude_skew` and `amplitude_kurtosis` with
the second, and every other feature with the original NEURAL's output.

## 3. Band bins: independent closed intervals

**Definition.** `spectral_features.band_bins(low, high, n_fft, Fs)` returns
the one-sided FFT bins `ceil(low * n_fft / Fs)` to `floor(high * n_fft / Fs)`,
inclusive, computed exactly as the reference package's `spectral.band_slice`:
two floating-point steps are allowed at each edge for roundoff in the
multiplication and division, the last bin is at most the Nyquist bin
`n_fft // 2`, and each band is independent of the others. Adjacent bands share
a bin that lies exactly on their common edge. All six band loops and the total
band of `gen_spectrum` use it. For coherence the FFT length comes from
`gen_cross_spectrum` (internal `connectivity_features._coherence`;
`gen_coherence` still returns five values).

**Departure from MATLAB NEURAL.** MATLAB NEURAL and the original Python port
start each later band at the previous band's last bin. This change follows
the reference package, whose `docs/definitions.md` documents independent
closed intervals as the intended definition (see row 3), not MATLAB.

**When the two rules agree.** For bands whose selections are not empty and
not clipped (at bin 0 or the Nyquist bin), and whose edges are not within
about two floating-point steps of a bin, the two rules select the same bins
exactly when, for every band after the first, its first bin
`ceil(low * N / Fs)` is the previous band's last bin `floor(high * N / Fs)`:
the band's lower edge and the previous band's upper edge fall within the
same bin step. The usual case is
one shared edge exactly on a bin; overlapping bands whose edges round to the
same bin also agree, and disjoint bands never do (the old rule filled the
gap). The first band's lower edge and the last band's upper edge do not
matter. This was checked on 39,912 random sets of 2 to 4 bands whose edges
are either on bins or at least 1 % of a bin away from one, on grids where the
bins are exact binary fractions (`tests/test_band_bins.py` repeats it on
3,000 random draws; both checks leave out the cases below). Two exceptions
lie outside this scope. A band left empty under both rules can agree even
though the equation fails. And an edge within about two floating-point
steps of a bin, for example a decimal edge meant to be on a bin that is not
exact in binary, can agree or differ: `band_bins` allows two steps and
computes `low * N / Fs`, the old rule allowed none and computed
`low * (N / Fs)`. With 3 bands whose
shared edges were meant to lie on bins, the rules still differed in 2,811 of
4,000 random sets at 63.93 Hz with a 127-point FFT, and in 90 of 4,000 at
64 Hz with 4000 points.

**Where the bins differ in practice.** With the default bands at 64 Hz (the
settings of the test data) the condition holds for every
spectrum whose length is set by a window: 2 bins per Hz for the spectral
features (2 s window), 8 for connectivity (8 s window), and 64 for the
periodogram of a full 64 s epoch, at 64 Hz. The periodogram of
`spectral_power` is computed on the epoch's samples after NaN removal, so its
length, and with it the bins per Hz, changes when an epoch contains NaN; band
edges can then fall between bins. Example at 64 Hz: 4000 samples (62.5 bins
per Hz) gave alpha the extra bin 437 (6.992 Hz) and beta the extra bin 812
(12.99 Hz); 3999 samples also gave theta the extra bin 249 (3.985 Hz). Custom
bands whose edges are not on the bin grid are also affected, and so are
disjoint bands, whose gap the old rule filled. A non-integer sampling rate
can move even the default bands off the grid: at 63.93 Hz a 2 s window has
127 samples (1.987 bins per Hz), and theta started at bin 7 (delta's last
bin), now at bin 8 (`tests/test_band_bins.py`).

**Unusable bands and bands with no bins.** A band whose upper edge is not
above its lower edge, or not below the Nyquist frequency Fs / 2, is rejected
before any computation with a `ValueError` that names it (e.g. `spectral
freq_bands[1] [40, 50] Hz: the upper edge must be below the Nyquist frequency
(32 Hz)`), as in the reference package. Each feature checks only the bands
it uses: `freq_bands` for `spectral_power`, `spectral_relative_power`,
`spectral_flatness`, `spectral_entropy`, `spectral_diff` and the connectivity
features; the spectral `total_freq_bands` for `spectral_relative_power` and
`spectral_edge_frequency`. So the edge frequency needs no `freq_bands`, as
before. (The reference package checks every configured band for every
feature.) Edges must also be finite numbers. The total band is computed
(`gen_spectrum`, new keyword `total_band`) and checked only for the two
features that use it, so even `total_freq_bands = [NaN, NaN]` leaves absolute
power, flatness and entropy at their values. The checks are in `spectral_features.check_band`, called by
`band_bins`, by the two total-band features, and by `main_spectral` and
`main_connectivity` outside their error-masking `try`. A valid band that
contains no bin gives NaN, without warnings. Measured per feature on the
same synthetic 64 Hz signals in all three ("before" is commit bac1c62, the
old rule; the reference package through `extract_features`; "the 7 band
features" are all eight outputs except `spectral_edge_frequency`):

| Case (bands; total band) | Reference package | Before | Now |
| --- | --- | --- | --- |
| `[[1, 2], [4.101, 4.102]]`; `[1, 4.102]`: second band has no bin | 7 band features NaN; SEF a value (its own settings: 3.41 Hz) | all values (the old rule took the previous band's last bin); SEF 3.5 Hz | 7 band features NaN, no warnings; SEF 3.5 Hz (it uses only the total band) |
| `[[1, 2], [7, 4]]`; `[1, 4]`: inverted band | `ValueError` (band creation) | values; SEF 3.5 Hz | 7 band features `ValueError` naming the band; SEF 3.5 Hz (does not use `freq_bands`) |
| `[[1, 2], [40, 50]]`; `[1, 50]`: band and total above Nyquist | `ValueError` ("upper edge must be below Nyquist") | values (Nyquist bin repeated); SEF 29.5 Hz | `ValueError` for all 8 (SEF: the total band) |
| `[[1, 2], [30, 40]]`; `[1, 40]`: partly above Nyquist | `ValueError` | values; SEF 29.5 Hz | `ValueError` for all 8 (SEF: the total band) |
| `[[4.101, 4.102]]`; `[4.101, 4.102]`: band and total band have no bin | NaN, all 8 | 7 features `ValueError` "Feature function not found"; SEF 0 Hz with a warning | NaN, all 8, no warnings |
| default bands; `[40, 50]`: total band above Nyquist | not possible (the total band spans the bands) | values; SEF 32 Hz | `spectral_relative_power` and SEF `ValueError` naming `total_freq_bands`; the other 6 unchanged |
| default bands; `[4.101, 4.102]`: total band has no bin | not possible | `spectral_relative_power` `ValueError` "Feature function not found", SEF 0 Hz with a warning (the new rule before this fix: relative power inf with a warning) | `spectral_relative_power` and SEF NaN, no warnings; the other 6 unchanged |

Coherence is also NaN without warnings when no band has a bin and the input
is a single 8 s window (the analytic threshold, which divides by zero then,
is not computed), and for an all-zero input (the 0 / 0 coherence is computed
under a local `np.errstate`, and empty means and medians are skipped). The
all-zero input warned the same way before this change.

Before this fix, the new rule alone gave such bands 0 (power), NaN with
"Mean of empty slice" warnings (flatness, BSI, coherence), 0 with a
divide-by-zero warning (entropy), and a crash in `spectral_diff` that
`main_spectral` reported as "Feature function not found". With the default
bands below Nyquist none of this applies, and no stored value changes.

**Size of the change in the test data.** Only `spectral_power` and
`spectral_relative_power` change, and only in epochs that contain NaN. In the
artefacts recording every computed epoch contains some NaN: 108 of 168 values
per feature change (delta, the first band, never does), by a median of 0.15 %
and at most 3.5 %; the summary per band changes by 0, -0.42, -0.058 and
-0.16 % (`spectral_power`) and 0, -2.4, -1.1 and -0.031 % (`spectral_relative_power`)
for delta, theta, alpha and beta. In the edge cases (pre-existing NaN, +inf
line) up to 0.42 %. Every changed value in the test data is lower. The clean
recording is unchanged: its only NaN, the padding of the final epoch, leaves
44 s (2816 samples, 44 bins per Hz), so the edges stay on bins.

**Reference values.** `tests/make_reference.py` also runs the original NEURAL
with only its band-bin selection (the band loop of `spectral_power` and the
total band of `gen_spectrum`) replaced, in memory, by an independent copy of
`band_slice`, and stores the `spectral_power` and `spectral_relative_power`
values in a new section, `with_neural_eeg_features_0.6.1_band_bins`, of the
clean, artefacts, edge cases and input types references.
`neural_outputs.with_fixes` applies it after the other two sections. The other
bin-based features get the same bins under both rules for every stored setting
(64 Hz, the default bands, 2 s and 8 s windows; checked by
`tests/test_band_bins.py`), so they are compared with the original. The
"about" texts of the three fix sections in these four files now also state
the order in which the tests apply them. The four files were remade with the
original NEURAL (commit 78c9425) and the library versions in the script's
header. The unchanged script first reproduced the committed files byte for
byte. After undoing the new section, the new "about" entry and the added
order text in the two existing "about" entries, each new file is
byte-identical to the committed one (only those two lines changed; the rest
is added). CI's drift guard passes on them. `reference_windows.json` (no
`spectral_power`) is unchanged; the script keeps its original "about" text.

**Measured gap in `spectral_diff`.** Before this change, both packages were
run on the same 300 s synthetic recording (the regression tests' clean case,
preprocessed by NEURAL_py: 8 bipolar channels at 64 Hz) with NEURAL_py-like
settings in the reference package (64 s epochs with 50 % overlap; 2 s Hamming
windows with 50 % overlap, no FFT padding; default bands). The summary gap was
-8.4, -3.2, +10.1 and -2.8 % (delta to beta), and up to 25 % on single
channels. The band-bin rule accounts for none of it (the bins are identical
there). Dropping NEURAL_py's final, NaN-padded partial epoch (256-300 s) closes
it exactly; on the 8 complete epochs, the 256 per-channel values agree to
2.2e-15 relative.

**Not changed here (possible later steps).**

- Final partial epoch: `generate_all_features` also computed a final epoch
  padded with NaN (kept if less than 50 % NaN; skipped, like any epoch, if
  its NaN share reached or exceeded 50 %); the reference package uses
  complete epochs only. This affects every per-epoch feature and explains the
  whole `spectral_diff` gap above. Changed in section 4.
- NaN inside epochs: NEURAL_py removes NaN samples before a spectrum
  (`gen_spectrum`; `spectral_power`, flatness, entropy, edge frequency) or
  skips NaN windows (`spectral_diff`); the reference package returns NaN for a
  spectral feature if the epoch contains any NaN.
- Bartlett hop: NEURAL_py's PSD helper uses a hop of
  `ceil((L - 1) * ((100 - overlap) / 100))`, so its Bartlett windows (0 % overlap,
  the default connectivity method) overlap by one sample; the reference
  package's are disjoint.
- Bands with bins but no usable power, which the reference package also
  gives as NaN: a band with a single bin gives `spectral_entropy` -inf with a
  divide-by-zero warning (the reference package needs more than one bin);
  zero power in a band or the total band (e.g. an all-zero signal) gives
  flatness inf, relative power 0, entropy 0 and spectral edge frequency
  0 Hz, with warnings.
- Further band checks of the reference package: it also rejects a lower edge
  of 0 or less and unordered or overlapping bands, and checks the amplitude,
  rEEG and FD bands against Nyquist; NEURAL_py does not (those three use
  filters, not FFT bins).
- Warnings that remain with valid bands: coherence of a single 8 s window
  (one segment: the analytic threshold divides by zero; also before this
  change), and `connectivity_BSI` of an all-zero input (0 / 0 and an empty
  mean); both give the same values as before.
- `connectivity_BSI` with the periodogram method: the band bins use the FFT
  length of the last channel's spectrum, which differs from the others when
  channels lose different numbers of NaN samples (also before this change).

## 4. Complete epochs only

**Rule.** `generate_all_features.overlap_epochs` makes `(N - L_epoch) // L_hop
+ 1` epochs of `L_epoch = floor(EPOCH_LENGTH * Fs)` samples, epoch k holding
samples `k * L_hop` to `k * L_hop + L_epoch - 1`; samples at the end that do not
fill another epoch are not used. `generate_all_features.epoch_count` computes
this count for `overlap_epochs` and `get_max_num_epochs` alike, so the rows
preallocated for `feats_median_ch` always equal the epochs (at even and odd
epoch lengths, e.g. 63.93 Hz). Before, NEURAL made
`ceil((N - (L_epoch - L_hop)) / L_hop)` epochs, at least 1, padding the last one
with NaN; at 50 % overlap the padding alone stayed below the 50 % NaN
threshold, so that epoch was kept unless NaN already in the signal brought
its NaN share to 50 % or more (the rule skipped an epoch whose NaN share
reached or exceeded 50 %). The hop is unchanged; at the tested settings (50 % and
75 % overlap at 64, 100, 250, 256, 63.93 and 127.99 Hz) it equals the
reference package's `size - int(size * overlap // 100)`.

**Basis.** The reference package's `docs/definitions.md`, "Missing data and
recording boundaries": "Ordinary epochs are complete windows only: trailing
incomplete data do not create an additional epoch. A recording shorter than one
ordinary epoch raises `ValueError` when ordinary features are requested." Its
"Version changes and validation limits" lists version 0.1's behaviours that
"are replaced by the processing defaults above", among them "padded ordinary
final epochs". Its README: "Shorter recordings raise `ValueError`; incomplete
trailing windows are discarded."

**Short recordings.** If an epoch-based feature (spectral, amplitude, FD, rEEG
or connectivity) is requested and the recording is shorter than one epoch,
`generate_all_features` raises `ValueError` before computing any feature, e.g.
`Recording is shorter than one analysis epoch: 4032 samples (63 s at 64 Hz); an
epoch is 4096 samples (EPOCH_LENGTH = 64 s)`. Requests with only IBI features
(computed on the whole recording) and an empty feature list return as before,
with no rows in `feats_median_ch`. Before, such a recording gave one padded
epoch: values if more than half of it was data, NaN otherwise. Because NEURAL_py
still uses 64 s epochs, the minimum recording length here is 64 s, against 16 s
with the reference package's defaults; this is temporary: step 3 adopts the
reference package's default settings (16 s epochs with 75 % overlap), as its
author has confirmed.

**Size of the change.** In the test data the complete epochs are bit-identical
and only the final, padded epoch is dropped. Summary per feature (largest
change over the frequency bands), synthetic recordings from the regression
tests' generator, all 19 non-IBI features:

| Recording | Epochs before / after | Features whose summary changes | Largest change | Median over features of the largest change |
| --- | --- | --- | --- | --- |
| 300 s, clean (test data) | 9 / 8 | 18 of 19 | 15.7 % (`amplitude_skew`) | 4.2 % |
| 300 s, artefacts (test data) | 9 / 8 | 18 of 19 | 42.9 % (`rEEG_asymmetry`) | 4.4 % |
| 30 min, clean | 56 / 55 | 18 of 19 | 3.9 % (`rEEG_asymmetry`) | 0.42 % |
| 30 min, artefacts | 56 / 55 | 18 of 19 | 3.7 % (`rEEG_asymmetry`) | 0.37 % |
| 60 min, clean | 112 / 111 | 18 of 19 | 1.4 % (`amplitude_skew`) | 0.23 % |
| 60 min, artefacts | 112 / 111 | 18 of 19 | 2.1 % (`amplitude_skew`) | 0.24 % |

The 300 s sizes are large because those recordings have only 9 epochs, so one
epoch more or less moves the medians a lot; for longer recordings the change
shrinks (the 30 and 60 min recordings were made with the same generator; their
time-limited artefacts all lie in the first 300 s, while the loose F4 and the
shorted Cz electrodes span the whole recording). `spectral_edge_frequency` did
not change in any of these. The edge-case inputs (120 s: 3 to 2 epochs) change
in all 19 features, the row-index inputs in 18 of 19.

**Comparison with the reference package.** The `spectral_diff` gap measured in
section 3 (clean 300 s test recording, preprocessed by NEURAL_py; the reference
package with NEURAL_py-like settings: 64 s / 50 % epochs, 2 s Hamming windows
with 50 % overlap, `n_fft` 128, default bands) closes: per band the summaries
agree to at most 5.2e-18 absolute and 4.7e-16 relative (theta exactly), per
channel to 1.1e-15 relative, and per channel and epoch to 2.2e-15 relative (256
values). Before: -8.4 % to +10.1 % per band, up to 25 % per channel. The
artefacts recording cannot be compared: every epoch contains NaN, which the
reference package rejects (step 5).

**Before/after.** Exact comparison with the previous code (commit 90543fc) on
all test cases: 80 per-epoch arrays lose exactly their final epoch and keep
every other epoch bit-identical; the window-type outputs, the read-only arrays
and the few-channel connectivity cases (64 s: one epoch under both rules) are
unchanged; the IBI outputs are unchanged (they are NaN on these synthetic
signals, so this shows only that the IBI path does not use the epochs). The
row-index case that fails with a KeyError still fails in `overlap_epochs`, as
the stored reference records.

**Reference values.** `tests/make_reference.py` also runs the original NEURAL
with the count lines of its `overlap_epochs` and `get_max_num_epochs` replaced,
in memory, by `(N - L_epoch) // L_hop + 1`, and with the three fixes above
applied too, and stores all 19 non-IBI features in a new section,
`with_neural_eeg_features_0.6.1_complete_epochs`, of the clean, artefacts, edge
cases and input types references (1,605, 1,285, 52 and 94 added lines). It is
applied last, so it replaces the earlier sections for these features; those
stay, as they document each change. `neural_outputs.with_fixes` now takes all
sections out before applying them, and limits this section to the
`generate_all_features` outputs, as `reference_windows.json` computes its
features on one 64 s array, without epochs (that file is unchanged). The
unchanged script first reproduced the committed files byte for byte; without
the new section, the new "about" entry and the added order text in the three
existing "about" entries, each new file is byte-identical to the committed
one; CI's drift guard passes on them (24,147 floats). A regression test checks
that the section's per-epoch values equal the earlier values on the complete
epochs and that its summaries are their medians; it fails if the padded epoch
is kept.

**Not changed here.**

- Epochs with NaN: the 50 % NaN rule stays; the reference package also
  rejects spectral epochs with any NaN (step 5).
- `preprocessing_EEG.overlap_epochs`: an unused copy that keeps the old rule
  (now marked as such in a comment); its output fingerprint in
  `reference_input_types.json` is unchanged (that file gains only the new
  section and its "about" text).
- The hop at custom settings: `utils.gen_epoch_window` computes
  `ceil(L_epoch * ((100 - overlap) / 100))` in floating point, which can differ
  by one sample from the reference package's
  `size - int(size * overlap // 100)`: e.g. a 100-sample epoch at 44 %
  overlap gives 57 here and 56 there.
- rEEG: NEURAL_py still computes rEEG per ordinary epoch; the reference
  package computes it on its own 128 s summary windows (its README: "Selecting
  rEEG with the defaults requires at least 128 seconds of input").
- `experiments/sensitivity/results.md` was made with the old rule; its tools
  (`sensitivity_tools.epochs_of`) now follow the new one.

## 5. Settings passed explicitly (`params`)

**Why.** Step 3 adopts the reference package's default settings, which
changes almost every stored value. The regression tests compare this
repository with the original NEURAL on the original's settings (its
defaults); to keep doing so, they must be able to pass those settings
explicitly, and so must anyone who wants the original settings back. Before,
`generate_all_features` took no settings: it and every feature function it
called made their own `NEURAL_parameters()`.

**Interface.** `generate_all_features(data, save_p_l=None, channel_names=None,
feat_set=None, params=None)`; the new argument is last, so positional calls are
unaffected, and `None` uses `NEURAL_parameters()` exactly as before. A given
`params` is first checked by `NEURAL_parameters.check_parameters`: it must have
the keys of `NEURAL_parameters()` at every level, none missing and none
unknown, with values of the same kind (number, text, list, dictionary; a
zero-dimensional numpy array is not a list or a number; FD
`method` may be `None`, as `main_fd` accepts; `REMOVE_ART` and rEEG
`APPLY_LOG_LINEAR_SCALE` may be `True`/`False`). Otherwise `ValueError` names
every problem before anything is computed, e.g. `params does not match the
structure of NEURAL_parameters(): params['spectral']['L_window'] is missing`.
With the check switched off (for comparison), a misspelt key was silently
ignored, and a missing key or a value of the wrong kind failed inside a feature
(`KeyError`, `TypeError`, `IndexError`, or `Feature function not found`). Values themselves (e.g. a
window type's name) are still checked where they are used. `params` is copied
and never changed; each feature function call gets its own copy of its
group's settings (`spectral_power`, for one, changes the dictionary it is
given), as when each call made its own. `size_feature` also takes `params`.
The `main_*` feature functions already took their group's settings and are
unchanged.

**Not read from `params`** (as before, these are not read by
`generate_all_features`): `LP_fc`, `REMOVE_ART` and `ART_*`, which
`preprocessing_EEG` takes from `NEURAL_parameters()`; `Fs_new`, `BI_MONT`,
`EEG_DATA_DIR` and `EEG_DATA_DIR_CSV`, which nothing reads (the rate after
preprocessing is the `Fs_new` argument of `main_preprocessing`, default 64 Hz,
and the montage that of `utils.set_bi_montage`); and the top-level
`FREQ_BANDS` and `FILTER_REPLACE_ARTEFACTS`, which only give the groups their
defaults inside `NEURAL_parameters()` (each group has its own `freq_bands` and
`FILTER_REPLACE_ARTEFACTS`). Assigning new values to them in `params` leaves
the outputs unchanged (checked for `FREQ_BANDS`, `FILTER_REPLACE_ARTEFACTS`,
`LP_fc`, `Fs_new`, `BI_MONT`, `REMOVE_ART`, `ART_HIGH_VOLT` and
`EEG_DATA_DIR`). In `NEURAL_parameters()` the spectral, amplitude, rEEG and
connectivity `freq_bands` are the very list `FREQ_BANDS`, so editing that list
in place changes those four groups' bands (not FD's band or the spectral total
band, separate lists); `FILTER_REPLACE_ARTEFACTS` is text and cannot be edited
in place. No warning is given for either.

**Column names and the feature set.** Three faults of the output code, also on
the previous code when the same settings were made by editing
`NEURAL_parameters()` (checked there for all five band-using groups):

- A single band given as one row, `[[0.5, 4]]` (a list or a numpy array), was
  taken for a flat `[low, high]` pair: `IndexError` in `get_feature_names`,
  although the feature functions accept it. Now each row is a band
  (`feature_band_edges`); a flat pair is still one band.
- Every band edge except a lower edge of 0.5 was cut to its integer part, so
  distinct bands could share a column name: `[0.5, 4.1]` and `[0.5, 4.9]` both
  gave `spectral_power__05_4`, and the summary held the second band's value in
  both columns (per-epoch values 156.5 and 170.1 for the first epoch of one
  channel; summary 181.98 twice). Now an edge that is a whole number or 0.5 is
  written as before (all default column names are unchanged) and any other
  edge in full with `p` for the decimal point (`band_edge_label`: `4p1`,
  `0p25`), so distinct edges get distinct names (`05_4p1`, `05_4p9`). This
  renames the columns of non-default bands with such edges (e.g. `[0.5, 3.5]`
  was `05_3`, now `05_3p5`; an upper edge of 0.5 was `0`, now `05`). Two bands
  with the same edges would still share a name, so that raises `ValueError`
  naming both bands, before anything is computed.
- The columns came from `params['FEATURE_SET_ALL']` filtered by `feat_set`, so
  a requested feature missing from `FEATURE_SET_ALL` was computed and then
  failed (`ValueError: Feature name spectral_power__05_4 does not exist`; also
  on the previous code with an edited `NEURAL_parameters()`). Now a given
  `feat_set` decides both the features and the columns;
  `FEATURE_SET_ALL` is the feature set when `feat_set` is not given and
  orders the columns, as before (features not in it follow, in `feat_set`
  order). With the default `FEATURE_SET_ALL` the columns are as before, whatever
  the order of `feat_set`.
- Feature names: every requested name (`feat_set`, or `FEATURE_SET_ALL` when
  `feat_set` is not given) must now be one of the 23 supported features
  (`NEURAL_parameters.SUPPORTED_FEATURES`, the default `FEATURE_SET_ALL`;
  `check_requested_features`, which first applies `check_feature_names` and
  its message for the 7 removed names), else `ValueError` names the unknown
  ones, before any feature is computed. A supported feature missing from a
  custom `FEATURE_SET_ALL` is accepted. On the previous code a misspelt name
  also raised `ValueError`, but later and with varying messages (`Feature name
  IBI_burst_pct__05_30 does not exist`, `Feature function not found:
  spectral_pwr`); without this check, the column change above would have
  given a misspelt IBI name (no burst detector) or connectivity name (one
  channel) a column of NaN. A valid IBI name without the burst detector still
  gives NaN, as before.

**Not changed here.**

- An empty band list (`freq_bands = []`, which `main_rEEG` and `main_fd`
  accept as one unfiltered band) still fails with `IndexError` when naming
  the columns, as before.
- rEEG `APPLY_LOG_LINEAR_SCALE` has no effect (the inverted condition below);
  it will follow the reference package's scaling, verified against it, in
  the rEEG change of step 3.
- The three coherence failures described below.

**Tests.** `tests/neural_outputs.py` writes out the original's settings
(`original_settings()`, built as the original's `NEURAL_parameters()` builds
them; its `FEATURE_SET_ALL` less the 7 removed names). They equal the
original's `NEURAL_parameters()`, checked with the original in its own
environment and in the 2020 environment (values, key order and the groups'
shared `FREQ_BANDS` list), and, for now, this repository's defaults. The
regression tests (`compute_features(..., params)`), the edge cases (each
`*_results(params=...)`), and the unit tests whose expected values were
recorded with these settings (`test_band_bins.py`,
`test_connectivity_crashes.py`, `test_spectral_diff_fix.py`, and the column
counts of `test_removed_features.py`) pass them explicitly. The tests of general
rules (epoch counts, FD bands) stay at the defaults. `make_reference.py` is
unchanged: it calls the shared helpers without `params`, so the original runs
with its own defaults; run again through the changed helpers, it gives the
committed reference files byte for byte (the four modern ones with pandas
2.3.3, the windows file in the 2020 environment). The sensitivity experiment
also passes the original settings when the NEURAL in use takes `params`.

**Checks** (`tests/test_params.py`): for each setting that
`generate_all_features` or a feature group reads (30 cases over the spectral,
amplitude, rEEG, FD and connectivity groups and the epoch settings, and the
connectivity window type and overlap each on their own against the Welch PSD),
the per-epoch values equal those of the feature function called directly with
the same settings, and differ from the defaults, while an untouched
`NEURAL_parameters()` still gives the defaults; `FEATURE_SET_ALL` is read from
`params`; the IBI features read no settings; `params` is unchanged after a
call; calls with different settings are independent; a feature call does not
change the next one's settings; bad `params` (including zero-dimensional
arrays) raise `ValueError` naming the setting; the default column names (all
74, written out) are unchanged; one band as a list or an array works for every
band-using feature; fractional bands get their own columns and values; the
same band twice raises `ValueError`; `feat_set` decides the columns; the
top-level `FREQ_BANDS` behaves as described above. `APPLY_LOG_LINEAR_SCALE`
reaches `rEEG.gen_rEEG`, but the scaling never changes a value: its condition
is inverted (`if not ihigh:`, as in the original 78c9425), so it runs only
when no range exceeds 50, when there is nothing to scale; not changed here,
and recorded by a strict expected-failure test. Three coherence settings fail in `connectivity_coh` (unchanged code;
not reached with the defaults), each reported as `Feature function not found`:
the surrogate threshold (`IndexError`: the threshold has shape (1, N), so the
mask `coh[p, :] < threshold` is two-dimensional and `coh[p, mask]` has too many
indices), no threshold (`''` is compared with `.lower` itself, so it is rejected
as an unknown option), and the Welch PSD with the analytic threshold (the
switch to Bartlett warns with a list as its message, which Python's warnings
registry cannot store, from the second warning on). A test records them; the
last goes with the switch to Bartlett in step 3.

## Assumptions for review

- Missing data: the handling of NaN inside epochs will follow
  neural_eeg_features 0.6.1 (step 5).
- Filters: the feature filters will follow the 0.6.1 code exactly (step 4).
- Referential check: the option to skip the referential check will be both a
  NEURAL_py parameter and an app setting.
- IBI: the burst detector and the IBI features will follow 0.6.1 (step 6).
- Settings: neural_eeg_features 0.6.1 is the reference, and its default
  settings (16 s epochs with 75 % overlap and the others) will be adopted in
  step 3, as the reference package's author has confirmed.
- Original settings stay reproducible: the old filter and the old
  missing-data rule will stay selectable in steps 4-5, so that results at the
  original settings (passed as `params`, section 5) can still be reproduced
  and the regression tests can keep comparing them with the original NEURAL.
