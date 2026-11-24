# Changes to match neural_eeg_features 0.6.1

The reference package neural_eeg_features 0.6.1 revises the NEURAL feature set
and its filters. This file lists every change made to this NEURAL_py to match
it, one row per change, in the order they were made. Section names refer to
the reference package's `docs/definitions.md`.

| # | Change | Before | After | Reason (reference `docs/definitions.md`) | Verification |
| --- | --- | --- | --- | --- | --- |
| 1 | Remove 7 features: `amplitude_total_power`, `amplitude_SD`, `rEEG_mean`, `rEEG_width`, `rEEG_SD`, `connectivity_coh_max`, `connectivity_coh_freqmax` | `FEATURE_SET_ALL` has 30 names (26 non-IBI); with the default bands, 102 feature columns; a default call's `feats_median_ch` has 98 columns (the non-IBI ones) | `FEATURE_SET_ALL` has the reference package's 23 names in the same order (19 non-IBI); 74 columns. `feats_median_ch` still keeps the first 98 columns (`[:98]` unchanged): the same explicit feature list gives the same columns; a default call gives 74 (28 removed-feature columns gone, the 4 always-NaN IBI columns now included). Requesting a removed name raises `ValueError` naming it, in `generate_all_features`, `main_amplitude`, `main_rEEG` and `main_connectivity`. Public functions `amplitude_total_power`, `amplitude_SD`, `rEEG_mean`, `rEEG_width`, `rEEG_SD` deleted; coherence max and max-frequency branches removed | "Version changes and validation limits" (0.2 removes the two coherence features, 0.3 the two amplitude features, 0.4 `rEEG_mean`, 0.5 `rEEG_width` and `rEEG_SD`; requesting a removed name raises `ValueError`); "Deliberate settings and feature-selection differences" (the seven names deliberately removed; 23 remain); "Feature catalogue" (the amplitude pair removed as largely redundant measures of band energy) | Exact comparison with the previous code (commit dc272ea) on all test cases, with the same explicit feature lists: 16,299 values, 0 differ, same columns (details below). Regression tests against `tests/data/` (removed features skipped): all pass, 0 values outside tolerance. New `tests/test_removed_features.py`: each removed name raises `ValueError`; `FEATURE_SET_ALL` equals the reference package's `ALL_FEATURES` and the removed names equal those in its `docs/definitions.md`; `feats_median_ch` keeps all columns of a request with fewer than 98 columns, as before (73 for all features except FD; 4 with empty rEEG bands and `spectral_power` only; 74 for the default call, including the 4 always-NaN IBI columns) |

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

**Reference values.** The regression reference files in `tests/data/` are
unchanged: they were made by the original NEURAL and still hold the 7 removed
features. The tests skip them when loading the files
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
