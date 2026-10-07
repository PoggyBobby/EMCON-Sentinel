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
            expected = hashlib.sha256(source.read_bytes()).hexdigest()
            url = "https://repo.maven.apache.org/maven2/fixture/artifact.jar"
            from unittest.mock import patch
            import io
            with patch.object(module.urllib.request, "urlopen",
                              return_value=io.BytesIO(source.read_bytes())):
                module.download_verified(url, destination, expected)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            destination.write_bytes(b"corrupt cache")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                module.download_verified(url, destination, expected)
            bad = Path(folder) / "bad.jar"
            with patch.object(module.urllib.request, "urlopen",
                              return_value=io.BytesIO(source.read_bytes())):
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    module.download_verified(url, bad, "0" * 64)
            self.assertFalse(bad.exists())


class ArtifactValidationTests(unittest.TestCase):
    def test_download_is_bounded_and_cache_install_is_atomic(self):
        import hashlib
        import io
        from unittest.mock import patch
        module = runner()
        url = "https://repo.maven.apache.org/maven2/fixture/artifact.jar"
        data = b"verified fixture bytes"
        expected = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            destination = Path(folder) / "artifact.jar"

            class ObservedStream(io.BytesIO):
                def read(self, size=-1):
                    self.assert_bounded(size)
                    return super().read(size)

                def assert_bounded(self, size):
                    if size < 0:
                        raise AssertionError("download must use bounded reads")
                    if destination.exists():
                        raise AssertionError("unverified destination became visible")

            with patch.object(module.urllib.request, "urlopen", return_value=ObservedStream(data)):
                module.download_verified(url, destination, expected)
            self.assertEqual(destination.read_bytes(), data)
            destination.unlink()
            with patch.object(module, "MAX_ARTIFACT_BYTES", 8, create=True), patch.object(
                    module.urllib.request, "urlopen", return_value=io.BytesIO(data)):
                with self.assertRaisesRegex(ValueError, "size limit"):
                    module.download_verified(url, destination, expected)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_redirect_away_from_reviewed_url_and_symlinked_cache_fail_closed(self):
        import hashlib
        import io
        from unittest.mock import patch
        module = runner()
        url = "https://repo.maven.apache.org/maven2/fixture/artifact.jar"
        data = b"verified fixture bytes"
        expected = hashlib.sha256(data).hexdigest()

        class Redirected(io.BytesIO):
            def geturl(self):
                return "http://mirror.example/artifact.jar"

        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            destination = Path(folder) / "artifact.jar"
            with patch.object(module.urllib.request, "urlopen", return_value=Redirected(data)):
                with self.assertRaisesRegex(ValueError, "URL"):
                    module.download_verified(url, destination, expected)
            self.assertEqual(list(Path(folder).iterdir()), [])
            target = Path(folder) / "elsewhere.jar"
            target.write_bytes(data)
            destination.symlink_to(target)
            with patch.object(module.urllib.request, "urlopen") as fetch:
                with self.assertRaisesRegex(ValueError, "symlink"):
                    module.download_verified(url, destination, expected)
                fetch.assert_not_called()

    def test_download_timeout_is_bounded_and_leaves_no_partial_cache(self):
        import hashlib
        import io
        import socket
        from unittest.mock import patch
        module = runner()
        url = "https://repo.maven.apache.org/maven2/fixture/artifact.jar"
        expected = hashlib.sha256(b"complete").hexdigest()

        class Stalls(io.BytesIO):
            def read(self, *args):
                if self.tell():
                    raise socket.timeout("read timed out")
                return super().read(4)

        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            destination = Path(folder) / "artifact.jar"
            stale = Path(folder) / ".download-interrupted"
            stale.write_bytes(b"complete")  # stale partial from a prior run is never trusted
            with patch.object(module.urllib.request, "urlopen",
                              return_value=Stalls(b"complete")) as fetch:
                with self.assertRaises(socket.timeout):
                    module.download_verified(url, destination, expected)
            timeout = fetch.call_args.kwargs.get("timeout")
            self.assertIsNotNone(timeout, "network reads require an explicit timeout")
            self.assertLessEqual(timeout, 60)
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), [stale.name])

    def test_unreviewed_urls_and_malformed_sha256_fail_before_io(self):
        from unittest.mock import patch
        module = runner()
        good = "https://repo.maven.apache.org/maven2/fixture/artifact.jar"
        urls = ["http://repo.maven.apache.org/maven2/a.jar", "file:///a.jar",
                "https://evil.example/a.jar", "https://user@repo.maven.apache.org/maven2/a.jar",
                good + "#fragment", good + "?query=1",
                "https://repo.maven.apache.org:444/maven2/a.jar",
                "https://repo.maven.apache.org/maven2/../a.jar",
                "https://repo.maven.apache.org/maven2/%2e%2e/a.jar",
                "https://repo.maven.apache.org/maven2/a%2fb.jar"]
        cases = [(url, "a" * 64) for url in urls]
        cases += [(good, digest) for digest in ("a" * 40, "g" * 64, "a" * 65, "", None, 123)]
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            destination = Path(folder) / "unused/cache.jar"
            for url, digest in cases:
                with self.subTest(url=url, digest=digest), patch.object(
                        module.urllib.request, "urlopen", return_value=__import__("io").BytesIO(b"fixture")) as fetch:
                    with self.assertRaisesRegex(ValueError, "URL|SHA-256"):
                        module.download_verified(url, destination, digest)
                    fetch.assert_not_called()
                    self.assertFalse(destination.parent.exists())


