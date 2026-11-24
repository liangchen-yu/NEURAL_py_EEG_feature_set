"""The REMOVE_ART switch in preprocessing_EEG.main_preprocessing.

MATLAB NEURAL removes artefacts only if REMOVE_ART is on
(preprocessing/resample_savemat.m: if(REMOVE_ART) ... end). The Python
version now does the same. remove_art=None (the default) reads REMOVE_ART
from NEURAL_parameters.py, which is 1; True and False override it.

Each test writes synthetic EEG from utils.gen_test_EEGdata (fixed seed) to an
EDF file in pytest's temporary folder. No real recordings are used.
"""
import mne
import numpy as np
import pandas as pd
import pytest

from NEURAL_py_EEG import NEURAL_parameters, preprocessing_EEG, utils

SEED = 2026
DURATION = 120  # seconds

# NEURAL's default EDF header uses physical minimum -5482.288 (9 characters);
# an EDF header field holds 8, so pyedflib warns and stores -5482.28.
# Expected, so not shown.
pytestmark = pytest.mark.filterwarnings("ignore:Physical minimum:UserWarning")


def write_edf(path, Fs, spikes=False, c3_c4_reference=False):
    """Write synthetic EEG (9 electrodes) to an EDF file and return its path.

    spikes: add three 300 uV one-sample spikes to F4. Each is a sudden jump
        (over 200 uV between samples), so remove_artefacts removes 0.5 s on
        each side of it, in every channel.
    c3_c4_reference: re-reference every electrode to the average of C3 and C4.
    """
    state = np.random.get_state()  # do not change numpy's random state for other tests
    np.random.seed(SEED)
    try:
        eeg = utils.gen_test_EEGdata(DURATION, Fs)["eeg_data_ref"]
    finally:
        np.random.set_state(state)
    if spikes:
        for second in (30, 60, 90):
            eeg.loc[second * Fs, "F4"] += 300
    if c3_c4_reference:
        eeg = eeg.sub((eeg["C3"] + eeg["C4"]) / 2, axis=0)
    utils.save_pd_as_edf(eeg, str(path), Fs=Fs)
    return path


def run(path, **kwargs):
    with mne.utils.use_log_level("WARNING"):  # only hides mne's progress messages
        return preprocessing_EEG.main_preprocessing(str(path), **kwargs)


def must_not_be_called(*args, **kwargs):
    raise AssertionError("remove_artefacts was called")


def all_nan_channels(eeg):
    return [name for name in eeg.columns if eeg[name].isna().all()]


def test_default_is_the_same_as_remove_art_true(tmp_path):
    path = write_edf(tmp_path / "spikes.edf", 256, spikes=True)

    default_data, default_removed = run(path)
    true_data, true_removed = run(path, remove_art=True)

    pd.testing.assert_frame_equal(default_data["eeg_data"], true_data["eeg_data"], check_exact=True)
    assert default_data["Fs"] == true_data["Fs"]
    assert default_data["ch_labels"] == true_data["ch_labels"]
    np.testing.assert_array_equal(default_removed[:4], true_removed[:4])
    np.testing.assert_array_equal(default_removed[4], true_removed[4])
    # artefacts were removed, so the comparison checks the removal path
    assert default_removed[3] > 0
    assert default_data["eeg_data"].isna().any().all()


def test_remove_art_false_skips_remove_artefacts(tmp_path, monkeypatch):
    path = write_edf(tmp_path / "spikes.edf", 256, spikes=True)
    monkeypatch.setattr(preprocessing_EEG, "remove_artefacts", must_not_be_called)

    data, amount_removed = run(path, remove_art=False)

    assert amount_removed is None
    assert not data["eeg_data"].isna().any().any()


def test_remove_art_0_in_parameters_skips_remove_artefacts(tmp_path, monkeypatch):
    path = write_edf(tmp_path / "spikes.edf", 256, spikes=True)
    neural_parameters = NEURAL_parameters.NEURAL_parameters

    def parameters_with_remove_art_off():
        params = neural_parameters()
        params["REMOVE_ART"] = 0
        return params

    monkeypatch.setattr(NEURAL_parameters, "NEURAL_parameters", parameters_with_remove_art_off)
    monkeypatch.setattr(preprocessing_EEG, "remove_artefacts", must_not_be_called)

    data, amount_removed = run(path)  # remove_art=None: use REMOVE_ART

    assert amount_removed is None
    assert not data["eeg_data"].isna().any().any()


def test_c3_c4_reference_at_200_hz(tmp_path):
    """With the C3/C4-average reference, C3 and C4 have a low mean correlation
    with the other electrodes, and every bipolar channel contains C3 or C4.
    So the referential check removes all 8 bipolar channels. Turning artefact
    removal off keeps them."""
    path = write_edf(tmp_path / "c3_c4_reference.edf", 200, c3_c4_reference=True)

    on_data, on_removed = run(path, remove_art=True)
    off_data, off_removed = run(path, remove_art=False)

    assert len(on_data["eeg_data"].columns) == 8
    assert all_nan_channels(on_data["eeg_data"]) == list(on_data["eeg_data"].columns)
    assert len(off_data["eeg_data"].columns) == 8
    assert all_nan_channels(off_data["eeg_data"]) == []
    assert off_removed is None
