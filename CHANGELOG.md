# Change Log
All notable changes to this project will be documented in this file. Project first added to GitHub on
2020-02-20. 

## Unreleased
Maintained fork (see README, "Maintenance"). With the same library versions, the results are
identical to release 0.1.3 (commit 78c9425), except at the rates changed by the downsampling fix
(odd multiples of 32 Hz above 64 Hz), for recordings that are not a whole number of seconds at
non-integer rate ratios (e.g. 200 or 250 Hz), and when artefact removal is turned off
(`REMOVE_ART = 0` or `remove_art=False`); the tests in `tests/` check this.

### Changed
- Readability pass on the fork's own changes (comments and layout only; results unchanged).
- Package metadata moved from `setup.cfg` (removed) to the `[project]` table of `pyproject.toml`
  (build backend setuptools >= 77). The dependencies are declared there: Python >= 3.14,
  numpy >= 2.4.6, scipy >= 1.18.0, pandas >= 2.3.3 (pandas 3 supported), mne >= 1.13.2,
  matplotlib >= 3.10.8, pyedflib >= 0.1.42. pytest is in the `dev` dependency group.
- `utils.save_pd_as_edf` uses the pyedflib header key `sample_frequency` instead of `sample_rate`,
  which pyedflib 0.1.41 and later refuse (same meaning).

### Fixed
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

