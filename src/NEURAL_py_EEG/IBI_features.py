# Author:       Brian Murphy
# Date started: 30/01/2020
# Last updated: <25/07/2022 16:40:13 (BrianM)>

from NEURAL_py_EEG import utils
import os
import numpy as np
import matplotlib.pyplot as plt
import sys
from pathlib import Path


def mat_percentile(x, q):
    """Pass in an array or list and return its q-th percentile, q in percent
    (MATLAB-style percentile, to mimic MATLAB's prctile). q can be a number
    or a list. Ignores NaN; all-NaN or empty input gives NaN.
    Units: same as input.

    >mat_percentile([1,2,3,4], 50)
    2.5
    """
    q = np.array(q) / 100
    x = np.delete(x, np.where(np.isnan(x))[0])
    n = len(x)
    if n == 0:
        return np.nan
    y = np.sort(x)
    return np.interp(q, np.linspace(1 / (2 * n), (2 * n - 1) / (2 * n), n), y)


def estimate_IBI_lengths(anno, percentiles_all, Fs):
    """Pass in a burst annotation (1 = burst, 0 = inter-burst) and return the
    given percentile(s) of the inter-burst interval lengths (IBI length).
    Gaps shorter than Fs/4 samples (0.25 s) are dropped; if none remain,
    returns array([0.]). A NaN sample ends a gap. Lengths come from
    utils.len_cont_zeros, which counts one sample fewer than each gap.
    Units: seconds.
    """
    min_ibi_interval = Fs / 4
    lens_anno = utils.len_cont_zeros(anno)[0]

    ishort = np.where(lens_anno < min_ibi_interval)[0]

    if ishort.size > 0:
        lens_anno = np.delete(lens_anno, ishort)

    # len() of this comparison is just the number of gaps, so this asks
    # whether any gaps are left.
    if len(lens_anno != 0):
        pc_anno = mat_percentile(lens_anno, percentiles_all)
    else:
        pc_anno = np.zeros(1)
    return pc_anno / Fs


def main_IBI(x, Fs, feat_name):
    """Return a burst / inter-burst interval (IBI) feature for one channel
    (assuming preterm EEG, <32 weeks GA).

    Syntax: featx = main_IBI(x, Fs, feat_name)

    Inputs:
        x          - EEG data for one channel (1-D array of N samples)
        Fs         - sampling frequency (in Hz)
        feat_name  - IBI feature to calculate, e.g. 'IBI_length_max';
                     see the 'IBI_' features in FEATURE_SET_ALL
                     (NEURAL_parameters.py)

    Outputs:
        featx  - feature value:
                 'IBI_length_max'     - 95th percentile IBI length (seconds)
                 'IBI_length_median'  - median IBI length (seconds)
                 'IBI_burst_prc'      - % of samples marked as burst
                                        (NaN samples count as not burst)
                 'IBI_burst_number'   - number of bursts
                 NaN if the burst detector is not found

    Note: needs the external burst detector [1] (eeg_burst_detector.py).
    Its folder is set in bdetect_path_string below; until that placeholder
    is edited, a message is printed and NaN is returned for every feat_name.
    An unknown feat_name raises ValueError only once the detector is found.

    Example:
        import sys
        sys.path.append('path to ->\\py_burst_detector-master\\')
        from burst_detector import utils as bdutils
        from NEURAL_py_EEG import IBI_features

        N = 5000
        Fs = 64
        x = bdutils.gen_impulsive_noise(N)

        featx = IBI_features.main_IBI(x,Fs,'IBI_burst_number');

    [1] JM O'Toole, GB Boylan, RO Lloyd, RM Goulding, S Vanhatalo,
    NJ Stevenson (2017). Detecting Bursts in the EEG of Very and Extremely
    Premature Infants using a Multi-Feature Approach. under review, 2017.
    """

    DBplot = 0

    # Placeholder: edit to the folder of the downloaded burst detector. Until
    # then the check below fails and every IBI feature returns NaN.
    bdetect_path_string = (
        "Enter path to ->" + "py_burst_detector-master/py_burst_detector-master/"
    )
    bdetect_path = Path(bdetect_path_string)

    bdetect_path_exist = os.path.isfile(
        Path(bdetect_path_string + "burst_detector/" + "eeg_burst_detector.py")
    )
    if not bdetect_path_exist:
        print("\n** ------------ **\n")
        print("Burst detector not included in path (eeg_burst_detector.py)\n\n")
        print("If installed, ensure eeg_burst_detector.py and associated files \n")
        print("are included in the python path.\n")
        print(
            "To do this, update the bdetect_path with the location of the burst detector.\n"
        )
        print("(for more on search paths see: ")
        print(
            [
                "<a href=https://docs.python.org/3/library/os.path.html>python os path</a>)\n\n"
            ]
        )
        print("If the burst detector is not installed, download from:\n")
        print(
            [
                "<a href=http://otoolej.github.io/code/py_burst_detector/> py burst detector source code </a>\n"
            ]
        )
        print("** ------------ **\n")

        return np.nan

    sys.path.append(str(bdetect_path))
    from burst_detector import eeg_burst_detector

    burst_anno, svm_out = eeg_burst_detector.eeg_bursts(x.copy(), Fs)

    if DBplot:
        plt.figure()
        ax1 = plt.subplot(2, 1, 1)
        plt.plot(x)
        plt.subplot(2, 1, 2, sharex=ax1)
        plt.plot(burst_anno)
        plt.ylim((-0.2, 1.2))

    if feat_name == "IBI_length_max":
        """
        ---------------------------------------------------------------------
        max. (95th percentile) inter-burst interval
        ---------------------------------------------------------------------
        """
        return estimate_IBI_lengths(burst_anno, 95, Fs)

    elif feat_name == "IBI_length_median":
        """
        ---------------------------------------------------------------------
        median inter-burst interval
        ---------------------------------------------------------------------
        """
        return estimate_IBI_lengths(burst_anno, 50, Fs)

    elif feat_name == "IBI_burst_prc":
        """
        ---------------------------------------------------------------------
        percentage of bursts
        ---------------------------------------------------------------------
        """
        return (np.nansum(burst_anno) / burst_anno.size) * 100

    elif feat_name == "IBI_burst_number":
        """
        ---------------------------------------------------------------------
        number of bursts
        ---------------------------------------------------------------------
        """
        return utils.len_cont_zeros(burst_anno, 1)[0].size

    else:
        raise ValueError('\n Unknown feature "%s"; check spelling\n' % feat_name)
