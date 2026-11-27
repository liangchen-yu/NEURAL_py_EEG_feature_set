"""The synthetic inputs of the neural_eeg_features 0.6.1 fixtures
(tests/data/reference_neural_eeg_features_0.6.1.json).

Built with numpy only, without NEURAL's code: tests/make_reference_neural_eeg_features.py
(run once with the reference package) and tests/test_neural_eeg_features_defaults.py
(run with this repository's NEURAL) build exactly the same arrays, and the test checks
their SHA-256 against the one stored with the fixtures.

Each input is the "clean" synthetic recording of synthetic_edf.py (whole numbers at
256 Hz, a fixed seed), in microvolts (/ 10), as NEURAL's 8 bipolar channels (the
difference of two electrodes, in the order of utils.set_bi_montage), optionally
every 4th sample (64 Hz, without a filter) and cut to a whole number of seconds.
"""
import hashlib

import numpy as np

import synthetic_edf

# NEURAL's bipolar channels (utils.set_bi_montage's default montage, in its order)
BIPOLAR = [("C3", "O1"), ("C4", "O2"), ("Cz", "C3"), ("C4", "Cz"), ("C3", "T3"), ("C4", "T4"), ("F3", "C3"),
           ("F4", "C4")]
CHANNELS = ["%s_%s" % pair for pair in BIPOLAR]
# The left/right pairs that NEURAL's connectivity_features.channel_hemisphere_pairs
# finds for these channels (the test checks this); given to the reference package
# explicitly, as it pairs only names with '-'.
PAIRS = [("C3_O1", "C4_O2"), ("C3_T3", "C4_T4"), ("F3_C3", "F4_C4")]

# NaN runs of the "missing" input: channel -> list of (first second, last second), at 64 Hz
NAN_RUNS = {"C3_O1": [(50, 52)], "F4_C4": [(120, 130)], "C4_T4": [(75, 75 + 1 / 64)]}

CASES = {
    # name: (sampling rate in Hz, seconds, with NaN runs)
    "64 Hz": (64, 300, False),
    "256 Hz": (256, 128, False),
    "64 Hz with missing samples": (64, 192, True),
}
RECIPE = ("synthetic_edf.make_signals('clean') (seed synthetic_edf.SEED) / 10 microvolts; bipolar "
          "channels = electrode differences in the order of CHANNELS; 64 Hz cases: every 4th sample "
          "(no filter); the first 'seconds' seconds; the missing-samples case sets NAN_RUNS to NaN "
          "(tests/neural_eeg_features_inputs.py)")


def make_input(case):
    """(samples x channels float64 array, sampling rate) of one case."""
    rate, seconds, with_nan = CASES[case]
    microvolts = synthetic_edf.make_signals("clean") / 10.0
    index = {name: i for i, name in enumerate(synthetic_edf.ELECTRODES)}
    bipolar = np.stack([microvolts[index[a]] - microvolts[index[b]] for a, b in BIPOLAR], axis=1)
    step = synthetic_edf.FS // rate
    x = np.ascontiguousarray(bipolar[::step][:seconds * rate], dtype=np.float64)
    if with_nan:
        for channel, runs in NAN_RUNS.items():
            for first, last in runs:
                x[int(round(first * rate)):int(round(last * rate)), CHANNELS.index(channel)] = np.nan
    return x, rate


def sha256(x):
    """SHA-256 of the array's float64 bytes (little-endian, C order) and shape."""
    data = np.ascontiguousarray(x, dtype="<f8")
    return hashlib.sha256(repr(data.shape).encode() + data.tobytes()).hexdigest()
