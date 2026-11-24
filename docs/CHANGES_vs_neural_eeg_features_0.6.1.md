# Changes to match neural_eeg_features 0.6.1

The reference package neural_eeg_features 0.6.1 revises the NEURAL feature set
and its filters. This file lists every change made to this NEURAL_py to match
it, one row per change, in the order they were made. Section names refer to
the reference package's `docs/definitions.md`.

| # | Change | Before | After | Reason (reference `docs/definitions.md`) | Verification |
| --- | --- | --- | --- | --- | --- |
| 1 | Remove 7 features: `amplitude_total_power`, `amplitude_SD`, `rEEG_mean`, `rEEG_width`, `rEEG_SD`, `connectivity_coh_max`, `connectivity_coh_freqmax` | `FEATURE_SET_ALL` has 30 names (26 non-IBI); with the default bands, 102 feature columns; a default call's `feats_median_ch` has 98 columns (the non-IBI ones) | `FEATURE_SET_ALL` has the reference package's 23 names in the same order (19 non-IBI); 74 columns. `feats_median_ch` still keeps the first 98 columns (`[:98]` unchanged): the same explicit feature list gives the same columns; a default call gives 74 (28 removed-feature columns gone, the 4 always-NaN IBI columns now included). Requesting a removed name raises `ValueError` naming it, in `generate_all_features`, `main_amplitude`, `main_rEEG` and `main_connectivity`. Public functions `amplitude_total_power`, `amplitude_SD`, `rEEG_mean`, `rEEG_width`, `rEEG_SD` deleted; coherence max and max-frequency branches removed | "Version changes and validation limits" (0.2 removes the two coherence features, 0.3 the two amplitude features, 0.4 `rEEG_mean`, 0.5 `rEEG_width` and `rEEG_SD`; requesting a removed name raises `ValueError`); "Deliberate settings and feature-selection differences" (the seven names deliberately removed; 23 remain); "Feature catalogue" (the amplitude pair removed as largely redundant measures of band energy) | Exact comparison with the previous code (commit dc272ea) on all test cases, with the same explicit feature lists: 16,299 values, 0 differ, same columns (details below). Regression tests against `tests/data/` (removed features skipped): all pass, 0 values outside tolerance. New `tests/test_removed_features.py`: each removed name raises `ValueError`; `FEATURE_SET_ALL` equals the reference package's `ALL_FEATURES` and the removed names equal those in its `docs/definitions.md`; `feats_median_ch` keeps all columns of a request with fewer than 98 columns, as before (73 for all features except FD; 4 with empty rEEG bands and `spectral_power` only; 74 for the default call, including the 4 always-NaN IBI columns) |
| 2 | `amplitude_skew` and `amplitude_kurtosis`: bias-corrected moments, as in the reference package | Biased moments: `abs(scipy.stats.skew(x, nan_policy="omit"))` and `scipy.stats.kurtosis(x, fisher=False)` (Pearson). `main_amplitude` removed NaN first; called directly, kurtosis gave NaN for NaN and both gave NaN for +/-inf. No explicit rule for short input: 2 values gave skewness 0 and kurtosis 1, 3 values gave a kurtosis. Constant input: NaN from scipy's own check | `abs(scipy.stats.skew(x, bias=False))` and `scipy.stats.kurtosis(x, fisher=False, bias=False)` (Pearson) on the finite values only (NaN and +/-inf ignored). NaN for fewer than 3 (skewness) or 4 (kurtosis) values, and for constant values (range not above eps * max(1, max abs value)), as in the reference package's `amplitude.py`. In the test data every value rose slightly (skewness +0.04-0.06 %, kurtosis +0.04-0.16 %). The skewness magnitude always increases with the correction (factor sqrt(n(n-1))/(n-2), +0.037 % for a full 64 s epoch, n = 4096), unless it is 0; the kurtosis usually does for EEG-like data but can decrease for very flat signals (4096 alternating -1/+1 values: 1.0 becomes 0.99902). No other output changes | "Skewness and kurtosis: correction to the earlier audit" (the reference package uses `bias=False`, and `fisher=False` for Pearson kurtosis; the older NEURAL Python port uses biased moments; example `[-2, -1, 0, 1, 2]`: kurtosis 1.8, original 1.7); "Feature catalogue" (absolute bias-corrected skewness; bias-corrected Pearson kurtosis, not excess kurtosis) | Same arrays through the reference package's `amplitude_features()` (in its own environment) and this repository's functions: 488 arrays (456 real band-filtered epochs of the synthetic test recordings, 32 synthetic edge cases), every finite value exactly equal (max abs and rel difference 0), NaN in the same places (skewness 10, kurtosis 12). Exact comparison with the previous code (commit 2bd0742) on all test cases: 15,070 values of other features, 0 differ; of each moment's 748 values, 684 changed, 64 NaN in both. Regression tests against the new reference section `with_neural_eeg_features_0.6.1_moments` and the original: all pass, difference 0. New `tests/test_amplitude_moments.py` (closed-form formulas, the reference package's example, short, constant, NaN and +/-inf inputs) |

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
