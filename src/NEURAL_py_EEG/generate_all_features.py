# Author:       Brian Murphy
# Date started: 30/01/2020
# Last updated: <25/07/2022 16:40:13 (BrianM)>

from NEURAL_py_EEG import amplitude_features
from NEURAL_py_EEG import spectral_features
from NEURAL_py_EEG import connectivity_features
from NEURAL_py_EEG import rEEG
from NEURAL_py_EEG import fd_features
from NEURAL_py_EEG import utils
import copy
import numpy as np
import pandas as pd
from NEURAL_py_EEG import IBI_features
from NEURAL_py_EEG import NEURAL_parameters


def size_feature(feat_name, params=None):
    """
    size_feature: size of feature (e.g. array or 1 point)

    Syntax: N = size_feature(feat_name, params)

    Inputs:
        feat_name - feature name (e.g. 'spectral_power')
        params    - settings, as returned by NEURAL_parameters() (default:
                    None, which uses NEURAL_parameters())

    Outputs:
        N - number of frequency bands

    Example:
        import generate_all_features
        N = generate_all_features.size_feature('spectral_power')
        print('Feature has %d frequency bands\n' % N)

    :param feat_name:  feature name (e.g. 'spectral_power')
    :param params: settings (default None: NEURAL_parameters())
    :return: N - number of frequency bands
    """

    if params is None:
        params = NEURAL_parameters.NEURAL_parameters()
    feat_group = feat_name.split("_")

    feat_group = feat_group[0]

    if feat_group == "IBI":
        return 1

    if feat_name == "spectral_edge_frequency":
        # ---------------------------------------------------------------------
        # SPECIAL cases
        # ---------------------------------------------------------------------
        N = 1
    else:
        # ---------------------------------------------------------------------
        # feature set is size number of frequency bands
        # ---------------------------------------------------------------------
        bands = np.array(params[feat_group]["freq_bands"])
        if bands.ndim == 1:
            N = 1
        else:
            N = bands.shape[0]

    return N


# The feature groups computed per epoch (IBI uses the whole recording).
EPOCH_GROUPS = ("spectral", "amplitude", "rEEG", "FD", "connectivity")


