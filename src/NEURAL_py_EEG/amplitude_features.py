# Author:       Brian Murphy
# Date started: 30/01/2020
# Last updated: <25/07/2022 16:40:13 (BrianM)>

import numpy as np
from scipy import signal
from scipy import stats
from NEURAL_py_EEG import utils
from NEURAL_py_EEG import NEURAL_parameters


def amplitude_total_power(data):
    """Pass in an array or list and return the signal power (average of the
    squared values). Ignores NaN. Units: input units squared.

    >amplitude_total_power([3,7,8,9,1])
    40.8
    """
    return np.nanmean(np.abs(data) ** 2)


def amplitude_env_mean(data):
    """Pass in an array or list and return the average power of the signal's
    envelope, its smooth outline (squared Hilbert envelope). Any NaN gives NaN.
    Units: input units squared.

    >amplitude_env_mean([3,7,8,9,1])
    50.24
    """
    squared_envelope = np.abs(signal.hilbert(data)) ** 2
    return np.nanmean(squared_envelope)


def amplitude_SD(data):
    """Pass in an array or list and return how much the signal spreads around
    its average (sample standard deviation). Ignores NaN. Units: same as input.

    >amplitude_SD([3,7,8,9,1])
    3.4351
    """
    return np.nanstd(data, ddof=1)


def amplitude_env_SD(data):
    """Pass in an array or list and return how much the envelope power varies
    (sample SD of the squared envelope). Any NaN gives NaN.
    Units: input units squared.

    >amplitude_env_SD([3,7,8,9,1])
    32.8035
    """
    squared_envelope = np.abs(signal.hilbert(data)) ** 2
    return np.nanstd(squared_envelope, ddof=1)


def amplitude_skew(data):
    """Pass in an array or list and return how lopsided the values are;
    0 = symmetric (absolute skewness). Ignores NaN. No units.

    >amplitude_skew([3,7,8,9,1])
    0.4071
    """
    return np.abs(stats.skew(data, nan_policy="omit"))


def amplitude_kurtosis(data):
    """Pass in an array or list and return how spiky / heavy-tailed the signal
    is; 3 = normal (Pearson kurtosis). Any NaN gives NaN. No units.

    >amplitude_kurtosis([3,7,8,9,1])
    1.4904
    """
    return stats.kurtosis(data, fisher=False)


def main_amplitude(x, Fs, feat_name, params=None):
    """Return an amplitude feature for each configured frequency band.

    Syntax: band_features = main_amplitude(x, Fs, feat_name, params)

    Inputs:
        x          - epoch of EEG data (1-D array of N samples)
        Fs         - sampling frequency (in Hz)
        feat_name  - amplitude feature to calculate, e.g. 'amplitude_total_power';
                     see the 'amplitude_' features in FEATURE_SET_ALL
                     (NEURAL_parameters.py)
        params     - amplitude settings (dictionary); None or empty uses the
                     NEURAL defaults. Reads 'freq_bands' and
                     'FILTER_REPLACE_ARTEFACTS'

    Outputs:
        band_features  - feature value for each frequency band
                         (one unfiltered value if 'freq_bands' is empty)

    Note: NaN samples are removed after band filtering (if any), before the
    feature is calculated.

    Example:
        from NEURAL_py_EEG import utils
        from NEURAL_py_EEG import amplitude_features

        Fs = 64
        data_st = utils.gen_test_EEGdata(32, Fs, 1)
        x = data_st['eeg_data'][data_st['ch_labels'][0]].values

        featx = amplitude_features.main_amplitude(x, Fs, 'amplitude_env_mean')
    """
    if params is None:
        params = NEURAL_parameters.NEURAL_parameters()
        if "amplitude" in params:
            params = params["amplitude"]
        else:
            raise ValueError("No default parameters found")
    elif len(params) == 0:
        params = NEURAL_parameters.NEURAL_parameters()
        if "amplitude" in params:
            params = params["amplitude"]
        else:
            raise ValueError("No default parameters found")

    frequency_bands = params["freq_bands"]

    band_count = len(frequency_bands)
    if band_count == 0:
        band_count = 1

    # Filters can fill gaps in place; each band needs the original samples.
    filter_input = x.copy()

    band_features = np.empty(band_count)
    for band_index in range(band_count):
        if not len(frequency_bands) == 0:
            # The filter API expects the upper cutoff before the lower cutoff.
            band_samples, ignored_nan_indices = utils.filter_butterworth_withnans(
                filter_input,
                Fs,
                frequency_bands[band_index][1],
                frequency_bands[band_index][0],
                5,
                params["FILTER_REPLACE_ARTEFACTS"],
            )
            filter_input = x.copy()
        else:
            band_samples = x.copy()

        try:
            band_samples = np.delete(band_samples, np.where(np.isnan(band_samples))[0])
            band_features[band_index] = eval(feat_name)(band_samples)
        except:
            raise ValueError("Feature function not found: %s" % feat_name)

    return band_features
