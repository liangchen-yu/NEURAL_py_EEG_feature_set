# Change Log
All notable changes to this project will be documented in this file. Project first added to GitHub on
2020-02-20.

## Unreleased
Maintained fork (see README, "Maintenance"). With the same library versions, the results are
identical to release 0.1.3 (commit 78c9425), except at the rates changed by the downsampling fix
(odd multiples of 32 Hz above 64 Hz), for recordings that are not a whole number of seconds at
non-integer rate ratios (e.g. 200 or 250 Hz), when artefact removal is turned off
(`REMOVE_ART = 0` or `remove_art=False`), for `spectral_diff` (see "Output changes"), for FD
with three or more frequency bands or `method = 'katz'` (and `main_fd`, called directly, now
accepts the empty `[]` and single-row `[[low, high]]` band layouts, which raised `IndexError`
before), for band-pass and high-pass filters
built by `utils.filter_zerophase` (not used by the default pipeline), and for two connectivity
edge cases (see the `connectivity_features` entry); the tests in `tests/` check this.

### Output changes
- `spectral_diff` (default feature set): fix ported from the MATLAB NEURAL, MATLAB commit
  a279ddd (2020-04-23; `spectral_features.m`: `spec_diff=zeros(1,N_epochs - 1)`). The feature is
  the median of the N_epochs - 1 differences between consecutive spectrogram windows; the array
  had N_epochs entries, so one unfilled 0 was also in the median, lowering it.
  **Default `spectral_diff` values change**; they can only increase or stay the same. With no
  valid window-to-window difference the result is now NaN instead of 0, as in MATLAB, and numpy
  warns: "Mean of empty slice" for a single window (with the defaults, any input shorter than
  3 s, including inputs shorter than 2 s), "All-NaN slice encountered" if every window contains
  NaN. No other output changes.
  Measured with the default settings (64 Hz, 2 s windows, 50 % overlap), change per band
  (0.5-4 / 4-7 / 7-13 / 13-30 Hz):
  - white noise, 200 seeds, median [range]: 64 s (63 windows) +1.3 / +1.4 / +1.2 / +0.6 %
    [0 to +10 %]; 8 s (7 windows) +13 / +13 / +12 / +6 % [0 to +281 %].
  - synthetic EEG (`tests/synthetic_edf.py`, channel C3: every 4th sample of the 256 Hz signal,
    `[::4]`, i.e. 64 Hz; first 64 s / first 8 s): 64 s +3.9 / +0.05 / +6.0 / +1.1 %;
    8 s +14 / +24 / +27 / +15 %.
  - full pipeline on the synthetic test recordings (64 s epochs, median over channels and
    epochs): clean +0.9 / +2.2 / +2.9 / +0.5 %, artefacts +2.7 / +3.0 / +1.1 / +0.8 %; per
    channel and epoch, +0.01 % to +27 %.
  The regression tests compare every other output with the original's reference values, and
  `spectral_diff` with the original plus this one-line fix (see "Added").
  `tests/test_spectral_diff_fix.py` shows that the fixed `spectral_diff` is right.

### Changed
- Readability pass on the fork's own changes (comments and layout only; results unchanged).
- Package metadata moved from `setup.cfg` (removed) to the `[project]` table of `pyproject.toml`
  (build backend setuptools >= 77). The dependencies are declared there: Python >= 3.14,
  numpy >= 2.4.6, scipy >= 1.18.0, pandas >= 2.3.3 (pandas 3 supported), mne >= 1.13.2,
  matplotlib >= 3.10.8, pyedflib >= 0.1.42. pytest is in the `dev` dependency group.
- `utils.save_pd_as_edf` uses the pyedflib header key `sample_frequency` instead of `sample_rate`,
  which pyedflib 0.1.41 and later refuse (same meaning).

