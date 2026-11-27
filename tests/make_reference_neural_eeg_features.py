"""Make tests/data/reference_neural_eeg_features_0.6.1.json with the reference
package neural_eeg_features 0.6.1 at its default settings.

These are the values this repository's NEURAL should give once it has adopted
the reference package's default settings and conventions (step 3 and steps
4-6 of docs/CHANGES_vs_neural_eeg_features_0.6.1.md);
tests/test_neural_eeg_features_defaults.py compares them. The reference
package is not needed to run the tests, only to remake this file.

Run once, in the reference package's own environment (it is not a dependency
of this repository), from this repository's top folder:

    set NUMBA_CACHE_DIR=<a folder outside both repositories>
    <reference package environment>\\Scripts\\python -B tests\\make_reference_neural_eeg_features.py

-B and NUMBA_CACHE_DIR keep Python and Numba from writing cache files into
the reference package's folder; the script stops unless NUMBA_CACHE_DIR is set
and resolves to a folder outside both this repository and the reference
package's folder. Add --output <folder> to write elsewhere.
The script stops unless the imported neural_eeg_features is version 0.6.1
with exactly the module files pinned below (SHA-256; text files with "\\n"
line endings).

Inputs: synthetic only (tests/neural_eeg_features_inputs.py). Settings: the
reference package's defaults, FeatureConfig() (without the IBI features at
256 Hz: its burst detector needs 64 Hz), with NEURAL's channel pairs given
explicitly. Stored per case: the summary, per-channel and per-epoch values
(NaN as null), with the provenance (package version and module hashes,
library versions, settings, input recipe and checksums, this script's
SHA-256).
"""
import hashlib
import json
import os
import platform
import sys
from importlib import metadata
from pathlib import Path

import numpy as np

import neural_eeg_features_inputs as inputs
import neural_outputs
import synthetic_edf

OUTPUT_NAME = "reference_neural_eeg_features_0.6.1.json"
VERSION = "0.6.1"
PINNED_SHA256 = {
    "__init__.py": "fdce06f47c175e8ab183fc9b4d0673878c8584f8ea67d9bd102d13cd569bf0a3",
    "_detector.py": "79cddd36c0e8c1e2fdba4a4aed59091ac9fc2f36c87e7ebb7ff0a03e2d11de69",
    "_detector_filters.py": "858438b8cb6784d731c58eb389ee9098e1654a9c98661cf4917a6788c42b840e",
    "_detector_parameters.py": "0c931d69b16c0ebcac895eaff0c60d0ef16079840a92e63d2adc3f1cff524ca3",
    "_numeric.py": "8a8a6ac8d8d90d131e31b9c4d72489ae63e029a8f1736046707a6ce74dffccfc",
    "_resources/detector_filters.json": "0c9a4537d8a925fac699af1c7abd1a4926117433acb1b4a30e5ad27be34c9ab2",
    "_resources/ellip_filters.npz": "72a697355c0db789e0229bfd57a3daa7434f7552401ec3c1cc0ab51c82acdc3c",  # as stored
    "amplitude.py": "05529caee2277bd5335c2ffe2d1cfe88fc912a9e169dbeb933a387051d8726f7",
    "config.py": "addeb094587624eed258df7e9195c07f4aa37655b33721363b8f503d015c4e31",
    "connectivity.py": "8716dd4b1bc890ca87ff1f5a3ac8652002604ff3314a3471fa59adf8dc482c74",
    "extraction.py": "64a5535b721552e7d8c6fcdb9295f551edd6d565f5b5e87c8157191cbc775f33",
    "fractal.py": "f31a1539ec39951793e7636990183b34fba190d5f550f7b7bcb6b4e7d56ca668",
    "ibi.py": "1e5ad7a60cd1ae40bf77af423a7c51e91dec7e1af14e1d9f5b307bb255c4c4db",
    "reeg.py": "2578f2147b1ee76a0f3e7c67921fa93cf264e5dc830d4d94c6325f4be7845547",
    "spectral.py": "3121406792487ed17a8281bb212619abc597c8352065b2eb36b3097a57b3eaf9",
}
LIBRARIES = ("numpy", "scipy", "pandas", "numba")

