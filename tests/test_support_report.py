"""Isolated, generic fixtures; never consult developer configuration."""
import contextlib
import errno
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

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/support_report.py"


class SupportReportTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="support-report-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)

    def collector(self):
        self.assertTrue(SCRIPT.is_file(), "offline support collector is not implemented")
        spec = importlib.util.spec_from_file_location("support_report_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def fixture(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_jvm_summary_emits_only_status_counts(self):
        secret = "SYNTHETIC_PASSWORD=never-share-me"
        self.fixture("verification/build/jvm/summary.json", {
            "status": "passed", "tests_run": 3,
            "test_classes": [{"status": "passed", "tests_run": 3,
                              "class": secret, "log": "/private/keys/raw.log"}],
            "commands": ["/Users/private/bin/java", secret],
            "error": "GPS=37.421999,-122.084057\u001b[31m " + secret,
        })
        report = self.collector().collect(self.root)
        self.assertEqual(report["verification"]["jvm"], {
            "status": "passed", "tests_run": 3, "class_count": 1,
        })
        serialized = json.dumps(report)
        for forbidden in (secret, "/Users/", "/private/", "GPS", "37.421999", "122.084057", "\\u001b"):
            self.assertNotIn(forbidden, serialized)

    VALID_JVM = {"status": "passed", "tests_run": 1,
                 "test_classes": [{"status": "passed", "tests_run": 1}]}

    def jvm_status(self, payload):
        path = self.root / "verification/build/jvm/summary.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        report = self.collector().collect(self.root)
        return report, report["verification"]["jvm"]

    def test_malformed_or_malicious_jvm_summary_fails_closed(self):
        secret = "SYNTHETIC_TOKEN_ghp_000000000000000000000000000000000000"
        valid = self.VALID_JVM
        base = json.dumps(valid).encode()
        self.assertEqual(self.jvm_status(base)[1],
                         {"status": "passed", "tests_run": 1, "class_count": 1},
                         "base fixture must be a genuinely valid passing summary")

        def both_counts(value):
            return json.dumps(dict(valid, tests_run=value, test_classes=[
                {"status": "passed", "tests_run": value}])).encode()

        def with_extra(raw):
            return base[:-1] + b', "extra": ' + raw + b"}"

        # Each payload is the valid base with exactly one defect, so it would be
        # reported as passed if the protection under test were removed.
        cases = {
            "invalid_json": b"{not json " + secret.encode(),
            "non_utf8": with_extra(b'"\xff' + secret.encode() + b'"'),
            "not_object": json.dumps([valid, secret]).encode(),
            "unknown_status": json.dumps(dict(valid, status=secret)).encode(),
            "status_with_control": json.dumps(dict(valid, status="passed\n")).encode(),
            "negative_count": both_counts(-1),
            "boolean_count": both_counts(True),
            "huge_count": both_counts(10 ** 12),
            "float_count": both_counts(1.0),
            "nan_constant": with_extra(b"NaN"),
            "infinity_constant": with_extra(b"-Infinity"),
            "classes_not_list": json.dumps(dict(valid, test_classes=secret)).encode(),
            "missing_fields": json.dumps({"status": "passed"}).encode(),
            "duplicate_status": b'{"status": "failed", "status": "passed", "tests_run": 1, '
                                b'"test_classes": [{"status": "passed", "tests_run": 1}]}',
            "duplicate_class_status": b'{"status": "passed", "tests_run": 1, "test_classes": '
                                      b'[{"status": "failed", "status": "passed", "tests_run": 1}]}',
            "oversized": with_extra(b'"' + b"A" * (300 * 1024) + b'"'),
            "deep_nesting": with_extra(b"[" * 100000 + b"]" * 100000),
        }
        for name, payload in cases.items():
            with self.subTest(name):
                report, jvm = self.jvm_status(payload)
                self.assertEqual(jvm, {"status": "invalid"})
                self.assertNotIn(secret, json.dumps(report))

    def test_symlinked_or_special_inputs_are_refused(self):
        outside = tempfile.TemporaryDirectory(prefix="support-outside-")
        self.addCleanup(outside.cleanup)
        target = Path(outside.name) / "local.properties.json"
        # Control: the target content is a valid passing summary when it is a
        # regular in-tree file, so refusal below can only come from symlink checks.
        passing = {"status": "passed", "tests_run": 7,
                   "test_classes": [{"status": "passed", "tests_run": 7}]}
        summary = self.root / "verification/build/jvm/summary.json"
        summary.parent.mkdir(parents=True)
        summary.write_text(json.dumps(passing))
        self.assertEqual(self.collector().collect(self.root)["verification"]["jvm"],
                         {"status": "passed", "tests_run": 7, "class_count": 1})
        summary.unlink()
        target.write_text(json.dumps(passing))
        summary.symlink_to(target)
        with self.subTest("file_symlink"):
            self.assertEqual(self.collector().collect(self.root)["verification"]["jvm"],
                             {"status": "invalid"})
        summary.unlink()
        (self.root / "verification/build/jvm").rmdir()
        (self.root / "verification/build/jvm").symlink_to(Path(outside.name))
        (Path(outside.name) / "summary.json").write_text(target.read_text())
        with self.subTest("parent_symlink"):
            self.assertEqual(self.collector().collect(self.root)["verification"]["jvm"],
                             {"status": "invalid"})
        (self.root / "verification/build/jvm").unlink()
        (self.root / "verification/build/jvm").mkdir()
        os.mkfifo(summary)
        with self.subTest("fifo"):
            self.assertEqual(self.collector().collect(self.root)["verification"]["jvm"],
                             {"status": "invalid"})

    def doctor_output(self, **overrides):
        checks = [{"id": name, "status": "blocked",
                   "message": "Configure /Users/someone/secret/keystore.jks password=SYNTHETIC"}
                  for name in ("configuration_format", "jdk_17", "android_sdk",
                               "atak_sdk", "signing_configuration")]
        checks[1]["status"] = "ok"
        value = {"ready_for_build": False, "checks": checks,
                 "scope": "Prerequisites only; lat 51.5007 lon -0.1246"}
        value.update(overrides)
        return value

    def test_saved_doctor_output_emits_only_known_check_statuses(self):
        self.fixture("dist/release-doctor.json", self.doctor_output())
        report = self.collector().collect(self.root)
        self.assertEqual(report["verification"]["prerequisites"], {
            "status": "blocked",
            "checks": {"configuration_format": "blocked", "jdk_17": "ok",
                       "android_sdk": "blocked", "atak_sdk": "blocked",
                       "signing_configuration": "blocked"},
        })
        serialized = json.dumps(report)
        for forbidden in ("/Users/", "keystore", "SYNTHETIC", "51.5007", "-0.1246", "message"):
            self.assertNotIn(forbidden, serialized)

    def test_inconsistent_or_unknown_doctor_output_fails_closed(self):
        ready_but_blocked = self.doctor_output(ready_for_build=True)
        unknown = self.doctor_output()
        unknown["checks"].append({"id": "SYNTHETIC_SECRET_ID", "status": "ok"})
        duplicate = self.doctor_output()
        duplicate["checks"].append(dict(duplicate["checks"][0]))
        bad_status = self.doctor_output()
        bad_status["checks"][0]["status"] = "SYNTHETIC_SECRET_STATUS"
        missing = self.doctor_output()
        del missing["checks"][0]
        non_object = self.doctor_output()
        non_object["checks"][0] = "SYNTHETIC"
        for name, value in {"ready_contradiction": ready_but_blocked, "unknown_id": unknown,
                            "duplicate_id": duplicate, "bad_status": bad_status,
                            "missing_check": missing, "check_not_object": non_object,
                            "ready_not_bool": self.doctor_output(ready_for_build="yes")}.items():
            with self.subTest(name):
                self.fixture("dist/release-doctor.json", value)
                report = self.collector().collect(self.root)
                self.assertEqual(report["verification"]["prerequisites"], {"status": "invalid"})
                self.assertNotIn("SYNTHETIC", json.dumps(report))

    def write_tool_metadata(self, wrapper_url="https\\://services.gradle.org/distributions/gradle-7.6.4-bin.zip",
                            dependencies=None, inventory=None, wrapper_text=None):
        wrapper = self.root / "plugin/gradle/wrapper/gradle-wrapper.properties"
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        if wrapper_text is None:
            wrapper_text = ("distributionBase=GRADLE_USER_HOME\n"
                            "distributionUrl=" + wrapper_url + "\n"
                            "distributionSha256Sum=" + "0" * 64 + "\n")
        wrapper.write_bytes(wrapper_text.encode("utf-8"))
        self.fixture("verification/dependencies.json", dependencies if dependencies is not None else [
            {"url": "https://repo.maven.apache.org/maven2/junit/junit/4.13.2/junit-4.13.2.jar",
             "sha1": "8ac9e16d933b6fb43bc7f576336b8f4d7eb5ba12"},
            {"url": "https://repo.maven.apache.org/maven2/com/google/code/gson/gson/2.10.1/gson-2.10.1.jar",
             "sha1": "b3add478d4382b78ea20b1671390a858002feb6c"},
        ])
        self.fixture("verification/java-tests.json", inventory if inventory is not None else {
            "included_sources": ["a/A.java", "b/B.java"],
            "included_tests": ["a/ATest.java"],
            "excluded_tests": {"b/BTest.java": "needs /Users/someone/device GPS 37.4,-122.0"},
        })

    def test_tool_metadata_reports_public_version_tokens_and_counts(self):
        self.write_tool_metadata()
        metadata = self.collector().collect(self.root)["tool_metadata"]
        self.assertEqual(metadata, {
            "status": "ok", "gradle_wrapper": "7.6.4",
            "jvm_dependencies": {"junit:junit": "4.13.2", "com.google.code.gson:gson": "2.10.1"},
            "java_inventory": {"included_sources": 2, "included_tests": 1, "excluded_tests": 1},
        })
        self.assertNotIn("/Users/", json.dumps(metadata))

    def test_credentialed_or_unexpected_tool_metadata_fails_closed(self):
        cases = {
            "credentialed_wrapper": {"wrapper_url": "https\\://user:SYNTHETIC_PW@example.invalid/gradle-7.6.4-bin.zip"},
            "private_dependency_host": {"dependencies": [
                {"url": "https://SYNTHETIC_PW@repo.example.invalid/maven2/a/b/1.0/b-1.0.jar", "sha1": "0" * 40}]},
            "mismatched_artifact": {"dependencies": [
                {"url": "https://repo.maven.apache.org/maven2/junit/junit/4.13.2/SYNTHETIC-9.jar", "sha1": "0" * 40}]},
            "inventory_not_object": {"inventory": ["SYNTHETIC"]},
            "inventory_bad_list": {"inventory": {"included_sources": "SYNTHETIC",
                                                 "included_tests": [], "excluded_tests": {}}},
            "unicode_digit_version": {"dependencies": [
                {"url": "https://repo.maven.apache.org/maven2/junit/junit/\u0664.1/junit-\u0664.1.jar", "sha1": "0" * 40}]},
            "non_ascii_wrapper": {"wrapper_url": "https\\://services.gradle.org/distributions/gradle-7.6.4-bin.zip#SYNTHETIC\u00e9"},
            "duplicate_wrapper_url": {"wrapper_url": "https\\://services.gradle.org/distributions/gradle-7.6.4-bin.zip\n"
                                                     "distributionUrl=https\\://SYNTHETIC.invalid/gradle-1.0-bin.zip"},
            "empty_dependencies": {"dependencies": []},
            "dependency_not_object": {"dependencies": ["SYNTHETIC"]},
            "duplicate_dependency": {"dependencies": [
                {"url": "https://repo.maven.apache.org/maven2/junit/junit/4.13.2/junit-4.13.2.jar"},
                {"url": "https://repo.maven.apache.org/maven2/junit/junit/4.13.1/junit-4.13.1.jar"}]},
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                self.write_tool_metadata(**kwargs)
                metadata = self.collector().collect(self.root)["tool_metadata"]
                self.assertEqual(metadata, {"status": "invalid"})
                self.assertNotIn("SYNTHETIC", json.dumps(metadata))

    OFFICIAL_URL = "distributionUrl=https\\://services.gradle.org/distributions/gradle-7.6.4-bin.zip"
    OTHER_URL = "distributionUrl=https\\://SYNTHETIC.invalid/gradle-1.0-bin.zip"

    def test_wrapper_line_endings_and_comments_are_accepted(self):
        for name, text in {
            "lf": "distributionBase=GRADLE_USER_HOME\n" + self.OFFICIAL_URL + "\n",
            "crlf": "distributionBase=GRADLE_USER_HOME\r\n" + self.OFFICIAL_URL + "\r\n",
            "cr": "distributionBase=GRADLE_USER_HOME\r" + self.OFFICIAL_URL + "\r",
            "no_final_newline": "#Generated\n\n" + self.OFFICIAL_URL,
            "other_values_escaped": "zipStorePath=wrapper\\:dists\n" + self.OFFICIAL_URL + "\n",
        }.items():
            with self.subTest(name):
                self.write_tool_metadata(wrapper_text=text)
                metadata = self.collector().collect(self.root)["tool_metadata"]
                self.assertEqual((metadata["status"], metadata.get("gradle_wrapper")), ("ok", "7.6.4"))

    def test_ambiguous_wrapper_distribution_url_fails_closed(self):
        # java.util.Properties would resolve each of these to a different URL (or
        # none) than the single literal official line the collector can see.
        official, other = self.OFFICIAL_URL, self.OTHER_URL
        cases = {
            "indented_only_url": "  " + official + "\n",
            "indented_duplicate": official + "\n  " + other + "\n",
            "tab_indented_duplicate": official + "\n\t" + other + "\n",
            "formfeed_indented_duplicate": official + "\n\f" + other + "\n",
            "unicode_escaped_key": official + "\n" + other.replace("Url", "Ur\\u006c") + "\n",
            "backslash_escaped_key": official + "\n" + other.replace("Url", "\\Url") + "\n",
            "colon_separator_duplicate": official + "\n" + other.replace("=", ":", 1) + "\n",
            "space_separator_duplicate": official + "\n" + other.replace("=", " ", 1) + "\n",
            "spaced_equals_duplicate": official + "\n" + other.replace("=", " = ", 1) + "\n",
            "only_colon_separator": official.replace("=", ":", 1) + "\n",
            "continuation_hides_url": "distributionBase=GRADLE_USER_HOME\\\n" + official + "\n",
            "continuation_after_url": official + "\\\n  SYNTHETIC\n",
            "continuation_into_duplicate": official + "\nzipStorePath=x\\\n" + other + "\n",
            "vertical_tab_split": "distributionBase=GRADLE_USER_HOME\x0b" + official + "\n",
            "formfeed_split": "distributionBase=GRADLE_USER_HOME\x0c" + official + "\n",
            "file_separator_split": "distributionBase=GRADLE_USER_HOME\x1c" + official + "\n",
            "group_separator_split": "distributionBase=GRADLE_USER_HOME\x1d" + official + "\n",
            "record_separator_split": "distributionBase=GRADLE_USER_HOME\x1e" + official + "\n",
            "nul_in_file": official + "\n\x00" + other + "\n",
            "commented_duplicate": official + "\n#" + other + "\n",
            "url_in_other_value": "zipStorePath=" + other + "\n" + official + "\n",
            "exact_duplicate": official + "\n" + official + "\n",
            "missing_url": "distributionBase=GRADLE_USER_HOME\n",
        }
        for name, text in cases.items():
            with self.subTest(name):
                self.write_tool_metadata(wrapper_text=text)
                metadata = self.collector().collect(self.root)["tool_metadata"]
                self.assertEqual(metadata, {"status": "invalid"})
                self.assertNotIn("SYNTHETIC", json.dumps(metadata))

    def assert_no_partial_report(self, previous):
        dist = self.root / "dist"
        expected = ["support-report.json"] if previous is not None else []
        self.assertEqual(sorted(p.name for p in dist.iterdir()), expected)
        if previous is not None:
            self.assertEqual((dist / "support-report.json").read_bytes(), previous)

    def test_write_failures_remove_temporary_file_and_keep_previous_report(self):
        module = self.collector()
        real_write = os.write
        calls = []

        def partial_then_fail(fd, data):
            if not calls:
                calls.append(fd)
                return real_write(fd, bytes(data[:7]))
            raise OSError(errno.ENOSPC, "synthetic")

        failures = {
            "fchmod": {"fchmod": OSError(errno.EPERM, "synthetic")},
            "write": {"write": OSError(errno.ENOSPC, "synthetic")},
            "partial_write": {"write": partial_then_fail},
            "fsync": {"fsync": OSError(errno.EIO, "synthetic")},
            "replace": {"replace": OSError(errno.EIO, "synthetic")},
        }
        for previous in (None, b'{"previous": true}\n'):
            for name, patches in failures.items():
                with self.subTest(name, previous=previous is not None):
                    dist = self.root / "dist"
                    for child in (dist.iterdir() if dist.exists() else ()):
                        child.unlink()
                    if previous is not None:
                        dist.mkdir(exist_ok=True)
                        (dist / "support-report.json").write_bytes(previous)
                    calls.clear()
                    with contextlib.ExitStack() as stack:
                        for attribute, effect in patches.items():
                            stack.enter_context(mock.patch.object(module.os, attribute, side_effect=effect))
                        with self.assertRaises(OSError):
                            module.write_report(self.root, module.collect(self.root))
                    self.assert_no_partial_report(previous)

    def test_cli_reports_write_failure_without_leaving_files(self):
        module = self.collector()
        stderr = io.StringIO()
        with mock.patch.object(module.os, "fsync", side_effect=OSError(errno.EIO, "synthetic")), \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(module.main(["--root", str(self.root)]), 2)
        self.assertEqual(stderr.getvalue().strip(),
                         "Could not write dist/support-report.json safely; no report was written.")
        self.assert_no_partial_report(None)

    def test_only_allowlisted_files_opened_without_network_or_processes(self):
        self.write_tool_metadata()
        self.fixture("dist/release-doctor.json", self.doctor_output())
        self.fixture("verification/build/jvm/summary.json",
                     {"status": "passed", "tests_run": 1,
                      "test_classes": [{"status": "passed", "tests_run": 1}]})
        decoys = {"plugin/local.properties": "takReleaseKeyPassword=SYNTHETIC_DECOY\n",
                  ".env": "API_TOKEN=SYNTHETIC_DECOY\n",
                  "plugin/app/src/main/assets/demo.json": '{"lat": 12.3456, "SYNTHETIC_DECOY": 1}',
                  "verification/build/jvm/run-x/compile.log": "SYNTHETIC_DECOY /Users/x\n"}
        for relative, text in decoys.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        probe = (
            "import importlib.util, json, sys\n"
            "events = []\n"
            "def hook(event, args):\n"
            "    if event == 'open' and isinstance(args[0], (str, bytes)):\n"
            "        events.append(['open', str(args[0])])\n"
            "    elif event.startswith(('socket.', 'subprocess.', 'os.system', 'os.exec', 'os.posix_spawn', 'urllib.')):\n"
            "        events.append([event, ''])\n"
            "spec = importlib.util.spec_from_file_location('collector', sys.argv[1])\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(module)\n"
            "sys.addaudithook(hook)\n"
            "report = module.collect(sys.argv[2])\n"
            "print(json.dumps({'events': events, 'report': report}))\n")
        result = subprocess.run([sys.executable, "-I", "-c", probe, str(SCRIPT), str(self.root)],
                                capture_output=True, text=True, timeout=60,
                                env={"PATH": os.defpath, "HOME": str(self.root / "no-home")})
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual([event for event, _ in output["events"] if event != "open"], [])
        opened = {name for event, name in output["events"]}
        self.assertEqual(opened, {str(self.root), "verification", "build", "jvm", "summary.json",
                                  "dist", "release-doctor.json", "plugin", "gradle", "wrapper",
                                  "gradle-wrapper.properties", "dependencies.json", "java-tests.json"})
        self.assertNotIn("SYNTHETIC_DECOY", result.stdout)
        statuses = output["report"]
        self.assertEqual((statuses["verification"]["jvm"]["status"],
                          statuses["verification"]["prerequisites"]["status"],
                          statuses["tool_metadata"]["status"]), ("passed", "blocked", "ok"))

    def run_cli(self, *extra):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "--root", str(self.root), *extra],
                              capture_output=True, text=True, timeout=60,
                              env={"PATH": os.defpath, "HOME": str(self.root / "no-home")})

    def test_cli_writes_private_report_under_dist_without_absolute_paths(self):
        self.write_tool_metadata()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.root / "dist/support-report.json"
        self.assertEqual(json.loads(output.read_text()), self.collector().collect(self.root))
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result.stdout.strip(), "Wrote dist/support-report.json (review before sharing; nothing was uploaded).")
        self.assertNotIn(str(self.root), result.stdout + result.stderr + output.read_text())
        self.assertEqual(sorted(p.name for p in output.parent.iterdir()), ["support-report.json"])

    def test_cli_refuses_symlinked_output_locations(self):
        outside = tempfile.TemporaryDirectory(prefix="support-outside-")
        self.addCleanup(outside.cleanup)
        (self.root / "dist").symlink_to(outside.name)
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(Path(outside.name).iterdir()), [])
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_contradictory_jvm_success_claims_fail_closed(self):
        passed = {"status": "passed", "tests_run": 2}
        cases = {
            "zero_tests": dict(passed, tests_run=0, test_classes=[]),
            "count_mismatch": dict(passed, test_classes=[{"status": "passed", "tests_run": 1}]),
            "failed_class": dict(passed, test_classes=[{"status": "failed", "tests_run": 2}]),
            "class_not_object": dict(passed, test_classes=["SYNTHETIC"]),
            "class_bad_count": dict(passed, test_classes=[{"status": "passed", "tests_run": "2"}]),
        }
        for name, value in cases.items():
            with self.subTest(name):
                self.fixture("verification/build/jvm/summary.json", value)
                self.assertEqual(self.collector().collect(self.root)["verification"]["jvm"],
                                 {"status": "invalid"})
        self.fixture("verification/build/jvm/summary.json", {
            "status": "failed", "tests_run": 1,
            "test_classes": [{"status": "passed", "tests_run": 1},
                             {"status": "timed_out", "tests_run": 0}]})
        self.assertEqual(self.collector().collect(self.root)["verification"]["jvm"],
                         {"status": "failed", "tests_run": 1, "class_count": 2})

    def test_missing_inputs_are_explicit_not_success(self):
        report = self.collector().collect(self.root)
        self.assertEqual(report, {
            "schema_version": 1,
            "scope": "Local offline summary of saved development checks. Not CI, APK, "
                     "device, accuracy, or release evidence.",
            "verification": {"jvm": {"status": "missing"},
                             "prerequisites": {"status": "missing"}},
            "tool_metadata": {"status": "missing"},
        })
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
