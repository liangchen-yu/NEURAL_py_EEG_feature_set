# Numerical sensitivity experiment

This experiment checks, on one computer, where NEURAL's pipeline magnifies
last-digit rounding differences and whether second-order sections (SOS) reduce
it. It uses only the two synthetic recordings of the regression tests and does
not change NEURAL's code: the alternative filters are swapped in by the script
while it runs. The results, with a short summary, are in
[results.md](results.md).

| File | What it is |
|---|---|
| `run_sensitivity.py` | The experiment (parts A–D), the checks, the tables and the figure |
| `sensitivity_tools.py` | Building blocks: the ULP perturbation, the switch to SOS or to perturbed (b, a) coefficients, NEURAL's pipeline stage by stage, the difference measures |
| `results.md` | Summary, tables (between the GENERATED markers, written by the script) and limitations |
| `stage_differences.png` | The figure: difference after each stage, (b, a) versus SOS |

## How to run

From the repository's top folder, in an environment where this repository is
installed (`python -m pip install -e .`, see the main README, "Maintenance").
No other packages are needed.

    python experiments/sensitivity/run_sensitivity.py --work-dir ../sensitivity_work

This took about 11 minutes on the computer listed in results.md. It rewrites the
tables in `results.md` and the figure, and saves every per-seed number as JSON
(`A_ba.json`, `A_sos.json`, `other_results.json`) in the work folder, which must
be outside the repository. The work folder also receives the two synthetic EDF
files. Without `--work-dir`, a folder in the system's temporary directory is used.

Options:

- `--seeds N`: perturbation seeds per condition (default 10). `--seeds 2
  --dose-seeds 1 --no-report` is a quick check (about 3 minutes) that leaves
  `results.md` untouched.
- `--no-report`: write only the JSON files.
- `--report-from-json`: do not compute; rebuild the tables and the figure from
  the JSON files in `--work-dir`.
- `--forms ba` and `--parts A`: run only the (b, a) form or only part A
  (parts B and D need both forms).

The seeds are fixed, so a second run on the same computer with the same
library versions gives byte-identical JSON files and the same tables.

## Optional: the same (b, a) numbers with the original code

The (b, a) part can also be run with the original NEURAL (commit 78c9425)
installed in a separate environment (as in the header of
`tests/make_reference.py`):

    python experiments/sensitivity/run_sensitivity.py --work-dir ../sensitivity_original --forms ba --parts A --no-report

Then pass its `A_ba.json` to a run with the maintained version (a full run or
`--report-from-json`):

    python experiments/sensitivity/run_sensitivity.py --work-dir ../sensitivity_work --report-from-json --original-json ../sensitivity_original/A_ba.json

The Checks table in results.md then says whether the two files are byte for
byte identical.

## How the filter switch works

`utils.filter_butterworth_withnans` designs each filter with
`scipy.signal.butter` and applies it with `mfiltfilt.mat_filtfilt`. While the
experiment runs, these two names inside NEURAL's `utils` module are replaced by
stand-ins:

- **SOS:** the stand-in for `butter` also designs the same filter with
  `output="sos"`; the stand-in for `mat_filtfilt` then applies that SOS filter
  forwards and backwards with mat_filtfilt's edge handling (same padding
  length, odd reflection, steady-state initial conditions from
  `scipy.signal.sosfilt_zi`).
- **Coefficients:** the stand-in for `butter` returns the (b, a) coefficients
  with every coefficient moved by one unit in the last place (a[0] stays 1).

Everything else (NaN handling, padding, all calling functions) is NEURAL's own
code. The script checks that the stand-ins in (b, a) mode change nothing and
that in SOS mode no (b, a) filtering is left.
