# Review notes

These notes are for reviewing this maintained version of NEURAL_py against the original Python code by Brian M. Murphy and John M. O'Toole (commit 78c9425): what changed, how it was checked, the numerical differences found, and the decisions needed.

## In short

- **Same results on one machine:** for everything the 28 tests check with modern libraries, the outputs equal the original's exactly (difference 0); the one window-type check against the 2020 environment differs by at most 1.6e-15.
- **Small differences between environments:** the original itself reportedly varies by up to about 3e-7 relative (about 7 significant figures) between library versions and between computers. Artefact decisions and NaN positions did not change (reported).
- **Likely cause (to be tested):** the order-5 Butterworth band filters in `(b, a)` form, which can magnify rounding errors.
- **Original behaviour kept on purpose**, so results can be compared before any scientific change.
- **Issues found in the original:** some sample rates (e.g. 96, 160, 480 Hz) are downsampled to the wrong rate but labelled 64 Hz; preprocessing fails at 80 Hz or below (unless every channel has already been removed as artefact); the correlation feature is Pearson but the README says Spearman; two settings are never read.

## Decisions needed

1. **Tolerance:** what difference is acceptable per feature group, for summary and per-epoch values? (Tests use 1e-9 relative; the CI drift guard 1e-5.)
2. **Reference:** keep this Python version (78c9425) as the reference, or the MATLAB NEURAL? Could MATLAB outputs be shared for the two synthetic test files?
3. **Filter form:** keep `(b, a)`, which matches both the Python and MATLAB originals, or switch to the more stable second-order sections (SOS), which would change numbers (size to be measured)?
4. **Correlation:** both versions compute Pearson; the README says Spearman. Keep Pearson and correct the text?
5. **Downsampling:** fix the wrong output rates (e.g. 96, 160, 480 Hz), or reject such rates?
6. **Supported data:** require more than 80 Hz? Which sample rates and recording lengths should be supported and tested?
7. **Other inherited behaviour** (table below): fix or keep each item?
8. **Versions:** support Python older than 3.14? Which libraries should be pinned exactly, and which given only a minimum?
9. **IBI features:** keep them unsupported (they need a separate burst detector), or add and test the detector?

## What changed

Across **16 commits**, only **four modules** in `src/` changed for pandas 3, SciPy and pyedflib compatibility.
**Feature formulas**, filter designs and default parameters are unchanged.
The changes adapt array writes, indexing, window-function imports and EDF export; exact agreement on tested inputs does not guarantee every possible call.

<details>
<summary>Source changes, feature map and review context</summary>

