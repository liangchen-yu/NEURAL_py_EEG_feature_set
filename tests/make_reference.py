"""Make the reference values in tests/data/ with the ORIGINAL NEURAL.

The regression tests check that this repository's NEURAL still gives these
numbers, so they must come from the original, unmodified NEURAL: commit
78c9425 of https://github.com/BrianMur92/NEURAL_py_EEG_feature_set. Before
writing anything, this script checks that every NEURAL module it imports is
byte-for-byte that commit (SHA-256, line endings ignored); otherwise it stops.

What it makes, and where it must run:

  main     reference_clean.json, reference_artefacts.json  (tests/test_regression.py)
  edge     reference_edge_cases.json                       (tests/test_edge_cases.py)
  inputs   reference_input_types.json                      (tests/test_edge_cases.py)
           These three need the original NEURAL with pandas 2 (it does not
           run with pandas 3) and the tested numpy/scipy/mne versions.
  windows  reference_windows.json                          (tests/test_edge_cases.py)
           Needs SciPy < 1.13, where the original's window functions still
           exist: Brian's 2020 environment (Python 3.7, SciPy 1.3.1).

The files in tests/data/ were made on Windows 11 like this, from the
repository's top folder (on macOS/Linux use venv-original/bin/python):

    python -m venv venv-original
    venv-original\\Scripts\\python -m pip install numpy==2.5.3 scipy==1.18.1 pandas==2.3.3 mne==1.13.2 matplotlib==3.11.2 pyedflib==0.1.42
    venv-original\\Scripts\\python -m pip install "git+https://github.com/BrianMur92/NEURAL_py_EEG_feature_set.git@78c94258e4a3e6504e469f418443c78926e1a6be"
    venv-original\\Scripts\\python -B tests\\make_reference.py

and, for "windows", in a Python 3.7 environment with numpy 1.17.1, scipy 1.3.1,
pandas 0.25.1, mne 0.18.2, matplotlib 3.1.1, pyEDFlib 0.1.15 and the same
original NEURAL (plotting off: set MPLBACKEND=Agg):

    venv-2020\\Scripts\\python -B tests\\make_reference.py windows

-B: do not write __pycache__ folders. Add --output <folder> to write the
files elsewhere (e.g. to check they come out byte-identical). Running it
again in the same environment gives byte-identical files.

Each file also has a section "with_matlab_fix_a279ddd": the spectral_diff
values of the original with only the one-line fix of MATLAB commit a279ddd
(2020-04-23) applied in memory, made in the same run and environment. This
repository includes that fix, so the tests compare spectral_diff with these
values (see neural_outputs.with_fixes).

The main, edge and inputs files also have a section
"with_neural_eeg_features_0.6.1_moments": the amplitude_skew and
amplitude_kurtosis values of the original with only those two functions
replaced, in memory, by the definitions of neural_eeg_features 0.6.1
(bias-corrected; see with_neural_eeg_features_moments). This repository uses
those definitions, so the tests compare the two features with these values.
The windows file has no amplitude features, so it has no such section.

neural_outputs.with_fixes applies these sections in order: first the MATLAB
spectral_diff fix (with_matlab_fix_a279ddd), then the 0.6.1 moments section.
Every other feature is compared with the original NEURAL's output. (The
"about" texts ABOUT_FIX and ABOUT_MOMENTS are written into the reference
files; changing them means remaking the files, as the drift guard requires
the committed and runner-made texts to be equal.)

GitHub Actions runs "main edge inputs" with the original code on each runner.
The tests then compare the fork with those same-machine values, while a
separate drift guard checks them against the committed references. The
"windows" references remain the committed values from the 2020 environment.
"""
import contextlib
import glob
import hashlib
import inspect
import json
import os
import platform
import sys
import tempfile
from pathlib import Path

import numpy as np

import neural_outputs
import synthetic_edf

try:
    from importlib import metadata
except ImportError:  # Python 3.7 (the 2020 environment)
    metadata = None

DATA = Path(__file__).parent / "data"
LIBRARIES = ("numpy", "scipy", "pandas", "mne", "matplotlib", "pyedflib")

