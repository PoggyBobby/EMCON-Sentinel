#!/usr/bin/env python3
"""Execute generic tooling/infrastructure tests and the existing JVM subset."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

STAGE_TIMEOUT_SECONDS = 600
BOUNDARY = "Generic development checks only; NOT Android/ATAK, APK or device validation."
# Fixed bootstrap, never interpolated input. Discovery starts in the named suite
# (equivalent to -s), not -t .; empty suites must not count as successful checks.
PYTHON_SUITE = (
    "import sys, unittest; "
    "suite = unittest.defaultTestLoader.discover(start_dir=sys.argv[1], pattern='test_*.py'); "
    "sys.exit(1 if suite.countTestCases() == 0 else "
    "not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())"
)


def run_checks(root):
    """Trust this checkout's scripts/tests; use fresh, disposable JVM output."""
    with tempfile.TemporaryDirectory(prefix="generic-checks-") as folder:
        commands = (
            ("generic", [sys.executable, "-I", "-B", "-c", PYTHON_SUITE, "tests"]),
            ("infrastructure", [sys.executable, "-I", "-B", "-c", PYTHON_SUITE, "verification"]),
            ("jvm", [sys.executable, "-I", "-B", "scripts/test_java.py", "--report-dir", str(Path(folder) / "jvm")]),
        )
        for label, command in commands:
            try:
                result = subprocess.run(command, cwd=root, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, timeout=STAGE_TIMEOUT_SECONDS)
                passed = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                passed = False
            print(label + ": " + ("passed" if passed else "failed"), flush=True)
            if not passed:
                print(BOUNDARY, flush=True)
                return 1
        print(BOUNDARY, flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        return run_checks(Path(__file__).resolve().parents[1])
    except OSError:
        print("runner: failed", flush=True)
        print(BOUNDARY, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
