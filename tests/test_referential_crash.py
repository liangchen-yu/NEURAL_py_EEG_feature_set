"""remove_artefacts without referential data.

MATLAB remove_artefacts.m can be called without referential data: it then
skips its first check (low correlation between referential channels) and runs
the others. Its electrode-coupling check sizes its work array from the bipolar
channels (line 111, zeros(N_channels,N)). The Python version sized that array
from the referential data, so with none (an empty DataFrame) the coupling
check stopped with IndexError whenever it ran: more than 4 bipolar channels,
at least 2 on each side.

These tests check that:
- such a call now runs, and the coupling check still does its job;
- when the referential check would have removed nothing, skipping it gives
  exactly the same cleaned data;
- with referential data, results are unchanged (values made with the code
  before the fix, compared with the suite's tolerance).

Synthetic inputs only (tests/synthetic_edf.py), 120 s at 256 Hz.
"""
import contextlib
import io

import numpy as np
import pandas as pd
import pytest

import neural_outputs
import synthetic_edf
from NEURAL_py_EEG import preprocessing_EEG, utils

pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")

FS = synthetic_edf.FS
SECONDS = 120
READER_ORDER = ["F3", "F4", "C3", "C4", "O1", "O2", "T3", "T4", "Cz"]  # as NEURAL's EDF reader
# 3 left and 2 right bipolar channels: the coupling check runs (more than 4, at least 2 per side)
FIVE = ["C3_O1", "C3_T3", "F3_C3", "C4_O2", "F4_C4"]
# NaN already in the referential data: (electrode, first sample, last sample + 1)
NAN_RUNS = [("C3", 50 * FS, 52 * FS), ("T4", 60 * FS, 70 * FS), ("O2", 0, FS)]


def inputs(case, with_nans=False):
    """Referential and bipolar EEG (uV) for one synthetic recording."""
    signals = synthetic_edf.make_signals(case)[:, :SECONDS * FS]
    ref = pd.DataFrame({e: signals[synthetic_edf.ELECTRODES.index(e)] / 10.0 for e in READER_ORDER})
    if with_nans:
        for electrode, start, stop in NAN_RUNS:
            ref.loc[start:stop - 1, electrode] = np.nan
    return ref, utils.set_bi_montage(ref, FS)[0]


def remove(bipolar, referential):
    with contextlib.redirect_stdout(io.StringIO()):
        cleaned, removed = preprocessing_EEG.remove_artefacts(
            bipolar.copy(), np.array(list(bipolar.columns)), FS,
            referential, np.array(list(referential.columns)))
    return cleaned, removed


def removed_channels(removed):
    return [] if isinstance(removed[4], str) else sorted(str(c) for c in removed[4])


def test_eight_channels_without_referential_data():
    """Failed with IndexError before the fix. In this recording Cz is shorted
    to C4, so the coupling check must still remove C4_Cz; the loose F4, which
    only the skipped referential check finds, stays in."""
    ref, bip = inputs("artefacts")
    cleaned, removed = remove(bip, pd.DataFrame())
    assert list(cleaned.columns) == list(bip.columns)
    assert removed_channels(removed) == ["C4_Cz"]
    assert cleaned["C4_Cz"].isna().all()
    assert not cleaned["F4_C4"].isna().all()


def test_five_channels_without_referential_data():
    """3 left and 2 right channels: the coupling check runs. Failed with
    IndexError before the fix."""
    ref, bip = inputs("artefacts")
    cleaned, removed = remove(bip[FIVE].copy(), pd.DataFrame())
    assert list(cleaned.columns) == FIVE
    assert not cleaned.isna().all().any()


@pytest.mark.parametrize("with_nans", [False, True], ids=["no NaN", "NaN in the data"])
@pytest.mark.parametrize("channels", [None, FIVE], ids=["8 channels", "5 channels"])
def test_same_as_a_referential_check_that_removes_nothing(channels, with_nans):
    """In the clean recording the referential check removes no channel, so
    skipping it must give exactly the same cleaned data."""
    ref, bip = inputs("clean", with_nans)
    if channels:
        bip = bip[channels].copy()
    with_check, removed = remove(bip, ref.copy())
    assert removed_channels(removed) == []
    without_check, _ = remove(bip, pd.DataFrame())
    pd.testing.assert_frame_equal(without_check, with_check, check_exact=True)