# SHA-256 of each module of the original NEURAL (commit 78c9425), with "\n"
# line endings. Any other code is refused.
ORIGINAL_SHA256 = {
    "IBI_features.py": "9ae767a4350a61473e13dbc00b4a91fd3228b4325b7dee220b6cab2e85d1eb17",
    "NEURAL_parameters.py": "c0e9565df7f41c47292874687ceff7e49863dee2afe68f3fd12eaa2c4f4ae035",
    "__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "amplitude_features.py": "6fe8ded33804b0737767e3e8a8939eb379d0812ff93fab39c96ae16e16f98fd9",
    "connectivity_features.py": "4c0a634203a25dc512fe475ea2d51abef04e98cd22488786526623bd1bbd32a7",
    "demos.py": "5256aede59ec8ec727ffefa42ed94821d55f22bf43be9a1760560bf87d058f77",
    "fd_features.py": "4cffcdb001c7d637789f3e9c97b9f9f7caf17e4bead3f89947436d229718b3eb",
    "generate_all_features.py": "2c77832039dbd0f3de9491bc94d7796f25df494f0283001be901260fa5b9f2c5",
    "mfiltfilt.py": "fbb1cc1d63eef2fe9df74587b64abe0d4bbc8006811ec09a70b72bd3dcc340dd",
    "preprocessing_EEG.py": "ff2c8d07c3ea990cba2810cf4d3e810c31abc5c5333a1ea46f7c424fa27cf7db",
    "rEEG.py": "b618a1a1eafcc6b322c7c6f8cc08ca06ca67d903aba8873b9b74c8e5f81268ac",
    "spectral_features.py": "d404112ef6bf07092a41976851fab4b9fa22864ae6321b8aa32a2e2a0fe66c59",
    "utils.py": "128828611b30d87fc5534f0eaa62ab9b10936ed5598403e8c90807227db8923a",
}

ABOUT_FIX = ("spectral_diff values from the original NEURAL with only the one-line fix of MATLAB commit "
             "a279ddd (2020-04-23) applied (in spectral_diff, np.zeros(N_epochs) becomes "
             "np.zeros(N_epochs - 1)), at the same places as in the rest of this file. This repository "
             "includes that fix, so the tests compare its spectral_diff with these values.")

ABOUT_MOMENTS = ("amplitude_skew and amplitude_kurtosis values from the original NEURAL with only these two "
                 "functions replaced by the definitions of neural_eeg_features 0.6.1: absolute bias-corrected "
                 "skewness, abs(scipy.stats.skew(x, bias=False)), and bias-corrected Pearson kurtosis, "
                 "scipy.stats.kurtosis(x, fisher=False, bias=False), on the finite values; NaN for fewer than "
                 "3 (skewness) or 4 (kurtosis) values or for constant values. At the same places as in the rest "
                 "of this file. This repository uses these definitions, so the tests compare the two features "
                 "with these values.")

ABOUT = {
    "what": "Reference values for tests/test_regression.py: the outputs of the original NEURAL "
            "(see made_with) for one synthetic EDF file (see input). Made by tests/make_reference.py.",
    "input": "The synthetic EDF file made by tests/synthetic_edf.py; sha256 is its checksum.",
    "artefact_report": "Second output of preprocessing_EEG.main_preprocessing: for each artefact check, "
                       "the % of samples removed in the worst channel; and the bipolar channels removed.",
    "preprocessed": "Fingerprint of the first output of main_preprocessing (bipolar EEG, 64 Hz): per channel, "
                    "NaN count, NaN stretches as [first, last + 1] sample indices, mean, std, min, max "
                    "(of the non-NaN samples), and every 500th sample.",
    "features": "Per feature, the outputs of generate_all_features(data, feat_set=[feature]): columns "
                "(one per frequency band); feats_median_all (median over channels and epochs); feat_st; "
                "feats_median_ch [epochs][bands]; feats_per_epochs [channels][epochs][bands], not for "
                "connectivity features, which compare pairs of channels.",
    "null": "null means NaN (not a number), e.g. an epoch NEURAL skipped because it was mostly artefact.",
    neural_outputs.FIX_SECTION: ABOUT_FIX,
    neural_outputs.MOMENTS_SECTION: ABOUT_MOMENTS,
}

