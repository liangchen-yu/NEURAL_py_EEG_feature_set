"""The 7 features removed to match neural_eeg_features 0.6.1 (the reference
package; see docs/CHANGES_vs_neural_eeg_features_0.6.1.md).

- Requesting a removed feature raises ValueError naming it, through
  generate_all_features and through the feature group's main_* function.
- FEATURE_SET_ALL has exactly the 23 feature names of the reference package,
  in the same order: always against the names written out below, and, when
  the reference package is present, against its neural_eeg_features/config.py
  and the removed names listed in its docs/definitions.md. Those files are
  read as text (config.py is parsed, not imported or run).
- feats_median_ch still keeps the first 98 columns (the slice is unchanged):
  the same explicit feature list gives the same columns as before; a default
  call gives 74 (before 98), including the 4 always-NaN IBI columns.

The reference package is looked for in the folder given by the environment
variable NEURAL_EEG_FEATURES_REFERENCE, else in neural_eeg_features-0.6.1 next
to this repository's top folder; if it is not there, those tests are skipped.

That the remaining features are unchanged is checked by the regression tests
(test_regression.py, test_edge_cases.py), which skip the removed features.

Synthetic data only.
"""
import ast
import copy
import os
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from NEURAL_py_EEG import (NEURAL_parameters, amplitude_features, connectivity_features,
                           generate_all_features, rEEG)

REMOVED = [
    "amplitude_total_power",
    "amplitude_SD",
    "rEEG_mean",
    "rEEG_width",
    "rEEG_SD",
    "connectivity_coh_max",
    "connectivity_coh_freqmax",
]

# ALL_FEATURES of neural_eeg_features 0.6.1 (neural_eeg_features/config.py).
REFERENCE_23_FEATURES = [
    "spectral_power",
    "spectral_relative_power",
    "spectral_flatness",
    "spectral_diff",
    "spectral_entropy",
    "spectral_edge_frequency",
    "FD",
    "amplitude_skew",
    "amplitude_kurtosis",
    "amplitude_env_mean",
    "amplitude_env_SD",
    "connectivity_BSI",
    "connectivity_corr",
    "connectivity_coh_mean",
    "rEEG_median",
    "rEEG_lower_margin",
    "rEEG_upper_margin",
    "rEEG_CV",
    "rEEG_asymmetry",
    "IBI_length_max",
    "IBI_length_median",
    "IBI_burst_prc",
    "IBI_burst_number",
]

FS = 64
CHANNELS = ["F3-C3", "F4-C4", "C3-O1", "C4-O2"]


def synthetic_data():
    """32 s of seeded random noise in 4 bipolar channels at 64 Hz."""
    rng = np.random.default_rng(2026)
    eeg = pd.DataFrame(rng.normal(size=(32 * FS, len(CHANNELS))), columns=CHANNELS)
    return {"eeg_data": eeg, "Fs": FS, "ch_labels": CHANNELS}


# ---------------------------------------------------------------------------
# Removed names raise ValueError
# ---------------------------------------------------------------------------
def test_removed_list_matches_the_package():
    assert list(NEURAL_parameters.REMOVED_FEATURES) == REMOVED


@pytest.mark.parametrize("feature", REMOVED)
def test_generate_all_features_rejects_removed_feature(feature):
    with pytest.raises(ValueError, match=re.escape(repr(feature))):
        generate_all_features.generate_all_features(synthetic_data(), feat_set=[feature])


@pytest.mark.parametrize("feature", REMOVED)
def test_generate_all_features_rejects_removed_feature_among_others(feature):
    with pytest.raises(ValueError, match=re.escape(repr(feature))):
        generate_all_features.generate_all_features(
            synthetic_data(), feat_set=["spectral_power", feature, "rEEG_CV"])


@pytest.mark.parametrize("feature", REMOVED)
def test_main_function_rejects_removed_feature(feature):
    data = synthetic_data()
    x = data["eeg_data"][CHANNELS[0]].to_numpy()
    with pytest.raises(ValueError, match=re.escape(repr(feature))):
        if feature.startswith("amplitude_"):
            amplitude_features.main_amplitude(x, FS, feature)
        elif feature.startswith("rEEG_"):
            rEEG.main_rEEG(x, FS, feature)
        else:
            connectivity_features.main_connectivity(
                data["eeg_data"].to_numpy().T, FS, feature, np.array(CHANNELS))


@pytest.mark.parametrize("module, name", [
    (amplitude_features, "amplitude_total_power"),
    (amplitude_features, "amplitude_SD"),
    (rEEG, "rEEG_mean"),
    (rEEG, "rEEG_width"),
    (rEEG, "rEEG_SD"),
])
def test_removed_feature_functions_are_gone(module, name):
    """Nothing else used these public functions, so they were deleted."""
    assert not hasattr(module, name)


# ---------------------------------------------------------------------------
# feats_median_ch keeps the first 98 columns, as before
# ---------------------------------------------------------------------------
# generate_all_features keeps the hard-coded [:98] slice of dc272ea: a request
# with fewer than 98 columns keeps all of them, including the IBI ones, which
# are always NaN in feats_median_ch. Every request now has at most 74 columns,
# so this includes the default call (before: 102 columns, the 98 non-IBI kept).
LONG_CHANNELS = ["F3_C3", "F4_C4", "C3_O1", "C4_O2"]


