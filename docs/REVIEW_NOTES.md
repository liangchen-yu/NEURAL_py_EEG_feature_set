# Review notes

These notes are for reviewing this maintained version of NEURAL_py against the original Python code by Brian M. Murphy and John M. O'Toole (commit 78c9425): what changed, how it was checked, the numerical differences found, and the decisions needed.

## In short

- **Same results on one machine:** for everything the 28 regression and edge-case tests check with modern libraries, the outputs still equal the original's exactly (difference 0); the one window-type check against the 2020 environment differs by at most 1.6e-15. The suite has 54 tests: these 28, 22 downsampling tests and 4 `REMOVE_ART` tests.
- **Small differences between environments:** the original itself reportedly varies by up to about 3e-7 relative (about 7 significant figures) between library versions and between computers; artefact decisions and NaN positions did not change (reported). Two Windows CI jobs of one run, with identical pinned libraries and Python, drifted by 0 and 1.6e-7 (reported, 4 Nov), pointing to the runner machine rather than library versions (not yet confirmed; see [Run it on your PC](#run-it-on-your-pc)).
- **Likely cause:** the synthetic experiment supports rounding sensitivity in the order-5 Butterworth band filters in `(b, a)` form. It does not establish the cause of the cross-machine differences.
- **Original behaviour kept on purpose**, so results can be compared before any scientific change.
- **Python porting gaps:** downsampling now matches MATLAB. Results change at odd multiples of 32 Hz above 64 Hz (e.g. 96, 160 and 480 Hz gave wrong output rates, labelled 64 Hz) and can change for recordings that are not a whole number of seconds at rates that are not multiples of 64 Hz (1001 samples at 200 Hz gave 63.936 Hz). Whole-second recordings at other whole-number rates, including the tested 256 Hz, are unchanged. `REMOVE_ART` is now honoured; its default of 1 keeps results unchanged. FD's `method` setting is unused; retained-channel preprocessing requires more than 80 Hz.
- **Referential-check mismatch:** in a reported run of all 169 recordings of the public HIE dataset with the original code at default settings, the low-correlation check removed every bipolar channel in 50 of 96 recordings at 200 Hz and none of 73 at 256 Hz. Changing only the reference in software switched these removals on and off (see [Artefact detection](#artefact-detection) and decision 6). MATLAB lets users skip this check alone; in Python that currently fails whenever the electrode-coupling check runs.
- **Correlation:** the NEURAL paper and both implementations specify Pearson; the README table's "Spearman" was a documentation error, now corrected.

## Decisions needed

1. **Tolerance:** what difference is acceptable per feature group, for summary and per-epoch values? (Tests use 1e-9 relative; the CI drift guard 1e-5.)
2. **Reference:** keep this Python version (78c9425) as the reference, or the MATLAB NEURAL? A MATLAB run as ground truth may be possible: could it use the two synthetic test files?
3. **Filter form:** keep `(b, a)`, which matches both originals, or review SOS as a separate numerical change? The synthetic experiment recorded changes up to 5.7e-7 relative per epoch and 3.4e-9 in summaries. Keep the original references unchanged.
4. **Downsampling:** the integer check and the resampling ratio now match MATLAB; confirm.
5. **Supported data:** require more than 80 Hz? Which sample rates, recording lengths and reference montages should be supported and tested?
6. **Artefact switch and reference montage:** confirm the original author's intended default and testing strategy. Keeping `REMOVE_ART = 1` applies the artefact checks; `0` skips them and leaves artefacts unremoved. In the synthetic C3/C4-average-reference probe, all eight bipolar channels became all-NaN with removal on and had data with it off. Should feature generation and artefact detection be tested separately? For recordings with a C3/C4-average reference, which handling is intended: (a) `REMOVE_ART = 0`, which skips all six checks; (b) skip only the low-correlation check, as MATLAB allows by calling `remove_artefacts` without referential data (in Python this currently fails whenever the electrode-coupling check runs; see [Skipping only the referential check](#skipping-only-the-referential-check)); or (c) re-reference before the check, for example to one recorded electrode or the average of all electrodes, which keeps the faulty-electrode check but can remove channels of its own? Which settings were used for the published HIE analyses?
7. **Other inherited behaviour** (table below): fix or keep each item?
8. **Versions:** support Python older than 3.14? Which libraries should be pinned exactly, and which given only a minimum?
9. **IBI features:** keep them unsupported (they need a separate burst detector), or add and test the detector?
10. **NaN in summaries:** should across-channel medians (`feats_median_ch`, `feats_median_all`) ignore NaN like `feat_st`?

## What changed

Across **26 commits**, only **four modules** in `src/` changed, mostly for pandas 3, SciPy and pyedflib compatibility.
**Feature formulas**, filter designs and default parameters are unchanged.
The compatibility changes adapt array writes, indexing, window-function imports and EDF export; exact agreement on tested inputs does not guarantee every possible call.
Later commits changed `preprocessing_EEG.py` again, to match MATLAB: the downsampling integer check and resampling ratio in `signal_downsample`, and the `REMOVE_ART` switch, now read by `main_preprocessing` (default unchanged).
Package metadata moved from `setup.cfg` to `pyproject.toml`; `uv.lock` fixes every package version, and `.github/workflows/uv-drift.yml` runs the tests with it.

<details>
<summary>Source changes, feature map and review context</summary>

The comparison is against original NEURAL_py (BSD-3-Clause) at
[78c9425](https://github.com/BrianMur92/NEURAL_py_EEG_feature_set/commit/78c94258e4a3e6504e469f418443c78926e1a6be).
Source line numbers refer to f69a3c7 (later commits change only documentation): `src/` is unchanged
since 15e9aaa, and modules other than `preprocessing_EEG.py` since dd7235e.
MATLAB line numbers refer to qEEG_feature_set
[206a89b](https://github.com/otoolej/qEEG_feature_set/tree/206a89b8943f029a32947b1715f75b62ab8d5c8a).
**Reported** marks figures from GitHub Actions logs or earlier one-off checks
not independently reproduced in this review.

The source diff (`git diff 78c9425 f69a3c7 -- src`) has 140 lines added and 37
removed in the four modules, including comments and docstrings, plus the
one-line Spearman correction in `src/NEURAL_py_EEG/README.md`. After the
decisions, suggested reading is the numerical findings, then the four-file
source diff.

Only Python 3.14 has been tested; `pyproject.toml` requires Python ≥ 3.14 and
declares minimum library versions. `tests.yml` pins the other libraries while
testing two pandas versions. `uv.lock` pins every package (numpy 2.5.4, SciPy
1.18.1, pandas 3.1.0, MNE 1.13.2, matplotlib 3.11.2, pyedflib 0.1.42, pytest
9.2.0), but not the Python patch version.

IBI requires a separate burst detector. `IBI_features.main_IBI` looks at a
placeholder location (line 85) and returns NaN if the detector is missing
(line 115); on Windows that location cannot exist (see below).

`git diff 78c9425 f69a3c7` shows no changes to the other nine modules:
`NEURAL_parameters.py`, `amplitude_features.py`, `spectral_features.py`,
`rEEG.py`, `fd_features.py`, `IBI_features.py`, `mfiltfilt.py`, `demos.py`
and `__init__.py`.

| Module | Change | Reason |
|---|---|---|
| `preprocessing_EEG.py` | `remove_artefacts` filters channel copies, writes filled NaN values back as the original did through pandas views, and uses `.loc` for +inf replacement; `overlap_epochs` retains pandas < 3 indexing. Later: `signal_downsample` uses MATLAB's integer check and the ratio Fs_new/Fs; `main_preprocessing` reads `REMOVE_ART` and has a new `remove_art` argument | pandas 3; match MATLAB `resample_savemat.m` |
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
In a synthetic probe, one channel with every epoch at least 50 % NaN (but not
all-NaN) left `feat_st` with values, while `feats_median_all` and every
`feats_median_ch` row were NaN (decision 10). With default preprocessing,
shared artefact removal (`preprocessing_EEG.py:432`) puts NaN at the same
samples in every retained channel.

</details>

<details>
<summary>All 26 commits on master since 78c9425, oldest first; no merges</summary>

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
| 81910e2 | added review notes and updated the README for the maintained version |
| c724e3e | Add numerical sensitivity experiment for the filter rounding hypothesis |
| 6e6a345 | Correct sensitivity wording, add artefact citation and new findings to review notes |
| f6fe1df | Complete review notes summary and decisions for the new findings |
| 7cb25f2 | Fix downsampling integer check to match MATLAB; correct connectivity_corr to Pearson |
| 399a4ad | Read REMOVE_ART in main_preprocessing, as in MATLAB |
| f2e1f02 | Use the exact rate ratio when resampling, as in MATLAB |
| 15e9aaa | Fix fractional target rates in signal_downsample and add a NaN-gap test |
| 22f2d08 | Move package metadata into pyproject.toml and add uv.lock |
| f69a3c7 | Add a CI check of cross-machine drift with the uv.lock environment |

</details>

## How it was checked

- **Inputs:** two synthetic EDFs, “clean” and “artefacts”, each 300 s, 256 Hz and 9 electrodes; all 26 non-IBI features under tested settings; no real recordings opened.
- **References:** the original source was SHA-256 verified; outputs include feature values and sampled EEG checks.
- **Tests:** relative tolerance 1e-9, absolute 1e-12; the 28 regression and edge-case tests still show modern-reference differences of exactly 0, with a separate 2020 window exception below. The suite has 54 tests: these 28, 22 downsampling tests (21 sample-rate tests and 1 NaN-gap test) and 4 `REMOVE_ART` tests.
- **CI:** Windows and Ubuntu compare this maintained version and the original on the same runner, then guard drift from committed references, also requiring matching structures, NaN positions and discrete outputs. A second workflow runs the tests in the `uv.lock` environment, for information only.

<details>
<summary>Run results, inputs, reference provenance, tolerances and CI</summary>

**Run for this update:** `uv run pytest` in the `uv.lock` environment
(Windows 11, Python 3.14.7, numpy 2.5.4, SciPy 1.18.1, pandas 3.1.0, MNE
1.13.2, matplotlib 3.11.2, pyedflib 0.1.42, pytest 9.2.0):

```text
54 passed in 50.72s
```

**Earlier runs (historical counts):** with numpy 2.5.3 and pandas 3.0.2
(SciPy, MNE, matplotlib and pyedflib as above), `28 passed in 45.83s` before the sample-rate
tests existed, and `39 passed in 42.07s` after the downsampling fix (the 28
plus 11 sample-rate tests).

In this run, as in the earlier ones, every checked modern-reference group had
a largest difference of exactly 0. The separate 2020 window comparison had a
largest relative difference of 1.61e-15 and absolute difference of 8.88e-16.

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

**uv workflow.** `.github/workflows/uv-drift.yml` runs on each push and on
demand, on Windows and Ubuntu. It installs uv 0.13.7, builds the environment
with `uv sync --locked`, lists the installed versions and runs `uv run pytest`
against the committed references. The test step has `continue-on-error`, so a
tolerance failure does not fail the workflow; the printed table shows the
drift of this maintained version from the reference PC's values.

</details>

## Run it on your PC

These steps, from the repository's top folder, give results that can be compared across three machines. They use only the synthetic test inputs.

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (CI uses uv 0.13.7). pyedflib 0.1.42 is compiled during installation: on Windows this needs the Microsoft C++ Build Tools, on Linux or macOS a C compiler.
2. Build the locked environment and run the tests:

   ```text
   uv sync --locked
   uv run pytest
   ```

   `uv sync --locked` creates `.venv` with the exact versions in `uv.lock` and stops if the lock file would change. `uv run pytest` runs the 54 tests and ends with a table of the largest differences from the committed references. On another machine some regression tests may fail the 1e-9 tolerance; that is the drift being measured, so please keep the output.
3. Make reference values with the original NEURAL, as described in `tests/make_reference.py` (Windows commands; on macOS or Linux use `venv-original/bin/python` and forward slashes):

   ```text
   python -m venv venv-original
   venv-original\Scripts\python -m pip install numpy==2.5.3 scipy==1.18.1 pandas==2.3.3 mne==1.13.2 matplotlib==3.11.2 pyedflib==0.1.42
   venv-original\Scripts\python -m pip install "git+https://github.com/BrianMur92/NEURAL_py_EEG_feature_set.git@78c94258e4a3e6504e469f418443c78926e1a6be"
   venv-original\Scripts\python -B tests\make_reference.py --output my-references
   ```

   `python` must be Python 3.14 (the committed files used 3.14.7); otherwise `uv venv venv-original --python 3.14 --seed` replaces the first line. The script refuses to run unless the installed NEURAL is the original 78c9425 code (SHA-256). `--output` leaves the committed files in `tests/data/` unchanged.
4. Send back the four files in `my-references`: `reference_clean.json`, `reference_artefacts.json`, `reference_edge_cases.json` and `reference_input_types.json`, with the `uv run pytest` output. Each file records its OS, Python and library versions in `made_with`. `uv run python tests/check_reference_drift.py tests/data my-references` prints their drift from the committed files.

## Numerical differences

**Relative difference** means absolute difference divided by the absolute reference value, when nonzero.

| Comparison | What differs | Largest relative difference |
|---|---|---|
| This maintained version vs original, one machine and modern pinned libraries; original uses pandas 2.3.3 | Compatibility changes; this maintained version also tested with pandas 3 | Exactly 0 for checked modern-reference outputs |
| Original: 2020 environment vs modern environment | Libraries and Python version | Up to 3e-7 (reported) |
| Original: GitHub Windows runner vs reference PC | Machine, Windows version and Python patch version | 1.6e-7 (reported) |
| Original: two Windows jobs of one CI run vs reference PC (4 Nov) | Between the two jobs, the runner machine (identical pinned libraries and Python 3.14.10) | 0 and 1.594e-7 (reported) |
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
with pandas 2.3.3, 3.0.2, 3.0.6 and 3.1.0. Those are historical runs. The
probes for this correction used the installed pandas 3.1.0 environment;
pytest reports installed library versions (`tests/conftest.py:61–66`),
rather than selecting one of the pandas versions in that table.

For the runner comparisons, all 13,867 floats in the four modern references
were reported checked, with matching NaN positions, counts and structure.
The Windows runner was reported as Windows Server 2025, Python 3.14.9,
versus Windows 11 and Python 3.14.7 on the reference PC. Pinned library
versions matched, so that comparison alone is not machine-only.

**4 Nov CI evidence (reported).** Two Windows jobs of the same `tests.yml`
run built identical reference environments: the same pinned libraries
(`tests.yml` installs the original with pandas 2.3.3 in both jobs) and
Python 3.14.10. Their drift guards gave largest relative drift 0 and
1.594e-7; in an earlier run, the other job drifted. The job with drift 0 also
differed from the reference PC in Python patch version (3.14.10 vs 3.14.7).
This points to the runner machine (for example CPU-dependent numerical paths)
rather than library versions. Not yet confirmed: the workflows log no CPU
information.

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
Rounding sensitivity is a **likely cause** of the sensitivity seen in the synthetic experiment. The cause of the actual cross-machine differences remains unverified.

**Results:** the [single-machine synthetic experiment](../experiments/sensitivity/results.md)
recorded input changes near 1e-15 through preprocessing, then about 7e-10
relative RMS difference in the 0.5–4 Hz and FD band outputs. Per-epoch feature
differences reached 3.5e-7 relative; summaries reached 2.5e-9. SOS reduced the
0.5–4 Hz band difference to about 1.8e-14, roughly 40,000 times smaller.
The SOS feature differences reached 8e-12 per epoch and 1.3e-13 in summaries.
These measure the combined feature computation; downstream stages were not
isolated. No artefact decisions changed in the 40 perturbed part-A runs.
Switching unperturbed calculations to SOS changed features by up to 5.7e-7
relative per epoch and 3.4e-9 in summaries. This would be a separate numerical
change, compared against unchanged original references. The byte-identity
checks were recorded during the run; their JSON files are not in the repository.

<details>
<summary>Filter paths, MATLAB citations, experiment design and coefficient analysis</summary>

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

**Single-machine experiment design:**

1. Perturb synthetic input EEG by about 1e-15 relative, a few units in the last
   place (ULP: the spacing between nearby representable numbers).
2. Measure differences after artefact removal, the 30 Hz low-pass,
   downsampling, the band filter, envelope or rEEG calculation, and features.
   Include per-epoch values and medians.
3. Repeat using `scipy.signal.butter(..., output='sos')`. Preserve
   `mat_filtfilt`’s padding length, odd reflection and steady-state start.
4. If SOS reduces the differences by orders of magnitude, that supports the
   hypothesis. Otherwise, examine the other stages.

The run and its checks are recorded in
[results.md](../experiments/sensitivity/results.md). This is synthetic evidence
for a likely cause, not a cross-machine or MATLAB comparison.

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
DataFrames before later checks (`remove_artefacts:309–318,363–371`).
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
rather than 2.635e-7 for the single polynomial. These coefficient observations
do not quantify feature errors; the experiment above measures feature differences.

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
| All channels removed | Feature extraction raises `IndexError`; the reported open-HIE removals are explained below. |
| Skipping the referential check | Passing no referential data skips it, as in MATLAB, but the coupling check, when it runs, then raises `IndexError` (details below). |
| Mixed sample rates | MNE upsamples to one loaded rate; original channel rates unchecked. |
| Low input rate | Retained-channel preprocessing needs > 80 Hz; feature bands need > 60 Hz; exceptions below. |
| Correlation | Paper and code specify Pearson on squared envelopes; the README table's Spearman was a documentation error and is now corrected to Pearson. |
| Settings | FD's `method` is unused. |
| NaN gaps in resampling | At non-integer rate ratios, NaN gaps grow slightly during resampling (`resample_poly`'s filter), as in the original: a 0.5 s gap at 200 Hz becomes about 0.83 s at 64 Hz. |
| Per-epoch output | `feats_per_epochs` holds only the last per-channel feature of one `generate_all_features` call. |
| Two channels | Connectivity raises `IndexError` when exactly two bipolar channels with data remain. |
| BSI with one matched left channel | Synthetic 64 Hz, 64 s probes with three or four channels, exactly one left channel and a matched right counterpart raised `IndexError` inside BSI; the caller reports `ValueError: Feature function not found: connectivity_BSI`. |
| Epoch table | Default hops are equal at whole-number rates, but short inputs pre-allocate 0 rows and produce 1 epoch; some 0 % overlap lengths raise `ValueError` (conditions below). |
| IBI on Windows | The burst-detector placeholder path contains `>`, which Windows does not allow in file names. |

**Fixed: downsampling.** The original's integer check in `signal_downsample`
used `x == round(x, 1)`; MATLAB `resample_savemat.m:140` uses `x == round(x)`.
Ratios ending in .5 therefore took the slicing branch, and its rounded step
gave wrong output rates labelled 64 Hz. For example, a 5 Hz sine at 96 Hz input
appeared at 6.67 Hz. This maintained version now uses `round(x)`, as MATLAB
does. Only odd multiples of 32 Hz above 64 Hz are affected;
`tests/test_downsample_rates.py` checks 11 rates.

**Fixed: artefact switch.** MATLAB `resample_savemat.m:120–122` calls
`remove_artefacts` only inside `if(REMOVE_ART) ... end`. The NEURAL paper,
section 3, documents `REMOVE_ART=0` to turn removal off. The original Python
always called `remove_artefacts`, so the setting had no effect.
`main_preprocessing` now reads `REMOVE_ART`; its new `remove_art` argument
overrides it for one run. With removal off, no artefact check runs and the
artefact report is `None`. The default of 1 keeps results identical.
`tests/test_remove_art_switch.py` checks both settings.

<details>
<summary>Code locations, inherited effects and probe results</summary>

This maintained version retains these issues so it can be compared with the original before
scientific changes. This is not evidence that the behaviours are desirable.
Code inspection checked every row. Marked synthetic probes reran with the
original on pandas 2.3.3 and this maintained version on pandas 3.0.2. The
per-epoch output, two-channel, epoch-table and IBI-on-Windows rows were
probed with this maintained version only (`uv.lock` environment, pandas
3.1.0); their code is unchanged from 78c9425. This correction reran the BSI
layout and epoch-count probes in that maintained environment. Requiring more than 80 Hz
does not establish that every rate is supported. The length-based resampling ratio described below is now fixed.

| Behaviour | Where | Effect and evidence | Decision |
|---|---|---|---|
| `x[np.isnan(x)] = []` does not remove NaN | `connectivity_features.gen_cross_spectrum:57` | Probe: does nothing without NaN; raises `ValueError` with NaN. Default `connectivity_coh` deletes NaN before this call (lines 374–375). Direct calls with NaN fail. | Fix or keep? |
| The first real sample after leading NaN is also set to 0 | `utils.replace_start_ends_NaNs_with_zeros:623`; used by `filter_butterworth_withnans` | Probe: [NaN, NaN, 5, 6, 7, NaN] becomes [0, 0, 0, 6, 7, 0], because `x[0:istart+1] = 0`. This can affect epochs starting inside artefacts; the resulting feature change has not been measured. An all-NaN input raises `IndexError`. | Fix or keep? |
| Only +inf is converted to NaN at the final replacement step | `preprocessing_EEG.remove_artefacts:428` | The line does not replace −inf. Earlier filter calls fail on infinities unless an earlier flat-zero check has already replaced them. The tests reach this otherwise blocked step with a stand-in. See the qualified infinity limitation in README. | Fix or keep? |
| Nonempty `channel_names=[...]` selection fails with `KeyError` | `generate_all_features:163–173`, error at 172 | Probe: matching, missing and all channel names fail. Select DataFrame columns before calling the function instead. | Fix or keep? |
| `len_cont_zeros` warns “Must be a binary signal” when input is binary | `utils.len_cont_zeros:697` | Probe confirms the reversed check. It emits `DeprecationWarning`, normally hidden by Python; tests suppress this message. It does not change numerical outputs, but warning-as-error settings can stop the call. | Fix or keep? |
| All channels removed: feature extraction raises `IndexError: tuple index out of range` | `generate_all_features:175–184` drops all-NaN channels; `add_feat_data_to_array:496` fails | Probes: all-NaN channels, and independent electrode noise that removes all 8 bipolar channels. The reported open-HIE run found the low-correlation check removed all bipolar channels in 50 of 96 recordings at 200 Hz and 0 of 73 at 256 Hz. See the reference-montage explanation under Artefact detection. | Review the referential check and define the empty-output behaviour. |
| Without referential data, the coupling check fails | `remove_artefacts:307` skips the referential check when `data_ref` is empty, but line 362 sizes `x_filt` from `data_ref.shape`; when the coupling check runs (more than four remaining bipolar channels and at least two in each hemisphere, lines 356–359), the loop fails at line 369 | Probes with this maintained version only (pandas 3.0.5 and 3.1.0; synthetic, 60 s, 256 Hz): with eight bipolar channels, `IndexError: index 0 is out of bounds for axis 0 with size 0` at line 369, while the same input with referential data completes; with five channels, a 3 + 2 hemisphere split failed and a 4 + 1 split completed. MATLAB `remove_artefacts.m` skips the check at line 65 and sizes its array as `zeros(N_channels,N)` at line 111 (206a89b). The default pipeline always passes referential data, so it is unaffected. | Fix if option (b) of decision 6 is chosen? |
| One loaded sample rate is used for the file | `load_edf_EEG_file:61–62`; `main_preprocessing:552` takes `ch_fs[0]` | `ch_fs` repeats MNE’s `info["sfreq"]`. MNE [documents upsampling mixed-rate signals to the highest loaded rate](https://mne.tools/stable/generated/mne.io.read_raw_edf.html). This code does not check each EEG channel’s original rate. | Fix or keep? |
| Default retained-channel preprocessing requires Fs > 80 Hz | `art_per_channel:161` uses a fixed 40 Hz upper cutoff | Probes at 40, 60, 64 and 80 Hz fail with an invalid Butterworth critical frequency; 81 Hz completes. If every channel is removed first, that filter is skipped: a 64 Hz probe returned all-NaN data. Feature bands reaching 30 Hz separately need Fs > 60 Hz. Intended post-downsampling rate is 64 Hz. | Define and test supported rates? |
| `feats_per_epochs` holds only the last per-channel feature of one call | `generate_all_features:235–237` re-creates it for each amplitude, spectral, rEEG or FD feature (filled at 267, returned at 358); connectivity and IBI never set it | Probe: for `['amplitude_SD', 'rEEG_mean', 'connectivity_BSI']` it equals the `rEEG_mean`-only result (8 × 9 × 4); with only connectivity features it is an empty array. Summaries cover every feature. `tests/neural_outputs.compute_features` stores it for the last per-channel feature only. | Fix or keep? |
| Connectivity raises `IndexError: tuple index out of range` with exactly two bipolar channels with data | `connectivity_features.main_connectivity:751–757`, after `generate_all_features:175–184` drops all-NaN channels | For two channels, line 755 sets `ipairs = np.array([1, 2])`, which is one-dimensional, so `ipairs.shape[1]` fails at line 757. Probe: BSI, corr and coh_mean all fail; one channel returns NaN instead (lines 737–739). [MATLAB](https://github.com/otoolej/qEEG_feature_set/blob/206a89b8943f029a32947b1715f75b62ab8d5c8a/connectivity_features/connectivity_features.m#L80-L83) pairs channels by label for two or more channels. | Fix or keep? |
| BSI failed in synthetic probes with three or four channels, exactly one left channel and a matched right counterpart | `connectivity_features.connectivity_BSI:257–264,283`; caller `main_connectivity:757–792` | Default settings, 64 s at 64 Hz: `['F4_C4', 'F3_C3', 'C4_T4']` raises `IndexError: index 4 is out of bounds for axis 0 with size 1` at line 283. The single-left branch keeps two-dimensional spectra, then indexes their channel axis with frequency-bin indices. The bare `except` at 791–792 relabels it as `ValueError: Feature function not found: connectivity_BSI`, also through `generate_all_features`. One left plus three right channels with a match also failed. Two left plus one right, two matched pairs and three matched pairs returned finite values. Three left-only channels, three right-only channels and one left plus two unmatched right channels returned NaN. These results do not imply that every unbalanced montage fails. | Fix or keep? |
| `feats_median_ch` pre-allocation can differ from the real epoch count | `generate_all_features:198–207` pre-allocates `get_max_num_epochs` rows; `get_max_num_epochs:431–432` uses the Hamming-window hop `ceil((L_epoch − 1) · (1 − overlap))`, `overlap_epochs:78–84` the rectangular hop `ceil(L_epoch · (1 − overlap))` (`utils.gen_epoch_window:214–221`) | With default 64 s epochs and 50 % overlap, the hops are equal at whole-number rates (probe: 1–2048 Hz). Counts agree for N > 32 × Fs; for 0 < N ≤ 32 × Fs, pre-allocation gives 0 while `overlap_epochs` clamps its count to 1. At 64 Hz, probes at 1,024 and 2,048 samples gave 0 vs 1; `amplitude_SD` extraction returned one table row because the first assignment expands the empty table. At 2,049 samples both counts were 1; at 300 s both were 9. With 0 % overlap at 64 Hz, pre-allocation is `ceil((N − 1) / 4095)` and the real count is `max(1, ceil(N / 4096))`: 128 s gave 3 vs 2 and 256 s gave 5 vs 4, raising `ValueError: Length of values (2) does not match length of index (3)` and `ValueError: Length of values (4) does not match length of index (5)` respectively. At 8,193 and 16,385 samples both counts matched and extraction succeeded. With IBI features in a partial feature set, the table also has their columns, all NaN (lines 205–207 keep the first 98 names). | Fix or keep? |
| The IBI burst-detector placeholder path contains `>` | `IBI_features.main_IBI:85–92`; NaN returned at 115 | `main_IBI` looks for `Enter path to ->py_burst_detector-master/py_burst_detector-master/burst_detector/eeg_burst_detector.py`, relative to the working folder; the path is meant to be edited in the source. Windows does not allow `>` in file names, so there the check always fails and IBI features are NaN. Probe (Windows): making such a folder fails with `WinError 123`; `main_IBI` returns NaN. | See decision 9. |

In the full pipeline, downsampling follows the 30 Hz low-pass.
For ten-second inputs, the original gives:

| Input rate | Output samples | Actual output rate | Declared rate |
|---|---|---|---|
| 96 Hz | 480 | 48 Hz | 64 Hz |
| 160 Hz | 800 | 80 Hz | 64 Hz |
| 224 Hz | 560 | 56 Hz | 64 Hz |
| 288 Hz | 720 | 72 Hz | 64 Hz |
| 480 Hz | 600 | 60 Hz | 64 Hz |
| 200 Hz | 640 | 64 Hz | 64 Hz |
| 256 Hz | 640 | 64 Hz | 64 Hz |

This maintained version now gives 640 samples (64 Hz) for every listed rate.
In the original, the affected integer input rates are odd multiples of 32 Hz
above 64 Hz; see the "Fixed" note above.

In the original, direct downsampling at 32 Hz raises `ValueError` because the
slice step is zero; this maintained version now upsamples it to 64 Hz with
`resample_poly`. Integer ratios at 128, 256, 512, 1024 and 2048 Hz select every k-th
sample correctly. Rates such as 200, 250, 500 and 1000 Hz use
`resample_poly` toward 64 Hz. The original based the ratio on the recording
length (the target sample count was rounded), so when the length was not a
whole number of seconds the ratio was not exactly 64/Fs: for example, 1001
samples at 200 Hz gave 63.936 Hz, labelled 64 Hz. This maintained version now
uses the ratio Fs_new/Fs, as MATLAB `resample(x, Fs_new, Fs)` does in
`resample_savemat.m:152`; the ratio is exact when both rates are whole numbers
and approximated by a fraction with denominator <= 10000 otherwise. Whole-second
recordings at whole-number rates give identical results. Other lengths change
only when N × Fs_new / Fs is not a whole number: in a probe, 1001 samples at
200 Hz changed and 1025 samples (5.125 s) did not. `tests/test_downsample_rates.py`
checks both cases and a 64.5 Hz target rate.

</details>

<details>
<summary>Documentation mismatch and settings</summary>

| Behaviour | Where | Effect | Decision |
|---|---|---|---|
| Pearson is specified; the README table said Spearman | `connectivity_features.connectivity_corr:523–526`; NEURAL paper, section 4, eq. 21 and Table B.3 | Both Python and MATLAB use Pearson on squared Hilbert envelopes, `abs(hilbert(x)) ** 2`. The README table's Spearman was a documentation error and is now corrected to Pearson. | Corrected; no statistic decision is needed. |
| `params['FD']['method']` (“either 'higuchi' or 'katz'”) is never read | `fd_features.main_fd:135–136` | Through `generate_all_features`, “FD” always maps to Higuchi. | Implement or remove/document setting? |

[MATLAB also uses Pearson](https://github.com/otoolej/qEEG_feature_set/blob/206a89b8943f029a32947b1715f75b62ab8d5c8a/connectivity_features/connectivity_features.m#L338-L341).
The [NEURAL paper](https://arxiv.org/abs/1704.05694), section 4, eq. 21 and
Table B.3, specifies Pearson. The README's Spearman description was a
documentation error and is now corrected to Pearson.

</details>

## Artefact detection

The **low-correlation check** removes bipolar channels containing electrodes whose absolute mean Pearson correlation with other loaded electrodes is below 0.15, using the whole loaded recording.

JM O'Toole and GB Boylan (2017),
[NEURAL: quantitative features for newborn EEG using Matlab](https://arxiv.org/abs/1704.05694),
arXiv:1704.05694, section 3, describes the first referential low-correlation
check as targeting improper electrode placement. It describes the 1500 µV
high-amplitude threshold as suitable for preterm infants (<32 weeks).
Figure 1 illustrates the intended setting: most referential channels are
highly correlated (r > 0.8). The removal cutoff remains 0.15.

**Reported open-HIE run, not rerun in this review.** All 169 one-hour
recordings of the public neonatal HIE dataset
([Zenodo record](https://doi.org/10.5281/zenodo.7477575), CC BY 4.0;
[dataset paper](https://doi.org/10.1038/s41597-023-02002-8)) were downloaded
from Zenodo and processed locally with an application that calls the original
code (78c9425) at default settings. Only aggregate counts are reported here;
the recordings themselves are not in this repository. The dataset paper describes the
256 Hz recordings (NicoletOne) as referenced to FCz and the 200 Hz recordings
(Neurofax) as referenced to the average of C3 and C4.

| | 200 Hz (96 recordings) | 256 Hz (73 recordings) |
|---|---|---|
| Every bipolar channel removed | 50 | 0 |
| Ran with one or two of the eight bipolar channels | 20 | 0 |
| Median electrodes flagged by the low-correlation check | 5 | 0 |

No other check or error caused a failure. An earlier approximation on 33 of
these recordings found the same all-removed 200 Hz recordings, and `C3 + C4`
close to zero at 200 Hz (standard deviation ratio 0.015–0.37, versus
1.35–3.22 at 256 Hz).

**Reported reference test.** The low-correlation check alone was rerun on each
recording with the original code's loader, filter and threshold, after
changing only the reference in software: subtracting a recorded channel, or the
average of recorded channels, from every electrode. This is exact in exact
arithmetic; in floating point the results can differ in the last digits. Its
as-recorded result matched the full run's all-removed outcome in 169 of 169
recordings.

| Recordings with every channel removed | As recorded | Converted to C3/C4 average | Converted to Cz |
|---|---|---|---|
| 200 Hz (96) | 50 | 50 | 2 |
| 256 Hz (73) | 0 | 31 | 1 |

Changing only the reference switched the removals on and off. A single
reference electrode is not neutral: with Cz, 15 recordings kept fewer channels
than as recorded, and Cz itself becomes a flat channel that the check cannot
assess (its correlations are NaN, so it is never flagged).

With little common signal in the referential channels, their mean correlations
can fall below 0.15. A common reference cancels in bipolar differences, so in
exact arithmetic the bipolar signals and their features do not depend on it when
the same channels and samples are retained; in floating point, a synthetic Cz
re-reference changed bipolar samples by at most 3.55e-15, and features can then
differ slightly through the rounding sensitivity described above. The
referential removal check does depend on the reference.

**Settings** are read inside preprocessing functions. The one per-run argument is `remove_art`: `main_preprocessing` now accepts it, to override `REMOVE_ART`.
Direct feature wrappers accept parameters, but `generate_all_features` does not forward them.

<details>
<summary>Artefact stages and exact default parameters</summary>

`main_preprocessing` loads the EDF, builds the bipolar montage and, if
`REMOVE_ART` is on (the default), calls `remove_artefacts`. Optional
preprocessing arguments preserving the defaults are a possible follow-up,
subject to review.

`preprocessing_EEG.remove_artefacts:250–440` runs:

1. **Referential low-correlation check** (301–346), detailed below.
2. **Electrode coupling** (352–398), when more than 4 bipolar channels remain
   and each hemisphere has at least 2. A channel with mean power in 0.5–20 Hz
   below one-quarter of its hemisphere's median is removed. Every channel
   below the cutoff is removed: `ch_labels[ishort][0]` selects the whole row
   of the two-dimensional index array.
3. **Per-channel checks**, `art_per_channel:119–247`: exact zeros, high
   amplitude, constant values and sudden jumps.
4. **Shared removal** (432): a sample marked in any remaining channel becomes
   NaN in all of them.

Defaults in `NEURAL_parameters.py:42–62` are described there as “some default
values used for preterm infants (<32 weeks of gestation)”.

| Parameter | Default | Meaning as implemented | Read in |
|---|---|---|---|
| `REMOVE_ART` | 1 | 0 turns artefact removal off, as in the paper and MATLAB; the `remove_art` argument overrides it | `main_preprocessing` |
| `ART_ELEC_CHECK` | 1 s | Removes exact-zero runs at least this long, plus 1 sample on each side | `art_per_channel:145` |
| `ART_HIGH_VOLT` | 1500 µV | Threshold on the absolute Hilbert envelope of the 0.1–40 Hz filtered channel | `art_per_channel:171` |
| `ART_TIME_COLLAR` | 10 s | Removes this interval on each side of a high-amplitude sample | `art_per_channel:166` |
| `ART_DIFF_MIN_TIME` | 0.1 s | Removes runs of zero first differences longer than 0.1 × Fs samples; these mark constant values | `art_per_channel:201` |
| `ART_DIFF_VOLT` | 200 µV | Removes jumps between consecutive samples exceeding this threshold | `art_per_channel:225` |
| `ART_DIFF_TIME_COLLAR` | 0.5 s | Removes this interval on each side of a constant stretch or jump | `art_per_channel:192,221` |
| `ART_REF_LOW_CORR` | 0.15 | Threshold for the absolute mean referential correlation | `remove_artefacts:326` |
| `FILTER_REPLACE_ARTEFACTS` | `'nans'` | Feature band filters fill internal NaN by piecewise-cubic (PCHIP) interpolation, then restore NaN after filtering. Artefact-check filters instead use default `'linear_interp'`. Edge NaN are zeroed first, including the extra real sample described in the NaN-edge row above. | `main_amplitude`, `main_rEEG`, `main_fd`, `connectivity_corr` |

Fixed in code: the 0.5–20 Hz referential/coupling filter (orders 5/5),
the 0.1–40 Hz high-amplitude filter (low/high orders 5/2), and the coupling
threshold of one-quarter of median power.

</details>

<details>
<summary>Referential check: step-by-step code path</summary>

In `remove_artefacts:301–346`:

1. Use every referential channel loaded from the EDF, up to nine selected
   electrodes: F3, F4, C3, C4, O1, O2, T3, T4 and Cz. Use the loaded
   sample rate and the whole recording.
2. Apply `filter_butterworth_withnans(x, Fs, 20, 0.5, 5)`: order-5
   low-pass, then order-5 high-pass. Fill NaN by linear interpolation first.
3. Compute the Pearson matrix (`np.corrcoef`, line 320); ignore its diagonal.
4. Average each electrode’s correlations with all others (`np.nanmean`,
   line 322).
5. Flag electrodes whose mean correlation has absolute value < 0.15 (326).
6. Set to NaN every bipolar channel whose name contains a flagged electrode
   (332–346). For example, flagging C4 removes F4_C4, C4_T4, C4_Cz and C4_O2.

The comment asks whether there is a problem with one channel, for example Cz,
but the implementation does not limit how many electrodes it flags.

</details>

<details>
<summary>Every relevant NEURAL_parameters() call site</summary>

| Function | Call line(s) | Artefact settings read |
|---|---|---|
| `preprocessing_EEG.main_preprocessing` | 557, only when `remove_art` is None | `REMOVE_ART` |
| `preprocessing_EEG.art_per_channel` | 132 | `ART_ELEC_CHECK`, `ART_TIME_COLLAR`, `ART_HIGH_VOLT`, `ART_DIFF_TIME_COLLAR`, `ART_DIFF_MIN_TIME`, `ART_DIFF_VOLT` |
| `preprocessing_EEG.remove_artefacts` | 296 | `ART_REF_LOW_CORR` |
| `amplitude_features.main_amplitude` | 113,119 | `FILTER_REPLACE_ARTEFACTS` |
| `rEEG.main_rEEG` | 205,211 | `FILTER_REPLACE_ARTEFACTS` |
| `fd_features.main_fd` | 139,145 | `FILTER_REPLACE_ARTEFACTS` |
| `connectivity_features.main_connectivity` | 719,725 | `FILTER_REPLACE_ARTEFACTS`, passed to `connectivity_corr` |

`main_preprocessing` accepts one artefact argument, `remove_art`. Neither
`remove_artefacts` nor `art_per_channel` accepts an artefact-parameter
argument. The feature wrappers accept `params`,
but `generate_all_features:250–260,316` does not supply one.

Other calls are `generate_all_features:38,146`,
`spectral_features.main_spectral:466,472`, and `LPF_zero_phase:454`
(for `LP_fc`). Defaults for optional feature parameters are therefore read
inside the wrappers unless those wrappers are called directly with `params`.

</details>

### Skipping only the referential check

MATLAB `remove_artefacts.m` runs the referential check only when referential
data are passed (line 65, 206a89b), so `remove_artefacts(data,
ch_labels, Fs)` skips it and keeps the coupling and per-channel checks. The
Python function also skips the check when `data_ref` is empty
(`remove_artefacts:307`), but the coupling check sizes its array from
`data_ref` (line 362) instead of the number of bipolar channels, as MATLAB does
(`zeros(N_channels,N)`, line 111). Whenever the coupling check runs (more than
four remaining bipolar channels and at least two in each hemisphere,
`remove_artefacts:356–359`), it then fails; otherwise the call completes (see
the inherited-behaviour table). The
default pipeline always passes referential data and is unaffected. This is not
changed in this version; see decision 6.

## Not covered yet / planned work

**Not covered:**

- IBI/burst features.
- Feature comparisons on real recordings; aggregate open-HIE removal results are reported above.
- macOS.
- Non-default settings, except the three tested window types and `REMOVE_ART = 0`, which is now tested.

**Completed / proposed:**

- Completed: the single-machine synthetic filter sensitivity experiment; see its recorded results above.
- Completed: `uv.lock`, and `.github/workflows/uv-drift.yml`, which runs the tests with it in CI.
- Completed: one per-run artefact setting (`remove_art`); others remain proposed.
- Proposed: log the runner's CPU in CI, to test the machine explanation of the Windows drift.
- Proposed: reference values from three machines ([Run it on your PC](#run-it-on-your-pc)) and, if possible, a MATLAB run on the synthetic files.
- Proposed: feature-output comparisons on public real recordings.
- Proposed: decide how to handle C3/C4-average-reference recordings (decision 6), and fix the coupling-check array size if option (b) is chosen.
- Proposed: feature-code readability improvements after review.
