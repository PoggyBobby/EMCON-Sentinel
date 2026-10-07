"""Tests for generic JVM verification infrastructure (never product behavior)."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/test_java.py"
SCRATCH = Path(os.environ.get("JAVA_TEST_SCRATCH", str(Path.home() / ".hermes/cache/scratch")))
SCRATCH.mkdir(parents=True, exist_ok=True)


def runner():
    spec = importlib.util.spec_from_file_location("test_java_runner", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InventoryTests(unittest.TestCase):
    def test_existing_tests_are_all_explicitly_accounted_for(self):
        self.assertTrue(SCRIPT.is_file(), "SDK-independent runner is missing")
        included, excluded = runner().inventory(ROOT)
        actual = sorted(str(p.relative_to(ROOT / "plugin/app/src/test/java"))
                        for p in (ROOT / "plugin/app/src/test/java").rglob("*.java"))
        self.assertEqual(sorted(included + list(excluded)), actual)
        self.assertEqual(len(included), 14)
        self.assertEqual(excluded, {})

    def test_unaccounted_test_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            root = Path(folder)
            (root / "verification").mkdir()
            (root / "verification/java-tests.json").write_text(json.dumps({
                "included_tests": [], "excluded_tests": {}, "included_sources": []}))
            tests = root / "plugin/app/src/test/java"
            tests.mkdir(parents=True)
            (tests / "NewTest.java").write_text("class NewTest {}")
            with self.assertRaisesRegex(ValueError, "unaccounted.*NewTest"):
                runner().inventory(root)


    def test_empty_included_suite_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            root = Path(folder)
            (root / "verification").mkdir()
            (root / "plugin/app/src/test/java").mkdir(parents=True)
            (root / "verification/java-tests.json").write_text(json.dumps({
                "included_tests": [], "excluded_tests": {}, "included_sources": []}))
            with self.assertRaisesRegex(ValueError, "no included tests"):
                runner().inventory(root)


class ArtifactTests(unittest.TestCase):
    def test_download_verifies_bytes_before_installing(self):
        import hashlib
        module = runner()
        self.assertTrue(callable(getattr(module, "download_verified", None)),
                        "verified artifact download is missing")
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            source = Path(folder) / "source.jar"
            destination = Path(folder) / "cache/artifact.jar"
            source.write_bytes(b"verified fixture bytes")
            expected = hashlib.sha1(source.read_bytes()).hexdigest()
            module.download_verified(source.as_uri(), destination, expected)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            destination.write_bytes(b"corrupt cache")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                module.download_verified(source.as_uri(), destination, expected)
            bad = Path(folder) / "bad.jar"
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                module.download_verified(source.as_uri(), bad, "0" * 40)
            self.assertFalse(bad.exists())


class CliTests(unittest.TestCase):
    def test_list_is_real_cli_output_without_an_sdk(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, str(SCRIPT), "--list"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn('"included_tests"', result.stdout,
                      "CLI must enumerate coverage instead of silently exiting")
        self.assertEqual(len(json.loads(result.stdout)["included_tests"]), 14)

    def test_missing_jdk_fails_instead_of_silently_skipping(self):
        import subprocess
        import sys
        env = dict(os.environ)
        env.pop("JAVA_HOME", None)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            env["JAVA_TEST_REPORT_DIR"] = folder
            result = subprocess.run([sys.executable, str(SCRIPT)], env=env,
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("JDK 17", result.stderr)
            self.assertEqual(json.loads((Path(folder) / "summary.json").read_text())["status"],
                             "failed")


class ExecutionTests(unittest.TestCase):
    def test_real_junit_compiles_current_sources_and_reports_provenance(self):
        module = runner()
        self.assertTrue(callable(getattr(module, "run_suite", None)),
                        "actual compiler/JUnit execution is missing")
        java_home = os.environ.get("JAVA_HOME")
        if not java_home:
            self.skipTest("JAVA_HOME must point to JDK 17 for execution tests")
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            root = Path(folder)
            (root / "verification").mkdir()
            (root / "verification/java-tests.json").write_text(json.dumps({
                "included_tests": ["HelloTest.java"], "excluded_tests": {},
                "included_sources": ["Hello.java"]}))
            (root / "verification/dependencies.json").write_bytes(
                (ROOT / "verification/dependencies.json").read_bytes())
            main = root / "plugin/app/src/main/java"
            tests = root / "plugin/app/src/test/java"
            main.mkdir(parents=True)
            tests.mkdir(parents=True)
            (main / "Hello.java").write_text(
                "public class Hello { public static int value() { return 7; } }")
            (tests / "HelloTest.java").write_text(
                "import org.junit.Test; import static org.junit.Assert.*; "
                "public class HelloTest { @Test public void value() { "
                "assertEquals(7, Hello.value()); } }")
            reports = root / "reports"
            cache = Path(os.environ.get("JAVA_TEST_CACHE", str(root / "dependencies")))
            self.assertEqual(module.run_suite(root, Path(java_home), cache, reports), 0)
            report = json.loads((reports / "summary.json").read_text())
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["tests_run"], 1)
            self.assertIn("java_version", report, "report must identify actual JDK used")
            self.assertIn('"17.', report["java_version"])
            self.assertEqual(report["test_classes"][0]["class"], "HelloTest")
            import hashlib
            self.assertEqual(report["inputs_sha256"]["plugin/app/src/main/java/Hello.java"],
                             hashlib.sha256((main / "Hello.java").read_bytes()).hexdigest())
            self.assertTrue((reports / report["compile_log"]).is_file())
            self.assertIn("OK (1 test)",
                          (reports / report["test_classes"][0]["log"]).read_text())
            import subprocess
            import sys
            cli_reports = root / "cli-reports"
            cli = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(root),
                                  "--java-home", java_home, "--cache-dir", str(cache),
                                  "--report-dir", str(cli_reports)],
                                 capture_output=True, text=True, check=False)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertIn("OK (1 test)", cli.stdout, "CLI must actually execute JUnit")
            self.assertEqual(json.loads((cli_reports / "summary.json").read_text())["tests_run"], 1)
            # Change only infrastructure-fixture source, not its assertions.
            # A second run must recompile rather than reuse stale passing classes.
            (main / "Hello.java").write_text(
                "public class Hello { public static int value() { return 8; } }")
            self.assertEqual(module.run_suite(root, Path(java_home), cache, reports), 1)
            failed = json.loads((reports / "summary.json").read_text())
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["tests_run"], 1)
            self.assertIn("FAILURES!!!",
                          (reports / failed["test_classes"][0]["log"]).read_text())
            (main / "Hello.java").write_text("this does not compile")
            try:
                exit_code = module.run_suite(root, Path(java_home), cache, reports)
            except Exception as error:
                self.fail("compiler failure must return nonzero and retain a failure report: " + str(error))
            self.assertEqual(exit_code, 1)
            failed = json.loads((reports / "summary.json").read_text())
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["tests_run"], 0)
            self.assertEqual(failed["test_classes"], [])
            # Only this run's evidence may be referenced, even after old success/failure logs.
            self.assertIn("run_dir", failed, "summary must isolate current-run evidence")
            self.assertNotEqual(failed["run_dir"], report["run_dir"])
            self.assertEqual(json.loads((reports / failed["run_dir"] / "summary.json").read_text()),
                             failed)
            self.assertIn("error:", (reports / failed["compile_log"]).read_text())
            self.assertEqual(set(p.name for p in (reports / failed["run_dir"]).glob("*.log")),
                             {"compile.log"})
            self.assertIn("OK (1 test)",
                          (reports / report["test_classes"][0]["log"]).read_text())


class FailureReportTests(unittest.TestCase):
    def setUp(self):
        java_home = os.environ.get("JAVA_HOME")
        if not java_home:
            self.skipTest("JAVA_HOME must point to JDK 17 for execution tests")
        temporary = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.java_home = Path(java_home)
        self.cache = Path(os.environ.get("JAVA_TEST_CACHE", str(self.root / "cache")))
        self.reports = self.root / "reports"
        self.module = runner()
        (self.root / "verification").mkdir()
        self.manifest = self.root / "verification/java-tests.json"
        self.manifest.write_text(json.dumps({"included_tests": ["FirstTest.java", "LastTest.java"],
                                             "excluded_tests": {}, "included_sources": []}))
        (self.root / "verification/dependencies.json").write_bytes(
            (ROOT / "verification/dependencies.json").read_bytes())
        self.tests = self.root / "plugin/app/src/test/java"
        self.tests.mkdir(parents=True)
        (self.root / "plugin/app/src/main/java").mkdir(parents=True)
        for name in ("FirstTest", "LastTest"):
            (self.tests / (name + ".java")).write_text(
                "import org.junit.Test; public class " + name +
                " { @Test public void works() {} }")
        self.assertEqual(self.run_direct(), 0)
        self.previous = self.summary()
        # Legacy artifacts and unrelated user data must not be deleted or referenced.
        (self.reports / "compile.log").write_text("legacy compiler output")
        (self.reports / "LastTest.log").write_text("legacy OK (99 tests)")
        (self.reports / "keep.txt").write_text("unrelated user data")

    def run_direct(self, java_home=None):
        return self.module.run_suite(self.root, java_home or self.java_home,
                                     self.cache, self.reports)

    def summary(self):
        return json.loads((self.reports / "summary.json").read_text())

    def assert_current_failure(self):
        report = self.summary()
        self.assertEqual(report["status"], "failed")
        self.assertNotEqual(report["run_dir"], self.previous["run_dir"])
        self.assertEqual(json.loads((self.reports / report["run_dir"] / "summary.json").read_text()),
                         report)
        self.assertEqual((self.reports / "keep.txt").read_text(), "unrelated user data")
        self.assertEqual((self.reports / "compile.log").read_text(), "legacy compiler output")
        self.assertEqual((self.reports / "LastTest.log").read_text(), "legacy OK (99 tests)")
        self.assertIn("OK (1 test)",
                      (self.reports / self.previous["test_classes"][0]["log"]).read_text())
        for entry in report["test_classes"]:
            self.assertEqual(Path(entry["log"]).parent.as_posix(), report["run_dir"])
        if "compile_log" in report:
            self.assertEqual(Path(report["compile_log"]).parent.as_posix(), report["run_dir"])
        return report

    def test_junit_timeout_preserves_current_partial_results_for_direct_and_cli_calls(self):
        import subprocess
        from unittest.mock import patch
        (self.tests / "LastTest.java").write_text(
            "import org.junit.Test; public class LastTest { "
            "@Test public void waits() throws Exception { "
            'System.out.println("current timeout output"); System.out.flush(); '
            "Thread.sleep(20000); } }")
        (self.tests / "AfterTest.java").write_text(
            "import org.junit.Test; public class AfterTest { @Test public void works() {} }")
        manifest = json.loads(self.manifest.read_text())
        manifest["included_tests"].append("AfterTest.java")
        self.manifest.write_text(json.dumps(manifest))
        real_run = subprocess.run

        def shortened_timeout(command, **kwargs):
            # Execute real javac and JUnit; only shorten the last class's deadline.
            if command[-1] == "LastTest":
                kwargs["timeout"] = 0.75
            return real_run(command, **kwargs)

        for direct in (True, False):
            with self.subTest(direct=direct), patch.object(self.module.subprocess, "run",
                                                        side_effect=shortened_timeout):
                if direct:
                    with self.assertRaises(subprocess.TimeoutExpired):
                        self.run_direct()
                else:
                    self.assertEqual(self.module.main([
                        "--repo", str(self.root), "--java-home", str(self.java_home),
                        "--cache-dir", str(self.cache), "--report-dir", str(self.reports)]), 1)
            report = self.assert_current_failure()
            self.assertEqual(report["tests_run"], 1)
            self.assertEqual([entry["class"] for entry in report["test_classes"]],
                             ["FirstTest", "LastTest"])
            first, last = report["test_classes"]
            self.assertEqual(first["status"], "passed")
            self.assertEqual(last["status"], "timed_out")
            self.assertIsNone(last["exit_code"])
            self.assertEqual(last["tests_run"], 0)
            self.assertIn("OK (1 test)", (self.reports / first["log"]).read_text())
            self.assertIn("current timeout output", (self.reports / last["log"]).read_text())
            self.assertNotIn("OK (", (self.reports / last["log"]).read_text())
            self.assertIn("AfterTest.java", report["included_tests"])
            self.assertFalse((self.reports / report["run_dir"] / "AfterTest.log").exists())

    def test_compiler_timeout_references_no_previous_compiler_or_class_logs(self):
        import subprocess
        from unittest.mock import patch
        real_run = subprocess.run

        def shortened_timeout(command, **kwargs):
            if "--release" in command:
                kwargs["timeout"] = 0.001
            return real_run(command, **kwargs)

        with patch.object(self.module.subprocess, "run", side_effect=shortened_timeout):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_direct()
        report = self.assert_current_failure()
        self.assertIn("compile_log", report, "even a timed-out compiler needs current-run evidence")
        self.assertEqual(report["compile_status"], "timed_out")
        self.assertIsNone(report["compile_exit_code"])
        self.assertTrue((self.reports / report["compile_log"]).is_file())
        self.assertNotIn("legacy", (self.reports / report["compile_log"]).read_text())
        self.assertEqual(report["tests_run"], 0)
        self.assertEqual(report["test_classes"], [])
        self.assertEqual(set(p.name for p in (self.reports / report["run_dir"]).glob("*.log")),
                         {"compile.log"})

    def run_cli(self, *extra, without_java_home=False):
        import subprocess
        import sys
        environment = dict(os.environ)
        if without_java_home:
            environment.pop("JAVA_HOME", None)
        return subprocess.run([
            sys.executable, str(SCRIPT), "--repo", str(self.root),
            "--cache-dir", str(self.cache), "--report-dir", str(self.reports), *extra],
            env=environment, capture_output=True, text=True, timeout=30, check=False)

    def test_real_cli_compiler_failure_has_only_current_compile_evidence(self):
        (self.tests / "LastTest.java").write_text("this cannot compile")
        result = self.run_cli("--java-home", str(self.java_home))
        self.assertEqual(result.returncode, 1, result.stderr)
        report = self.assert_current_failure()
        self.assertEqual(report["compile_status"], "failed")
        self.assertNotEqual(report["compile_exit_code"], 0)
        self.assertIn("error:", (self.reports / report["compile_log"]).read_text())
        self.assertEqual(report["test_classes"], [])
        self.assertEqual(report["tests_run"], 0)

    def test_real_cli_assertion_failure_keeps_successful_class_results(self):
        (self.tests / "LastTest.java").write_text(
            "import org.junit.Test; public class LastTest { "
            '@Test public void fails() { throw new AssertionError("current failure"); } }')
        result = self.run_cli("--java-home", str(self.java_home))
        self.assertEqual(result.returncode, 1, result.stderr)
        report = self.assert_current_failure()
        self.assertEqual(report["tests_run"], 2)
        first, last = report["test_classes"]
        self.assertEqual(first["status"], "passed")
        self.assertEqual(last["status"], "failed")
        self.assertIn("current failure", (self.reports / last["log"]).read_text())

    def test_removed_inventory_class_has_no_current_log(self):
        (self.tests / "LastTest.java").unlink()
        manifest = json.loads(self.manifest.read_text())
        manifest["included_tests"].remove("LastTest.java")
        self.manifest.write_text(json.dumps(manifest))
        self.assertEqual(self.run_direct(), 0)
        report = self.summary()
        self.assertEqual(report["status"], "passed")
        self.assertNotEqual(report["run_dir"], self.previous["run_dir"])
        self.assertEqual(report["included_tests"], ["FirstTest.java"])
        self.assertEqual([entry["class"] for entry in report["test_classes"]], ["FirstTest"])
        self.assertEqual(set(p.name for p in (self.reports / report["run_dir"]).glob("*.log")),
                         {"compile.log", "FirstTest.log"})
        self.assertTrue((self.reports / self.previous["test_classes"][1]["log"]).is_file())

    def test_real_bootstrap_errors_fail_closed_for_direct_and_cli_calls(self):
        manifest_bytes = self.manifest.read_bytes()
        for field, value, exception in (("excluded_tests", [], AttributeError),
                                        ("included_tests", None, TypeError),
                                        ("included_sources", None, TypeError)):
            with self.subTest(field=field):
                manifest = json.loads(manifest_bytes)
                manifest[field] = value
                self.manifest.write_text(json.dumps(manifest))
                with self.assertRaises(exception):
                    self.run_direct()
                self.assert_current_failure()
                result = self.run_cli("--java-home", str(self.java_home))
                self.assertEqual(result.returncode, 1, result.stderr)
                report = self.assert_current_failure()
                self.assertEqual(report["test_classes"], [])
                self.assertNotIn("compile_log", report)
        self.manifest.write_bytes(manifest_bytes)
        for extra, missing in ((("--java-home", str(self.root / "missing-jdk")), False),
                               ((), True)):
            with self.subTest(extra=extra, missing=missing):
                result = self.run_cli(*extra, without_java_home=missing)
                self.assertEqual(result.returncode, 1, result.stderr)
                report = self.assert_current_failure()
                self.assertEqual(report["tests_run"], 0)
                self.assertNotIn("compile_log", report)
        with self.assertRaisesRegex(ValueError, "JAVA_HOME"):
            self.module.run_suite(self.root, None, self.cache, self.reports)
        self.assert_current_failure()

    def test_list_inventory_failure_replaces_prior_passed_summary(self):
        (self.tests / "LastTest.java").unlink()
        result = self.run_cli("--list", without_java_home=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = self.assert_current_failure()
        self.assertIn("unaccounted or missing tests", report["error"])
        self.assertEqual(report["test_classes"], [])

    def test_direct_bootstrap_failure_cannot_retain_a_passed_report(self):
        # Real download/checksum rejection, before any compiler invocation.
        source = self.root / "bad.jar"
        source.write_bytes(b"checksum fixture")
        (self.root / "verification/dependencies.json").write_text(json.dumps([
            {"url": source.as_uri(), "sha1": "0" * 40}]))
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.run_direct()
        report = self.assert_current_failure()
        self.assertEqual(report["tests_run"], 0)
        self.assertEqual(report["test_classes"], [])
        self.assertNotIn("compile_log", report)
        self.assertEqual(list((self.reports / report["run_dir"]).glob("*.log")), [])
        self.assertIn("checksum mismatch", report["error"])
        result = self.run_cli("--java-home", str(self.java_home))
        self.assertEqual(result.returncode, 1, result.stderr)
        report = self.assert_current_failure()
        self.assertEqual(report["tests_run"], 0)
        self.assertNotIn("compile_log", report)


if __name__ == "__main__":
    unittest.main()
