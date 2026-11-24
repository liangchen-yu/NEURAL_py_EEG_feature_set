# Author:       Brian Murphy
# Date started: 30/01/2020
# Last updated: <25/07/2022 16:40:13 (BrianM)>

import math
import numpy as np
from NEURAL_py_EEG import utils
from NEURAL_py_EEG import NEURAL_parameters

# The spectral features that use params['freq_bands'] (one value per band),
# and those that use params['total_freq_bands'].
BAND_FEATURES = ("spectral_power", "spectral_relative_power", "spectral_flatness", "spectral_entropy",
                 "spectral_diff")
TOTAL_BAND_FEATURES = ("spectral_relative_power", "spectral_edge_frequency")


def check_band(low, high, Fs, name="frequency band"):
    """Raise ValueError unless the band [low, high] Hz has finite edges, its
    upper edge above its lower edge and below the Nyquist frequency Fs / 2.
    The reference package neural_eeg_features 0.6.1 rejects such bands before
    computing any feature (its config.Band and
    extraction._validate_recording_settings)."""
    if not (np.isfinite(low) and np.isfinite(high)):
        raise ValueError("%s [%g, %g] Hz: the edges must be finite numbers" % (name, low, high))
    if not high > low:
        raise ValueError("%s [%g, %g] Hz: the upper edge must be above the lower edge"
                         % (name, low, high))
    if not high < Fs / 2:
        raise ValueError("%s [%g, %g] Hz: the upper edge must be below the Nyquist frequency (%g Hz)"
                         % (name, low, high, Fs / 2))


def band_bins(low, high, n_fft, Fs):
    """Indices of the one-sided FFT bins in the closed frequency band
    [low, high] Hz, for an FFT of length n_fft at sampling frequency Fs: from
    ceil(low * n_fft / Fs) to floor(high * n_fft / Fs), inclusive, at most
    n_fft // 2 (the Nyquist bin) and at least 0. Two floating-point steps are
    allowed at each edge for roundoff in the multiplication and division.
    The band must satisfy check_band (ValueError otherwise). A narrow band can
    contain no bin: the result is then empty, and the features give NaN for
    that band, as in neural_eeg_features 0.6.1.

    Each band is an independent closed interval, as in neural_eeg_features
    0.6.1 (spectral.band_slice): adjacent bands share a bin that lies exactly
    on their common edge. Before, as in MATLAB NEURAL, each later band started
    at the previous band's last bin, which added a bin below the band when its
    lower edge was not on a bin, and filled gaps between disjoint bands.

    Example: band_bins(4, 7, 128, 64) -> [8, 9, ..., 14] (2 bins per Hz).
    """
    check_band(float(low), float(high), float(Fs))
    return _bins(low, high, n_fft, Fs)


