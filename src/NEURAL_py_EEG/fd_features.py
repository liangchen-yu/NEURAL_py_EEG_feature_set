# Author:       Brian Murphy
# Date started: 30/01/2020
# Last updated: <25/07/2022 16:40:13 (BrianM)>

import numpy as np
from NEURAL_py_EEG import utils
from NEURAL_py_EEG import NEURAL_parameters


def fd_higuchi(x, kmax="Nope"):
    """Pass in a NumPy array and return how rough or complex the signal is
    (Higuchi fractal dimension, [1] in main_fd): about 1 for a smooth line,
    about 2 for white noise. kmax is the largest scale k, in samples; if not
    given, it is len(x) / 10 rounded down. Differences that involve NaN are
    left out of the curve lengths. No units.

    >fd_higuchi(np.sin(np.arange(1000) / 20), 6)
    1.0033
    """
    sample_count = len(x)
    if kmax == "Nope":
        kmax = int(np.floor(len(x) / 10))

    # what value of k to compute
    # Past k = 4 the scales grow roughly geometrically (5, 6, 8, 9, 11, ...),
    # so they spread evenly on the log-log plot below.
    k_step = 1
    k_all = np.empty(0)
    candidate_k = 0

    while candidate_k < kmax:
        if k_step <= 4:
            candidate_k = k_step
        else:
            candidate_k = np.floor(2 ** ((k_step + 5) / 4))

        if candidate_k <= kmax:
            k_all = np.append(k_all, candidate_k)
        k_step = k_step + 1

    """
    ---------------------------------------------------------------------
    curve length for each vector:
    ---------------------------------------------------------------------
    """

    # k (scale) and m (start offset) follow Higuchi's notation [1].
    k_position = 0
    mean_curve_lengths = np.zeros(len(k_all))

    for k in k_all:
        curve_lengths = np.zeros(k.astype(int))
        for m in range(k.astype(int)):
            interval_indices = np.array(
                range(1, np.floor((sample_count - m - 1) / k).astype(int) + 1)
            )
            scale_factor = (sample_count - 1) / (
                np.floor((sample_count - m - 1) / k) * k
            )
            curve_lengths[m] = np.nansum(
                np.abs(
                    x[m + np.array(interval_indices) * k.astype(int)]
                    - x[m + (interval_indices - 1) * k.astype(int)]
                )
            ) * (scale_factor / k)

        mean_curve_lengths[k_position] = np.nanmean(curve_lengths)
        k_position += 1

    """
    -------------------------------------------------------------------
     form log-log plot of scale v. curve length
    -------------------------------------------------------------------
    """

    log_k = np.log2(k_all)
    log_curve_length = np.log2(mean_curve_lengths)
    line_coefficients = np.polyfit(log_k, log_curve_length, 1)
    fractal_dimension = -line_coefficients[0]

    # y_fit = line_coefficients[0]*log_k + line_coefficients[1]
    # y_residuals = log_curve_length - y_fit
    # r2 = 1 - np.sum(y_residuals**2) / ((sample_count-1) * np.var(log_curve_length))

    # return fractal_dimension, r2, k_all, mean_curve_lengths
    return fractal_dimension


def fd_katz(x, dum=0):

    """Pass in an array or list and return how rough or complex the signal is
    (Katz fractal dimension, [2] in main_fd). Each sample step counts as 1
    unit of distance, so the result changes with the amplitude scale. The
    second argument is ignored; it lets main_fd call both methods the same
    way. Any NaN gives NaN. No units.

    >fd_katz([3,7,8,9,1])
    2.3875
    """
    N = len(x)
    p = N - 1

    # 1. line-length
    L = np.empty(N - 1)
    for n in range(N - 1):
        L[n] = np.sqrt(1 + (x[n] - x[n + 1]) ** 2)

    L = np.sum(L)

    # 2. maximum distance
    d = np.zeros(p)
    for n in range(N - 1):
        d[n] = np.sqrt((n + 1) ** 2 + (x[0] - x[n + 1]) ** 2)

    d = np.max(d)

    D = np.log(p) / (np.log(d / L) + np.log(p))

    return D