The comparison is against original NEURAL_py (BSD-3-Clause) at
[78c9425](https://github.com/BrianMur92/NEURAL_py_EEG_feature_set/commit/78c94258e4a3e6504e469f418443c78926e1a6be).
Source line numbers refer to dd7235e. **Reported** marks figures from GitHub
Actions logs or earlier one-off checks not independently reproduced in this review.

The source diff has 96 lines added and 21 removed, including comments and
docstrings. After the decisions, suggested reading is the numerical findings,
then the four-file source diff.

Only Python 3.14 has been tested; `setup.cfg` requires Python ≥ 3.14.
The package declares minimum library versions; CI pins the other libraries
while testing two pandas versions. A lock file is proposed.

IBI requires a separate burst detector. `IBI_features.main_IBI` looks at a
placeholder location (line 85) and returns NaN if the detector is missing
(line 115).

`git diff 78c9425 dd7235e` shows no changes to `NEURAL_parameters.py`,
`amplitude_features.py`, `spectral_features.py`, `rEEG.py`,
`fd_features.py`, `IBI_features.py` or `mfiltfilt.py`.

| Module | Change | Reason |
|---|---|---|
| `preprocessing_EEG.py` | `remove_artefacts` filters channel copies, writes filled NaN values back as the original did through pandas views, and uses `.loc` for +inf replacement; `overlap_epochs` retains pandas < 3 indexing | pandas 3 |
| `utils.py` | Window functions come from `scipy.signal.windows`; adds `index_like_pandas2`; EDF export uses copies and `sample_frequency`; updates docstrings | SciPy ≥ 1.13, pandas 3, pyedflib ≥ 0.1.41 |
| `generate_all_features.py` | `overlap_epochs` calls `utils.index_like_pandas2` | pandas 3 |
| `connectivity_features.py` | `gen_cross_spectrum` works on a private copy | pandas 3 read-only arrays |

The README’s “Maintenance / What changed and why” also lists packaging,
dependency and test changes.

| What | Module in `src/NEURAL_py_EEG/` | Read first |
|---|---|---|
| Defaults | [`NEURAL_parameters.py`](../src/NEURAL_py_EEG/NEURAL_parameters.py) | `NEURAL_parameters()` |
| Epochs and summaries | [`generate_all_features.py`](../src/NEURAL_py_EEG/generate_all_features.py) | `generate_all_features`: defaults are 64 s epochs, 50 % overlap; NaN exclusion and summaries are described below |
| Spectral (6 features) | [`spectral_features.py`](../src/NEURAL_py_EEG/spectral_features.py) | `main_spectral`, `gen_spectrum`, `gen_STFT`, then feature functions |
| Amplitude (6) | [`amplitude_features.py`](../src/NEURAL_py_EEG/amplitude_features.py) | `main_amplitude`: band filter, then feature functions |
| rEEG (8) | [`rEEG.py`](../src/NEURAL_py_EEG/rEEG.py) | `main_rEEG`, `gen_rEEG`, then feature functions |
| FD (1) | [`fd_features.py`](../src/NEURAL_py_EEG/fd_features.py) | `main_fd`, `fd_higuchi` |
| Connectivity (5) | [`connectivity_features.py`](../src/NEURAL_py_EEG/connectivity_features.py) | `main_connectivity`, `connectivity_BSI`, `connectivity_corr`, `connectivity_coh`, `gen_coherence` |
| IBI (4) | [`IBI_features.py`](../src/NEURAL_py_EEG/IBI_features.py) | `main_IBI`: requires the separate burst detector |
| Filters | [`utils.py`](../src/NEURAL_py_EEG/utils.py), [`mfiltfilt.py`](../src/NEURAL_py_EEG/mfiltfilt.py) | `filter_butterworth_withnans`, `mat_filtfilt`, `filter_zerophase` |
| Preprocessing | [`preprocessing_EEG.py`](../src/NEURAL_py_EEG/preprocessing_EEG.py) | `main_preprocessing`, `remove_artefacts`, `art_per_channel`, `LPF_zero_phase`, `signal_downsample` |

For amplitude, spectral, rEEG and FD, a channel-epoch with ≥ 50 % NaN is
skipped. Connectivity applies that threshold to all channel-samples in the
epoch together (`generate_all_features:246–249,314–315`).

The returned summaries handle NaN differently. For amplitude, spectral, rEEG
and FD, `feat_st` uses `np.nanmedian` over epochs, then channels (lines
269,271). `feats_median_all` uses ordinary `np.median` across those channel
medians (line 282). `feats_median_ch` uses ordinary median across channels
for each epoch (line 275). Ordinary median propagates NaN; `nanmedian`
ignores it. Connectivity uses `nanmedian` over epochs (lines 321,327).

</details>

<details>
<summary>All 16 commits on master since 78c9425, oldest first; no merges</summary>

| Commit | Subject |
|---|---|
| a1edbc4 | added pandas 3 fix to preprocessing |
| bc59d0f | added fork readme update |
| 704db5a | added gitignore for python, pip and pytest |
| 00da1be | added tested dependency versions and requirements dev txt |
| d63b1e1 | fixed NaN filling to write filled value back so pandas3 matches the original value |
| 6883210 | fixed inf to NaN replacement using .loc so it works on pandas 3 |
| 9b38abb | fixed EDF export for pandas 3 and new pyedflib while keeping original behaviour |
| 8df94de | fixed window functions moved to scipy.signal.windows in new SciPy |
| 89827a3 | fixed invalid escape sequence warning in docstring for Python 3.12+ |
| f5b2af1 | kept pandas 2 positional indexing in overlap_epochs so pandas 3 picks the same samples |
| 60c1d1d | fixed read-only array crash in gen_cross_spectrum on pandas 3 using a private copy |
| 92482f2 | added notes on in-place functions and updated examples for pandas 3 |
| 1876125 | added regression and edge case tests comparing against the original NEURAL outputs |
| ddf1c1e | added GitHub Actions workflow to run tests on Windows and Ubuntu with pandas 2 and 3 |
| 056317f | added maintenance section to README and changelog entry for the updated fork |
| dd7235e | made CI compare with the original on each runner and fail on large reference drift |

</details>

## How it was checked

- **Inputs:** two synthetic EDFs, “clean” and “artefacts”, each 300 s, 256 Hz and 9 electrodes; all 26 non-IBI features under tested settings; no real recordings opened.
- **References:** the original source was SHA-256 verified; outputs include feature values and sampled EEG checks.
- **Tests:** relative tolerance 1e-9, absolute 1e-12; 28 passed, with modern-reference differences exactly 0 and a separate 2020 window exception below.
- **CI:** Windows and Ubuntu compare this maintained version and the original on the same runner, then guard drift from committed references, also requiring matching structures, NaN positions and discrete outputs.

<details>
<summary>Run results, inputs, reference provenance, tolerances and CI</summary>

**Run for these notes:** Windows, Python 3.14.7, numpy 2.5.3, SciPy 1.18.1,
pandas 3.0.2, MNE 1.13.2, matplotlib 3.11.2 and pyedflib 0.1.42.

```text
28 passed in 45.83s
```

Every checked modern-reference group had a largest difference of exactly 0.
The separate 2020 window comparison had a largest relative difference of
1.61e-15 and absolute difference of 8.88e-16.

No real recordings were opened for this review. The inputs are “clean” and
“artefacts”. The three tested window types are `'tuke'`, `'bart'` and
`'blackmanharris'`.

To obtain synthetic files for a MATLAB comparison, run
`python tests/synthetic_edf.py <folder>`.

**Inputs.** `tests/synthetic_edf.py` uses a fixed seed and whole-number
arithmetic to make byte-identical files across machines. Tests check their
SHA-256 checksums. The “artefacts” input exercises all four per-channel
checks and both channel-removal checks. `tests/edge_cases.py` covers
pre-existing NaN, +/-inf, row indexes, read-only arrays and EDF export.
These checks extend beyond what the synthetic EDF inputs can represent.

**References.** `tests/make_reference.py:150–160` checks the SHA-256 hashes
of 13 original modules against commit 78c9425 before writing references.
It normalizes Windows line endings to Unix line endings before hashing;
this is source identity after that normalization, not literal byte identity.
For EDF export, the reference harness adapts the obsolete header key
`sample_rate` to `sample_frequency` at the pyedflib boundary. Read-only
array references use writable inputs because the original cannot accept
read-only ones.

The committed main, edge-case and input-type references record Windows 11,
Python 3.14.7, numpy 2.5.3, SciPy 1.18.1, pandas 2.3.3, MNE 1.13.2,
matplotlib 3.11.2 and pyedflib 0.1.42 in `made_with`.
`reference_windows.json` records the 2020 environment, including SciPy 1.3.1:
the original window imports require SciPy < 1.13.

**What is compared.** Stored feature outputs and the checked discrete outputs
must agree. The EEG is checked by summaries and sampled values, not every
sample: every 500th sample in the main checks, every 997th in the NaN/inf
edge checks (`tests/neural_outputs.py`). Descriptive metadata is not all
compared by pytest.

For floating-point outputs, `tests/neural_outputs.py` sets:

```text
abs(new - reference) <= 1e-12 + 1e-9 * abs(reference)
```

NaN must occur in the same positions. Checked counts, positions, text and
whole numbers must match exactly.

**Workflow.** `.github/workflows/tests.yml` runs on each push and pull request,
with four Windows/Ubuntu × pandas combinations: pandas 2.3.3 and latest 3.x,
all on Python 3.14. It pins numpy, SciPy, MNE,
matplotlib and pyedflib to the versions above. Each job:

1. Installs original commit 78c9425 with pandas 2.3.3 in a separate environment.
2. Regenerates the main, edge-case and input-type references there, then compares
   this maintained version with them at the unchanged test tolerance. The committed
   `reference_windows.json` remains in use.
3. Runs `tests/check_reference_drift.py`, even after test failure, **provided
   `REFERENCE_TEMP` has been recorded**. A failure before that setup can skip
   the guard. It fails above `1e-12 + 1e-5 * abs(committed)`, or for different
   structures, NaN positions or discrete values. Only recorded OS and Python
   versions may differ without failure; those changes are printed.

The four regenerated references contain 13,867 floats: clean 7,042,
artefacts 4,354, edge cases 1,384 and input types 1,087. The retained 2020
window reference has another 1,355 floats and is outside the drift guard.

The guard can catch changes shared by the original and this maintained version, including
shared-helper errors. Shared changes smaller than roughly 1e-5 relative can
escape it; the absolute allowance matters near zero. It does not establish
the cause of drift or guarantee that every environment passes.

</details>

## Numerical differences

**Relative difference** means absolute difference divided by the absolute reference value, when nonzero.

| Comparison | What differs | Largest relative difference |
|---|---|---|
| This maintained version vs original, one machine and modern pinned libraries; original uses pandas 2.3.3 | Compatibility changes; this maintained version also tested with pandas 3 | Exactly 0 for checked modern-reference outputs |
| Original: 2020 environment vs modern environment | Libraries and Python version | Up to 3e-7 (reported) |
| Original: GitHub Windows runner vs reference PC | Machine, Windows version and Python patch version | 1.6e-7 (reported) |
| Original: GitHub Ubuntu runner vs reference PC | Runner environment, including machine and OS | 3.2e-7 (reported) |

- **Decisions:** the 2020 comparison reported identical artefact reports, removed channels and NaN positions.
- **Scale:** the largest relative differences were small-valued per-epoch features, with small absolute differences; the comparisons change several components and cannot isolate a cause.
- **Earlier figure:** ~1e-8 was a lower bound because failed comparisons stopped before later arrays.

<details>
<summary>Environment versions, worst values and interpretation</summary>

Runner maxima are reported from the dd7235e drift-guard step. They passed
the guard’s 1e-5 relative limit with its additional 1e-12 absolute allowance.
The pattern is consistent with numerical sensitivity already present in the
original; it still needs the direct test described below.

The one-off 2020 comparison is described in the README and was not rerun.
It used Python 3.7.9, numpy 1.17.1, SciPy 1.3.1, pandas 0.25.1, MNE 0.18.2,
matplotlib 3.1.1 and pyEDFlib 0.1.15. These match the README’s comparison
paragraph. The original Requirements table instead lists pyEDFlib 0.1.14;
the README explains that it had no Python 3.7 Windows build.

The README’s “Tested versions” reports zero modern-reference differences
with pandas 2.3.3, 3.0.2, 3.0.6 and 3.1.0. This review reran 3.0.2 only.

For the runner comparisons, all 13,867 floats in the four modern references
were reported checked, with matching NaN positions, counts and structure.
The Windows runner was reported as Windows Server 2025, Python 3.14.9,
versus Windows 11 and Python 3.14.7 on the reference PC. Pinned library
versions matched. This is not a machine-only comparison.

The reported worst relative differences were:

- Windows: a per-epoch `rEEG_asymmetry` value around 0.0049, absolute
  difference around 8e-10.
- Ubuntu: a per-epoch `amplitude_skew` value around 0.0012, absolute
  difference around 4e-10.
- Largest absolute difference: around 4.3e-7 for `amplitude_env_SD` values
  around 684, or around 6e-10 relative.

The largest relative differences are about 63 and 31 times smaller than
1e-5, respectively. The guard actually uses both relative and absolute
allowances, rather than a relative limit alone.

`amplitude_skew` is absolute skewness (`amplitude_features.py:73`), near
zero for a nearly symmetric sample distribution. `rEEG_asymmetry` is
`(B - A) / (A + B)` (`rEEG.py:170–172`), near zero when its percentile
margins lie equally far from its median. A small reference magnitude can
increase the relative difference even when the absolute difference is small.
The source of those absolute differences has not yet been localized.

The README now gives the complete runner maxima. The CHANGELOG retains the
historical ~1e-8 figure explicitly as a first-run lower bound.

</details>

## Likely cause

The **larger reported differences** occur in band-filtered groups using order-5 Butterworth filters in `(b, a)` form; spectral, BSI and coherence agreed to about 1e-14 in the reported 2020 comparison.
[SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.butter.html) recommends **second-order sections (SOS)**, the same intended filter split into short stages: “It is recommended to work with the SOS representation.”
Rounding sensitivity is a **likely amplifier**, a hypothesis to test by perturbing synthetic EEG and comparing processing stages with both forms, including per-epoch values and medians.
**Results:** to be added.

<details>
<summary>Filter paths, MATLAB citations, planned experiment and coefficient analysis</summary>

The default amplitude, rEEG, FD and `connectivity_corr` calculations use
`utils.filter_butterworth_withnans`. Each band uses an order-5 low-pass,
then an order-5 high-pass. In `(b, a)` form each stage uses numerator and
denominator coefficient arrays. Low cutoffs can make this form sensitive to
rounding. Spectral, BSI and coherence do not directly use it, but share preprocessing.

SciPy warns that converting roots to polynomial coefficients can cause numerical
problems from order four onward. Its legacy default remains `'ba'`; SOS is
recommended for general filtering. The quoted documentation was also checked
against installed SciPy 1.18.1. Hilbert envelopes, skewness, percentiles and
other stages may contribute to the feature differences.

Public MATLAB NEURAL also [designs `(b, a)` filters](https://github.com/otoolej/qEEG_feature_set/blob/206a89b8943f029a32947b1715f75b62ab8d5c8a/utils/filter_butterworth_withnans.m#L59-L76)
and [uses `filtfilt(b,a,x)`](https://github.com/otoolej/qEEG_feature_set/blob/206a89b8943f029a32947b1715f75b62ab8d5c8a/utils/filter_butterworth_withnans.m#L102).
Keeping this form follows both originals; SOS would change both implementations’
numerical form. This does not establish equality between MATLAB and Python outputs.

**Planned test on one machine:**

1. Perturb synthetic input EEG by about 1e-15 relative, a few units in the last
   place (ULP: the spacing between nearby representable numbers).
2. Measure differences after artefact removal, the 30 Hz low-pass,
   downsampling, the band filter, envelope or rEEG calculation, and features.
   Include per-epoch values and medians.
3. Repeat using `scipy.signal.butter(..., output='sos')`. Preserve
   `mat_filtfilt`’s padding length, odd reflection and steady-state start.
4. If SOS reduces the differences by orders of magnitude, that supports the
   hypothesis. Otherwise, examine the other stages.

This experiment has not been run for these notes.

`utils.filter_butterworth_withnans:517–607` designs the filters with
`scipy.signal.butter` (lines 565 and 567), then applies
`mfiltfilt.mat_filtfilt:57–93`. It filters forward and backward using
`scipy.signal.lfilter`, with steady-state initial conditions and odd-reflection
padding of `3 * (max(len(b), len(a)) - 1)` samples at each end. This is
3 × order for these filters. Its docstring states the intent to match MATLAB
`filtfilt`; that statement does not prove identical outputs.

| Directly uses this band filter | Does not directly use it |
|---|---|
| All 6 amplitude features: `main_amplitude:136` | All 6 spectral features: `gen_spectrum`, `gen_STFT` (periodogram or Welch) |
| All 8 rEEG features: `main_rEEG:228` | `connectivity_BSI`: Welch or Bartlett spectrum |
| FD, default 0.5–30 Hz: `main_fd:162,171` | `connectivity_coh_mean`, `_max`, `_freqmax`: `gen_coherence` |
| `connectivity_corr:497` | — |

Preprocessing uses this helper for removal decisions: 0.5–20 Hz with orders
5/5 in `remove_artefacts`, and 0.1–40 Hz with low/high orders 5/2 in
`art_per_channel`. It does not pass the band-filtered signal onward.
However, the referential and coupling calls fill pre-existing NaN in their
DataFrames before later checks (`remove_artefacts:307–316,361–369`).
The 30 Hz low-pass in `LPF_zero_phase` is an FIR filter, a weighted sum
without recursive feedback, implemented by `utils.filter_zerophase`.

**Rechecked coefficient example.** For a 0.5 Hz, order-5 high-pass at 64 Hz
(used in the 0.5–4 Hz band and FD), SciPy 1.18.1 gives rounded denominator
coefficients:

```text
a = [1, -4.841, 9.377, -9.084, 4.401, -0.853]
```

Using full precision, their sum is 2.635e-7. The pole radii are
0.9521–0.9850; poles describe how feedback persists through later samples.
The slowest has a decay time constant of 1.03 s. The denominator-only
gain at zero frequency, `abs(1 / sum(a))`, is about 3.795 million.
This is not the gain of the complete high-pass filter, which rejects zero
frequency, and does not predict the size of a feature error.

Double-precision arithmetic carries roughly 16 significant digits. Such
coefficient cancellation can amplify rounding sensitivity. In the re-probe,
keeping `a[0] = 1` and moving `a[1:]` one representable number toward
negative infinity shifted poles by up to 4.06e-9. Other perturbation directions
gave different shifts.

SOS represents this filter as one first-order and two second-order sections.
Their denominator coefficients sum to about 0.0479, 0.00232 and 0.00237,
rather than 2.635e-7 for the single polynomial. These observations support
testing SOS; they do not quantify its effect on the final EEG features.

**Other observations consistent with the hypothesis:**

- The reported 2020 comparison gives differences up to 3e-7 for groups using
  the band filter, versus about 1e-14 for spectral, BSI and coherence.
- The window-type test calculates spectral, BSI and rEEG features without
  the band filter. Its 2020-reference comparison differs by at most 1.61e-15.
- The first GitHub run reported preprocessed-EEG differences around 1e-14
  (README; not independently reproduced here).
- A reported simulation added 1–4 ULP to preprocessed EEG and reran features:
  per-epoch `amplitude_skew` and `rEEG_asymmetry` changed by up to about
  4e-7 relative, median-channel values by about 2e-9 to 9e-9.
  This is a one-off sensitivity estimate, not a hosted-runner measurement.

</details>

## Original behaviour kept on purpose

| Behaviour | Effect |
|---|---|
| Cross-spectrum with NaN | Direct calls fail; the default pipeline removes NaN first. |
| Leading NaN | First valid sample also zeroed; all-NaN input raises `IndexError`. |
| Infinity replacement | Only +inf replaced at the final step; earlier filters can fail. |
| Channel selection | Nonempty selections raise `KeyError`. |
| Binary-input warning | Reversed check; warnings-as-errors can stop execution. |
| All channels removed | Feature extraction raises `IndexError`. |
| Mixed sample rates | MNE upsamples to one loaded rate; original channel rates unchecked. |
| Downsampling | Some actual rates differ from the declared 64 Hz. |
| Low input rate | Retained-channel preprocessing needs > 80 Hz; feature bands need > 60 Hz; exceptions below. |
| Correlation | Pearson on squared envelopes; README says Spearman. |
| Unused settings | `REMOVE_ART` and FD’s `method` have no effect. |

<details>
<summary>Code locations, inherited effects and probe results</summary>

This maintained version retains these issues so it can be compared with the original before
scientific changes. This is not evidence that the behaviours are desirable.
Code inspection checked every row. Marked synthetic probes reran with the
original on pandas 2.3.3 and this maintained version on pandas 3.0.2. Requiring more than 80 Hz
does not establish that every rate is supported; the resampling issues remain.

| Behaviour | Where | Effect and evidence | Decision |
|---|---|---|---|
| `x[np.isnan(x)] = []` does not remove NaN | `connectivity_features.gen_cross_spectrum:57` | Probe: does nothing without NaN; raises `ValueError` with NaN. Default `connectivity_coh` deletes NaN before this call (lines 374–375). Direct calls with NaN fail. | Fix or keep? |
| The first real sample after leading NaN is also set to 0 | `utils.replace_start_ends_NaNs_with_zeros:623`; used by `filter_butterworth_withnans` | Probe: [NaN, NaN, 5, 6, 7, NaN] becomes [0, 0, 0, 6, 7, 0], because `x[0:istart+1] = 0`. This can affect epochs starting inside artefacts; the resulting feature change has not been measured. An all-NaN input raises `IndexError`. | Fix or keep? |
| Only +inf is converted to NaN at the final replacement step | `preprocessing_EEG.remove_artefacts:426` | The line does not replace −inf. Earlier filter calls fail on infinities unless an earlier flat-zero check has already replaced them. The tests reach this otherwise blocked step with a stand-in. See the qualified infinity limitation in README. | Fix or keep? |
| Nonempty `channel_names=[...]` selection fails with `KeyError` | `generate_all_features:163–173`, error at 172 | Probe: matching, missing and all channel names fail. Select DataFrame columns before calling the function instead. | Fix or keep? |
| `len_cont_zeros` warns “Must be a binary signal” when input is binary | `utils.len_cont_zeros:697` | Probe confirms the reversed check. It emits `DeprecationWarning`, normally hidden by Python; tests suppress this message. It does not change numerical outputs, but warning-as-error settings can stop the call. | Fix or keep? |
| All channels removed: feature extraction raises `IndexError: tuple index out of range` | `generate_all_features:175–184` drops all-NaN channels; `add_feat_data_to_array:496` fails | Probes: all-NaN channels, and independent electrode noise that removes all 8 bipolar channels. The result is an error rather than NaN feature values. | Fix or keep? |
| One loaded sample rate is used for the file | `load_edf_EEG_file:59–60`; `main_preprocessing:532` takes `ch_fs[0]` | `ch_fs` repeats MNE’s `info["sfreq"]`. MNE [documents upsampling mixed-rate signals to the highest loaded rate](https://mne.tools/stable/generated/mne.io.read_raw_edf.html). This code does not check each EEG channel’s original rate. | Fix or keep? |
| The slicing branch can return the wrong rate while declaring 64 Hz | `preprocessing_EEG.signal_downsample:483–519` | If Fs/64 has at most one decimal place, it keeps every round(Fs/64)-th sample. Otherwise it uses `resample_poly`, with ratio `round(N * 64 / Fs) / N`. See the probe table below. | Fix resampling or reject affected rates? |
| Default retained-channel preprocessing requires Fs > 80 Hz | `art_per_channel:159` uses a fixed 40 Hz upper cutoff | Probes at 40, 60, 64 and 80 Hz fail with an invalid Butterworth critical frequency; 81 Hz completes. If every channel is removed first, that filter is skipped: a 64 Hz probe returned all-NaN data. Feature bands reaching 30 Hz separately need Fs > 60 Hz. Intended post-downsampling rate is 64 Hz. | Define and test supported rates? |

In the full pipeline, downsampling follows the 30 Hz low-pass.
For ten-second synthetic inputs, both the original and this maintained version gave:

| Input rate | Output samples | Actual output rate | Declared rate |
|---|---|---|---|
| 96 Hz | 480 | 48 Hz | 64 Hz |
| 160 Hz | 800 | 80 Hz | 64 Hz |
| 480 Hz | 600 | 60 Hz | 64 Hz |
| 200 Hz | 640 | 64 Hz | 64 Hz |
| 256 Hz | 640 | 64 Hz | 64 Hz |

Direct downsampling at 32 Hz raises `ValueError` because the slice step is
zero. Integer ratios at 128, 256, 512, 1024 and 2048 Hz select every k-th
sample correctly. Rates such as 200, 250, 500 and 1000 Hz use
`resample_poly` toward 64 Hz; for arbitrary input lengths its target sample
count is rounded, so the ratio is not always exactly 64/Fs.

</details>

<details>
<summary>Documentation mismatch and unused settings</summary>

| Behaviour | Where | Effect | Decision |
|---|---|---|---|
| Code uses Pearson; README says “correlation (Spearman)” | `connectivity_features.connectivity_corr:523–526`; README “Quantitative features” | `stats.pearsonr` is applied to squared Hilbert envelopes, `abs(hilbert(x)) ** 2`. The function docstring also says Pearson. | Preserve Pearson and correct description, or change statistic? |
| `REMOVE_ART` (“0 to turn off”) is never read | `NEURAL_parameters.py:42`; `main_preprocessing` | Setting it to 0 has no effect; preprocessing always calls `remove_artefacts`. | Implement or remove/document setting? |
| `params['FD']['method']` (“either 'higuchi' or 'katz'”) is never read | `fd_features.main_fd:135–136` | Through `generate_all_features`, “FD” always maps to Higuchi. | Implement or remove/document setting? |

[MATLAB also uses Pearson](https://github.com/otoolej/qEEG_feature_set/blob/206a89b8943f029a32947b1715f75b62ab8d5c8a/connectivity_features/connectivity_features.m#L338-L341).
Keeping Pearson would preserve the statistic and correct its description;
Spearman would deliberately change it.

</details>

## Artefact detection

The **low-correlation check** removes bipolar channels containing electrodes whose absolute mean Pearson correlation with other loaded electrodes is below 0.15, using the whole loaded recording.
**Reported, not re-verified:** several one-hour, 200 Hz public neonatal recordings lost most or all bipolar channels; the reason is uninvestigated [citation to be added].
**Settings** are read inside preprocessing functions, with no per-run parameter argument.
Direct feature wrappers accept parameters, but `generate_all_features` does not forward them.

<details>
<summary>Artefact stages and exact default parameters</summary>

`main_preprocessing` loads the EDF, builds the bipolar montage and calls
`remove_artefacts`. Optional preprocessing arguments preserving the defaults
are a possible follow-up, subject to review.

`preprocessing_EEG.remove_artefacts:248–438` runs:

1. **Referential low-correlation check** (299–344), detailed below.
2. **Electrode coupling** (350–396), when more than 4 bipolar channels remain
   and each hemisphere has at least 2. A channel with mean power in 0.5–20 Hz
   below one-quarter of its hemisphere’s median is removed. Only the first
   qualifying channel is removed.
3. **Per-channel checks**, `art_per_channel:117–245`: exact zeros, high
   amplitude, constant values and sudden jumps.
4. **Shared removal** (430): a sample marked in any remaining channel becomes
   NaN in all of them.

Defaults in `NEURAL_parameters.py:42–62` are described there as “some default
values used for preterm infants (<32 weeks of gestation)”.

| Parameter | Default | Meaning as implemented | Read in |
|---|---|---|---|
| `REMOVE_ART` | 1 | Described as “0 to turn off”; never read | — |
| `ART_ELEC_CHECK` | 1 s | Removes exact-zero runs at least this long, plus 1 sample on each side | `art_per_channel:143` |
| `ART_HIGH_VOLT` | 1500 µV | Threshold on the absolute Hilbert envelope of the 0.1–40 Hz filtered channel | `art_per_channel:169` |
| `ART_TIME_COLLAR` | 10 s | Removes this interval on each side of a high-amplitude sample | `art_per_channel:164` |
| `ART_DIFF_MIN_TIME` | 0.1 s | Removes runs of zero first differences longer than 0.1 × Fs samples; these mark constant values | `art_per_channel:199` |
| `ART_DIFF_VOLT` | 200 µV | Removes jumps between consecutive samples exceeding this threshold | `art_per_channel:223` |
| `ART_DIFF_TIME_COLLAR` | 0.5 s | Removes this interval on each side of a constant stretch or jump | `art_per_channel:190,219` |
| `ART_REF_LOW_CORR` | 0.15 | Threshold for the absolute mean referential correlation | `remove_artefacts:324` |
| `FILTER_REPLACE_ARTEFACTS` | `'nans'` | Feature band filters fill internal NaN by piecewise-cubic (PCHIP) interpolation, then restore NaN after filtering. Artefact-check filters instead use default `'linear_interp'`. Edge NaN are zeroed first, including the extra real sample described in the NaN-edge row above. | `main_amplitude`, `main_rEEG`, `main_fd`, `connectivity_corr` |

Fixed in code: the 0.5–20 Hz referential/coupling filter (orders 5/5),
the 0.1–40 Hz high-amplitude filter (low/high orders 5/2), and the coupling
threshold of one-quarter of median power.

</details>

<details>
<summary>Referential check: step-by-step code path</summary>

In `remove_artefacts:299–344`:

1. Use every referential channel loaded from the EDF, up to nine selected
   electrodes: F3, F4, C3, C4, O1, O2, T3, T4 and Cz. Use the loaded
   sample rate and the whole recording.
2. Apply `filter_butterworth_withnans(x, Fs, 20, 0.5, 5)`: order-5
   low-pass, then order-5 high-pass. Fill NaN by linear interpolation first.
3. Compute the Pearson matrix (`np.corrcoef`, line 318); ignore its diagonal.
4. Average each electrode’s correlations with all others (`np.nanmean`,
   line 320).
5. Flag electrodes whose mean correlation has absolute value < 0.15 (324).
6. Set to NaN every bipolar channel whose name contains a flagged electrode
   (330–344). For example, flagging C4 removes F4_C4, C4_T4, C4_Cz and C4_O2.

The comment asks whether there is a problem with one channel, for example Cz,
but the implementation does not limit how many electrodes it flags.

</details>

<details>
<summary>Every relevant NEURAL_parameters() call site</summary>

| Function | Call line(s) | Artefact settings read |
|---|---|---|
| `preprocessing_EEG.art_per_channel` | 130 | `ART_ELEC_CHECK`, `ART_TIME_COLLAR`, `ART_HIGH_VOLT`, `ART_DIFF_TIME_COLLAR`, `ART_DIFF_MIN_TIME`, `ART_DIFF_VOLT` |
| `preprocessing_EEG.remove_artefacts` | 294 | `ART_REF_LOW_CORR` |
| `amplitude_features.main_amplitude` | 113,119 | `FILTER_REPLACE_ARTEFACTS` |
| `rEEG.main_rEEG` | 205,211 | `FILTER_REPLACE_ARTEFACTS` |
| `fd_features.main_fd` | 139,145 | `FILTER_REPLACE_ARTEFACTS` |
| `connectivity_features.main_connectivity` | 719,725 | `FILTER_REPLACE_ARTEFACTS`, passed to `connectivity_corr` |

Neither `main_preprocessing`, `remove_artefacts` nor `art_per_channel`
accepts an artefact-parameter argument. The feature wrappers accept `params`,
but `generate_all_features:250–260,316` does not supply one.

Other calls are `generate_all_features:38,146`,
`spectral_features.main_spectral:466,472`, and `LPF_zero_phase:452`
(for `LP_fc`). Defaults for optional feature parameters are therefore read
inside the wrappers unless those wrappers are called directly with `params`.

</details>

## Not covered yet / planned work

**Not covered:**

- IBI/burst features.
- Real recordings.
- macOS.
- Non-default settings, except the three tested window types.

**Planned / proposed:**

- Planned: the filter sensitivity experiment.
- Proposed: a lock file in CI and per-run artefact settings.
- Proposed: a comparison on public real recordings.
- Proposed: feature-code readability improvements after review.
