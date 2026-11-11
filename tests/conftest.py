"""Shared set-up for the tests. pytest reads this file automatically.

- First, it stops unless Python imports this repository's NEURAL (src/).

- `reference`: the saved reference values (tests/data/reference_<case>.json).
- `run_preprocessing`: writes a synthetic EDF file to pytest's temporary
  folder and runs NEURAL's preprocessing on it, once per case (the slow part),
  shared by all tests.
- At the start, pytest shows which NEURAL and library versions are used; at
  the end, a table of the largest differences from the reference.
"""
import json
import os
from importlib import metadata
from pathlib import Path

import pytest

import neural_outputs
import synthetic_edf

DATA = Path(__file__).parent / "data"
THIS_REPOSITORY_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "NEURAL_py_EEG"


def check_tests_use_this_repository():
    """Stop at once if Python imported another copy of NEURAL (for example an
    older installed version): the tests must check this repository's code."""
    import NEURAL_py_EEG

    used = Path(NEURAL_py_EEG.__file__).resolve().parent
    if not os.path.samefile(str(used), str(THIS_REPOSITORY_PACKAGE)):
        pytest.exit("The tests must run this repository's NEURAL (%s), but Python imported %s. Run "
                    "pytest from the repository's top folder: pyproject.toml puts src/ first on the "
                    "path." % (THIS_REPOSITORY_PACKAGE, used), returncode=4)


check_tests_use_this_repository()


@pytest.fixture(scope="session")
def reference():
    return {case: json.loads((DATA / f"reference_{case}.json").read_text(encoding="utf-8"))
            for case in synthetic_edf.CASES}


@pytest.fixture(scope="session")
def run_preprocessing(tmp_path_factory):
    results = {}

    def run(case):
        if case not in results:
            path = tmp_path_factory.mktemp("edf") / f"synthetic_{case}.edf"
            path.write_bytes(synthetic_edf.make_edf(case))
            results[case] = neural_outputs.preprocess(path)
        return results[case]

    return run


def pytest_report_header(config):
    import NEURAL_py_EEG

    versions = ", ".join(f"{name} {metadata.version(name)}"
                         for name in ("numpy", "scipy", "pandas", "mne", "matplotlib", "pyedflib"))
    return [f"NEURAL_py_EEG used: {Path(NEURAL_py_EEG.__file__).parent}", f"versions: {versions}"]


def pytest_terminal_summary(terminalreporter):
    results = neural_outputs.RESULTS
    if not results:
        return
    write = terminalreporter.write_line
    terminalreporter.section("NEURAL regression check: largest differences from the reference")
    write(f"tolerance: |new - reference| <= {neural_outputs.ATOL:g} + {neural_outputs.RTOL:g} * |reference|;"
          " NaN must be NaN in both")
    write(f"{'case':<10} {'what':<22} {'values':>7} {'NaN':>5} {'largest abs diff':>17} "
          f"{'largest rel diff':>17} {'outside tolerance':>18}")

    rows = {}
    for result in results:
        row = rows.setdefault((result["case"], result["group"]), {
            "values": 0, "nan_places": 0, "largest_abs": 0.0, "largest_rel": 0.0, "outside_tolerance": 0})
        for key in ("values", "nan_places", "outside_tolerance"):
            row[key] += result[key]
        for key in ("largest_abs", "largest_rel"):
            row[key] = max(row[key], result[key])

    def number(x):
        return "0" if x == 0 else f"{x:.2e}"

    for (case, group), row in rows.items():
        write(f"{case:<10} {group:<22} {row['values']:>7} {row['nan_places']:>5} "
              f"{number(row['largest_abs']):>17} {number(row['largest_rel']):>17} {row['outside_tolerance']:>18}")
