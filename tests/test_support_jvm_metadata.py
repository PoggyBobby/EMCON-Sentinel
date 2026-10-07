"""Synthetic manifest/runner linkage fixtures; never use developer config."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/support_report.py"
INPUTS = ("verification/java-tests.json", "verification/dependencies.json",
          "scripts/test_java.py")
SUMMARY = "verification/build/jvm/summary.json"
SUCCESS = ("Saved JVM manifest/runner hashes match current bytes; "
           "test execution and source/assets were not verified.\n")


class JvmMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="support-jvm-metadata-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hashes = {}
        for relative, data in zip(INPUTS, (b'{"synthetic": 1}\n', b'[]\n', b'# synthetic runner\n')):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.hashes[relative] = hashlib.sha256(data).hexdigest()
        self.summary = self.root / SUMMARY
        self.summary.parent.mkdir(parents=True)
        self.save({"inputs_sha256": self.hashes})

    def save(self, value):
        self.summary.write_text(json.dumps(value))

    def cli(self, *extra):
        return subprocess.run([sys.executable, "-I", "-B", str(SCRIPT), "--root",
                               str(self.root), "--check-jvm-metadata", *extra],
                              capture_output=True, text=True, timeout=30,
                              env={"PATH": os.defpath, "HOME": str(self.root / "no-home")})

    def test_changed_fixed_input_is_refused_without_values_or_writes(self):
        for relative in INPUTS:
            with self.subTest(relative):
                path = self.root / relative
                original = path.read_bytes()
                path.write_bytes(original + b'SYNTHETIC_PRIVATE_DETAIL\n')
                before = self.summary.read_bytes()
                result = self.cli()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.summary.read_bytes(), before)
                for value in (str(self.root), "SYNTHETIC_PRIVATE_DETAIL", "Traceback"):
                    self.assertNotIn(value, result.stdout + result.stderr)
                self.assertFalse((self.root / "dist").exists())
                path.write_bytes(original)

    def assert_refused(self):
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr,
                         "Saved JVM manifest/runner linkage is missing, unsafe, invalid or differs; "
                         "nothing was written.\n")
        self.assertFalse((self.root / "dist").exists())
        for value in (str(self.root), "SYNTHETIC_PRIVATE_DETAIL", "Traceback"):
            self.assertNotIn(value, result.stdout + result.stderr)

    def test_missing_fixed_input_or_summary_is_refused(self):
        for relative in (*INPUTS, SUMMARY):
            with self.subTest(relative):
                path = self.root / relative
                original = path.read_bytes()
                path.unlink()
                self.assert_refused()
                self.assertFalse(path.exists())
                path.write_bytes(original)

    def test_malformed_linkage_is_refused_without_disclosure(self):
        for relative in INPUTS:
            for digest in (None, True, 1, [], {}, "0" * 64,
                           self.hashes[relative].upper(), "SYNTHETIC_PRIVATE_DETAIL"):
                with self.subTest(relative=relative, digest=digest):
                    self.save({"inputs_sha256": dict(self.hashes, **{relative: digest})})
                    self.assert_refused()
            incomplete = dict(self.hashes)
            incomplete.pop(relative)
            self.save({"inputs_sha256": incomplete})
            self.assert_refused()
        for value in (None, [], {}, {"inputs_sha256": None}, {"inputs_sha256": []},
                      {"inputs_sha256": "SYNTHETIC_PRIVATE_DETAIL"}):
            with self.subTest(value=value):
                self.save(value)
                self.assert_refused()
        base = json.dumps({"inputs_sha256": self.hashes}).encode()
        for payload in (b'{SYNTHETIC_PRIVATE_DETAIL', b'\xff',
                        base[:-1] + b', "inputs_sha256": {}}',
                        base[:-1] + b', "extra": NaN}',
                        b'[' * 100000 + b']' * 100000):
            with self.subTest(payload=payload[:32]):
                self.summary.write_bytes(payload)
                self.assert_refused()

    def test_symlinked_or_fifo_fixed_inputs_are_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        for relative in (*INPUTS, SUMMARY):
            with self.subTest(relative):
                path = self.root / relative
                original = path.read_bytes()
                target = outside / "synthetic"
                target.write_bytes(original)
                path.unlink()
                path.symlink_to(target)
                self.assert_refused()
                self.assertTrue(path.is_symlink())
                path.unlink()
                os.mkfifo(path)
                self.assert_refused()
                path.unlink()
                path.write_bytes(original)
                self.assertEqual(target.read_bytes(), original)
        build = self.root / "verification/build"
        moved = self.root / "saved-build"
        build.rename(moved)
        build.symlink_to(moved, target_is_directory=True)
        self.assert_refused()
        self.assertTrue(build.is_symlink())

    def test_oversized_fixed_input_is_refused(self):
        for relative in (*INPUTS, SUMMARY):
            with self.subTest(relative):
                path = self.root / relative
                original = path.read_bytes()
                if relative == SUMMARY:
                    path.write_text(json.dumps({"inputs_sha256": self.hashes,
                                                "extra": "A" * (300 * 1024)}))
                else:
                    data = b"A" * (300 * 1024)
                    path.write_bytes(data)
                    self.save({"inputs_sha256": dict(self.hashes, **{
                        relative: hashlib.sha256(data).hexdigest()})})
                self.assert_refused()
                path.write_bytes(original)
                self.save({"inputs_sha256": self.hashes})

    def test_linkage_does_not_certify_execution_or_source_freshness(self):
        for status in ("passed", "failed", "running", "SYNTHETIC_PRIVATE_DETAIL"):
            with self.subTest(status=status):
                self.save({"inputs_sha256": dict(self.hashes, **{
                    "plugin/app/src/main/java/Synthetic.java": "0" * 64,
                    "../../SYNTHETIC_PRIVATE_DETAIL": "0" * 64}),
                           "status": status, "tests_run": 0,
                           "error": "SYNTHETIC_PRIVATE_DETAIL"})
                result = self.cli()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, SUCCESS)
                self.assertNotIn("SYNTHETIC_PRIVATE_DETAIL", result.stdout + result.stderr)
        # Same-length metadata edit still invalidates linkage even if a support
        # projection's counts would be unchanged. This mode hashes raw bytes.
        source = self.root / INPUTS[0]
        source.write_bytes(source.read_bytes().replace(b'1', b'2'))
        self.assert_refused()

    def test_other_check_flag_is_mutually_exclusive(self):
        result = self.cli("--check")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root / "dist").exists())
        self.assertNotIn(str(self.root), result.stdout + result.stderr)

    def test_only_fixed_paths_are_read_once_without_execution(self):
        self.save({"inputs_sha256": dict(self.hashes, **{
            "../SYNTHETIC_PRIVATE_DETAIL": "0" * 64,
            "/private/SYNTHETIC_PRIVATE_DETAIL": "0" * 64}),
                   "commands": ["SYNTHETIC_PRIVATE_DETAIL"]})
        probe = (
            "import importlib.util, json, sys\n"
            "spec = importlib.util.spec_from_file_location('collector', sys.argv[1])\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(module)\n"
            "events = []\n"
            "def hook(event, args):\n"
            "    if event == 'open' and isinstance(args[0], (str, bytes)):\n"
            "        events.append(['open', str(args[0])])\n"
            "    elif event.startswith(('socket.', 'subprocess.', 'os.system', 'os.exec', 'os.posix_spawn', 'urllib.')):\n"
            "        events.append([event, ''])\n"
            "sys.addaudithook(hook)\n"
            "matches = module.jvm_metadata_matches(sys.argv[2])\n"
            "print(json.dumps({'events': events, 'matches': matches}))\n")
        result = subprocess.run([sys.executable, "-I", "-B", "-c", probe,
                                 str(SCRIPT), str(self.root)], capture_output=True,
                                text=True, timeout=30,
                                env={"PATH": os.defpath, "HOME": str(self.root / "no-home")})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIs(data["matches"], True)
        self.assertTrue(all(event == "open" for event, _ in data["events"]))
        opened = [name for _, name in data["events"]]
        for name in ("summary.json", "java-tests.json", "dependencies.json", "test_java.py"):
            self.assertEqual(opened.count(name), 1)
        self.assertEqual(set(opened), {str(self.root), "verification", "build", "jvm",
                                      "summary.json", "java-tests.json", "dependencies.json",
                                      "scripts", "test_java.py"})
        self.assertNotIn("SYNTHETIC_PRIVATE_DETAIL", result.stdout)

    def test_matching_metadata_is_read_only_without_collecting_support(self):
        before = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_ino,
                                            p.stat().st_mtime_ns)
                  for p in self.root.rglob("*") if p.is_file()}
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, SUCCESS)
        self.assertEqual(result.stderr, "")
        after = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_ino,
                                           p.stat().st_mtime_ns)
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(after, before)
        self.assertFalse((self.root / "dist").exists())
        self.assertNotIn(str(self.root), result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