ABOUT_EDGE = {
    "what": "Reference values for tests/test_edge_cases.py, from the original NEURAL (see made_with), "
            "for inputs an EDF file cannot hold. Made by tests/make_reference.py; inputs and steps are "
            "in tests/edge_cases.py.",
    "nan_input": "remove_artefacts with pre-existing NaN runs (referential and bipolar), then the rest "
                 "of the preprocessing (preprocessed: 64 Hz) and all 26 non-IBI features (features: "
                 "feats_median_all, one value per frequency band). data_ref_after: the original also "
                 "filled the NaN in the referential DataFrame it was given.",
    "inf_line": "The +inf line of remove_artefacts, reached through a stand-in for art_per_channel "
                "(no real input reaches it).",
    "inf_input": "Real +/-inf input: the original fails with this error.",
    "edf_export": "utils.save_pd_as_edf: what the written files contain, and the caller's DataFrame "
                  "afterwards (the original also set its NaN to 0). pyedflib 0.1.41+ refuses the "
                  "original's header key 'sample_rate', so while making this reference the key was "
                  "renamed to 'sample_frequency' (same meaning) on its way into pyedflib.",
    "fingerprint": "Per column: NaN stretches as [first, last + 1], number of +inf and -inf, sum and sum "
                   "of squares of the finite values, min, max, and every 997th sample.",
    "null": "null means NaN (not a number).",
    neural_outputs.FIX_SECTION: ABOUT_FIX,
    neural_outputs.MOMENTS_SECTION: ABOUT_MOMENTS,
}

ABOUT_INPUTS = {
    "what": "Reference values for tests/test_edge_cases.py from the original NEURAL with pandas 2.3.3 (see "
            "made_with): other kinds of row index, and read-only arrays. Steps: "
            "edge_cases.index_type_results and edge_cases.read_only_results.",
    "index_types": "The same EEG with a default, datetime, text, reversed-integer or 1000-based integer row "
                   "index: generate_all_features (feats_median_all of all 26 non-IBI features), the "
                   "preprocessing steps (artefact report and a fingerprint of the 64 Hz result) and "
                   "preprocessing_EEG.overlap_epochs (a fingerprint of the epochs). {error, "
                   "in_neural_function} records where the original stopped with an error.",
    "read_only": "connectivity_features.gen_coherence on two bipolar channels at 64 Hz. The original needs "
                 "writable arrays, so these values were made with writable ones; the tests use read-only "
                 "arrays (as pandas 3 gives) and expect the same values. inputs_unchanged: the input arrays "
                 "were left unchanged.",
    neural_outputs.FIX_SECTION: ABOUT_FIX,
    neural_outputs.MOMENTS_SECTION: ABOUT_MOMENTS,
}

ABOUT_WINDOWS = {
    "what": "Reference values for the window types 'tuke', 'bart' and 'blackmanharris' (tests/"
            "test_edge_cases.py), from the original NEURAL in Brian Murphy's 2020 environment (see "
            "made_with), where scipy.signal still had these functions. Steps: edge_cases.window_results.",
    "windows": "The window functions themselves (utils.get_window, gen_epoch_window, gen_window).",
    "features": "Every feature whose result depends on the window type, computed with each window "
                "(values), and how many times NEURAL's utils.get_window was asked for that window "
                "type (window_calls; it must be more than 0).",
    neural_outputs.FIX_SECTION: ABOUT_FIX,
}


# ---------------------------------------------------------------------------
# Which NEURAL and which environment
# ---------------------------------------------------------------------------
def verify_original_neural():
    """Stop unless every imported NEURAL module is exactly the original 78c9425 code."""
    import NEURAL_py_EEG

    folder = Path(NEURAL_py_EEG.__file__).parent
    problems = []
    for name, expected in sorted(ORIGINAL_SHA256.items()):
        path = folder / name
        if not path.exists():
            problems.append(name + ": missing")
        elif hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != expected:
            problems.append(name + ": not the 78c9425 version")
    if problems:
        raise SystemExit("No reference written: the imported NEURAL is not the original (commit 78c9425).\n  "
                         + "\n  ".join(problems)
                         + "\nRun this script with the original NEURAL installed (see the top of this file).")
    print("NEURAL source verified: all %d modules are the original 78c9425 code." % len(ORIGINAL_SHA256))