def main_fd(x, fs, feat_name="fd_higuchi", params=None):
    """Return the fractal dimension (FD) of a signal for each frequency band.

    Syntax: band_features = main_fd(x, fs, feat_name, params)

    Inputs:
        x          - epoch of EEG data (1-D array of N samples)
        fs         - sampling frequency (in Hz)
        feat_name  - 'FD' (the name in FEATURE_SET_ALL, NEURAL_parameters.py)
                     uses params['method']: 'higuchi' or 'katz' (missing
                     or None means 'higuchi'); 'fd_higuchi' (default) or
                     'fd_katz' choose directly
        params     - FD settings (dictionary); None or empty uses the NEURAL
                     defaults. Reads 'freq_bands', 'FILTER_REPLACE_ARTEFACTS',
                     'qmax' (kmax, read only for fd_higuchi) and, for 'FD',
                     'method'

    Outputs:
        band_features  - fractal dimension for each frequency band
                         (one value if 'freq_bands' is empty)

    Note: as in MATLAB fd_features.m, each row of 'freq_bands' is one band,
    with column 0 as the low and column 1 as the high cutoff; a single
    [low, high] pair (default 0.5-30 Hz) is one band. Every band is filtered
    from the original x. Empty 'freq_bands' gives one value from the
    unfiltered x.
    main_fd accepts any of these shapes; generate_all_features' column
    naming (generate_all_features.feature_band_edges) supports a flat list
    (a [low, high] pair, or a longer list such as [0.5, 4, 30], which works
    but uses only its first two values) or a list of one or more
    [low, high] bands; it fails for [].
    A missing or None params['method'] selects Higuchi, as main_fd did
    before it read 'method'. Results can still differ from that older code
    where the band handling changed (e.g. 4 bands now give 4 values, not 2).
    'method' must otherwise be the string 'higuchi' or 'katz'; any other
    value or type (array, list, number) raises ValueError (MATLAB's
    otherwise-branch was not run, so it is not matched).
    NaN samples are not removed: NaNs left after filtering are skipped by
    fd_higuchi and make fd_katz return NaN; the 'zeros' and interpolation
    modes fill gaps during filtering.

    Example:
        from NEURAL_py_EEG import utils
        from NEURAL_py_EEG import fd_features

        Fs = 64
        data_st = utils.gen_test_EEGdata(32, Fs, 1)
        x = data_st['eeg_data'][data_st['ch_labels'][0]].values

        featx = fd_features.main_fd(x, Fs)

    [1] T Higuchi, "Approach to an irregular time series on the basis of the
    fractal theory," Phys. D Nonlinear Phenom., vol. 31, pp. 277-283, 1988.

    [2] MJ Katz, Fractals and the analysis of waveforms. Computers in Biology
    and Medicine, vol. 18, no. 3, pp. 145-156. 1988
    """
    if params is None:
        params = NEURAL_parameters.NEURAL_parameters()
        if "FD" in params:
            params = params["FD"]
        else:
            raise ValueError("No default parameters found")
    elif len(params) == 0:
        params = NEURAL_parameters.NEURAL_parameters()
        if "FD" in params:
            params = params["FD"]
        else:
            raise ValueError("No default parameters found")

    # As in MATLAB, the generic name 'FD' takes its method from the settings.
    if feat_name == "FD":
        # Missing or None means Higuchi, as before 'method' was read.
        # Only None or a str: == on an array or list would not give a plain bool.
        method = params.get("method")
        if method is None or (isinstance(method, str) and method == "higuchi"):
            feat_name = "fd_higuchi"
        elif isinstance(method, str) and method == "katz":
            feat_name = "fd_katz"
        else:
            raise ValueError(
                "Unknown FD method: %r (use 'higuchi' or 'katz')" % (method,)
            )

    # One band per row, like MATLAB's size(freq_bands, 1): a flat list is one
    # row, and only its first two numbers are used as cutoffs.
    frequency_bands = np.atleast_2d(np.array(params["freq_bands"]))
    band_count = frequency_bands.shape[0]
    if frequency_bands.size == 0:
        band_count = 1

    band_features = np.empty(band_count)
    for band_index in range(band_count):
        # Filters can fill NaN gaps in place, so each band starts from a fresh
        # copy of x: bands stay independent and the caller's x is unchanged.
        band_samples = x.copy()
        if frequency_bands.size > 0:
            low_cutoff = frequency_bands[band_index, 0]
            high_cutoff = frequency_bands[band_index, 1]
            # The filter API expects the upper cutoff before the lower cutoff.
            band_samples, ignored_nan_indices = utils.filter_butterworth_withnans(
                band_samples,
                fs,
                high_cutoff,
                low_cutoff,
                5,
                params["FILTER_REPLACE_ARTEFACTS"],
            )

        try:
            # Only Higuchi takes kmax; Katz gets x alone (MATLAB line 71).
            feature_args = (params["qmax"],) if feat_name == "fd_higuchi" else ()
            band_features[band_index] = eval(feat_name)(band_samples, *feature_args)
        except:
            raise ValueError("Feature function not found: %s" % feat_name)

    return band_features