class ManifestSchemaTests(unittest.TestCase):
    GOOD = {"url": "https://repo.maven.apache.org/maven2/fixture/a/1/a-1.jar",
            "sha256": "a" * 64, "sha1": "b" * 40}

    def write_dependencies(self, root, value):
        (root / "verification").mkdir(exist_ok=True)
        (root / "verification/dependencies.json").write_text(json.dumps(value))

    def test_repository_lock_pins_sha256_for_every_reviewed_dependency(self):
        dependencies = runner().load_dependencies(ROOT)
        self.assertEqual([d["url"].rsplit("/", 1)[1] for d in dependencies],
                         ["junit-4.13.2.jar", "hamcrest-core-1.3.jar", "gson-2.10.1.jar"])
        for dependency in dependencies:
            self.assertRegex(dependency["sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(dependency["sha1"], r"^[0-9a-f]{40}$")

    def test_malformed_dependency_lock_fails_closed(self):
        other = dict(self.GOOD, url=self.GOOD["url"].replace("fixture/a", "other/a"))
        cases = {"not a list": {"url": self.GOOD["url"]}, "empty": [], "scalar item": ["x"],
                 "missing sha256": [{"url": self.GOOD["url"], "sha1": "b" * 40}],
                 "unknown key": [dict(self.GOOD, mirror="https://example.com")],
                 "bad sha1 provenance": [dict(self.GOOD, sha1="z" * 40)],
                 "uppercase digest": [dict(self.GOOD, sha256="A" * 64)],
                 "duplicate cache name": [self.GOOD, other],
                 "plain HTTP": [dict(self.GOOD, url=self.GOOD["url"].replace("https", "http"))]}
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            root = Path(folder)
            self.write_dependencies(root, [self.GOOD])
            self.assertEqual(runner().load_dependencies(root), [self.GOOD])
            for name, value in cases.items():
                with self.subTest(name):
                    self.write_dependencies(root, value)
                    with self.assertRaisesRegex(ValueError, "dependenc|SHA|URL"):
                        runner().load_dependencies(root)
            (root / "verification/dependencies.json").write_text("{not json")
            with self.assertRaisesRegex(ValueError, "dependenc"):
                runner().load_dependencies(root)

    def make_repo(self, folder):
        root = Path(folder)
        (root / "verification").mkdir(parents=True)
        tests = root / "plugin/app/src/test/java"
        main = root / "plugin/app/src/main/java"
        tests.mkdir(parents=True)
        main.mkdir(parents=True)
        (tests / "OkTest.java").write_text("class OkTest {}")
        (main / "Ok.java").write_text("class Ok {}")
        return root

    def write_manifest(self, root, **changes):
        manifest = {"included_tests": ["OkTest.java"], "excluded_tests": {},
                    "included_sources": ["Ok.java"]}
        manifest.update(changes)
        (root / "verification/java-tests.json").write_text(json.dumps(manifest))

    def test_manifest_paths_cannot_escape_source_roots(self):
        cases = {"parent test": {"included_tests": ["../OkTest.java"]},
                 "absolute test": {"included_tests": ["/tmp/OkTest.java"]},
                 "dot segment": {"included_tests": ["./OkTest.java"]},
                 "backslash": {"included_tests": ["a\\OkTest.java"]},
                 "non-java": {"included_tests": ["OkTest.txt"]},
                 "non-string": {"included_tests": [7]},
                 "parent source": {"included_sources": ["../../main/java/Ok.java"]},
                 "missing source": {"included_sources": ["Missing.java"]},
                 "duplicate source": {"included_sources": ["Ok.java", "Ok.java"]},
                 "excluded list": {"excluded_tests": []},
                 "sources null": {"included_sources": None},
                 "unknown key": {"extra": True}}
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            root = self.make_repo(folder)
            self.write_manifest(root)
            self.assertEqual(runner().inventory(root), (["OkTest.java"], {}))
            for name, changes in cases.items():
                with self.subTest(name):
                    self.write_manifest(root, **changes)
                    with self.assertRaisesRegex(ValueError, "manifest|unaccounted"):
                        runner().inventory(root)

    def test_symlinked_test_or_source_outside_roots_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder, \
                tempfile.TemporaryDirectory(dir=SCRATCH) as outside:
            (Path(outside) / "Escape.java").write_text("class Escape {}")
            for kind in ("test", "main"):
                with self.subTest(kind):
                    root = self.make_repo(Path(folder) / kind)
                    link = root / "plugin/app/src" / kind / "java/Escape.java"
                    link.symlink_to(Path(outside) / "Escape.java")
                    if kind == "test":
                        self.write_manifest(root, included_tests=["OkTest.java", "Escape.java"])
                    else:
                        self.write_manifest(root, included_sources=["Ok.java", "Escape.java"])
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        runner().inventory(root)


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
        for field, value in (("excluded_tests", []), ("included_tests", None),
                             ("included_sources", None)):
            with self.subTest(field=field):
                manifest = json.loads(manifest_bytes)
                manifest[field] = value
                self.manifest.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, "manifest"):
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
        # Real cached-artifact SHA-256 rejection, before any compiler invocation.
        dependencies = json.loads((ROOT / "verification/dependencies.json").read_text())
        (self.root / "verification/dependencies.json").write_text(json.dumps([
            dict(dependencies[0], sha256="0" * 64)]))
        cached = self.cache / dependencies[0]["url"].rsplit("/", 1)[1]
        cached_bytes = cached.read_bytes()
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
        self.assertEqual(cached.read_bytes(), cached_bytes, "mismatch must not rewrite cache")


if __name__ == "__main__":
    unittest.main()