def library_version(name):
    if metadata is not None:
        return metadata.version(name)
    return __import__(name).__version__  # Python 3.7: no importlib.metadata


def direct_url():
    """How pip installed NEURAL (its direct_url.json), or {}."""
    if metadata is not None:
        try:
            return json.loads(metadata.distribution("NEURAL_py_EEG").read_text("direct_url.json") or "{}")
        except metadata.PackageNotFoundError:
            return {}
    import NEURAL_py_EEG
    site = os.path.dirname(os.path.dirname(NEURAL_py_EEG.__file__))
    for folder in glob.glob(os.path.join(site, "*.dist-info")):
        path = os.path.join(folder, "direct_url.json")
        if os.path.basename(folder).lower().startswith("neural") and os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return {}


def neural_source():
    """Which NEURAL is running: the git commit pip installed it from, and
    whether its preprocessing already contains the pandas-3 fix."""
    from NEURAL_py_EEG import preprocessing_EEG

    info = direct_url()
    commit = info.get("vcs_info", {}).get("commit_id")
    repository = info["url"] if info.get("url", "").startswith("https://") else None  # never a local path
    return {
        "neural_repository": repository,
        "neural_commit": commit,
        "neural_has_pandas3_fix": "to_numpy(copy=True)" in inspect.getsource(preprocessing_EEG),
    }


def made_with():
    versions = {"python": platform.python_version(), "os": "%s %s" % (platform.system(), platform.release())}
    versions.update({name: library_version(name) for name in LIBRARIES})
    versions.update(neural_source())
    return versions


@contextlib.contextmanager
def with_matlab_fix_a279ddd():
    """The original NEURAL with only the one-line fix of MATLAB commit a279ddd
    (2020-04-23) applied, in memory: spectral_diff's array of differences gets
    N_epochs - 1 entries instead of N_epochs. The installed files are not changed."""
    from NEURAL_py_EEG import spectral_features

    original = spectral_features.spectral_diff
    source = inspect.getsource(original)
    old, new = "spec_diff = np.zeros(N_epochs)", "spec_diff = np.zeros(N_epochs - 1)"
    if source.count(old) != 1:
        raise SystemExit("No reference written: the line %r is not in the original spectral_diff." % old)
    # main_spectral looks spectral_diff up in the module when it is called.
    exec(compile(source.replace(old, new), "<spectral_diff with MATLAB fix a279ddd>", "exec"),
         vars(spectral_features))
    try:
        yield
    finally:
        spectral_features.spectral_diff = original


def fix_section(make):
    """make() run again with the MATLAB fix; only its spectral_diff values are kept."""
    with with_matlab_fix_a279ddd():
        return neural_outputs.only_features(make(), (neural_outputs.FIXED_FEATURE,))