# Made with the code before the fix (commit 6e7d343) on the inputs below:
# per bipolar channel, the number of NaN samples and the sum and sum of squares
# of the other samples; and the channels removed.
BEFORE_FIX = {
    'clean, no NaN, 8 channels': {
        "removed": [],
        "channels": {
            'C3_O1': [0, -8535.8, 15384937.98],
            'C4_O2': [0, 2679.699999999999, 17202378.63],
            'Cz_C3': [0, 8197.400000000001, 9696836.120000001],
            'C4_Cz': [0, -8783.499999999998, 10935679.77],
            'C3_T3': [0, -3278.099999999995, 14259389.63],
            'C4_T4': [0, -11146.600000000002, 16500203.100000001],
            'F3_C3': [0, -3658.2000000000007, 14121107.56],
            'F4_C4': [0, -1214.9999999999964, 16040823.959999999],
        },
    },
    'clean, no NaN, 5 channels': {
        "removed": [],
        "channels": {
            'C3_O1': [0, -8535.8, 15384937.98],
            'C3_T3': [0, -3278.099999999995, 14259389.63],
            'F3_C3': [0, -3658.2000000000007, 14121107.56],
            'C4_O2': [0, 2679.699999999999, 17202378.63],
            'F4_C4': [0, -1214.9999999999964, 16040823.959999999],
        },
    },
    'clean, NaN, 8 channels': {
        "removed": [],
        "channels": {
            'C3_O1': [386, -9130.499999999998, 14948500.369064327],
            'C4_O2': [386, 7222.099999999997, 16706618.21],
            'Cz_C3': [386, 5456.999999999998, 9444052.447030539],
            'C4_Cz': [386, -4141.300000000003, 10652426.07],
            'C3_T3': [386, -3963.999999999999, 13881139.230461339],
            'C4_T4': [386, -22332.6, 15605816.932010932],
            'F3_C3': [386, -4858.1, 13756436.42248863],
            'F4_C4': [386, -7133.200000000001, 15654062.120000001],
        },
    },
    'clean, NaN, 5 channels': {
        "removed": [],
        "channels": {
            'C3_O1': [386, -9130.499999999998, 14948500.369064327],
            'C3_T3': [386, -3963.999999999999, 13881139.230461339],
            'F3_C3': [386, -4858.1, 13756436.42248863],
            'C4_O2': [386, 7222.099999999997, 16706618.21],
            'F4_C4': [386, -7133.200000000001, 15654062.120000001],
        },
    },
    'artefacts, no NaN, 8 channels': {
        "removed": ['C4_Cz', 'F4_C4'],
        "channels": {
            'C3_O1': [6270, 1584.0, 11290315.28],
            'C4_O2': [6270, 13553.5, 12383665.21],
            'Cz_C3': [6270, 3998.999999999998, 4541397.040000001],
            'C4_Cz': [30720, 0.0, 0.0],
            'C3_T3': [6270, 10197.599999999997, 10519789.42],
            'C4_T4': [6270, 5352.099999999995, 12236198.829999998],
            'F3_C3': [6270, -6344.9000000000015, 10263936.190000001],
            'F4_C4': [30720, 0.0, 0.0],
        },
    },
    'artefacts, no NaN, 5 channels': {
        "removed": ['F4_C4'],
        "channels": {
            'C3_O1': [897, -7958.099999999997, 14651560.65],
            'C3_T3': [897, -6280.699999999995, 13510826.75],
            'F3_C3': [897, -8657.000000000004, 13437220.92],
            'C4_O2': [897, 4668.100000000001, 16216956.85],
            'F4_C4': [30720, 0.0, 0.0],
        },
    },
    'artefacts, NaN, 8 channels': {
        "removed": ['C4_Cz', 'F4_C4'],
        "channels": {
            'C3_O1': [6270, -585.2000000000007, 11163941.619064327],
            'C4_O2': [6270, 13553.5, 12383665.21],
            'Cz_C3': [6270, -2041.699999999999, 4595391.305451592],
            'C4_Cz': [30720, 0.0, 0.0],
            'C3_T3': [6270, 9823.6, 10387023.470461339],
            'C4_T4': [6270, -9847.7, 11764544.702010933],
            'F3_C3': [6270, -3345.4000000000033, 10163982.212488629],
            'F4_C4': [30720, 0.0, 0.0],
        },
    },
    'artefacts, NaN, 5 channels': {
        "removed": ['F4_C4'],
        "channels": {
            'C3_O1': [1409, -6952.9, 14495162.830000002],
            'C3_T3': [1409, -7038.699999999996, 13377058.370000001],
            'F3_C3': [1409, -8780.7, 13313965.39],
            'C4_O2': [1409, 5277.899999999997, 16067368.41],
            'F4_C4': [30720, 0.0, 0.0],
        },
    },
}


def fingerprint(cleaned, removed):
    channels = {}
    for name in cleaned.columns:
        x = cleaned[name].to_numpy(dtype=float)
        ok = x[~np.isnan(x)]
        channels[str(name)] = [int(np.isnan(x).sum()), float(ok.sum()), float((ok ** 2).sum())]
    return {"channels": channels, "removed": removed_channels(removed)}


CASES = [(case, with_nans, channels) for case in ("clean", "artefacts")
         for with_nans in (False, True) for channels in ("8", "5")]


@pytest.mark.parametrize("case, with_nans, channels", CASES)
def test_with_referential_data_unchanged(case, with_nans, channels):
    ref, bip = inputs(case, with_nans)
    if channels == "5":
        bip = bip[FIVE].copy()
    new = fingerprint(*remove(bip, ref.copy()))
    old = BEFORE_FIX["%s, %s, %s channels" % (case, "NaN" if with_nans else "no NaN", channels)]
    assert new["removed"] == old["removed"]
    assert list(new["channels"]) == list(old["channels"])
    for name, (nan_count, total, squares) in old["channels"].items():
        assert new["channels"][name][0] == nan_count, name
        neural_outputs.compare(new["channels"][name][1:], [total, squares], case, "referential crash fix",
                               "%s sum, sum of squares" % name)
