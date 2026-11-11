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