@pytest.fixture(scope="module")
def long_data():
    """128 s of seeded random noise in 4 bipolar channels at 64 Hz."""
    rng = np.random.default_rng(2026)
    eeg = pd.DataFrame(rng.normal(size=(128 * FS, len(LONG_CHANNELS))), columns=LONG_CHANNELS)
    return {"eeg_data": eeg, "Fs": FS, "ch_labels": LONG_CHANNELS}


def median_ch_columns(data, feat_set):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # NEURAL's warnings for noise input are not tested here
        out = generate_all_features.generate_all_features(copy.deepcopy(data), feat_set=feat_set)
    _, names, _, median_ch, _ = out
    return list(names), median_ch


def test_subset_keeps_all_its_columns(long_data):
    """All features except FD: 73 columns, all kept, as on dc272ea."""
    features = [f for f in REFERENCE_23_FEATURES if f != "FD"]
    names, median_ch = median_ch_columns(long_data, features)
    assert len(names) == 73
    assert list(median_ch.columns) == names


def test_unrequested_group_with_empty_bands_does_not_matter(long_data, monkeypatch):
    """rEEG freq_bands = [] does not affect a spectral_power call (4 columns)."""
    original = NEURAL_parameters.NEURAL_parameters

    def params_without_reeg_bands():
        params = original()
        params["rEEG"]["freq_bands"] = []
        return params

    monkeypatch.setattr(NEURAL_parameters, "NEURAL_parameters", params_without_reeg_bands)
    names, median_ch = median_ch_columns(long_data, ["spectral_power"])
    assert names == ["spectral_power__05_4", "spectral_power__4_7", "spectral_power__7_13",
                     "spectral_power__13_30"]
    assert list(median_ch.columns) == names


def test_full_set_keeps_74_columns_with_nan_ibi_columns(long_data):
    """The 23 names: 74 columns, fewer than 98, so all kept; the 4 IBI columns
    are all NaN (IBI features are not computed per epoch)."""
    names, median_ch = median_ch_columns(long_data, None)
    assert len(names) == 74
    assert list(median_ch.columns) == names
    ibi = [name for name in names if name.startswith("IBI_")]
    assert len(ibi) == 4 and names[-4:] == ibi
    assert median_ch[ibi].isna().all().all()


# ---------------------------------------------------------------------------
# The feature set equals the reference package's
# ---------------------------------------------------------------------------
def test_feature_set_has_the_reference_23_names():
    features = NEURAL_parameters.NEURAL_parameters()["FEATURE_SET_ALL"]
    assert features == REFERENCE_23_FEATURES
    assert not set(features) & set(REMOVED)


def reference_package():
    folder = os.environ.get("NEURAL_EEG_FEATURES_REFERENCE")
    if folder:
        path = Path(folder)
    else:
        path = Path(__file__).resolve().parents[2] / "neural_eeg_features-0.6.1"
    if not (path / "neural_eeg_features" / "config.py").is_file():
        pytest.skip("neural_eeg_features 0.6.1 not found at %s (set NEURAL_EEG_FEATURES_REFERENCE)" % path)
    return path


def evaluate(node, names):
    """Value of the few expressions config.py uses to build ALL_FEATURES:
    tuples of strings, names, '+', and tuple(f"prefix_{name}" for name in (...))."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(evaluate(item, names) for item in node.elts)
    if isinstance(node, ast.Name):
        return names[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return evaluate(node.left, names) + evaluate(node.right, names)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tuple"
            and len(node.args) == 1 and not node.keywords and isinstance(node.args[0], ast.GeneratorExp)):
        generator = node.args[0]
        (loop,) = generator.generators
        if not isinstance(loop.target, ast.Name) or loop.ifs or not isinstance(generator.elt, ast.JoinedStr):
            raise ValueError("unsupported generator in config.py: %s" % ast.dump(generator))
        values = []
        for item in evaluate(loop.iter, names):
            parts = []
            for part in generator.elt.values:
                if isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name) \
                        and part.value.id == loop.target.id and part.conversion == -1 \
                        and part.format_spec is None:
                    parts.append(item)
                else:
                    parts.append(evaluate(part, names))
            values.append("".join(parts))
        return tuple(values)
    raise ValueError("unsupported expression in config.py: %s" % ast.dump(node))


def reference_all_features(config_text):
    names = {}
    for statement in ast.parse(config_text).body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1 \
                and isinstance(statement.targets[0], ast.Name):
            target = statement.targets[0].id
            if target.endswith("_FEATURES"):
                names[target] = evaluate(statement.value, names)
    return list(names["ALL_FEATURES"])


def test_feature_set_matches_reference_package_config():
    path = reference_package()
    version = re.search(r'^version\s*=\s*"([^"]+)"', (path / "pyproject.toml").read_text(encoding="utf-8"),
                        re.MULTILINE)
    assert version and version.group(1) == "0.6.1"
    reference = reference_all_features(
        (path / "neural_eeg_features" / "config.py").read_text(encoding="utf-8"))
    assert reference == REFERENCE_23_FEATURES
    assert NEURAL_parameters.NEURAL_parameters()["FEATURE_SET_ALL"] == reference


def test_removed_names_match_reference_package_definitions():
    """docs/definitions.md, section "Deliberate settings and feature-selection
    differences": "The paper/MATLAB catalogue also contains seven names
    deliberately removed here: ..."."""
    text = (reference_package() / "docs" / "definitions.md").read_text(encoding="utf-8")
    paragraph = re.search(r"seven names deliberately removed here:(.*?)\. ", text, re.DOTALL)
    assert paragraph
    assert re.findall(r"`([^`]+)`", paragraph.group(1)) == REMOVED
