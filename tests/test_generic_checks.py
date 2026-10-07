"""Runner tests use isolated synthetic projects, never developer configuration."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_generic.py"


class GenericChecksTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="generic-checks-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for suite in ("tests", "verification"):
            (self.root / suite).mkdir()
            (self.root / suite / "test_synthetic.py").write_text(
                "import unittest\nclass Synthetic(unittest.TestCase):\n"
                "    def test_fixture(self):\n        self.assertTrue(True)\n")
        (self.root / "scripts").mkdir()
        (self.root / "scripts/test_java.py").write_text(
            "import argparse, json\nfrom pathlib import Path\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('--report-dir', required=True)\n"
            "args = parser.parse_args()\n"
            "Path('observed.json').write_text(json.dumps(vars(args)))\n")

    def module(self):
        self.assertTrue(SCRIPT.is_file(), "generic entry point is not implemented")
        spec = importlib.util.spec_from_file_location("generic_checks_under_test", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def execute(self, **kwargs):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = self.module().run_checks(self.root, **kwargs)
        return result, output.getvalue()

    def test_entry_point_runs_both_python_suites_then_jvm_in_fresh_output(self):
        old = self.root / "verification/build/jvm/summary.json"
        old.parent.mkdir(parents=True)
        old.write_text('{"status": "passed", "SYNTHETIC_PRIVATE": true}')
        before = old.read_bytes()
        result, output = self.execute()
        self.assertEqual(result, 0, output)
        self.assertIn("generic: passed\ninfrastructure: passed\njvm: passed", output)
        self.assertIn("NOT Android/ATAK", output)
        observed = json.loads((self.root / "observed.json").read_text())
        report = Path(observed["report_dir"])
        self.assertTrue(report.is_absolute())
        self.assertNotEqual(report, old.parent)
        self.assertFalse(report.exists(), "private temporary evidence must be removed")
        self.assertEqual(old.read_bytes(), before)
        self.assertNotIn(str(self.root), output)
        self.assertNotIn("SYNTHETIC_PRIVATE", output)

    def test_early_test_failure_is_terminal_without_reusing_saved_success(self):
        (self.root / "tests/test_synthetic.py").write_text(
            "import unittest\nclass Synthetic(unittest.TestCase):\n"
            "    def test_fixture(self):\n        self.fail('SYNTHETIC_PRIVATE_FAILURE')\n")
        (self.root / "verification/test_synthetic.py").write_text(
            "from pathlib import Path\nPath('later-stage').write_text('unexpected')\n")
        saved = self.root / "dist/support-report.json"
        saved.parent.mkdir()
        saved.write_text('{"verification": {"jvm": {"status": "passed"}}}')
        before = (saved.read_bytes(), saved.stat().st_mtime_ns)
        result, output = self.execute()
        self.assertEqual(result, 1, output)
        self.assertEqual(output, "generic: failed\n" + self.module().BOUNDARY + "\n")
        self.assertFalse((self.root / "later-stage").exists())
        self.assertFalse((self.root / "observed.json").exists())
        self.assertEqual((saved.read_bytes(), saved.stat().st_mtime_ns), before)
        self.assertNotIn("SYNTHETIC_PRIVATE_FAILURE", output)

    def test_empty_python_suite_is_not_success(self):
        (self.root / "tests/test_synthetic.py").unlink()
        result, output = self.execute()
        self.assertEqual(result, 1, output)
        self.assertEqual(output, "generic: failed\n" + self.module().BOUNDARY + "\n")
        self.assertFalse((self.root / "observed.json").exists())

    def test_timed_out_child_is_terminal_without_raw_output(self):
        (self.root / "scripts/test_java.py").write_text(
            "import time\nprint('SYNTHETIC_PRIVATE_TIMEOUT', flush=True)\ntime.sleep(2)\n")
        module = self.module()
        output = io.StringIO()
        with mock.patch.object(module, "STAGE_TIMEOUT_SECONDS", 0.5, create=True), \
                contextlib.redirect_stdout(output):
            try:
                result = module.run_checks(self.root)
            except Exception:
                self.fail("child timeout must become a value-free terminal failure")
        self.assertEqual(result, 1, output.getvalue())
        self.assertEqual(output.getvalue(), "generic: passed\ninfrastructure: passed\njvm: failed\n"
                         + module.BOUNDARY + "\n")

    def test_unavailable_child_cwd_is_a_value_free_failure(self):
        module = self.module()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                result = module.run_checks(self.root / "SYNTHETIC_PRIVATE_MISSING")
            except OSError:
                self.fail("unavailable child must not raise a path-bearing exception")
        self.assertEqual(result, 1)
        self.assertEqual(output.getvalue(), "generic: failed\n" + module.BOUNDARY + "\n")

    def test_cli_scratch_failure_does_not_disclose_exception(self):
        module = self.module()
        output = io.StringIO()
        with mock.patch.object(module.tempfile, "TemporaryDirectory",
                               side_effect=OSError("SYNTHETIC_PRIVATE_SCRATCH")), \
                contextlib.redirect_stdout(output):
            try:
                result = module.main([])
            except OSError:
                self.fail("scratch failure must have a value-free CLI result")
        self.assertEqual(result, 1)
        self.assertEqual(output.getvalue(), "runner: failed\n" + module.BOUNDARY + "\n")

    def test_infrastructure_failure_does_not_execute_jvm(self):
        (self.root / "verification/test_synthetic.py").write_text(
            "import unittest\nclass Synthetic(unittest.TestCase):\n"
            "    def test_fixture(self):\n        self.fail('SYNTHETIC_PRIVATE_FAILURE')\n")
        result, output = self.execute()
        self.assertEqual(result, 1)
        self.assertEqual(output, "generic: passed\ninfrastructure: failed\n" + self.module().BOUNDARY + "\n")
        self.assertFalse((self.root / "observed.json").exists())

    def test_jvm_nonzero_exit_cannot_be_overridden_by_saved_success(self):
        (self.root / "scripts/test_java.py").write_text(
            "import sys\nprint('SYNTHETIC_PRIVATE_FAILURE')\nsys.exit(7)\n")
        result, output = self.execute()
        self.assertEqual(result, 1)
        self.assertEqual(output, "generic: passed\ninfrastructure: passed\njvm: failed\n"
                         + self.module().BOUNDARY + "\n")

    def test_repeated_runs_use_disjoint_private_jvm_directories(self):
        self.assertEqual(self.execute()[0], 0)
        first = json.loads((self.root / "observed.json").read_text())["report_dir"]
        self.assertEqual(self.execute()[0], 0)
        second = json.loads((self.root / "observed.json").read_text())["report_dir"]
        self.assertNotEqual(first, second)
        for value in (first, second):
            self.assertFalse(Path(value).parent.exists())

    def test_empty_infrastructure_suite_fails_before_jvm(self):
        (self.root / "verification/test_synthetic.py").unlink()
        result, output = self.execute()
        self.assertEqual(result, 1)
        self.assertEqual(output, "generic: passed\ninfrastructure: failed\n" + self.module().BOUNDARY + "\n")
        self.assertFalse((self.root / "observed.json").exists())

    def test_cli_success_uses_its_checkout_not_callers_cwd(self):
        module = self.module()
        output = io.StringIO()
        with mock.patch.object(module, "__file__", str(self.root / "scripts/check_generic.py")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(module.main([]), 0)
        self.assertIn("jvm: passed", output.getvalue())
        self.assertTrue((self.root / "observed.json").is_file())

    def test_real_cli_suppresses_child_output_and_ignores_python_environment(self):
        script = self.root / "scripts/check_generic.py"
        script.write_bytes(SCRIPT.read_bytes())
        (self.root / "scripts/test_java.py").write_text(
            "import sys\nprint('SYNTHETIC_PRIVATE_STDOUT')\n"
            "print('SYNTHETIC_PRIVATE_STDERR', file=sys.stderr)\nsys.exit(7)\n")
        poison = self.root / "poison"
        poison.mkdir()
        (poison / "sitecustomize.py").write_text("raise RuntimeError('SYNTHETIC_POISON')\n")
        result = subprocess.run([sys.executable, "-I", "-B", str(script)],
                                cwd=self.root / "tests", capture_output=True, text=True, timeout=30,
                                env={"PATH": os.defpath, "HOME": str(self.root / "no-home"),
                                     "TMPDIR": str(self.root), "PYTHONPATH": str(poison),
                                     "PYTHONSTARTUP": str(poison / "sitecustomize.py")})
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "generic: passed\ninfrastructure: passed\njvm: failed\n"
                         + self.module().BOUNDARY + "\n")
        self.assertEqual(result.stderr, "")
        self.assertFalse(list(self.root.glob("generic-checks-*")))


if __name__ == "__main__":
    unittest.main()
