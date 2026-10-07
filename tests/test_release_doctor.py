"""Generic release infrastructure tests; no application algorithms exercised."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Optional, Union
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release_doctor.py"
DESCRIPTOR = "META-INF/gradle-plugins/atak-takdev-plugin.properties"


class ReleaseDoctorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("release_doctor", SCRIPT)
        if spec is None or spec.loader is None:
            raise AssertionError("release doctor must exist")
        cls.doctor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.doctor)

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "plugin").mkdir()
        self.properties = self.root / "plugin/local.properties"

    def inspect(self, environment=None, java_version: Optional[int] = 17):
        return self.doctor.inspect(self.root, environment={} if environment is None else environment,
                                   java_version=java_version)

    def status(self, report, check_id):
        return next(item["status"] for item in report["checks"] if item["id"] == check_id)

    def write_properties(self, props):
        self.properties.write_text("\n".join(key + "=" + value for key, value in props.items()),
                                   encoding="utf-8")

    def android_sdk(self):
        sdk = self.root / "android-sdk"
        (sdk / "platforms/android-34").mkdir(parents=True)
        (sdk / "platforms/android-34/android.jar").write_bytes(b"structural fixture")
        (sdk / "build-tools/34.0.0").mkdir(parents=True)
        for tool in ("aapt2", "apksigner", "zipalign"):
            (sdk / "build-tools/34.0.0" / tool).write_bytes(b"structural fixture")
        return sdk

    def sdk_archives(self, descriptor: Union[str, bytes] = "implementation-class=example.Plugin",
                     compression=zipfile.ZIP_STORED, include_class=True):
        # Structural fixtures only: not a functional SDK or Gradle plugin.
        sdk = self.root / "sdk"
        sdk.mkdir(exist_ok=True)
        jar = sdk / "atak-gradle-takdev.jar"
        with zipfile.ZipFile(sdk / "main.jar", "w") as archive:
            archive.writestr("com/atakmap/android/maps/MapView.class", b"fixture")
        with zipfile.ZipFile(jar, "w", compression=compression) as archive:
            archive.writestr(DESCRIPTOR, descriptor)
            if include_class:
                archive.writestr("example/Plugin.class", b"fixture")
        return {"sdk.path": str(sdk), "takdev.plugin": str(jar)}

    def signing_properties(self, password="fixture-password-not-a-real-credential"):
        key = self.root / "fixture.jks"
        key.write_bytes(b"structural fixture, not a usable signer")
        return {"tak" + kind + suffix: value
                for kind in ("Debug", "Release")
                for suffix, value in (("KeyFile", str(key)), ("KeyFilePassword", password),
                                      ("KeyAlias", "fixture-alias"), ("KeyPassword", password))}

    def test_missing_sdk_is_a_blocker(self):
        report = self.inspect(java_version=None)
        self.assertFalse(report["ready_for_build"])
        self.assertEqual("blocked", self.status(report, "android_sdk"))

    def test_jdk_17_required(self):
        for version in (None, 11, 21):
            self.assertEqual("blocked", self.status(self.inspect(java_version=version), "jdk_17"))
        self.assertEqual("ok", self.status(self.inspect(), "jdk_17"))

    def test_sdk_directory_requires_platform_and_build_tools(self):
        env = {"ANDROID_HOME": str(self.root / "android-sdk")}
        self.assertEqual("blocked", self.status(self.inspect(env), "android_sdk"))
        self.android_sdk()
        self.assertEqual("ok", self.status(self.inspect(env), "android_sdk"))

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory search permissions")
    def test_inaccessible_android_sdk_is_blocked_without_path_disclosure(self):
        sdk = self.android_sdk()
        sdk.chmod(0o000)
        try:
            for source in ("sdk.dir", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
                self.write_properties({"sdk.dir": str(sdk)} if source == "sdk.dir" else {})
                env = {"PATH": ""}
                if source != "sdk.dir":
                    env[source] = str(sdk)
                for as_json in (False, True):
                    with self.subTest(source=source, as_json=as_json):
                        args = [sys.executable, str(SCRIPT), "--root", str(self.root)]
                        if as_json:
                            args.append("--json")
                        result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=5)
                        self.assertEqual(1, result.returncode)
                        self.assertNotIn(str(sdk), result.stdout + result.stderr)
                        self.assertNotIn(str(self.root), result.stdout + result.stderr)
                        self.assertEqual("", result.stderr)
                        if as_json:
                            self.assertEqual("blocked", self.status(json.loads(result.stdout), "android_sdk"))
                        else:
                            self.assertIn("blocked: android_sdk:", result.stdout)
                self.assertEqual("blocked", self.status(self.inspect(env), "android_sdk"))
        finally:
            sdk.chmod(0o700)

    def test_android_sdk_probe_errors_are_blocked_without_path_disclosure(self):
        sdk = self.android_sdk()
        original = Path.is_file
        for error_type in (OSError, ValueError):
            def probe(path):
                if sdk in path.parents:
                    raise error_type(str(sdk))
                return original(path)
            with self.subTest(error_type=error_type.__name__):
                with patch.object(Path, "is_file", autospec=True, side_effect=probe):
                    report = self.inspect({"ANDROID_HOME": str(sdk)})
                self.assertEqual("blocked", self.status(report, "android_sdk"))
                self.assertNotIn(str(sdk), json.dumps(report))

    def test_relative_android_sdk_paths_are_rejected(self):
        sdk = self.android_sdk()
        cwd = Path.cwd()
        try:
            os.chdir(self.root)
            for source in ("sdk.dir", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
                with self.subTest(source=source):
                    self.write_properties({"sdk.dir": sdk.name} if source == "sdk.dir" else {})
                    env = {"ANDROID_HOME": str(sdk)} if source == "sdk.dir" else {source: sdk.name}
                    self.assertEqual("blocked", self.status(self.inspect(env), "android_sdk"))
        finally:
            os.chdir(cwd)
        self.write_properties({"sdk.dir": str(sdk)})
        self.assertEqual("ok", self.status(self.inspect(), "android_sdk"))

    def test_empty_sdk_stub_cannot_pass(self):
        sdk = self.root / "sdk"
        sdk.mkdir()
        jar = sdk / "atak-gradle-takdev.jar"
        (sdk / "main.jar").touch()
        jar.touch()
        self.write_properties({"sdk.path": str(sdk), "takdev.plugin": str(jar)})
        self.assertEqual("blocked", self.status(self.inspect(), "atak_sdk"))
        self.write_properties(self.sdk_archives())
        self.assertEqual("ok", self.status(self.inspect(), "atak_sdk"))

    def test_signing_files_and_all_fields_required_without_leaking_secrets(self):
        secret = "fixture-password-not-a-real-credential"
        self.assertEqual("blocked", self.status(self.inspect(), "signing_configuration"))
        props = self.signing_properties(secret)
        self.write_properties(props)
        report = self.inspect()
        self.assertNotIn(secret, json.dumps(report))
        self.assertEqual("ok", self.status(report, "signing_configuration"))
        for kind in ("Debug", "Release"):
            with self.subTest(kind=kind):
                incomplete = dict(props)
                del incomplete["tak" + kind + "KeyPassword"]
                self.write_properties(incomplete)
                self.assertEqual("blocked", self.status(self.inspect(), "signing_configuration"))

    def test_malformed_archive_entries_are_blockers(self):
        import zlib
        for kind, expected in (("encrypted", RuntimeError),
                               ("unsupported", NotImplementedError),
                               ("deflate", zlib.error)):
            with self.subTest(kind=kind):
                props = self.sdk_archives(compression=zipfile.ZIP_DEFLATED)
                jar = Path(props["takdev.plugin"])
                data = bytearray(jar.read_bytes())
                central = data.index(b"PK\x01\x02")
                if kind == "encrypted":
                    struct.pack_into("<H", data, 6, 1)
                    struct.pack_into("<H", data, central + 8, 1)
                elif kind == "unsupported":
                    struct.pack_into("<H", data, 8, 99)
                    struct.pack_into("<H", data, central + 10, 99)
                else:
                    name_size, extra_size = struct.unpack_from("<HH", data, 26)
                    data[30 + name_size + extra_size] = 7  # Invalid deflate block type.
                jar.write_bytes(data)
                with self.assertRaises(expected):
                    with zipfile.ZipFile(jar) as archive:
                        archive.read(DESCRIPTOR)
                self.write_properties(props)
                self.assertEqual("blocked", self.status(self.inspect(), "atak_sdk"))

    def test_corrupt_lzma_descriptor_is_a_blocker(self):
        import lzma
        props = self.sdk_archives(compression=zipfile.ZIP_LZMA)
        jar = Path(props["takdev.plugin"])
        data = bytearray(jar.read_bytes())
        name_size, extra_size = struct.unpack_from("<HH", data, 26)
        payload = 30 + name_size + extra_size
        data[payload + 4] = 255  # Invalid LZMA filter properties after its ZIP header.
        jar.write_bytes(data)
        with self.assertRaises(lzma.LZMAError):
            with zipfile.ZipFile(jar) as archive:
                self.assertEqual(zipfile.ZIP_LZMA, archive.getinfo(DESCRIPTOR).compress_type)
                archive.read(DESCRIPTOR)
        self.write_properties(props)
        self.assertEqual("blocked", self.status(self.inspect(), "atak_sdk"))

    def test_archive_eof_is_a_blocker(self):
        self.write_properties(self.sdk_archives())
        # EOFError depends on decompressor/runtime; inject only this read failure.
        with patch.object(zipfile.ZipFile, "read", side_effect=EOFError("fixture archive error")):
            self.assertEqual("blocked", self.status(self.inspect(), "atak_sdk"))

    def test_bad_archive_paths_and_descriptors_are_blockers(self):
        for descriptor, include_class in (("unrelated=value", True),
                                          ("implementation-class=example.Plugin", False),
                                          ("x" * 4097, True), (b"\xff", True)):
            with self.subTest(descriptor_size=len(descriptor), include_class=include_class):
                self.write_properties(self.sdk_archives(descriptor, include_class=include_class))
                self.assertEqual("blocked", self.status(self.inspect(), "atak_sdk"))
        props = self.sdk_archives()
        jar = Path(props["takdev.plugin"])
        for content in (b"not a ZIP", jar.read_bytes()[:20]):
            jar.write_bytes(content)
            self.write_properties(props)
            self.assertEqual("blocked", self.status(self.inspect(), "atak_sdk"))
        for path in (self.root / "missing.jar", self.root):
            self.write_properties(dict(props, **{"takdev.plugin": str(path)}))
            self.assertEqual("blocked", self.status(self.inspect(), "atak_sdk"))

    def test_duplicate_implementation_class_properties_are_blockers(self):
        for last in ("implementation-class=example.Missing",
                     "implementation-class=example.Plugin",
                     "implementation-class=",
                     "  implementation-class = example.Missing"):
            with self.subTest(last=last):
                descriptor = "implementation-class=example.Plugin\n" + last + "\n"
                self.write_properties(self.sdk_archives(descriptor))
                self.assertEqual("blocked", self.status(self.inspect(), "atak_sdk"))

    def test_descriptor_value_cannot_start_on_next_line(self):
        for descriptor in ("implementation-class=\nexample.Plugin",
                           "implementation-class\n=example.Plugin"):
            with self.subTest(descriptor=descriptor):
                self.write_properties(self.sdk_archives(descriptor))
                self.assertEqual("blocked", self.status(self.inspect(), "atak_sdk"))
        self.write_properties(self.sdk_archives("implementation-class \t= \texample.Plugin\t\n"))
        self.assertEqual("ok", self.status(self.inspect(), "atak_sdk"))

    def java_launcher(self, output=b'openjdk version "17.0.12"\n'):
        home = self.root / "jdk"
        (home / "bin").mkdir(parents=True, exist_ok=True)
        java = home / "bin/java"
        java.write_text("#!" + sys.executable + "\nimport os\nos.write(2, " + repr(output) + ")\n",
                        encoding="utf-8")
        java.chmod(0o700)
        return home

    def test_java_probe_replaces_undecodable_output(self):
        home = self.java_launcher(b'\xff\nopenjdk version "17.0.12"\n')
        self.assertEqual(17, self.doctor.detect_java_major({"JAVA_HOME": str(home), "LC_ALL": "C"}))

    @unittest.skipUnless(hasattr(sys, "set_int_max_str_digits"), "integer digit limit requires Python 3.11+")
    def test_java_probe_blocks_version_exceeding_integer_digit_limit(self):
        previous_limit = sys.get_int_max_str_digits()
        self.addCleanup(sys.set_int_max_str_digits, previous_limit)
        sys.set_int_max_str_digits(4300)
        digits = "9" * 5000
        with self.assertRaises(ValueError):
            int(digits)
        for version in (digits, "1." + digits):
            with self.subTest(legacy=version.startswith("1.")):
                home = self.java_launcher(('openjdk version "' + version + '"\n').encode("ascii"))
                self.assertIsNone(self.doctor.detect_java_major({"JAVA_HOME": str(home), "PATH": ""}))

    def test_java_probe_failure_paths(self):
        self.assertIsNone(self.doctor.detect_java_major({}))
        for error in (OSError("fixture launcher error"), subprocess.TimeoutExpired("java", 10)):
            with self.subTest(error=type(error).__name__):
                self.assertIsNone(self.doctor.detect_java_major({"JAVA_HOME": "/fixture/jdk"},
                                                               run=Mock(side_effect=error)))
        self.assertIsNone(self.doctor.detect_java_major({"JAVA_HOME": "/fixture/jdk"},
                         run=Mock(return_value=SimpleNamespace(returncode=0, stdout="", stderr="unknown"))))
        home = self.java_launcher()
        self.assertEqual(17, self.doctor.detect_java_major({"PATH": str(home / "bin")}))

    def test_properties_preserve_trailing_value_whitespace(self):
        self.properties.write_text("  key \t= \tvalue \t\n", encoding="ascii")
        self.assertEqual({"key": "value \t"}, self.doctor.read_properties(self.properties))
        props = self.signing_properties()
        props["takDebugKeyFile"] += " "
        self.write_properties(props)
        self.assertEqual("blocked", self.status(self.inspect(), "signing_configuration"))

    def complete_properties(self):
        props = self.sdk_archives()
        props.update(self.signing_properties())
        props["sdk.dir"] = str(self.android_sdk())
        return props

    def test_configuration_format_rejects_unsupported_properties(self):
        props = self.complete_properties()
        self.write_properties(props)
        self.assertTrue(self.inspect()["ready_for_build"])
        supported = self.properties.read_text(encoding="ascii")
        for line in ("unused:value", "unused value", "unused", "unused=\\u0041",
                     "unused=one\\\n two", "unused=back\\slash", "bad key=value",
                     "unused=café", "unused=bad\vcontrol", "unused=bad\x00control",
                     "unused=bad\x7fcontrol"):
            with self.subTest(line=line):
                self.properties.write_text(supported + "\n" + line, encoding="utf-8")
                report = self.inspect()
                self.assertFalse(report["ready_for_build"])
                self.assertIn("configuration_format", {c["id"] for c in report["checks"]
                                                       if c["status"] == "blocked"})

    def test_configuration_format_reports_unreadable_or_oversized_files(self):
        for content in (b"\xff", b"x" * (1024 * 1024 + 1)):
            with self.subTest(size=len(content)):
                self.properties.write_bytes(content)
                report = self.inspect()
                self.assertIn("configuration_format", {c["id"] for c in report["checks"]
                                                       if c["status"] == "blocked"})
        self.properties.unlink()
        for exists in (False, True):
            if exists:
                self.properties.mkdir()
            report = self.inspect()
            self.assertIn("configuration_format", {c["id"] for c in report["checks"]
                                                   if c["status"] == "blocked"})

    def test_configuration_format_supported_subset_preserves_java_values(self):
        self.properties.write_bytes(b" # comment\r\n ! comment\r\n\fkey\t= \tfirst\r\n"
                                    b"key = second \t\f\r\nempty= \t\f\r\n"
                                    b"literal = https://fixture.invalid/a=b#c!d\r\n")
        self.assertEqual({"key": "second \t\f", "empty": "",
                          "literal": "https://fixture.invalid/a=b#c!d"},
                         self.doctor.read_properties(self.properties))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO check")
    def test_configuration_format_fifo_does_not_block_cli(self):
        os.mkfifo(self.properties)
        try:
            result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--json"],
                                    env={"PATH": ""}, capture_output=True, text=True, timeout=2)
        except subprocess.TimeoutExpired:
            self.fail("release doctor blocked reading a non-regular local.properties file")
        self.assertEqual(1, result.returncode)
        self.assertEqual("blocked", self.status(json.loads(result.stdout), "configuration_format"))
        self.assertEqual("", result.stderr)

    def test_signing_password_angle_characters_are_not_placeholders(self):
        for password in ("fixture<angle>password", "fixture<", "fixture>"):
            with self.subTest(password=password):
                self.write_properties(self.signing_properties(password))
                self.assertEqual("ok", self.status(self.inspect(), "signing_configuration"))
        for placeholder in ("<password>", "<KEY_PASSWORD>"):
            with self.subTest(placeholder=placeholder):
                self.write_properties(self.signing_properties(placeholder))
                self.assertEqual("blocked", self.status(self.inspect(), "signing_configuration"))

    def test_signing_relative_or_empty_keystore_is_blocked(self):
        props = self.signing_properties()
        for kind in ("Debug", "Release"):
            with self.subTest(kind=kind):
                relative = dict(props)
                relative["tak" + kind + "KeyFile"] = "fixture.jks"
                self.write_properties(relative)
                self.assertEqual("blocked", self.status(self.inspect(), "signing_configuration"))
        Path(props["takDebugKeyFile"]).write_bytes(b"")
        self.write_properties(props)
        self.assertEqual("blocked", self.status(self.inspect(), "signing_configuration"))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO check")
    def test_archive_fifo_does_not_block_cli(self):
        for filename in ("main.jar", "atak-gradle-takdev.jar"):
            with self.subTest(filename=filename):
                props = self.sdk_archives()
                self.write_properties(props)
                fifo = Path(props["sdk.path"]) / filename
                fifo.unlink()
                os.mkfifo(fifo)
                try:
                    try:
                        result = subprocess.run(
                            [sys.executable, str(SCRIPT), "--root", str(self.root), "--json"],
                            env={"PATH": ""}, capture_output=True, text=True, timeout=2)
                    except subprocess.TimeoutExpired:
                        self.fail("release doctor blocked reading a non-regular archive")
                    self.assertEqual(1, result.returncode)
                    self.assertEqual("blocked", self.status(json.loads(result.stdout), "atak_sdk"))
                    self.assertEqual("", result.stderr)
                finally:
                    fifo.unlink()

    def test_cli_exit_codes_and_outputs_never_print_configuration_values(self):
        props = self.complete_properties()
        self.write_properties(props)
        home = self.java_launcher(b'\xff\nopenjdk version "17.0.12"\n')
        for ready in (True, False):
            if not ready:
                Path(props["takdev.plugin"]).write_bytes(b"not a ZIP")
            for as_json in (False, True):
                with self.subTest(ready=ready, as_json=as_json):
                    args = [sys.executable, str(SCRIPT), "--root", str(self.root)]
                    if as_json:
                        args.append("--json")
                    result = subprocess.run(args, env={"JAVA_HOME": str(home), "PATH": ""},
                                            capture_output=True, text=True, timeout=5)
                    self.assertEqual(0 if ready else 1, result.returncode)
                    self.assertEqual("", result.stderr)
                    for value in props.values():
                        self.assertNotIn(value, result.stdout + result.stderr)
                    self.assertNotIn(str(self.root), result.stdout + result.stderr)
                    if as_json:
                        report = json.loads(result.stdout)
                        self.assertEqual(ready, report["ready_for_build"])
                        self.assertEqual("ok", self.status(report, "configuration_format"))
                        self.assertEqual("ok" if ready else "blocked", self.status(report, "atak_sdk"))
                    else:
                        self.assertIn("ok: configuration_format:", result.stdout)
                        self.assertIn(("ok" if ready else "blocked") + ": atak_sdk:", result.stdout)
                        self.assertIn("Prerequisites only", result.stdout)
        self.properties.write_text("private.fixture=secret\\escape\n", encoding="ascii")
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--json"],
                                env={"PATH": ""}, capture_output=True, text=True, timeout=5)
        self.assertEqual(1, result.returncode)
        self.assertEqual("", result.stderr)
        self.assertEqual("blocked", self.status(json.loads(result.stdout), "configuration_format"))
        self.assertNotIn("secret", result.stdout)
        self.assertNotIn("private.fixture", result.stdout)

    def test_java_probe_parses_version_and_handles_failed_launcher(self):
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="", stderr='openjdk version "17.0.12"'))
        self.assertEqual(17, self.doctor.detect_java_major({"JAVA_HOME": "/fixture/jdk"}, run=runner))
        self.assertEqual(["/fixture/jdk/bin/java", "-version"], runner.call_args.args[0])
        runner.return_value = SimpleNamespace(returncode=1, stdout="", stderr="No Java Runtime")
        self.assertIsNone(self.doctor.detect_java_major({"JAVA_HOME": "/fixture/jdk"}, run=runner))
        runner.return_value = SimpleNamespace(returncode=0, stdout="", stderr='java version "1.8.0"')
        self.assertEqual(8, self.doctor.detect_java_major({"JAVA_HOME": "/fixture/jdk"}, run=runner))


if __name__ == "__main__":
    unittest.main()