### Fixed
- `utils.filter_zerophase` names the filter type for `scipy.signal.firwin`, as MATLAB
  `filter_zerophase.m` does. Before, firwin's default kept 0 Hz, so a band-pass gave a band-stop
  and a high-pass gave a low-pass. Ported from Brian Murphy's PyPI release 0.1.4 (26 Jul 2022),
  which was never on GitHub. Low-pass and band-stop filters are unchanged, and the default
  pipeline uses only the low-pass, so default results do not change
  (`tests/test_filter_zerophase_type.py`). A high-pass now needs an odd number of filter
  coefficients (scipy's rule): if the length actually used is even, it raises `ValueError`,
  where it used to return a low-pass. That length is the given `L_filt` only when it is between
  1 and a quarter of the signal length; `L_filt = 0` (the default) or a longer `L_filt` is
  replaced, as before, by an odd length, so those calls do not raise.
- pandas 3 (Copy-on-Write): `preprocessing_EEG.remove_artefacts` filters copies of the channels and
  keeps, explicitly, the original's in-place filling of pre-existing NaN in the DataFrames it is
  given (the cleaned output depends on it).
- pandas 3: the +inf to NaN step of `remove_artefacts` uses `.loc` instead of chained assignment,
  which pandas 3 ignores.
- pandas 3: `utils.save_pd_as_edf` works on copies (it crashed); as before, it also sets NaN to 0
  in the DataFrame it is given.
- pandas 3: `overlap_epochs` (in `generate_all_features` and `preprocessing_EEG`) failed for a
  datetime or text row index; the new `utils.index_like_pandas2` keeps the pandas < 3 rule
  (positions for such indexes, labels for integer ones).
- pandas 3: `connectivity_features.gen_cross_spectrum` (and `gen_coherence`) failed for read-only
  arrays; it now works on a private copy (its input was never changed).
- SciPy >= 1.13: window types 'tuke', 'bart' and 'blackmanharris' in `utils.get_window` and
  `utils.gen_window` now come from `scipy.signal.windows` (same values).
- Docstrings now say which functions change their input in place and need writable arrays.
- Invalid escape sequence in a `utils.py` docstring (SyntaxWarning); the text is unchanged.
- `preprocessing_EEG.signal_downsample`: the integer check uses `round(x)` instead of
  `round(x, 1)`, as in MATLAB `resample_savemat.m`. Before, odd multiples of 32 Hz above 64 Hz
  (e.g. 96, 160, 480 Hz) were downsampled to the wrong rate but labelled 64 Hz; only these rates
  change. Calling `signal_downsample` directly at 32 Hz now upsamples to 64 Hz instead of raising
  `ValueError`; `main_preprocessing` is unaffected, because it already fails at 80 Hz or below.
  `tests/test_downsample_rates.py` covers 11 rates.
- `preprocessing_EEG.main_preprocessing` now reads NEURAL's `REMOVE_ART` setting, as in MATLAB
  `resample_savemat.m` and the NEURAL paper (section 3): `REMOVE_ART = 0` turns artefact removal
  off. Before, the setting was never read. The new `remove_art` argument overrides it for one run;
  with removal off, the artefact report is `None`. The default (1) keeps results identical.
  `tests/test_remove_art_switch.py` covers this.
- `preprocessing_EEG.signal_downsample`: at non-integer rate ratios (e.g. 200, 250, 500 Hz),
  `resample_poly` now uses the ratio Fs_new/Fs, as MATLAB `resample(x, Fs_new, Fs)` in
  `resample_savemat.m`: exact when both rates are whole numbers, otherwise approximated by a
  fraction with denominator <= 10000. Before, the ratio depended on the recording length, so a
  recording that is not a whole number of seconds came out at a slightly wrong rate labelled 64 Hz
  (e.g. 1001 samples at 200 Hz gave 63.936 Hz). Whole-second recordings at whole-number rates give
  identical results. `tests/test_downsample_rates.py` covers odd and whole-second lengths, all-NaN
  channels, a 64.5 Hz target rate and the inherited growth of NaN gaps.
- `fd_features.main_fd` now matches MATLAB `fd_features.m`:
  - Bands: each row of `freq_bands` is one band, using columns 0 and 1 as the cutoffs. Every
    band is filtered from the original signal. Before, the band count was the array's number of
    dimensions, so three or more bands gave only the first two values.
  - Empty `freq_bands`: `[]` gives one value from the unfiltered signal (before: `IndexError`).
  - One band as a nested list: `[[low, high]]` works (before: `IndexError`).
  - Method: the name `'FD'` reads `params['method']`, `'higuchi'` or `'katz'`. Before, the
    setting was never read and FD was always Higuchi. A missing or `None` `method` selects
    Higuchi, as before; results can still differ from before where the band fix above applies
    (e.g. 4 bands now give 4 values instead of 2). Any other value or type (including arrays,
    lists and numbers) raises `ValueError`. `fd_katz` is called without `qmax`, as in MATLAB.
  - Unchanged: the default settings (one 0.5-30 Hz band, Higuchi), a single `[low, high]` pair,
    a flat list of more numbers (only the first two are used) and exactly two bands.
  - Limitation: `generate_all_features` column naming (`get_feature_names`,
    `add_feat_data_to_array`) still supports only a flat list or a list of two or more bands for
    FD. A flat list is a `[low, high]` pair or a longer list such as `[0.5, 4, 30]`, which works
    but uses only its first two values. It fails for `[[low, high]]` and `[]`, which only
    `main_fd` accepts.
  - Tests: `tests/test_fd_bands.py`.
- `preprocessing_EEG.remove_artefacts` called without referential data (an empty DataFrame) no
  longer stops with `IndexError` when the electrode-coupling check runs (more than 4 bipolar
  channels, at least 2 on each side). That check's work array is now sized from the bipolar
  channels, as in MATLAB `remove_artefacts.m` (line 111), not from the referential data. No change
  to results that previously worked. `tests/test_referential_crash.py` covers this.
- `connectivity_features`: crashes fixed, following the intent of MATLAB `connectivity_features.m`.
  Inputs that worked before give identical results, with two documented exceptions: the number of
  NaN values when there are no left/right pairs (below), and one BSI case (below).
  - `main_connectivity` crashed for exactly 2 channels (IndexError) and for missing channel
    labels. Channels are now paired by label whenever there are 2 or more; without labels it warns
    and returns NaN for each frequency band (the Python fix of 0.1.2, lost in the 2022 restructure;
    MATLAB 867849b). With no left/right pairs it returns NaN for each frequency band instead of
    always 4 values (MATLAB c521173); this changes only non-default numbers of bands, for which
    `generate_all_features` crashed on the 4 values.
  - `connectivity_BSI` crashed with a single left channel (reported as "Feature function not
    found"). It now uses that channel and its paired right channel.
  - Exception, the only case where a value computed before changes: BSI with a single
    left channel (3 or more channels). The old code indexed the channel axis instead of the
    frequency axis, so it avoided a crash only when every band's computed bin indices (after
    clipping) were just index 0, for any spectral method. Index 0 then selected the whole channel,
    so it returned the BSI averaged over the whole spectrum instead of the band, against the first
    right channel in label order (not necessarily the pair). Example with the default method (bins
    0.125 Hz apart): `freq_bands = [[0, 0.1]]` with C3_O1, C4_O2, C4_T4 gave 0.1711 instead of the
    0 Hz band value 0.2443. The old value was wrong, so it is not kept.
  - Deliberate differences from MATLAB: NaN for each frequency band where MATLAB returns a scalar
    NaN; no warning when there are no left/right pairs (MATLAB warns), so that inputs that worked
    before behave exactly as before; with one left channel and 2 or more right channels, BSI uses
    the matched pair, whereas MATLAB's `X(iright, :)` is a matrix that `X_right(ibandpass)`
    indexes column-major (`connectivity_features.m:150`), interleaving the right channels. Which of
    these is intended is an open question for the maintainer.
  - `tests/test_connectivity_crashes.py` covers these cases and the unchanged 8-channel results.

### Added
- Regression tests (`tests/`) that compare every output with reference values from the original
  code (78c9425), on deterministic synthetic inputs, including NaN, +/-inf, EDF export, other
  kinds of row index, read-only arrays and the window types above.
- Reference files: `tests/make_reference.py` also runs the original NEURAL with only the
  one-line fix of MATLAB commit a279ddd (2020-04-23) applied in memory, and stores its
  `spectral_diff` values in each reference file (section `with_matlab_fix_a279ddd`). They are
  made in the same run and environment as the rest of the file. On GitHub Actions, the four
  modern reference files (clean, artefacts, edge cases, input types) are regenerated on each
  runner, this section included; the committed 2020 window reference (`reference_windows.json`)
  is kept, with its section made in the 2020 environment. The tests
  compare `spectral_diff` with them and every other output with the original's values, with the
  same strict tolerance (`neural_outputs.with_matlab_fix`). All original values in the reference
  files are unchanged.
- `tests/test_spectral_diff_fix.py`: proves the fixed `spectral_diff` is right, against an
  independent computation of the window-to-window differences on synthetic signals, including
  NaN windows and inputs with no valid difference.
- GitHub Actions workflow (`.github/workflows/tests.yml`), `requirements-dev.txt`, `.gitignore`.
- Same-machine GitHub Actions comparison against the original code in an isolated
  environment, retaining the strict tolerance and committed 2020 window references.
- Independent committed-versus-runner reference drift guard: fails above relative
  1e-5 plus absolute 1e-12, or on structural/discrete changes; logs OS/Python changes.
  The relative limit is about 25 times a simulated 4e-7 sensitivity estimate; the
  first hosted run's reported 1e-8 drift was a lower bound because comparisons stopped
  at their first failure. Shared changes below roughly 1e-5 relative can escape.
  Differences in the runner environment can affect rounding; the exact cause of the
  first hosted run's differences has not been determined.
- `uv.lock`, with the exact version of every package, and `.python-version` (3.14):
  `uv sync --locked` builds that environment.
- GitHub Actions workflow `.github/workflows/uv-drift.yml`: on Windows and Ubuntu, builds the
  `uv.lock` environment and runs the tests against the committed reference values. It is for
  information only: a tolerance failure does not fail the workflow.

## [0.1.3] - 25-08-2022
### Changed
- Changed the file structure to be package compliant
### Removed
### Fixed
### Added






### Added
- Added entire NEURAL_py_EEG_Features repository
- Using [semantic versioning](http://semver.org/)
## [0.1.0] - 2020-02-20



[0.1.0]: https://github.com/BrianMur92/NEURAL_py_EEG_feature_set/releases/tag/0.1.0
[0.1.3]: https://github.com/BrianMur92/NEURAL_py_EEG_feature_set/releases/tag/0.1.3