def epoch_count(N, Fs, L_window, overlap=50, window_type="rect"):
    """
    Number of complete epochs in N samples: (N - L_epoch) // L_hop + 1, or 0
    if N < L_epoch, with the epoch length L_epoch and hop L_hop of
    utils.gen_epoch_window. As in neural_eeg_features 0.6.1, trailing data
    shorter than an epoch do not make another (NaN-padded) epoch.
    overlap_epochs and get_max_num_epochs both use it (same hop, same rule),
    so the preallocated rows always equal the epochs.

    :param N: number of samples
    :param Fs: sampling frequency (Hz)
    :param L_window: epoch length (seconds)
    :param overlap: overlap (percent)
    :param window_type: window type (sets the hop; overlap_epochs' default 'rect')
    :return: number of epochs
    """
    L_hop, L_epoch, dum = utils.gen_epoch_window(overlap, L_window, window_type, Fs)
    if N < L_epoch:
        return 0
    return int((N - L_epoch) // L_hop) + 1


def shorter_than_one_epoch(N, Fs, L_window, overlap=50, window_type="rect"):
    """The ValueError for a recording of N samples shorter than one epoch."""
    L_hop, L_epoch, dum = utils.gen_epoch_window(overlap, L_window, window_type, Fs)
    return ValueError(
        "Recording is shorter than one analysis epoch: %d samples (%g s at %g Hz); "
        "an epoch is %d samples (EPOCH_LENGTH = %g s)" % (N, N / Fs, Fs, L_epoch, L_window)
    )


def overlap_epochs(x, Fs, L_window, overlap=50, window_type="rect"):
    """
        ---------------------------------------------------------------------
        overlapping epochs in one matrix
        ---------------------------------------------------------------------
    Complete epochs only (epoch_count), as in neural_eeg_features 0.6.1:
    epoch k holds samples k * L_hop to k * L_hop + L_epoch - 1; trailing
    samples that do not fill another epoch are not used. Before, a final
    epoch was padded with NaN. A recording shorter than one epoch raises
    ValueError (shorter_than_one_epoch).

    :param x:
    :param Fs:
    :param L_window:
    :param overlap:
    :param window_type:
    :return:
    """

    L_hop, L_epoch, win_epoch = utils.gen_epoch_window(
        overlap, L_window, window_type, Fs
    )
    N = len(x)
    N_epochs = epoch_count(N, Fs, L_window, overlap, window_type)
    if N_epochs < 1:
        raise shorter_than_one_epoch(N, Fs, L_window, overlap, window_type)

    nw = np.array(list(range(L_epoch)))

    x_epochs = np.empty([N_epochs, L_epoch])

    # Preserve pandas < 3 position/label indexing for x[nf].
    x = utils.index_like_pandas2(x)
    for k in range(N_epochs):
        nf = nw + k * L_hop
        x_epochs[k, :] = x[nf] * win_epoch

    return x_epochs


def generate_all_features(data, save_p_l=None, channel_names=None, feat_set=None, params=None):
    """
    Syntax: feat_st = generate_all_features(data, save_path, channel_names, feat_set, params)

    Inputs:
        data          - either EEG filename or data dictionary with EEG
                         e.g. data dictionary: data_st = utils.gen_test_EEGdata(5*60, 64, 1)
        channel_names  - channel labels to process (default, process all)
                         e.g. ['C3-O1','C4-O2','F3-C3','F4-C4']
        feat_set       - list of features to compute,
                         e.g. ['spectral_relative_power','rEEG_CV', 'connectivity_BSI'];
                         a name in NEURAL_parameters.REMOVED_FEATURES, or any other name
                         not in NEURAL_parameters.SUPPORTED_FEATURES, raises ValueError
        params         - settings: a dictionary like NEURAL_parameters() returns,
                         e.g. params = NEURAL_parameters.NEURAL_parameters();
                         params['EPOCH_LENGTH'] = 32. Default None: NEURAL_parameters().
                         It must have the same keys at every level and the same
                         kinds of value (NEURAL_parameters.check_parameters raises
                         ValueError naming the setting otherwise). It is not changed;
                         each feature function gets its own copy of its group's
                         settings (params['spectral'], params['amplitude'],
                         params['rEEG'], params['FD'], params['connectivity']).
                         The epoch settings are params['EPOCH_LENGTH'],
                         ['EPOCH_OVERLAP'] and ['EPOCH_IGNORE_PRC_NANS'].
                         params['FEATURE_SET_ALL'] is the feature set when feat_set
                         is None; a given feat_set decides both the features computed
                         and the columns (FEATURE_SET_ALL then only orders them, see
                         get_feature_names). Not read here: LP_fc, REMOVE_ART and
                         ART_*, which preprocessing_EEG takes from NEURAL_parameters();
                         Fs_new, BI_MONT, EEG_DATA_DIR and EEG_DATA_DIR_CSV, which
                         nothing reads (main_preprocessing's Fs_new argument and
                         utils.set_bi_montage's montage have their own defaults); and
                         the top-level FREQ_BANDS and FILTER_REPLACE_ARTEFACTS, which
                         only set the groups' defaults in NEURAL_parameters(): to
                         change the bands or the NaN handling of a group, change
                         its own 'freq_bands' or 'FILTER_REPLACE_ARTEFACTS'.
                         Each band of a feature gets its own column (see
                         feature_column_names); two bands with the same edges
                         raise ValueError.

    Outputs:
        feats_per_epochs - features estimated over all epochs
        feat_pd_names - feature names for dataframe
        feat_st - dictionary containing results - not separated into individual frequency bands
        feats_median_ch - DataFrame containing the the median over all channels. Epoch output. Separated in freq bands
        feats_median_all - DataFrame containing the the median over all channels and epochs. Separated in freq bands

    Example:
        import utils
        import generate_all_features

        # generate 5 minutes of simulated multichannel EEG data, with 64 Hz sample frequency
        data_st = utils.gen_test_EEGdata(5 * 60, 64, 1)

        # select features to compute:
        feature_set = ['spectral_relative_power', 'rEEG_CV', 'connectivity_BSI']

        # generate all features:
        feats_per_epochs, feat_pd_names, feat_st, feats_median_ch, feats_median_all =
        generate_all_features.generate_all_features(data_st, feat_set=feature_set)

        # with other settings, e.g. 32 s epochs:
        from NEURAL_py_EEG import NEURAL_parameters
        params = NEURAL_parameters.NEURAL_parameters()
        params['EPOCH_LENGTH'] = 32
        feats_per_epochs, feat_pd_names, feat_st, feats_median_ch, feats_median_all =
        generate_all_features.generate_all_features(data_st, feat_set=feature_set, params=params)
    """

    if params is None:
        params = NEURAL_parameters.NEURAL_parameters()
    else:
        NEURAL_parameters.check_parameters(params)
        params = copy.deepcopy(params)  # the caller's settings are never changed

    # ---------------------------------------------------------------------
    # 1. load EEG data from .csv file
    # ---------------------------------------------------------------------

    if isinstance(data, dict):
        eeg_data = data["eeg_data"]
        Fs = data["Fs"]
        ch_labels = np.array(data["ch_labels"])
    else:
        eeg_data = pd.read_csv(data)
        Fs = int(data.split("_", -1)[-1][0:-4])
        ch_labels = np.array(eeg_data.columns)

    feats_per_epochs = np.array([])

    # select channels
    if not not channel_names:  # Check if channel_names is empty
        ikeep = []
        for n in range(len(channel_names)):
            it = [ind for ind, x in enumerate(ch_labels) if x == channel_names[n]]
            if not not it:
                ikeep.append(it)

        rem = [x for x in range(len(ch_labels)) if x not in ikeep]
        eeg_data = eeg_data.drop([ch_labels[rem]])
        ch_labels = ch_labels[ikeep]

    # or remove empty channels
    irem = []
    for n in range(len(ch_labels)):
        if all(np.isnan(eeg_data[ch_labels[n]])):
            irem.append(n)

    if not not irem:
        for r in range(len(irem)):
            eeg_data = eeg_data.drop([ch_labels[irem[r]]], axis=1)
        ch_labels = np.delete(ch_labels, irem)

    N_channels = len(eeg_data.columns)

    # ---------------------------------------------------------------------
    # 2. generate features
    # ---------------------------------------------------------------------
    if feat_set is None:
        feat_set = params["FEATURE_SET_ALL"]
    # Removed and unknown (e.g. misspelt) names raise ValueError before any
    # feature is computed; a supported name missing from a custom
    # params['FEATURE_SET_ALL'] is still accepted.
    NEURAL_parameters.check_requested_features(feat_set)

    # Epoch-based features need at least one complete epoch (as
    # neural_eeg_features 0.6.1): raise before computing anything. IBI-only
    # requests (and an empty feature list) still work on shorter recordings.
    if any(f.split("_")[0] in EPOCH_GROUPS for f in feat_set) and epoch_count(
        len(eeg_data), Fs, params["EPOCH_LENGTH"], params["EPOCH_OVERLAP"]
    ) < 1:
        raise shorter_than_one_epoch(len(eeg_data), Fs, params["EPOCH_LENGTH"], params["EPOCH_OVERLAP"])

    N_feats = len(feat_set)

    # A) iterate over features

    max_num_epochs = get_max_num_epochs(params, len(eeg_data), Fs)
    feat_pd_names = get_feature_names(params, feat_set)
    tmp1 = np.zeros([1, len(feat_pd_names)])
    tmp2 = np.zeros([max_num_epochs, len(feat_pd_names)])
    tmp1.fill(np.nan)
    tmp2.fill(np.nan)
    feats_median_all = pd.DataFrame(data=tmp1, columns=feat_pd_names)
    feats_median_ch = pd.DataFrame(
        data=tmp2[:, :98], columns=feat_pd_names[:98]
    )  # keeps the first 98 columns; with the 23-name default set (74 columns)
    # this includes the 4 IBI columns, which stay NaN here

    feat_st = dict()
    for n in range(N_feats):
        # print('%i / %i' % (n, N_feats-1))
        L_feature = size_feature(feat_set[n], params)
        feat_group = feat_set[n].split("_")
        feat_group = feat_group[0]

        # ---------------------------------------------------------------------
        # SPECTRAL and AMPLITUDE
        # (analysis on a per-channel basis and divide each channel into epochs)
        # ---------------------------------------------------------------------
        if feat_group in ["amplitude", "spectral", "rEEG", "FD"]:

            # B) iterate over all channels
            feats_channel = np.empty([N_channels, L_feature])
            feats_channel.fill(np.nan)

            for c in range(N_channels):
                x_epochs = overlap_epochs(
                    eeg_data[ch_labels[c]],
                    Fs,
                    params["EPOCH_LENGTH"],
                    params["EPOCH_OVERLAP"],
                )
                N_epochs, dum = x_epochs.shape

                if c == 0:
                    feats_per_epochs = np.empty([N_channels, N_epochs, L_feature])
                    feats_per_epochs.fill(np.nan)

                # C) iterate over epochs
                feats_epochs = np.empty([N_epochs, L_feature])
                feats_epochs.fill(np.nan)

                for e in range(N_epochs):
                    L_nans = len(np.where(np.isnan(x_epochs[e, :]))[0])
                    if (
                        100 * (L_nans / len(x_epochs[e, :]))
                        < params["EPOCH_IGNORE_PRC_NANS"]
                    ):
                        # Each call gets its own copy of its group's settings
                        # (spectral_power, for one, changes the dictionary it is
                        # given), as before, when each made its own with
                        # NEURAL_parameters().
                        group_params = copy.deepcopy(params[feat_group])
                        if feat_group == "spectral":
                            tmp = spectral_features.main_spectral(
                                x_epochs[e, :], Fs, feat_set[n], group_params
                            )
                        elif feat_group == "FD":
                            tmp = fd_features.main_fd(x_epochs[e, :], Fs, feat_set[n], group_params)
                        elif feat_group == "amplitude":
                            tmp = amplitude_features.main_amplitude(
                                x_epochs[e, :], Fs, feat_set[n], group_params
                            )
                        elif feat_group == "rEEG":
                            tmp = rEEG.main_rEEG(x_epochs[e, :], Fs, feat_set[n], group_params)
                        else:
                            raise ValueError(
                                'Incorrect "feat_group" - should not have entered here'
                            )

                        feats_epochs[e, :] = tmp
                feats_per_epochs[c, :, :] = feats_epochs
                # Median over all epochs
                feats_channel[c, :] = np.nanmedian(feats_epochs, axis=0)
            # Median over all channels
            feat_st[feat_set[n]] = np.nanmedian(feats_channel, axis=0)

            feats_median_ch = add_feat_data_to_array(
                feats_median_ch,
                np.median(feats_per_epochs, axis=0),
                feat_pd_names,
                feat_set[n],
                params,
            )
            feats_median_all = add_feat_data_to_array(
                feats_median_all,
                np.array([np.median(feats_channel, axis=0)]),
                feat_pd_names,
                feat_set[n],
                params,
            )
        # ---------------------------------------------------------------------
        # CONNECTIVITY FEATURES
        # (use over all channels but also divide into epochs)
        # ---------------------------------------------------------------------
        elif feat_group == "connectivity":
            dum_row = []
            x_epochs = []  # This is only to suppress warning
            for c in range(N_channels):
                tmp = overlap_epochs(
                    eeg_data[ch_labels[c]],
                    Fs,
                    params["EPOCH_LENGTH"],
                    params["EPOCH_OVERLAP"],
                )
                if c == 0:
                    dum_row, dumy = tmp.shape
                    x_epochs = np.empty([N_channels, dum_row, dumy])
                    x_epochs.fill(np.nan)
                x_epochs[c, :, :] = tmp

            N_epochs = dum_row

            # B) iterate over epochs:
            feats_epochs = np.empty([N_epochs, L_feature])
            feats_epochs.fill(np.nan)
            for e in range(N_epochs):
                x_ep = x_epochs[:, e, :]
                L_nans = len(np.where(np.isnan(x_ep))[0])
                if 100 * (L_nans / x_ep.size) < params["EPOCH_IGNORE_PRC_NANS"]:
                    tmp = connectivity_features.main_connectivity(
                        x_ep, Fs, feat_set[n], ch_labels, copy.deepcopy(params["connectivity"])
                    )
                    feats_epochs[e, :] = tmp
            # Median over all epochs
            feat_st[feat_set[n]] = np.nanmedian(feats_epochs, axis=0)
            feats_median_ch = add_feat_data_to_array(
                feats_median_ch, feats_epochs, feat_pd_names, feat_set[n], params
            )
            feats_median_all = add_feat_data_to_array(
                feats_median_all,
                np.array([np.nanmedian(feats_epochs, axis=0)]),
                feat_pd_names,
                feat_set[n],
                params,
            )

        elif feat_group == "IBI":
            # B) iterate over epochs:
            feats_channel = np.empty([N_channels, L_feature])
            feats_channel.fill(np.nan)
            for c in range(N_channels):
                feats_channel[c, :] = IBI_features.main_IBI(
                    eeg_data[ch_labels[c]].to_numpy(), Fs, feat_set[n]
                )

            # and the median over all channels
            feat_st[feat_set[n]] = np.nanmedian(feats_channel, axis=0)
            feats_median_all = add_feat_data_to_array(
                feats_median_all,
                np.array([np.nanmedian(feats_channel, axis=0)]),
                feat_pd_names,
                feat_set[n],
                params,
            )

    if save_p_l is not None:
        save_p_l = save_p_l + "_all_med"
        utils.save_pd_as_file(feats_median_all, save_p_l)
        save_p_l = save_p_l + "_ch_med"
        utils.save_pd_as_file(feats_median_ch, save_p_l)

    return feats_per_epochs, feat_pd_names, feat_st, feats_median_ch, feats_median_all


def get_feature_names(params, feat_set):
    """
    The purpose of this function to create an array that contains all the features names. This is the feature name,
    channel and frequency band. Array will be nans and one for every channel in the 'BI_MONT' param except for the
    connectivity features

    The columns are those of the features in feat_set (each once), in the
    order of params['FEATURE_SET_ALL']; a feature of feat_set that is not in
    params['FEATURE_SET_ALL'] comes after those, in the order of feat_set.
    (Before, a feature missing from params['FEATURE_SET_ALL'] got no column,
    and generate_all_features failed after computing it.) Each feature has
    one column per frequency band (feature_column_names).

    :param feat_set: The feature set being examined
    :param params: The parameters for the neural dataset
    :return: numpy string array containing feature names for all different frequency bands
    """
    order = list(params["FEATURE_SET_ALL"])
    features = list(dict.fromkeys(feat_set))  # each feature once, in the order given
    features.sort(key=lambda feat: order.index(feat) if feat in order else len(order))  # stable
    names = []
    for feat in features:
        names.extend(feature_column_names(params, feat))

    return names


def feature_band_edges(params, feat_name):
    """The (low, high) edges in Hz of each frequency band of feature
    feat_name, one per column: the IBI features have the one band [0.5, 30],
    spectral_edge_frequency the spectral 'total_freq_bands', every other
    feature its group's 'freq_bands'. A flat list [low, high] is one band
    (only its first two values are used, as main_fd does); otherwise each
    row is a band, including a single row [[low, high]] (as a list or a
    numpy array; before, a single row was taken for a flat pair and failed
    with IndexError)."""
    feat_group = feat_name.split("_")[0]
    if feat_group == "IBI":
        bands = np.array([0.5, 30])
    elif (
        "total_freq_bands" in params[feat_group].keys()
        and feat_name == "spectral_edge_frequency"
    ):
        bands = np.array(params[feat_group]["total_freq_bands"])
    else:
        bands = np.array(params[feat_group]["freq_bands"])

    if bands.ndim == 1:
        return [(bands[0], bands[1])]
    return [(band[0], band[1]) for band in bands]


def band_edge_label(edge):
    """One band edge as written in a column name: a whole number as an
    integer ('4', '30') and 0.5 as '05', as before (so the default column
    names are unchanged); any other value in full, with 'p' for the decimal
    point ('4p1', '0p25', '1p5'). Distinct edges thus get distinct labels.
    (Before, every edge except a lower edge of 0.5 was cut to its integer
    part: bands [0.5, 4.1] and [0.5, 4.9] both gave '05_4', and the second
    band's values overwrote the first's.)"""
    edge = float(edge)
    if edge == 0.5:
        return "05"
    if edge.is_integer():
        return str(int(edge))
    return repr(edge).replace(".", "p")


def feature_column_names(params, feat_name):
    """The column names of feature feat_name, one per band of
    feature_band_edges: feat_name + '__' + low + '_' + high (band_edge_label),
    e.g. 'spectral_power__05_4'. Two bands with the same edges would give
    the same name, so that raises ValueError naming them."""
    edges = feature_band_edges(params, feat_name)
    names = [feat_name + "__" + band_edge_label(low) + "_" + band_edge_label(high) for low, high in edges]
    for i, name in enumerate(names):
        if name in names[:i]:
            first = names.index(name)
            raise ValueError(
                "%s: frequency bands %d %r and %d %r give the same column name %r; "
                "each band of a feature must differ"
                % (feat_name, first, [float(e) for e in edges[first]], i, [float(e) for e in edges[i]], name)
            )
    return names


def get_max_num_epochs(params, N, Fs):
    """
    The purpose of this function is to find what the maximum number of epochs is so an empty nan np array can be made

        Inputs:
        params:           the parameter set
        N:                the number of samples in a single channel of an EEG
        Fs:               sampling frequency

    Outputs:
        a:                returns the number of epochs that will be generated

    The count comes from epoch_count, as in overlap_epochs (same hop, same
    rule: complete epochs only), so it always equals the number of epochs; it
    is 0 for a recording shorter than one epoch, where epoch-based features
    raise ValueError and an IBI-only request leaves the table empty. (Before
    commit 90543fc it used the hop of a 'hamm' window, one sample shorter
    than overlap_epochs' 'rect' hop at 50 % overlap when the epoch length in
    samples is odd: the two counts could then differ and
    generate_all_features failed.)
    """
    return epoch_count(N, Fs, params["EPOCH_LENGTH"], params["EPOCH_OVERLAP"])


def add_feat_data_to_array(all_data, new_data, feat_pd_names, feat_name, params):
    """
    Update all_data array by appending the new data. The new data contains the data from all freq bands

    Syntax: all_data = add_feat_data_to_array(all_data, new_data, feat_pd_names, feat_name, params)

    Inputs:
        all_data:               Full data array for all features
        new_data:               New data for all feat bands of 'feat_name'
        feat_pd_names:          All the feature names (with bands and channels)
        feat_name:              Name of current feature
        params:                 Needed to get the feature group

    Outputs:
        packaged_data:    dictionary including EEG data (referential montage), sampling
                          frequency, and channel labels. Data are pandas DataFrame
    """

    # the same column names as get_feature_names, band b of new_data in column b
    for b, a_feat_name in enumerate(feature_column_names(params, feat_name)):

        if a_feat_name not in feat_pd_names:
            raise ValueError(
                "Feature name %s does not exist - check code" % a_feat_name
            )

        # idx = [i for i, s in enumerate(feat_pd_names) if s == a_feat_name]

        # print(a_feat_name)
        if new_data.shape[0] == 1:
            all_data[a_feat_name] = [new_data[0][b]]
        else:
            all_data[a_feat_name] = new_data[:, b]

    return all_data
