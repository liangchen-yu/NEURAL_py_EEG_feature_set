"""Synthetic EEG recordings, written as EDF files, for the regression tests.

The tests need input files that are exactly the same on every computer. So
every sample is made with whole-number (integer) arithmetic only: a small
random-number generator (splitmix64), sums, products and integer division.
There is no floating-point maths, so the bytes do not depend on the operating
system, the processor or the numpy version. The SHA-256 checksum of each file
is stored in tests/data/ and checked by the tests.

Two recordings ("cases"), each 300 s, 256 Hz, 9 electrodes, in microvolts (uV):
  "clean"      EEG-like noise only;
  "artefacts"  the same recording with deliberate artefacts, one for each of
               NEURAL's artefact checks, so its artefact-removal code runs.

To write the two files to a folder (to look at them in an EDF viewer):
    python tests/synthetic_edf.py <folder>
"""
import hashlib
import sys
from pathlib import Path

import numpy as np

CASES = ("clean", "artefacts")
SEED = 2026
FS = 256  # samples per second
DURATION = 300  # seconds
ELECTRODES = ["F3", "F4", "C3", "C4", "O1", "O2", "T3", "T4", "Cz"]

# EDF stores whole numbers ("digital" values). Here one digital unit is 0.1 uV:
# digital -32768..32767 <-> physical -3276.8..3276.7 uV.
DIGITAL_MIN, DIGITAL_MAX = -32768, 32767
PHYSICAL_MIN, PHYSICAL_MAX = "-3276.8", "3276.7"
UNITS_PER_UV = 10

# eeg_like() has a standard deviation of about 869,430. Dividing by SCALE turns
# that into 10 digital units = 1 uV, so weights below are in microvolts.
SCALE = 86943

# Each electrode = shared activity (all electrodes) + regional activity (shared
# by a left/right pair, so it survives the bipolar montage and links the two
# hemispheres) + its own activity. The right side is a bit larger (asymmetry).
REGION = {"F3": "F", "F4": "F", "C3": "C", "C4": "C", "T3": "T", "T4": "T",
          "O1": "O", "O2": "O", "Cz": None}
WEIGHT_SHARED, WEIGHT_REGION = 20, 8  # uV
WEIGHT_OWN = {"F3": 6, "C3": 6, "T3": 6, "O1": 6, "Cz": 6,
              "F4": 7, "C4": 7, "T4": 7, "O2": 7}  # uV

# One random stream per signal, so that the signals are independent.
STREAM_SHARED = 1
STREAM_REGION = {"F": 2, "C": 3, "T": 4, "O": 5}
STREAM_RHYTHM = 6
STREAM_OWN = {name: 10 + i for i, name in enumerate(ELECTRODES)}
STREAM_LOOSE_F4, STREAM_SHORTED_CZ = 30, 31

# One cycle of a 32 Hz sine wave at 256 Hz (8 samples), 2000 uV peak, in
# digital units (2000 * sin(45 degrees) = 1414.2 uV), written out as whole numbers.
BURST_CYCLE = np.array([0, 14142, 20000, 14142, 0, -14142, -20000, -14142], dtype=np.int64)


def random_uint64(stream, n):
    """n pseudo-random 64-bit whole numbers (splitmix64). Each stream starts at
    its own place in the sequence. numpy's uint64 maths wraps around at 2**64,
    exactly like the C version of splitmix64."""
    counter = np.arange(1, n + 1, dtype=np.uint64) + np.uint64(stream) * np.uint64(2**32)
    z = np.uint64(SEED) + counter * np.uint64(0x9E3779B97F4A7C15)
    z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return z ^ (z >> np.uint64(31))


def noise(stream, n):
    """Bell-shaped random whole numbers with mean 0: the sum of the four 16-bit
    parts of a 64-bit random number, minus their mean. Standard deviation
    about 37,837; always between -131,070 and +131,070."""
    r = random_uint64(stream, n)
    parts = [((r >> np.uint64(shift)) & np.uint64(0xFFFF)).astype(np.int64)
             for shift in (0, 16, 32, 48)]
    return parts[0] + parts[1] + parts[2] + parts[3] - 2 * 65535


def moving_sum(x, length):
    """At every sample, the sum of the latest `length` samples (exact)."""
    c = np.concatenate([np.zeros(length, dtype=np.int64), np.cumsum(x)])
    return c[length:] - c[:-length]


def eeg_like(stream, n):
    """EEG-like noise with more power at low frequencies (roughly 1/f): white
    noise plus its moving sums over 4, 16 and 64 samples."""
    w = noise(stream, n)
    return 8 * w + 4 * moving_sum(w, 4) + 2 * moving_sum(w, 16) + moving_sum(w, 64)


def occipital_rhythm(n):
    """An 8 Hz rhythm for O1 and O2 (a triangle wave, period 32 samples) whose
    size changes randomly over a few seconds. Roughly 4.6 uV after scaling."""
    triangle = np.abs(np.arange(n, dtype=np.int64) % 32 - 16) - 8  # -8 .. 8
    return triangle * moving_sum(noise(STREAM_RHYTHM, n), 512)