ABOUT = {
    "what": "Values of the reference package neural_eeg_features 0.6.1 at its default settings, for "
            "tests/test_neural_eeg_features_defaults.py: what this repository's NEURAL should give once it "
            "has adopted that package's default settings and conventions. Made by "
            "tests/make_reference_neural_eeg_features.py (see made_with).",
    "inputs": "Synthetic inputs only (tests/neural_eeg_features_inputs.py): recipe, sampling rate, duration, "
              "channels, the channel pairs given to the reference package, and the SHA-256 of each input "
              "array (neural_eeg_features_inputs.sha256).",
    "config": "The reference package's resolved settings, FeatureConfig().to_dict(): its defaults; "
              "per case, 'features' lists the features computed (no IBI at 256 Hz: the burst detector "
              "needs 64 Hz).",
    "results": "Per case and feature: 'bands' maps each output band name to its [low, high] edges in Hz "
               "(null for IBI, which has no band); 'summary' one value per band; 'per_channel' "
               "[band][channel] (not for connectivity, which compares pairs of channels); 'epochs' the "
               "epoch start times in seconds, the epoch duration, and the values [band][channel][epoch] "
               "(connectivity: [band][epoch]); IBI features have no epochs. Channels in the order of "
               "inputs.channels.",
    "null": "null means NaN.",
}


def module_hashes(package_dir):
    result = {}
    for name in PINNED_SHA256:
        data = (package_dir / name).read_bytes()
        if not name.endswith(".npz"):
            data = data.replace(b"\r\n", b"\n")
        result[name] = hashlib.sha256(data).hexdigest()
    return result


def verify_reference():
    import neural_eeg_features

    version = metadata.version("neural_eeg_features")
    package_dir = Path(neural_eeg_features.__file__).parent
    hashes = module_hashes(package_dir)
    problems = [] if version == VERSION else ["version %s, not %s" % (version, VERSION)]
    problems += ["%s: not the pinned file" % name for name, expected in PINNED_SHA256.items()
                 if hashes[name] != expected]
    extra = sorted(p.relative_to(package_dir).as_posix() for p in package_dir.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts
                   and p.relative_to(package_dir).as_posix() not in PINNED_SHA256)
    problems += ["%s: not a pinned file" % name for name in extra]
    if problems:
        raise SystemExit("No fixture written: the imported neural_eeg_features is not the pinned 0.6.1.\n  "
                         + "\n  ".join(problems))
    print("neural_eeg_features %s verified: %d pinned files." % (version, len(hashes)))
    return version, hashes


def check_numba_cache_dir():
    """Stop unless NUMBA_CACHE_DIR is set and resolves to a folder outside
    both this repository and the reference package's folder (the folder that
    holds the imported neural_eeg_features), so that Numba writes no cache
    files into either. Checked before the package is imported."""
    from importlib import util

    value = os.environ.get("NUMBA_CACHE_DIR")
    if not value:
        raise SystemExit("Set NUMBA_CACHE_DIR to a folder outside both repositories first (see the top of this file).")
    cache = Path(value).resolve()
    repository = Path(__file__).resolve().parents[1]
    spec = util.find_spec("neural_eeg_features")
    if spec is None or spec.origin is None:
        raise SystemExit("neural_eeg_features is not importable here; run this in the reference package's environment.")
    reference = Path(spec.origin).resolve().parents[1]  # the folder that holds the neural_eeg_features package
    for name, folder in (("this repository", repository), ("the reference package's folder", reference)):
        if cache == folder or folder in cache.parents:
            raise SystemExit("NUMBA_CACHE_DIR must be outside %s; it resolves to a folder inside it." % name)


def feature_bands(config, name):
    """(band name, [low, high] or None) of each output band of a feature, in
    the reference package's order (its extraction._feature_bands)."""
    from neural_eeg_features.config import AMPLITUDE_FEATURES, IBI_FEATURES, REEG_FEATURES

    if name in IBI_FEATURES:
        return [("none", None)]
    if name == "spectral_edge_frequency":
        return [("wide", [config.bands[0].low, config.bands[-1].high])]
    if name == "FD":
        bands = config.fractal.bands
    elif name in AMPLITUDE_FEATURES:
        bands = config.amplitude_bands or config.bands
    elif name in REEG_FEATURES:
        bands = config.reeg_bands or config.bands
    else:
        bands = config.bands
    return [(band.name, [band.low, band.high]) for band in bands]


