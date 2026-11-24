"""Guard runner-made original outputs against the committed reference values.

Run: python tests/check_reference_drift.py <committed folder> <runner folder>
Exit 0 means within the drift limit; exit 1 means drift or unusable references;
argparse returns 2 for incorrect arguments. This does not import NEURAL or its
test helpers: a bug shared by generation and pytest must not change this check.

The separate drift limit is 1e-12 + 1e-5 * abs(committed). The reported 1e-8
GitHub drift is a lower bound: failing comparisons stopped before per-epoch
arrays. A simulation adding 1-4 ULP noise to preprocessed EEG and rerunning
the feature pipeline estimates per-epoch drift up to about 4e-7 relative,
giving about 25 times headroom. Differences in the runner environment can
affect rounding; the exact cause of the GitHub differences is not determined.
The absolute floor stays at the existing tests' 1e-12; no larger absolute drift
has been established near zero. Shared changes smaller than about 1e-5 relative
can escape; new environments may still be flagged for investigation. This
does not alter pytest's tolerance.
All structures and discrete values must match exactly. Only made_with.os and
made_with.python may differ without failing; those changes are always printed.
Reports include the first 20 errors, every structural/discrete error, and the
worst numeric breach measured as a multiple of its allowed absolute difference.
NaN is null and infinity is text in this JSON format. Windows references are
excluded here because they cannot be regenerated with the modern libraries.
"""
import argparse
import json
import math
from pathlib import Path

FILES = ("reference_clean.json", "reference_artefacts.json",
         "reference_edge_cases.json", "reference_input_types.json")
RTOL = 1e-5
ATOL = 1e-12
VARIABLE_METADATA = {("made_with", "os"), ("made_with", "python")}


def location(path):
    return "$" + "".join("[%s]" % json.dumps(key) for key in path)


def reject_constant(value):
    raise ValueError("invalid JSON constant: " + value)


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def load(path):
    return json.loads(path.read_text(encoding="utf-8"),
                      parse_constant=reject_constant, object_pairs_hook=unique_keys)


class Drift:
    def __init__(self):
        self.floats = 0
        self.changed = 0
        self.outside = 0
        self.errors = 0
        self.details = []
        self.required_details = []
        self.environment = []
        self.absolute = None
        self.relative = None
        self.worst_breach = None
        self.worst_detail = None

    def fail(self, path, reason, required=True):
        self.errors += 1
        detail = "%s: %s" % (location(path), reason)
        if len(self.details) < 20:
            self.details.append(detail)
        if required:
            self.required_details.append(detail)
        return detail

    def compare(self, committed, runner, path=()):
        if type(committed) is not type(runner):
            if committed is None or runner is None:
                self.fail(path, "NaN in only one file")
            else:
                self.fail(path, "types differ: %s vs %s" %
                          (type(committed).__name__, type(runner).__name__))
        elif isinstance(committed, dict):
            missing = sorted(committed.keys() - runner.keys())
            added = sorted(runner.keys() - committed.keys())
            if missing or added:
                self.fail(path, "keys differ: missing %r, added %r" % (missing, added))
            for key in committed:
                if key in runner:
                    self.compare(committed[key], runner[key], path + (key,))
        elif isinstance(committed, list):
            if len(committed) != len(runner):
                self.fail(path, "list lengths differ: %d vs %d" % (len(committed), len(runner)))
            for index, (old, new) in enumerate(zip(committed, runner)):
                self.compare(old, new, path + (index,))
        elif isinstance(committed, float):
            if not (math.isfinite(committed) and math.isfinite(runner)):
                self.fail(path, "nonfinite number; use null or infinity strings")
                return
            self.floats += 1
            difference = abs(runner - committed)
            if difference == 0:
                return
            self.changed += 1
            entry = (difference, path, committed, runner)
            if self.absolute is None or difference > self.absolute[0]:
                self.absolute = entry
            if committed != 0:
                relative = difference / abs(committed)
                if self.relative is None or relative > self.relative[0]:
                    self.relative = (relative, path, committed, runner)
            limit = ATOL + RTOL * abs(committed)
            if difference > limit:
                self.outside += 1
                detail = self.fail(path, "outside drift limit: committed %r, runner %r" %
                                   (committed, runner), required=False)
                multiple = difference / limit
                if self.worst_breach is None or multiple > self.worst_breach[0]:
                    self.worst_breach = (multiple, path, committed, runner)
                    self.worst_detail = detail
        elif path in VARIABLE_METADATA and isinstance(committed, str):
            if committed != runner:
                self.environment.append("%s: committed %r, runner %r" % (location(path), committed, runner))
        elif committed != runner:
            self.fail(path, "values differ: committed %r, runner %r" % (committed, runner))


def peak(entry):
    if entry is None:
        return "0"
    value, path, old, new = entry
    return "%.3e at %s (committed %r, runner %r)" % (value, location(path), old, new)


def check_file(name, committed_folder, runner_folder):
    found = Drift()
    print("\n" + name)
    try:
        committed = load(committed_folder / name)
        runner = load(runner_folder / name)
        found.compare(committed, runner)
        if found.floats == 0:
            found.fail((), "no finite floating-point values compared")
    except (OSError, ValueError, UnicodeError) as error:
        found.fail((), "cannot compare references: %s" % error)
    for change in found.environment:
        print("  environment: " + change)
    print("  floats=%d, changed=%d, outside_limit=%d, errors=%d" %
          (found.floats, found.changed, found.outside, found.errors))
    print("  largest absolute drift: " + peak(found.absolute))
    print("  largest relative drift (nonzero committed values): " + peak(found.relative))
    if found.worst_breach is not None:
        print("  worst numeric breach (multiple of limit): " + peak(found.worst_breach))
    details = found.details + found.required_details
    if found.worst_detail is not None:
        details.append(found.worst_detail)
    printed = set()
    for detail in details:
        if detail not in printed:
            print("  ERROR " + detail)
            printed.add(detail)
    if found.errors > len(printed):
        print("  ... %d more errors" % (found.errors - len(printed)))
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("committed_folder", type=Path)
    parser.add_argument("runner_folder", type=Path)
    args = parser.parse_args(argv)
    print("Reference drift limit: |runner - committed| <= 1e-12 + 1e-5 * |committed|")
    print("Structures, NaN positions and discrete values must match exactly.")
    print("Only OS and Python version metadata may differ; changes are printed.")
    results = [check_file(name, args.committed_folder, args.runner_folder) for name in FILES]
    errors = sum(result.errors for result in results)
    print("\nREFERENCE DRIFT %s: %d floats checked across %d files; %d errors" %
          ("FAILED" if errors else "PASSED", sum(result.floats for result in results), len(FILES), errors))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