def finite_varying(data):
    """neural_eeg_features 0.6.1 (amplitude.py): the finite values, or None if
    they are empty or constant (range not above eps * max(1, max |value|))."""
    values = np.asarray(data, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0 or not np.ptp(values) > np.finfo(float).eps * max(1, np.max(np.abs(values))):
        return None
    return values


def skew_neural_eeg_features(data):
    """Absolute bias-corrected skewness; NaN for fewer than 3 values."""
    from scipy import stats

    values = finite_varying(data)
    if values is None or values.size < 3:
        return np.nan
    return float(abs(stats.skew(values, bias=False)))


def kurtosis_neural_eeg_features(data):
    """Bias-corrected Pearson kurtosis; NaN for fewer than 4 values."""
    from scipy import stats

    values = finite_varying(data)
    if values is None or values.size < 4:
        return np.nan
    return float(stats.kurtosis(values, fisher=False, bias=False))


@contextlib.contextmanager
def with_neural_eeg_features_moments():
    """The original NEURAL with only amplitude_skew and amplitude_kurtosis
    replaced, in memory, by the definitions of neural_eeg_features 0.6.1
    (written out above, independently of this repository's code). The
    installed files are not changed."""
    from NEURAL_py_EEG import amplitude_features

    originals = {name: getattr(amplitude_features, name) for name in neural_outputs.MOMENTS_FEATURES}
    # main_amplitude looks the feature function up in the module when it is called.
    amplitude_features.amplitude_skew = skew_neural_eeg_features
    amplitude_features.amplitude_kurtosis = kurtosis_neural_eeg_features
    try:
        yield
    finally:
        for name, function in originals.items():
            setattr(amplitude_features, name, function)


def moments_section(make):
    """make() run again with the neural_eeg_features 0.6.1 skewness and
    kurtosis; only their values are kept."""
    with with_neural_eeg_features_moments():
        return neural_outputs.only_features(make(), neural_outputs.MOMENTS_FEATURES)


def write_json(value, folder, name):
    path = Path(folder) / name
    with open(str(path), "w", encoding="utf-8", newline="\n") as f:
        f.write(neural_outputs.dumps(neural_outputs.to_json(value)) + "\n")
    print("  saved %s (%s bytes)" % (name, format(path.stat().st_size, ",")))


def same_numbers(a, b):
    """Exactly equal, NaN equal to NaN (works with old numpy too)."""
    a, b = neural_outputs.to_array(a), neural_outputs.to_array(b)
    return a.shape == b.shape and bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))


# ---------------------------------------------------------------------------
# main: the two synthetic EDF files
# ---------------------------------------------------------------------------
def check_same(one_by_one, all_at_once, case):
    """Each feature computed on its own must give exactly the same numbers as
    all 26 computed in one call (otherwise the all-in-one test could not use
    these reference values)."""
    for feature, outputs in all_at_once.items():
        for output, value in outputs.items():
            alone = one_by_one[feature][output]
            same = (value == alone) if output == "columns" else same_numbers(value, alone)
            if not same:
                raise SystemExit("%s: %s %s differs between one call per feature and all features in "
                                 "one call; reference not saved." % (case, feature, output))


def make_main_reference(case, features, folder):
    edf = synthetic_edf.make_edf(case)
    path = Path(folder) / ("synthetic_%s.edf" % case)
    path.write_bytes(edf)

    data, amount_removed = neural_outputs.preprocess(path)
    one_by_one = {feature: neural_outputs.compute_features(data, [feature])[feature] for feature in features}
    check_same(one_by_one, neural_outputs.compute_features(data, features), case)

    return {
        "about": ABOUT,
        "made_with": made_with(),
        "input": {
            "case": case,
            "sha256": synthetic_edf.sha256(edf),
            "bytes": len(edf),
            "seed": synthetic_edf.SEED,
            "sampling_rate_hz": synthetic_edf.FS,
            "duration_s": synthetic_edf.DURATION,
            "electrodes": synthetic_edf.ELECTRODES,
        },
        "artefact_report": neural_outputs.artefact_report(amount_removed),
        "preprocessed": neural_outputs.preprocessed_summary(data),
        "features": one_by_one,
        neural_outputs.FIX_SECTION: fix_section(lambda: {"features": neural_outputs.compute_features(
            data, [neural_outputs.FIXED_FEATURE])}),
        neural_outputs.MOMENTS_SECTION: moments_section(lambda: {"features": {
            feature: neural_outputs.compute_features(data, [feature])[feature]
            for feature in neural_outputs.MOMENTS_FEATURES}}),
    }


def make_main(output):
    features = neural_outputs.non_ibi_features()
    with tempfile.TemporaryDirectory() as folder:
        for case in synthetic_edf.CASES:
            reference = make_main_reference(case, features, folder)
            report = reference["artefact_report"]
            print("%s: input sha256 %s" % (case, reference["input"]["sha256"]))
            print("  artefact report: %s, channels removed: %s"
                  % (report["percent_removed_worst_channel"], report["channels_removed"]))
            write_json(reference, output, "reference_%s.json" % case)