def results_of(result, config, features, channels):
    """The tables of a FeatureResult arranged per feature (see ABOUT)."""
    from neural_eeg_features.config import CONNECTIVITY_FEATURES, IBI_FEATURES

    epochs, per_channel, summary = result.epochs, result.per_channel, result.summary
    out = {}
    for name in features:
        bands = feature_bands(config, name)
        entry = {"bands": {band: edges for band, edges in bands}, "summary": {}}
        for band, _ in bands:
            rows = summary[(summary.feature == name) & (summary.band == band)]
            assert len(rows) == 1, (name, band)
            entry["summary"][band] = float(rows.value.iloc[0])
        if name not in CONNECTIVITY_FEATURES:
            entry["per_channel"] = {}
            for band, _ in bands:
                rows = per_channel[(per_channel.feature == name) & (per_channel.band == band)]
                values = dict(zip(rows.channel, rows.value.astype(float)))
                assert sorted(values) == sorted(channels), (name, band)
                entry["per_channel"][band] = [values[c] for c in channels]
        if name not in IBI_FEATURES:
            rows = epochs[epochs.feature == name]
            starts = sorted(set(rows.epoch_start_seconds.astype(float)))
            durations = set(rows.epoch_duration_seconds.astype(float))
            assert len(durations) == 1, name
            values = {}
            for band, _ in bands:
                selected = rows[rows.band == band]
                if name in CONNECTIVITY_FEATURES:
                    table = selected.set_index("epoch_start_seconds").value.astype(float)
                    assert len(table) == len(starts)
                    values[band] = [float(table[s]) for s in starts]
                else:
                    table = selected.set_index(["channel", "epoch_start_seconds"]).value.astype(float)
                    assert len(table) == len(starts) * len(channels)
                    values[band] = [[float(table[(c, s)]) for s in starts] for c in channels]
            entry["epochs"] = {"start_seconds": starts, "duration_seconds": durations.pop(), "values": values}
        out[name] = entry
    return out


def main(argv):
    output = Path(__file__).parent / "data"
    if "--output" in argv:
        output = Path(argv[argv.index("--output") + 1])
    check_numba_cache_dir()
    version, hashes = verify_reference()
    from neural_eeg_features import ALL_FEATURES, FeatureConfig, extract_features
    from neural_eeg_features.config import IBI_FEATURES

    default = FeatureConfig()
    reference = {"about": ABOUT}
    script = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    reference["made_with"] = {
        "package": "neural_eeg_features", "version": version, "module_sha256": hashes,
        "python": platform.python_version(), "os": "%s %s" % (platform.system(), platform.release()),
        **{name: metadata.version(name) for name in LIBRARIES},
        "generator": "tests/make_reference_neural_eeg_features.py",
        "generator_sha256": hashlib.sha256(script).hexdigest(),
    }
    reference["inputs"] = {}
    reference["config"] = default.to_dict()
    reference["results"] = {}
    for case, (rate, seconds, with_nan) in inputs.CASES.items():
        x, rate = inputs.make_input(case)
        features = tuple(f for f in ALL_FEATURES if rate == 64 or f not in IBI_FEATURES)
        config = FeatureConfig(features=features)
        reference["inputs"][case] = {
            "recipe": inputs.RECIPE, "seed": synthetic_edf.SEED, "sampling_rate_hz": rate, "seconds": seconds,
            "nan_runs_seconds": inputs.NAN_RUNS if with_nan else {}, "channels": inputs.CHANNELS,
            "channel_pairs": [list(pair) for pair in inputs.PAIRS], "features": list(features),
            "sha256": inputs.sha256(x),
        }
        result = extract_features(x, rate, channel_names=inputs.CHANNELS, config=config,
                                  channel_pairs=inputs.PAIRS)
        assert result.metadata["config"] == config.to_dict()
        assert [list(p) for p in result.metadata["channel_pairs"]] == [list(p) for p in inputs.PAIRS]
        reference["results"][case] = results_of(result, config, features, inputs.CHANNELS)
        print("%s: %d features, %d epoch rows" % (case, len(features), len(result.epochs)))
    output.mkdir(parents=True, exist_ok=True)
    path = output / OUTPUT_NAME
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(neural_outputs.dumps(neural_outputs.to_json(reference)) + "\n")
    print("saved %s (%s bytes)" % (path.name, format(path.stat().st_size, ",")))


if __name__ == "__main__":
    main(sys.argv[1:])
