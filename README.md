[![tests](../../actions/workflows/tests.yml/badge.svg)](../../actions/workflows/tests.yml)

> **About this fork:** NEURAL_py by Brian M. Murphy and John M. O'Toole
> (UCC, BSD-3-Clause), forked at commit 78c9425 and updated to work with
> current Python libraries (pandas 3, SciPy 1.13+, pyedflib 0.1.41+).
> Regression tests show it gives the same results as the original code.
> Used for INFANT neural-eeg-ui project. Details, tested versions and install
> notes: see [Maintenance](#maintenance).


NEURAL_py: A Neonatal EEG Feature Set in python
============================================

Python code that replicates the [MATLAB](https://github.com/otoolej/qEEG_feature_set) version of the NEURAL feature set. The code is used
to generate a set of quantitative features from multichannel EEG recordings. 
Features include amplitude measures, spectral measures, and basic connectivity
measures (across hemisphere's only). Also, for preterm EEG (assuming gestational age < 32
weeks), will generate features from bursts annotations (e.g. maximum inter-burst
interval). Burst annotations require a separate package, also available on
[github](https://github.com/otoolej/py_burst_detector). 

Full details of the methods can be found in: `JM O’Toole and GB Boylan (2017). NEURAL:
quantitative features for newborn EEG using Matlab. ArXiv e-prints, arXiv:1704.05694`
available at https://arxiv.org/abs/1704.05694.

---

[Requirements](#requirements) | [Use](#use) | [Quantitative
features](#quantitative-features) | [Files](#files) | [Test computer
setup](#test-computer-setup) | [Licence](#licence) | [References](#references) |
[Contact](#contact)

## Requirements:
Python 3.7 or newer with the following packages installed
| Package       | Version installed  |
| ------------- |:------------------:|
| mne           | 0.18.2             |
| pandas        | 0.25.1             |
| numpy         | 1.17.1             |
| matplotlib    | 3.1.1              |
| scipy         | 1.3.1              |
| pyEDFlib      | 0.1.14             |

## Use 

Set path `(path_to_NEURAL_py)` to the folder location of NEURAL_py. Then the following will load the main functions:
```
  import sys
  sys.path.append(path_to_NEURAL_py)
  import utils,  preprocessing_EEG, generate_all_features
```

As an example, generate simulated EEG and calculate relative spectral power, standard
deviation of range-EEG, and brain symmetry index:
```
  # generate EEG-like data (coloured Gaussian noise)
  data_st = utils.gen_test_EEGdata(5*60,64,1)

  # define feature set (or can define in neural_parameters.m):
  feature_set = ['spectral_relative_power','rEEG_SD', 'connectivity_BSI']
  
  # estimate features:
  feats_per_epochs, feat_pd_names, feat_st, feats_median_ch, feats_median_all = generate_all_features.generate_all_features(data_st, feat_set=feature_set)

  print('Features extracted')
  print(feat_pd_names)
```

See the `demos.py` file for further examples. To run the demo code without previously adding the package:
```
  import sys
  sys.path.append(path_to_NEURAL_py)
  import demos


  demos.artefact_removal_examples()
  demos.generate_a_subset_of_features_example()
  demos.generate_all_features_example()
  demos.preprocessing_and_feature_extraction()
  demos.load_edf_preprocessing_and_feature_extraction()
```





All parameters are set the file
`utils.NEURAL_parameters`.


## Quantitative features

The feature set contains amplitude, spectral, connectivity, and burst annotation features.
Amplitude features include range-EEG (D. O’ Reilly et al., 2012;
see [references](#references)), a clearly-defined alternative to amplitude-integrated EEG
(aEEG). All features are generated for four different frequency bands (typically 0.5–4,
4–7, 7–13, and 13–30 Hz), with some exceptions. The following table describes the features
in more detail:

| feature name               | description                                                                   | FB  |
|----------------------------|-------------------------------------------------------------------------------|-----|
| spectral\_power            | spectral power: absolute                                                      | yes |
| spectral\_relative\_power  | spectral power: relative (normalised to total spectral power)                 | yes |
| spectral\_flatness         | spectral entropy: Wiener (measure of spectral flatness)                       | yes |
| spectral\_entropy          | spectral entropy: Shannon                                                     | yes |
| spectral\_diff             | difference between consecutive short-time spectral estimates                  | yes |
| spectral\_edge\_frequency  | cut-off frequency (fc): 95% of spectral power contained between 0.5 and fc Hz | no  |
| FD                         | fractal dimension                                                             | yes |
| amplitude\_total\_power    | time-domain signal: total power                                               | yes |
| amplitude\_SD              | time-domain signal: standard deviation                                        | yes |
| amplitude\_skew            | time-domain signal: skewness (absolute value)                                 | yes |
| amplitude\_kurtosis        | time-domain signal: kurtosis                                                  | yes |
| amplitude\_env\_mean       | envelope: mean value                                                          | yes |
| amplitude\_env\_SD         | envelope: standard deviation (SD)                                             | yes |
| connectivity\_BSI          | brain symmetry index (see Van Putten 2007)                                    | yes |
| connectivity\_corr         | correlation (Spearman) between envelopes of hemisphere-paired channels        | yes |
| connectivity\_coh\_mean    | coherence: mean value                                                         | yes |
| connectivity\_coh\_max     | coherence: maximum value                                                      | yes |
| connectivity\_coh\_freqmax | coherence: frequency of maximum value                                         | yes |
| rEEG\_mean                 | range EEG: mean                                                               | yes |
| rEEG\_median               | range EEG: median                                                             | yes |
| rEEG\_lower\_margin        | range EEG: lower margin (5th percentile)                                      | yes |
| rEEG\_upper\_margin        | range EEG: upper margin (95th percentile)                                     | yes |
| rEEG\_width                | range EEG: upper margin - lower margin                                        | yes |
| rEEG\_SD                   | range EEG: standard deviation                                                 | yes |
| rEEG\_CV                   | range EEG: coefficient of variation                                           | yes |
| rEEG\_asymmetry            | range EEG: measure of skew about median                                       | yes |
| IBI\_length\_max           | burst annotation: maximum (95th percentile) inter-burst interval              | no  |
| IBI\_length\_median        | burst annotation: median inter-burst interval                                 | no  |
| IBI\_burst\_prc            | burst annotation: burst percentage                                            | no  |
| IBI\_burst\_number         | burst annotation: number of bursts                                            | no  |

FB: features generated for each frequency band (FB)


## Files
Some python files (.py files) have a description and an example in the header. To read this
header, type `help(filename)` in the console after importing (`import filename`).  Directory structure is as follows: 
```
├── amplitude_features.py                  # amplitude features
├── connectivity_features.py               # hemisphere connectivity features
├── demos.py                               # python file to give examples on how to use the code
├── fd_features.py                         # fractal dimension features
├── generate_all_features.py               # main function: generates feature set on EEG
├── IBI_features.py                        # features from the burst annotations  
├── LICENSE.md                             # license file  
├── mfiltfilt.py                           # MATLAB implementation of filtfilt function 
├── preprocessing_EEG.py                   # loads EEG from EDF files (including artefact removal)
├── README.md                              # readme file describing project
├── rEEG.py                                # range-EEG (similar to aEEG)
├── spectral_features.py                   # spectral features
└── utils.py                               # misc. functions
```




## Test computer setup
- hardware:  Intel Core i7-8700K @ 3.2GHz; 32GB memory.
- operating system: Windows 10 64-bit
- software: python 3.7


## Licence

```
Copyright (c) 2020, Brian M. Murphy and John M. O' Toole, University College Cork
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

  Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

  Redistributions in binary form must reproduce the above copyright notice, this
  list of conditions and the following disclaimer in the documentation and/or
  other materials provided with the distribution.

  Neither the name of the University College Cork nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```


## References

1. JM O’Toole and GB Boylan (2017). NEURAL: quantitative features for newborn EEG using
Matlab. ArXiv e-prints, arXiv:[1704.05694](https://arxiv.org/abs/1704.05694).

2. D O’Reilly, MA Navakatikyan, M Filip, D Greene, & LJ Van Marter (2012). Peak-to-peak
amplitude in neonatal brain monitoring of premature infants. Clinical Neurophysiology,
123(11):2139–2153.

3. MJAM van Putten (2007). The revised brain symmetry index. Clinical Neurophysiology,
118(11):2362–2367.

4. T Higuchi (1988). Approach to an irregular time series on the basis of the fractal theory,
Physica D: Nonlinear Phenomena, 31:277–283.

5. MJ Katz (1988). Fractals and the analysis of waveforms. Computers in Biology and
Medicine, 18(3):145–156.

6. AV Oppenheim, RW Schafer. Discrete-Time Signal Processing. Prentice-Hall, Englewood
Cliffs, NJ 07458, 1999.

7. JM O’ Toole, GB Boylan, S Vanhatalo, NJ Stevenson (2016). Estimating functional brain
maturity in very and extremely preterm neonates using automated analysis of the
electroencephalogram. Clinical Neurophysiology, 127(8):2910–2918

8. JM O’ Toole, GB Boylan, RO Lloyd, RM Goulding, S Vanhatalo, NJ Stevenson
(2017). Detecting Bursts in the EEG of Very and Extremely Premature Infants using a
Multi-Feature Approach. Medical Engineering and
Physics, vol. 45, pp. 42-50, 2017. 
[DOI:10.1016/j.medengphy.2017.04.003](https://dx.doi.org/10.1016/j.medengphy.2017.04.003)
  
9. JM O'Toole and GB Geraldine (2019). Quantitative Preterm EEG Analysis: The Need for
Caution in Using Modern Data Science Techniques. Frontiers in Pediatrics 7, 174
[DOI:10.3389/fped.2019.00174](https://doi.org/10.3389/fped.2019.00174)
  

## Contact

Brian M. Murphy

Neonatal Brain Research Group,  
[INFANT Research Centre](https://www.infantcentre.ie/),  
Department of Paediatrics and Child Health,  
Room 2.18 UCC Academic Paediatric Unit, Cork University Hospital,  
University College Cork,  
Ireland

- email: Brian.M.Murphy AT umail dot ucc dot ie 


## Maintenance

This fork keeps NEURAL_py working with current Python libraries. Regression
tests show that it gives the same numbers as the original code (commit
[78c9425](https://github.com/BrianMur92/NEURAL_py_EEG_feature_set/commit/78c94258e4a3e6504e469f418443c78926e1a6be)).
No algorithm or default parameter was changed.

**What "the same" covers.**

*Exactly the same* (largest difference 0), compared with the original code
run with the same library versions on the same computer:

- the default pipeline: EDF file → `preprocessing_EEG.main_preprocessing` →
  `generate_all_features`, for all 26 non-IBI features (summary, per-epoch and
  per-channel values), the artefact report and the removed channels, on a
  clean and an artefact-laden synthetic EDF file;
- data that already contain NaN when given to `remove_artefacts`: the
  artefact report, every feature's summary values (one per frequency band;
  per-channel and per-epoch values are not stored for this case), sampled
  checks of the cleaned and preprocessed EEG (where it is NaN, sums, minimum
  and maximum, every 997th sample), and the change the original also makes
  to the referential DataFrame it is given;
- the step of `remove_artefacts` that turns +inf into NaN, checked in the same
  way (no input reaches it, so the test supplies the infinities through a
  stand-in);
- EDF export with `utils.save_pd_as_edf`: the same digital samples and the
  same values in the checked header fields (label, unit, sample frequency,
  physical and digital range), and the same change to the DataFrame it is
  given;
- the same EEG with a datetime, text or integer row index, through
  `generate_all_features` (feature summaries), the preprocessing steps and
  `preprocessing_EEG.overlap_epochs`: the same results, and the same errors
  where the original stopped;
- `connectivity_features.gen_coherence` given read-only arrays (as pandas 3
  gives): the original's values, with its inputs left unchanged.

*Within a tolerance*, because other library versions change the last digits:

- the window types `'tuke'`, `'bart'` and `'blackmanharris'`, compared with
  the original in its 2020 environment (old SciPy): the windows themselves
  are identical, and the listed features agree to within 2e-15 relative
  under the tested settings: spectral flatness, entropy, diff and edge
  frequency; the rEEG features without their frequency-band filter; and BSI
  with method "PSD". Under other settings coherence can also depend on the
  window; that is not covered;
- the one-off comparison with the 2020 environment and the web-browser check
  described below.

Not covered: IBI (burst) features, which need a separate burst detector; real
recordings; parameter settings other than those above; categorical, interval
or multi-level row indexes; Linux and macOS (only Windows has been tested so
far).

**What changed and why**

- `preprocessing_EEG.remove_artefacts`: each channel is copied before it is
  filtered (`.to_numpy(copy=True)`), because pandas 3 (Copy-on-Write) gives
  read-only arrays and NEURAL writes into them.
- `preprocessing_EEG.remove_artefacts`, referential and electrode-coupling
  checks: when a channel already contains NaN, the filter's filled-in values
  are written back to the DataFrame. The original did this without saying so
  (pandas < 3 gave a view of the DataFrame), and the cleaned output depends
  on it; without it, data with NaN gave different results.
- `preprocessing_EEG.remove_artefacts`: `data[col][idx] = np.nan` became one
  `.loc` assignment with a True/False mask, because pandas 3 silently ignores
  this "chained assignment". No input reaches this line: an infinity either
  makes one of NEURAL's filters stop with an error first (as in the
  original), or, right next to a run of zeros of 1 s or more, is turned into
  NaN before it.
- `generate_all_features.overlap_epochs` and `preprocessing_EEG.overlap_epochs`:
  with pandas < 3, `x[positions]` on a pandas Series picked samples by
  position when the row index holds no numbers (for example dates or text)
  and by label otherwise; pandas 3 always uses labels, so a datetime or text
  index failed. The new `utils.index_like_pandas2` keeps the pandas < 3 rule.
- `connectivity_features.gen_cross_spectrum` (and so `gen_coherence`): works on
  a private copy of its input. One of its lines never changes the values but
  still needed a writable array, and pandas 3 gives read-only ones.
- The docstrings of the functions that change their input in place say so
  (see "Known limitations" below), and two docstring examples use
  `.to_numpy(copy=True)` instead of `.values`.
- `utils.save_pd_as_edf`: works on a copy (pandas 3 gives read-only arrays)
  and, as before, also sets NaN to 0 in the DataFrame it is given; uses the
  header key `sample_frequency`, because pyedflib 0.1.41 and later refuse the
  old name `sample_rate` (same meaning).
- `utils.get_window`, `utils.gen_window`: `'tuke'`, `'bart'` and
  `'blackmanharris'` come from `scipy.signal.windows`, because SciPy 1.13
  removed them from `scipy.signal` (same functions, same values).
- `utils.py`: a docstring now writes `'$\\mu$V'` instead of `'$\mu$V'` (the
  same text), because `\m` is an invalid escape sequence (`SyntaxWarning`).
- `setup.cfg`: the dependencies are declared (none were before), with the
  oldest tested versions as lower bounds and `python_requires >=3.14`.
- New: `tests/` (regression tests and reference values), `requirements-dev.txt`,
  pytest settings in `pyproject.toml`, `.gitignore`, and
  `.github/workflows/tests.yml` (automatic tests on GitHub).

**Install** (Python 3.14; from this folder, ideally in a virtual environment)

    python -m pip install -e .
    python -m pip install -r requirements-dev.txt

`-e` ("editable") means Python uses the code in this folder. pyedflib 0.1.42
has no ready-made package for Python 3.14, so pip compiles it: on Windows
this needs the Microsoft C++ Build Tools, on Linux a C compiler.

**Run the tests**

    python -m pytest

This takes about 45 seconds. pytest first shows which NEURAL and library
versions it uses (and stops if it would test any copy of NEURAL other than
this folder's `src/`); at the end it prints the largest difference from the
reference values for each group.

**How the results were verified**

- Inputs: two synthetic EDF files (300 s, 256 Hz, 9 electrodes; no real
  recordings): "clean", and "artefacts", whose deliberate artefacts trigger
  each of NEURAL's artefact checks and both channel-removal checks.
  `tests/synthetic_edf.py` makes them from a fixed seed with whole-number
  arithmetic only, so they are byte-identical on every computer; the tests
  check their SHA-256 checksums. An EDF file cannot contain NaN or infinity,
  so the edge cases build their inputs from the same signals and call
  NEURAL's functions directly (`tests/edge_cases.py`).
- Reference values (`tests/data/`): made by `tests/make_reference.py` with the
  original NEURAL. The script first checks that every NEURAL module is
  byte-for-byte commit 78c9425 (SHA-256) and refuses to run otherwise. The
  main and edge-case values come from the original with pandas 2.3.3; the
  window values from the original in its 2020 environment, the only place
  the old window functions still exist. The script's header lists the exact
  commands.
- Comparison: the tests check every stored value, allowing a relative
  difference of 1e-9 (absolute 1e-12) so that they can also run with other
  library versions; NaN must be NaN in both, and counts, positions and text
  must be equal. With the versions in the "Main" row below, the actual
  differences are 0, except for the comparison with the 2020 environment.
  The main tests store every value. The edge cases store sampled checks of
  the EEG (see above) and, for the features, only the summary values (one
  per frequency band).
- Reproducibility: the EDF inputs are byte-identical on any computer. The
  reference values are reproducible in the environment recorded in each file
  (`made_with`): running `tests/make_reference.py` there again gives
  byte-identical files. `made_with` records the operating system as Python
  reports it (Python 3.7, for example, calls Windows 11 "Windows 10").

**Tested versions** (native, Windows 11, Python 3.14.7; all 28 tests pass)

| | numpy | scipy | pandas | mne | matplotlib | pyedflib | Largest difference |
|---|---|---|---|---|---|---|---|
| Main | 2.5.3 | 1.18.1 | 2.3.3, 3.0.2, 3.0.6 and 3.1.0 | 1.13.2 | 3.11.2 | 0.1.42 | 0 |
| Minimum versions | 2.4.6 | 1.18.0 | 2.3.3 and 3.0.2 | 1.13.2 | 3.10.8 | 0.1.42 | 3e-15 relative |
| Newest (22 October 2026) | 2.5.4 | 1.18.1 | 3.1.0 | 1.13.2 | 3.11.2 | 0.1.42 | 0 |

The "Largest difference" column leaves out the window-type comparison with the
2020 environment, which every run also makes: at most 1.6e-15 relative.
The lower bounds in `setup.cfg` are the "Minimum versions" row, plus Python
3.14. The "Requirements" table above lists the versions the original code
was written with.

**Comparison with the original 2020 environment** (a one-off check, not part
of the tests). The original NEURAL was also run on the same synthetic files
with the versions in the Requirements table: Python 3.7.9, numpy 1.17.1,
scipy 1.3.1, pandas 0.25.1, mne 0.18.2, matplotlib 3.1.1, and pyEDFlib 0.1.15
(0.1.14 has no Python 3.7 build for Windows). The artefact report, the
removed channels and the NaN placement were identical. Spectral, BSI and
coherence features agreed to about 1e-14; amplitude, rEEG, connectivity_corr
and FD features to within 3e-7 relative. These small differences come from
last-digit changes in SciPy's filter routines, which NEURAL's 0.5 Hz
Butterworth high-pass filter amplifies.

**Web browser check** (a separate experiment, not included in this
repository). NEURAL with the same pandas-3 fix also ran in a web browser
(Pyodide 314.0.7: Python 3.14.2, numpy 2.4.6, scipy 1.18.0, pandas 3.0.2,
mne 1.13.2, matplotlib 3.10.8; pyedflib cannot be installed there, and NEURAL
only needs it for EDF export). All 26 non-IBI features ran; largest absolute
difference vs native 3.7e-8 (relative about 2e-8; up to 2e-6 for values near
zero), due to floating-point rounding in recursive filters. Spectral features
agree to about 1e-15.

**Automatic tests on GitHub.** `.github/workflows/tests.yml` runs the tests on
every push and pull request, on Windows and Ubuntu, with Python 3.14 and with
pandas 2.3.3 and the latest pandas 3.x; the other libraries are fixed to the
versions the reference values were made with. Each job first runs the original
code (commit 78c9425, pandas 2.3.3) in an isolated environment to regenerate the
main, edge-case and input-type references on that runner. The tests compare
the fork with those values at the unchanged tolerance (relative 1e-9, absolute
1e-12). The window references (`reference_windows.json`) stay committed: they
need the 2020 environment and are still tested.

The first GitHub run failed on all four jobs: the reported amplitude_skew and
rEEG differences from the committed Windows-PC references reached about 1e-8
relative, while preprocessed EEG differed by about 1e-14. The reported feature
drift is a lower bound: each failed comparison stopped later comparisons, so
some per-epoch arrays were never checked. For example, the clean amplitude
group recorded 708 values on GitHub, versus 1,992 in the complete local run.
Differences in the runner environment can affect the last digits that NEURAL's
0.5 Hz high-pass filter amplifies; the exact cause of that run's differences has
not been determined.

A separate simulation added 1-4 ULP (units in the last place) of noise to the
preprocessed EEG and reran the real feature pipeline. Relative changes in
median-channel values were about 2e-9 to 9e-9, while per-epoch amplitude_skew
and rEEG_asymmetry reached about 4e-7. These are sensitivity estimates, not
measurements from a hosted runner.

A separate check, `tests/check_reference_drift.py`, also gates the job. Once the
workflow has recorded `REFERENCE_TEMP`, it runs even if pytest fails. It prints
the largest committed-versus-runner drift and fails above
`1e-12 + 1e-5 * abs(committed)`. The relative limit is about 25 times the
simulated 4e-7 estimate; the absolute floor stays at 1e-12
because a larger allowance near zero has not been established. Structures,
checksums, NaN positions, text, booleans and integers must match exactly. Only
the recorded OS and Python version may differ without failing, and those
changes are printed. This catches larger changes that affect the original and
fork equally, including shared-helper bugs. Shared changes smaller than roughly
1e-5 relative can escape the guard, and the absolute floor matters near zero.
The guard may flag new environments for investigation; it does not establish
the cause of drift or guarantee every environment passes.

**Known limitations inherited from the original** (unchanged in this fork; the
same with pandas 2.3.3 and pandas 3)

- `generate_all_features(..., channel_names=[...])`: selecting channels fails
  with a `KeyError`, whichever channels are named.
- `utils.gen_test_EEGdata(..., discont_activity=1)` fails with an `IndexError`
  for recordings shorter than 100 s (they get no bursts); 100 s or longer
  works.
- Row index: like pandas < 3, NEURAL looks samples up by label when the row
  index holds integers. An integer index that does not start at 0 therefore
  makes `generate_all_features` fail with a `KeyError`, and one in another
  order uses the samples in label order. `remove_artefacts` with any index
  other than 0, 1, 2, ... fails with a `KeyError` once it finds artefacts.
- Some functions change the array they are given, so it must be writable;
  from pandas 3 on, pass for example `.to_numpy(copy=True)` rather than
  `.values`: `preprocessing_EEG.art_per_channel` (marks artefacts as NaN),
  `utils.filter_zerophase` (sets NaN to 0), `utils.filter_butterworth_withnans`
  (fills NaN, except in its `'cubic_interp'` and `'nans'` modes),
  `utils.replace_start_ends_NaNs_with_zeros` and `utils.naninterp`.
  `remove_artefacts` relies on this and passes copies itself.
- Infinite values (+/-inf) that reach one of NEURAL's Butterworth filters
  make `remove_artefacts` stop with an `IndexError` (in
  `utils.replace_start_ends_NaNs_with_zeros`). An infinity right next to a
  run of zeros of 1 s or more can be turned into NaN by the flat-zero check
  first, and processing then completes, but only if no earlier step filters
  the raw data: the referential check always filters the referential data,
  and the electrode-coupling check filters the bipolar data when there are
  more than 4 bipolar channels.
- `utils.len_cont_zeros` warns "Must be a binary signal" when the signal *is*
  binary (its check is the wrong way round). This is harmless; the tests hide
  this one message.
- `save_pd_as_edf`'s default physical minimum (-5482.288) has 9 characters but
  an EDF header field holds 8, so pyedflib warns and stores -5482.28.