def _bins(low, high, n_fft, Fs):
    """band_bins without check_band (for the total band in gen_spectrum, which
    only relative power and the spectral edge frequency use; they check it)."""
    low, high, n_fft, Fs = float(low), float(high), int(n_fft), float(Fs)
    first = math.ceil(math.nextafter(low * n_fft / Fs, -math.inf, steps=2))
    last = math.floor(math.nextafter(high * n_fft / Fs, math.inf, steps=2))
    return np.arange(max(first, 0), min(last, n_fft // 2) + 1)


# noinspection SpellCheckingInspection
def gen_spectrum(x, Fs, param_st, SCALE_PSD=0, total_band=True):
    """
    gen_spectrum: specturm using either:
                            1. periodogram
                            2. Welch's PSD
                            3. robust Welch PSD
    Syntax: pxx,itotal_bandpass,f_scale,Nfreq,fp = gen_spectrum(x,Fs,param_st,SCALE_PSD)
    Inputs:
        x             - input signal
        Fs            - sampling frequency (in Hz)
        param_st      - parameter structure (with window length, window type, overlap,
                        frequency bands, total frequency band, and method)
        SCALE_PSD     - scale PSD by factor of 2 (expect DC and Nyquist)? (0=no [default]
                        or 1=yes)
        total_band    - compute itotal_bandpass from param_st['total_freq_bands']
                        (True [default]; the band is checked with check_band first).
                        False for callers that do not use the total band, so that its
                        setting cannot affect them; itotal_bandpass is then NaN.
    Outputs:
        pxx              - spectral estimate (e.g. power spectral density)
        itotal_bandpass  - indices for total frequency band (defined in input args.;
                           NaN if there is none or total_band is False)
        f_scale          - frequency scaling factor
        Nfreq            - total length of pxx (including -ve frequencies)
        fp

    Example:
        import utils
        import spectral_features
        import matplotlib.pyplot as plt
        import numpy as np

        Fs = 64
        data_st = utils.gen_test_EEGdata(32, Fs, 1)
        x = data_st['eeg_data'][data_st['ch_labels'][0]].values

        param_st = dict()
        param_st['method'] = 'robust-PSD'
        param_st['L_window'] = 2
        param_st['window_type'] = 'hamm'
        param_st['overlap'] = 50
        param_st['freq_bands'] = [[0.5, 4], [4, 7], [7, 13], [13, 30]]
        param_st['total_freq_bands'] = [0.5, 30]

        [pxx,itotal_bandpass,~,~,fp]=spectral_features.gen_spectrum(x,Fs,param_st)

        plt.figure(1)
        plt.plot(fp, 10*np.log10(pxx))
        plt.plot([fp[itotal_bandpass[0]], fp[itotal_bandpass[0]]], [30, -30], 'k')
        plt.plot([fp[itotal_bandpass[-1]],  fp[itotal_bandpass[-1]]], [30, -30], 'k')
        plt.show()


    """
    L_window = param_st["L_window"]
    window_type = param_st["window_type"]
    overlap = param_st["overlap"]
    spec_method = param_st["method"].lower()

    # remove nans
    x = np.delete(x, np.where(np.isnan(x))[0])

    if spec_method == "bartlett-psd":
        # ---------------------------------------------------------------------
        # Bartlett PSD: same as Welch with 0 % overlap and rectangular window
        # ---------------------------------------------------------------------
        window_type = "rect"
        overlap = 0
        spec_method = "psd"

    if spec_method == "psd":
        # ---------------------------------------------------------------------
        # Welch PSD
        # ---------------------------------------------------------------------
        S_stft, Nfreq, f_scale, win_epoch = gen_STFT(
            x, L_window, window_type, overlap, Fs
        )
        pxx = np.nanmean(S_stft, 0)
        # N = len(pxx)

        # Normalise (so similar to pwelch)
        E_win = np.sum(np.abs(win_epoch) ** 2) / Nfreq
        pxx = pxx / (Nfreq * E_win * Fs)

    elif spec_method == "robust-psd":
        # ---------------------------------------------------------------------
        # Welch PSD with median instead of mean
        # ---------------------------------------------------------------------
        S_stft, Nfreq, f_scale, win_epoch = gen_STFT(
            x, L_window, window_type, overlap, Fs
        )
        pxx = np.nanmedian(S_stft, 0)
        # N = len(pxx) # Need to verify this

        # Normalise (so similar to pwelch)
        E_win = np.sum(np.abs(win_epoch) ** 2) / Nfreq
        pxx = pxx / (Nfreq * E_win * Fs)
    elif spec_method == "periodogram":
        # ---------------------------------------------------------------------
        # Periodogram
        # ---------------------------------------------------------------------
        X = np.abs(np.fft.fft(x)) ** 2

        # +ve frequencies only
        N = len(X)
        Nh = np.floor(N / 2).astype(int)
        X = X[range(Nh + 1)]
        Nfreq = N

        pxx = X / (Fs * N)

    else:
        raise ValueError(
            "Unknown spectral method - check spelling of: %s" % spec_method
        )

    if SCALE_PSD:
        pscale = np.ones(len(pxx)) + 1
        if Nfreq % 2 == 1:
            pscale[0] = 1
        else:
            pscale[0] = 1
            pscale[-1] = 1
        pxx = pxx * pscale

    N = len(pxx)
    f_scale = Nfreq / Fs
    fp = np.array(range(N)) / f_scale

    if total_band and "total_freq_bands" in param_st.keys():
        total_freq_bands = param_st["total_freq_bands"]

        # b) limit to frequency band of interest (checked first, as in band_bins):
        check_band(total_freq_bands[0], total_freq_bands[1], Fs, "spectral total_freq_bands")
        itotal_bandpass = _bins(total_freq_bands[0], total_freq_bands[1], Nfreq, Fs)
    else:
        itotal_bandpass = np.nan

    return pxx, itotal_bandpass, f_scale, Nfreq, fp


def gen_STFT(x, L_window, window_type, overlap, Fs, STFT_OR_SPEC=0):
    """
    gen_STFT: Short-time Fourier transform (or spectrogram)
    Syntax: S_stft,Nfreq,f_scale,win_epoch = spectral_features.gen_STFT(x,L_window,window_type,overlap,Fs)
    Inputs:
        x            - input signal
        L_window     - window length
        window_type  - window type
        overlap      - percentage overlap
        Fs           - sampling frequency (Hz)
        STFT_OR_SPEC - return short-time Fourier transform (STFT) or spectrogram
                   (0=spectrogram [default] and 1=STFT)
    Outputs:
        S_stft     - spectrogram
        Nfreq      - length of FFT
        f_scale    - frequency scaling factor
        win_epoch  - window

    Example:
        import utils
        import spectral_features
        import matplotlib.pyplot as plt

        Fs = 64
        data_st = utils.gen_test_EEGdata(32, Fs, 1)
        x = data_st['eeg_data'][data_st['ch_labels'][0]].values

        L_window = 2
        window_type = 'hamm'
        overlap = 80

        S_stft, dum, dum, dum = spectral_features.gen_STFT(x, L_window, window_type, overlap, Fs)

        plt.figure(1)
        plt.imshow(S_stft, origin='lower')
        plt.colorbar()
        plt.show()
        import utils
        import spectral_features
        import matplotlib.pyplot as plt
    """

    L_hop, L_epoch, win_epoch = utils.gen_epoch_window(
        overlap, L_window, window_type, Fs, 1
    )

    N = len(x)
    N_epochs = math.floor((N - (L_epoch - L_hop)) / L_hop)
    if N_epochs < 1:
        N_epochs = 1

    nw = np.array(range(L_epoch))
    Nfreq = L_epoch

    # ---------------------------------------------------------------------
    # generate short - time FT on all data:
    # ---------------------------------------------------------------------
    K_stft = np.zeros([N_epochs, L_epoch])
    for k in range(N_epochs):
        nf = np.array((nw + k * L_hop) % N).astype(
            int
        )  # matlab used k-1 as this index using just k here
        # to start with no initial shift
        K_stft[k][:] = x[nf] * win_epoch

    f_scale = Nfreq / Fs

    S_stft = np.empty([N_epochs, L_epoch])
    if STFT_OR_SPEC:
        S_stft = S_stft.astype(complex)
        for k in range(N_epochs):
            S_stft[k][:] = np.fft.fft(K_stft[k][:], Nfreq)
    else:
        for k in range(N_epochs):
            S_stft[k][:] = np.abs(np.fft.fft(K_stft[k, :], Nfreq)) ** 2

    S_stft = S_stft[:, np.array(range(np.floor(Nfreq / 2).astype(int) + 1))]

    return S_stft, Nfreq, f_scale, win_epoch


# noinspection SpellCheckingInspection,DuplicatedCode
def spectral_power(x, Fs, feat_name, params_st):
    """

    :param x: Epoch data
    :param Fs: Sampling frequency
    :param feat_name: Name of feature 'spectral_power' or 'spectral_relative_power'
    :param params_st: Parameters
    :return: feature value
    """
    freq_bands = params_st["freq_bands"]
    relative = feat_name == "spectral_relative_power"
    # Only relative power uses the total band: check it before any bin
    # arithmetic, and let absolute power ignore it.
    if relative and "total_freq_bands" in params_st:
        total = params_st["total_freq_bands"]
        check_band(total[0], total[1], Fs, "spectral total_freq_bands")
    params_st["method"] = "periodogram"
    pxx, itotal_bandpass, f_scale, N, fp = gen_spectrum(x, Fs, params_st, 1, total_band=relative)
    pxx = pxx * Fs

    if relative:
        # A total band with no bins gives NaN (as neural_eeg_features 0.6.1).
        if np.size(itotal_bandpass) == 0:
            pxx_total = np.nan
        else:
            pxx_total = np.nansum(pxx[itotal_bandpass]) / N
    else:
        pxx_total = 1

    spec_power = np.empty(len(freq_bands))
    spec_power.fill(np.nan)

    for p in range(len(freq_bands)):
        ibandpass = band_bins(freq_bands[p][0], freq_bands[p][1], N, Fs)
        if ibandpass.size == 0 or np.isnan(pxx_total):
            continue  # NaN: a band with no bins, or no total band

        spec_power[p] = np.nansum(pxx[ibandpass] / (N * pxx_total))

    return spec_power


# noinspection SpellCheckingInspection
def spectral_flatness(x, Fs, feat_name, params_st):
    """
    ---------------------------------------------------------------------
     spectral flatness (Wiener entropy)
    ---------------------------------------------------------------------
    :param x: Epoch data
    :param Fs: Sampling frequency
    :param feat_name: Name of feature
    :param params_st: Parameters
    :return: feature value
    """
    pxx, dum, f_scale, Nfreq, dum = gen_spectrum(x, Fs, params_st, total_band=False)

    # for each frequency band:
    freq_bands = params_st["freq_bands"]
    N_freq_bands = len(freq_bands)

    featx = np.empty(N_freq_bands)
    featx.fill(np.nan)
    for p in range(N_freq_bands):
        ibandpass = band_bins(freq_bands[p][0], freq_bands[p][1], Nfreq, Fs)
        if ibandpass.size == 0:
            continue  # NaN: a band with no bins

        featx[p] = np.exp(
            np.nanmean(np.log(pxx[ibandpass] + np.spacing(1)))
        ) / np.nanmean(pxx[ibandpass])

    return featx


def spectral_entropy(x, Fs, feat_name, params_st):
    """
    ---------------------------------------------------------------------
     spectral entropy (= Shannon entropy on normalised PSD)
    ---------------------------------------------------------------------
    :param x: Epoch data
    :param Fs: Sampling frequency
    :param feat_name: Name of feature
    :param params_st: Parameters
    :return: feature value
    """
    pxx, dum, f_scale, Nfreq, dum = gen_spectrum(x, Fs, params_st, total_band=False)

    # for each frequency band:
    freq_bands = params_st["freq_bands"]
    N_freq_bands = len(freq_bands)

    featx = np.empty(N_freq_bands)
    featx.fill(np.nan)
    for p in range(N_freq_bands):
        ibandpass = band_bins(freq_bands[p][0], freq_bands[p][1], Nfreq, Fs)
        if ibandpass.size == 0:
            continue  # NaN: a band with no bins

        pr = pxx[ibandpass] / np.nansum(pxx[ibandpass])

        featx[p] = -np.nansum(pr * np.log(pr + np.spacing(1))) / np.log(len(pr))

    return featx


def spectral_diff(x, Fs, feat_name, params_st):
    """
    ---------------------------------------------------------------------
     spectral difference using the spectrogram
    ---------------------------------------------------------------------
    For each frequency band, the spectrogram (windows of params_st['L_window']
    seconds, overlapping by params_st['overlap'] percent) is scaled by its
    largest value in the band. The result is the median, over the
    N_epochs - 1 pairs of consecutive windows, of the mean squared difference
    between the two windows' band spectra.

    NaN: a window with any NaN sample has an all-NaN spectrum; the
    differences that involve it are NaN and left out of the median. With no
    valid difference the result is NaN, with a numpy RuntimeWarning: a single
    window (with the defaults, any input shorter than 3 s, including inputs
    shorter than the 2 s window) gives "Mean of empty slice"; every window
    NaN gives "All-NaN slice encountered".

    :param x: Epoch data
    :param Fs: Sampling frequency
    :param feat_name: Name of feature
    :param params_st: Parameters
    :return: feature value
    """
    # a) generate spectrogram
    S_stft, Nfreq, f_scale, dum = gen_STFT(
        x, params_st["L_window"], params_st["window_type"], params_st["overlap"], Fs
    )

    N_epochs, M = S_stft.shape

    freq_bands = params_st["freq_bands"]
    N_freq_bands = len(freq_bands)

    featx = np.empty(N_freq_bands)
    featx.fill(np.nan)

    for p in range(N_freq_bands):
        ibandpass = band_bins(freq_bands[p][0], freq_bands[p][1], Nfreq, Fs)
        if ibandpass.size == 0:
            continue  # NaN: a band with no bins

        S_stft_band =S_stft[:, ibandpass] / np.nanmax(np.nanmax(S_stft[:, ibandpass]))

        # MATLAB commit a279ddd (2020-04-23): there are N_epochs - 1
        # differences between consecutive windows. Allocating N_epochs left one
        # unfilled 0 in the median, lowering the result. Changes default output.
        spec_diff = np.zeros(N_epochs - 1)
        for n in range(N_epochs - 1):
            v1 = S_stft_band[n, :]
            v2 = S_stft_band[n + 1, :]
            if all(np.isnan(v1)) or all(np.isnan(v2)):
                spec_diff[n] = np.nan
            else:
                spec_diff[n] = np.nanmean(np.abs(v1 - v2) ** 2)

        featx[p] = np.nanmedian(spec_diff)

    return featx


def spectral_edge_frequency(x, Fs, feat_name, params_st):
    """
    ---------------------------------------------------------------------
    spectral edge frequency
    ---------------------------------------------------------------------
    :param x: Epoch data
    :param Fs: Sampling frequency
    :param feat_name: Name of feature
    :param params_st: Parameters
    :return: feature value
    """
    if "total_freq_bands" in params_st:
        total = params_st["total_freq_bands"]
        check_band(total[0], total[1], Fs, "spectral total_freq_bands")
    pxx, itotal_bandpass, dum, dum, fp = gen_spectrum(x, Fs, params_st)

    # A total band with no bins gives NaN (as neural_eeg_features 0.6.1).
    if np.size(itotal_bandpass) == 0:
        return np.nan

    # only within this frequency band:
    pxx[np.setdiff1d(range(len(pxx)), itotal_bandpass)] = 0

    pxx = pxx / np.nansum(pxx)

    # compute the cumulative density
    pxx_cum = np.nancumsum(pxx)

    # spectral edge frequency corresponds to the frequency at (nearest to)
    # the point on the freq axis where pyy_cum = 0.05
    idx = np.argmin(np.abs(pxx_cum - params_st["SEF"]), axis=0)
    return fp[idx]


def main_spectral(x, Fs, feat_name, params=None):
    """
    Syntax: featx = spectral_features(x, Fs, feat_name, params)

    Inputs:
        x          - epoch of EEG data (size 1 x N)
        Fs         - sampling frequency (in Hz)
        feat_name  - feature type, defaults to 'spectral_power';
                     see full list of 'spectral_' features in params['FEATURE_SET_ALL']
        params  - parameters (as dictionary);
                     see NEURAL_parameters() for examples

    Outputs:
        featx  - feature at each frequency band

    Example:
        import utils
        import spectral_features
        Fs = 64
        data_st = utils.gen_test_EEGdata(32, Fs, 1)
        x = data_st['eeg_data'][data_st['ch_labels'][0]].values

        featx = spectral_features.main_spectral(x, Fs, 'spectral_relative_power')

    """
    if params is None:
        params = NEURAL_parameters.NEURAL_parameters()
        if "spectral" in params:
            params = params["spectral"]
        else:
            raise ValueError("No default parameters found")
    elif len(params) == 0:
        params = NEURAL_parameters.NEURAL_parameters()
        if "spectral" in params:
            params = params["spectral"]
        else:
            raise ValueError("No default parameters found")
    # Reject unusable bands before computing (as neural_eeg_features 0.6.1),
    # outside the try below, which reports every error as "Feature function
    # not found". Only the bands this feature uses are checked.
    if feat_name in BAND_FEATURES:
        for p, band in enumerate(params["freq_bands"]):
            check_band(band[0], band[1], Fs, "spectral freq_bands[%d]" % p)
    if feat_name in TOTAL_BAND_FEATURES and "total_freq_bands" in params:
        total = params["total_freq_bands"]
        check_band(total[0], total[1], Fs, "spectral total_freq_bands")

    try:
        if feat_name == "spectral_relative_power":
            featx = eval("spectral_power")(x, Fs, feat_name, params)
        else:
            featx = eval(feat_name)(x, Fs, feat_name, params)
    except:
        raise ValueError("Feature function not found: %s" % feat_name)

    return featx