def slow_envelope(n):
    """Overall size rising and falling between 1x and 2x every 120 s (a
    triangle), the same for all electrodes, so that epochs differ."""
    period = 120 * FS
    distance = np.abs(np.arange(n, dtype=np.int64) % period - period // 2)
    return period + 2 * distance, period  # (envelope, its value for 1x)


def clean_signals():
    """The clean recording: 9 rows (ELECTRODES order), whole numbers in 0.1 uV."""
    n = FS * DURATION
    shared = eeg_like(STREAM_SHARED, n)
    regional = {region: eeg_like(stream, n) for region, stream in STREAM_REGION.items()}
    rhythm = occipital_rhythm(n)
    envelope, one = slow_envelope(n)

    rows = []
    for name in ELECTRODES:
        x = WEIGHT_SHARED * shared + WEIGHT_OWN[name] * eeg_like(STREAM_OWN[name], n)
        if REGION[name] is not None:
            x = x + WEIGHT_REGION * regional[REGION[name]]
        if REGION[name] == "O":
            x = x + rhythm
        rows.append((x * envelope) // (SCALE * one))
    return np.array(rows)


def add_artefacts(signals):
    """Deliberate artefacts, one for each of NEURAL's artefact checks."""
    signals = signals.copy()
    row = {name: i for i, name in enumerate(ELECTRODES)}
    n = signals.shape[1]

    def seconds(start, end):
        return slice(int(start * FS), int(end * FS))

    # F4 not attached properly: unrelated noise -> low-correlation check
    signals[row["F4"]] = (WEIGHT_SHARED * eeg_like(STREAM_LOOSE_F4, n)) // SCALE
    # Cz shorted to C4: Cz = C4 + about 0.5 uV of noise -> electrode-coupling check
    signals[row["Cz"]] = signals[row["C4"]] + noise(STREAM_SHORTED_CZ, n) // 7567
    # 2000 uV, 32 Hz burst on T4 for 1 s -> high-amplitude check. 32 Hz is
    # outside the 0.5-20 Hz band of the correlation check, so T4 stays in.
    signals[row["T4"], seconds(100, 101)] += np.tile(BURST_CYCLE, FS // 8)
    # O2 jumps up by 400 uV for 5 s -> sudden-jump check
    signals[row["O2"], seconds(200, 205)] += 400 * UNITS_PER_UV
    # every electrode flat at 0 at the start, middle and end -> flat-zero
    # check (1 s or more), and gaps at the start, middle and end. The 40 s
    # gap makes two 64 s epochs more than half artefact, so NEURAL skips them.
    signals[:, seconds(0, 3)] = 0
    signals[:, seconds(140, 180)] = 0
    signals[:, seconds(298, 300)] = 0
    # every electrode flat at 0 for 0.5 s -> too short for the flat-zero
    # check, long enough for the constant-value check (0.1 s)
    signals[:, seconds(250, 250.5)] = 0
    return signals


def make_signals(case):
    """The signals of one case: 9 rows (ELECTRODES order), whole numbers in 0.1 uV."""
    if case not in CASES:
        raise ValueError(f"unknown case {case!r}; choose from {CASES}")
    signals = clean_signals()
    return add_artefacts(signals) if case == "artefacts" else signals


def _field(value, width):
    """One fixed-width EDF header field: text padded with spaces."""
    text = str(value)
    if len(text) > width:
        raise ValueError(f"{text!r} does not fit in {width} characters")
    return text.ljust(width)


def edf_bytes(signals):
    """The signals as a plain EDF file (a text header, then 16-bit whole
    numbers in 1-second records). Fixed dates, so the bytes never change."""
    n_signals, n_samples = signals.shape
    if n_samples % FS:
        raise ValueError("length must be a whole number of seconds")
    if signals.min() < DIGITAL_MIN or signals.max() > DIGITAL_MAX:
        raise ValueError("signal does not fit in EDF's 16-bit range")
    n_records = n_samples // FS

    header = "".join([
        _field("0", 8),  # format version
        _field("X X X X", 80),  # patient: anonymous
        _field("Startdate X X X X", 80),  # recording: anonymous
        _field("01.01.26", 8),  # fixed start date and time
        _field("00.00.00", 8),
        _field(256 * (n_signals + 1), 8),  # header size in bytes
        _field("", 44),  # reserved (blank = plain EDF)
        _field(n_records, 8),  # number of data records
        _field(1, 8),  # duration of one record, seconds
        _field(n_signals, 4),  # number of signals
    ])
    per_signal = [
        (ELECTRODES, 16),  # labels
        ([""] * n_signals, 80),  # transducer type
        (["uV"] * n_signals, 8),  # physical unit
        ([PHYSICAL_MIN] * n_signals, 8),
        ([PHYSICAL_MAX] * n_signals, 8),
        ([DIGITAL_MIN] * n_signals, 8),
        ([DIGITAL_MAX] * n_signals, 8),
        ([""] * n_signals, 80),  # prefiltering
        ([FS] * n_signals, 8),  # samples per record
        ([""] * n_signals, 32),  # reserved
    ]
    for values, width in per_signal:
        header += "".join(_field(value, width) for value in values)

    # each 1 s record holds 256 samples of signal 1, then of signal 2, ...
    records = signals.astype("<i2").reshape(n_signals, n_records, FS).transpose(1, 0, 2)
    return header.encode("ascii") + records.tobytes()


def make_edf(case):
    """The EDF file of one case, as bytes."""
    return edf_bytes(make_signals(case))


def sha256(data):
    """SHA-256 checksum (hex): identical files give identical checksums."""
    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    folder.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        data = make_edf(case)
        path = folder / f"synthetic_{case}.edf"
        path.write_bytes(data)
        print(f"{path}  {len(data)} bytes  sha256 {sha256(data)}")
