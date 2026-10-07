"""Committed-notices gate on isolated synthetic repositories, without ignored outputs."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_dependency_inventory import SCRIPT, fixture_repo, tool, write


class NoticesDriftTests(unittest.TestCase):
    def run_cli(self, root, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), '--root', str(root), *args],
                              capture_output=True, text=True, timeout=10)

    def test_check_notices_accepts_fresh_notices_without_ignored_sbom(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            _, notices = tool().build(root, root / 'verification/license-evidence.json')
            output = write(root, 'docs/third-party-notices.md', notices)
            before = output.read_bytes()
            before_stat = output.stat()
            result = self.run_cli(root, '--check-notices')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)['checked'])
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual((output.stat().st_ino, output.stat().st_mtime_ns),
                             (before_stat.st_ino, before_stat.st_mtime_ns))
            self.assertFalse((root / 'dist').exists())
            self.assertNotIn(str(root), result.stdout + result.stderr)

    def test_stale_or_missing_notices_fail_without_rewriting_or_creating_outputs(self):
        for contents in (None, 'hand edited\n'):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fixture_repo(root)
                output = root / 'docs/third-party-notices.md'
                if contents is not None:
                    write(root, 'docs/third-party-notices.md', contents)
                result = self.run_cli(root, '--check-notices')
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stderr,
                                 'error: generated output is stale: docs/third-party-notices.md\n')
                self.assertEqual(result.stdout, '')
                self.assertEqual(output.exists(), contents is not None)
                if contents is not None:
                    self.assertEqual(output.read_text(), contents)
                self.assertFalse((root / 'dist').exists())

    def test_changed_declaration_fails_against_previously_fresh_notices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            _, notices = tool().build(root, root / 'verification/license-evidence.json')
            output = write(root, 'docs/third-party-notices.md', notices)
            declaration = root / 'plugin/app/build.gradle'
            declaration.write_text(declaration.read_text().replace('gson:2.10.1', 'gson:2.10.2'))
            result = self.run_cli(root, '--check-notices')
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('docs/third-party-notices.md', result.stderr)
            self.assertEqual(output.read_text(), notices)
            self.assertFalse((root / 'dist').exists())

    def test_ignored_sbom_is_not_inspected_but_full_check_still_requires_it(self):
        import os
        for kind in ('absent', 'stale', 'directory-symlink', 'file-symlink', 'fifo'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fixture_repo(root)
                _, notices = tool().build(root, root / 'verification/license-evidence.json')
                output = write(root, 'docs/third-party-notices.md', notices)
                sentinel = write(root, 'outside/sentinel.json', 'private synthetic sentinel')
                sbom = root / 'dist/source-sbom.cdx.json'
                if kind == 'directory-symlink':
                    sbom.parent.symlink_to(sentinel.parent, target_is_directory=True)
                elif kind != 'absent':
                    sbom.parent.mkdir()
                    if kind == 'stale':
                        sbom.write_text('stale')
                    elif kind == 'file-symlink':
                        sbom.symlink_to(sentinel)
                    else:
                        os.mkfifo(sbom)
                result = self.run_cli(root, '--check-notices')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output.read_text(), notices)
                self.assertEqual(sentinel.read_text(), 'private synthetic sentinel')
                self.assertNotIn(str(root), result.stdout + result.stderr)
                full = self.run_cli(root, '--check')
                self.assertEqual(full.returncode, 1 if kind in ('absent', 'stale') else 3)
                self.assertEqual(output.read_text(), notices)

    def test_unsafe_notices_are_rejected_without_touching_target(self):
        import os
        for kind in ('directory-symlink', 'file-symlink', 'hardlink', 'fifo'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fixture_repo(root)
                sentinel = write(root, 'outside/sentinel.md', 'private synthetic sentinel')
                output = root / 'docs/third-party-notices.md'
                if kind == 'directory-symlink':
                    output.parent.symlink_to(sentinel.parent, target_is_directory=True)
                else:
                    output.parent.mkdir()
                    if kind == 'file-symlink':
                        output.symlink_to(sentinel)
                    elif kind == 'hardlink':
                        os.link(sentinel, output)
                    else:
                        os.mkfifo(output)
                result = self.run_cli(root, '--check-notices')
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertEqual(sentinel.read_text(), 'private synthetic sentinel')
                self.assertNotIn(str(root), result.stdout + result.stderr)
                self.assertFalse((root / 'dist').exists())

    def test_custom_notices_path_is_checked_without_creating_default_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            _, notices = tool().build(root, root / 'verification/license-evidence.json')
            output = write(root, 'docs/custom.md', notices)
            result = self.run_cli(root, '--check-notices', '--notices', 'docs/custom.md')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_text(), notices)
            self.assertFalse((root / 'docs/third-party-notices.md').exists())
            self.assertFalse((root / 'dist').exists())

    def test_invalid_inputs_fail_even_when_notices_are_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            _, notices = tool().build(root, root / 'verification/license-evidence.json')
            output = write(root, 'docs/third-party-notices.md', notices)
            write(root, 'LICENSE', 'changed')
            result = self.run_cli(root, '--check-notices')
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(output.read_text(), notices)
            self.assertNotIn(str(root), result.stdout + result.stderr)
            self.assertFalse((root / 'dist').exists())

    def test_check_modes_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            result = self.run_cli(root, '--check', '--check-notices')
            self.assertEqual(result.returncode, 2)
            self.assertIn('not allowed with argument', result.stderr)
            self.assertFalse((root / 'docs/third-party-notices.md').exists())
            self.assertFalse((root / 'dist').exists())


if __name__ == '__main__':
    unittest.main()