# ---------------------------------------------------------------------------
# edge and windows: inputs an EDF file cannot hold
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def pyedflib_accepts_sample_rate():
    """pyedflib 0.1.41+ raises an error for the header key "sample_rate" that
    the original save_pd_as_edf uses; its newer name is "sample_frequency"
    (same meaning). Rename it on its way into pyedflib, so the original code
    can write its file. Nothing else is changed."""
    import pyedflib
    import pyedflib.edfwriter

    if "sample_frequency" not in inspect.getsource(pyedflib.edfwriter):
        yield  # an older pyedflib that still uses "sample_rate"
        return
    real = pyedflib.EdfWriter.setSignalHeaders

    def renamed(self, headers):
        headers = [dict(h) for h in headers]
        for h in headers:
            if "sample_rate" in h:
                h["sample_frequency"] = h.pop("sample_rate")
        return real(self, headers)

    pyedflib.EdfWriter.setSignalHeaders = renamed
    try:
        yield
    finally:
        pyedflib.EdfWriter.setSignalHeaders = real


def make_edge(output):
    import edge_cases

    reference = {"about": ABOUT_EDGE,
                 "made_with": dict(made_with(), neural_sha256_verified=True),
                 "nan_input": edge_cases.nan_case_results(),
                 "inf_line": edge_cases.inf_line_results(),
                 "inf_input": edge_cases.inf_input_failure()}
    with tempfile.TemporaryDirectory() as folder, pyedflib_accepts_sample_rate():
        reference["edf_export"] = edge_cases.export_results(folder)
    reference[neural_outputs.FIX_SECTION] = fix_section(lambda: {
        "nan_input": edge_cases.nan_case_results(), "inf_line": edge_cases.inf_line_results()})
    reference[neural_outputs.MOMENTS_SECTION] = moments_section(lambda: {
        "nan_input": edge_cases.nan_case_results(), "inf_line": edge_cases.inf_line_results()})
    print("edge cases: NaN artefact report %s; real +/-inf input: %s"
          % (reference["nan_input"]["artefact_report"]["percent_removed_worst_channel"], reference["inf_input"]))
    write_json(reference, output, "reference_edge_cases.json")


def make_inputs(output):
    import edge_cases

    reference = {"about": ABOUT_INPUTS,
                 "made_with": dict(made_with(), neural_sha256_verified=True),
                 "index_types": edge_cases.index_type_results(),
                 "read_only": edge_cases.read_only_results(read_only=False),
                 neural_outputs.FIX_SECTION: fix_section(lambda: {"index_types": edge_cases.index_type_results()}),
                 neural_outputs.MOMENTS_SECTION: moments_section(
                     lambda: {"index_types": edge_cases.index_type_results()})}
    write_json(reference, output, "reference_input_types.json")


def make_windows(output):
    import edge_cases
    from scipy import signal

    if not hasattr(signal, "tukey"):
        raise SystemExit("No reference written: this SciPy no longer has scipy.signal.tukey, so the "
                         "original window code cannot run. Use the 2020 environment (see the top of this file).")
    reference = {"about": ABOUT_WINDOWS,
                 "made_with": dict(made_with(), neural_sha256_verified=True),
                 "windows": edge_cases.window_results(),
                 neural_outputs.FIX_SECTION: fix_section(lambda: {"windows": edge_cases.window_results()})}
    write_json(reference, output, "reference_windows.json")


def main(argv):
    output = DATA
    if "--output" in argv:
        output = Path(argv[argv.index("--output") + 1])
        argv = argv[:argv.index("--output")] + argv[argv.index("--output") + 2:]
    chosen = argv or ["main", "edge", "inputs"]
    unknown = [name for name in chosen if name not in ("main", "edge", "inputs", "windows")]
    if unknown:
        raise SystemExit("unknown part(s): %s; choose from main, edge, inputs, windows" % ", ".join(unknown))

    verify_original_neural()
    output.mkdir(parents=True, exist_ok=True)
    if "main" in chosen:
        make_main(output)
    if "edge" in chosen:
        make_edge(output)
    if "inputs" in chosen:
        make_inputs(output)
    if "windows" in chosen:
        make_windows(output)


if __name__ == "__main__":
    main(sys.argv[1:])
