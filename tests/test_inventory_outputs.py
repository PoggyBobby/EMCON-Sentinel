"""Output safety regressions using isolated synthetic repositories only."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from test_dependency_inventory import fixture_repo, tool, write


class OutputSafetyTests(unittest.TestCase):
    def run_cli(self, module, root, *args):
        errors = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            code = module.main(['--root', str(root), *args])
        self.assertNotIn(str(root), errors.getvalue())
        return code

    def test_output_current_fdopen_failure_closes_all_fds(self):
        import errno
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'artifact.json'
            output.write_text('previous complete artifact', encoding='utf-8')
            module = tool()
            original_open = module.os.open
            opened = []

            def track_open(path, flags, *args, **kwargs):
                fd = original_open(path, flags, *args, **kwargs)
                opened.append(fd)
                return fd

            try:
                with patch.object(module.os, 'open', side_effect=track_open), \
                        patch.object(module.os, 'fdopen', side_effect=OSError('before wrapping')) as fdopen:
                    with self.assertRaisesRegex(OSError, '^before wrapping$'):
                        module.output_current(output, 'previous complete artifact')
                self.assertEqual(len(opened), 2)
                self.assertEqual(fdopen.call_count, 1)
                self.assertEqual(fdopen.call_args.args[0], opened[1])
                self.assertEqual(output.read_text(), 'previous complete artifact')
                self.assertEqual([p.name for p in output.parent.iterdir()], [output.name])
                for fd in opened:
                    with self.subTest(fd=fd):
                        with self.assertRaises(OSError) as closed:
                            module.os.fstat(fd)
                        self.assertEqual(closed.exception.errno, errno.EBADF)
            finally:
                for fd in opened:
                    try:
                        module.os.close(fd)
                    except OSError as exc:
                        if exc.errno != errno.EBADF:
                            raise

    def test_write_output_fdopen_failure_closes_all_fds_and_preserves_artifact(self):
        import errno
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'artifact.json'
            output.write_text('previous complete artifact', encoding='utf-8')
            module = tool()
            original_open = module.os.open
            opened = []

            def track_open(path, flags, *args, **kwargs):
                fd = original_open(path, flags, *args, **kwargs)
                opened.append(fd)
                return fd

            try:
                with patch.object(module.os, 'open', side_effect=track_open), \
                        patch.object(module.os, 'fdopen', side_effect=OSError('before wrapping')) as fdopen:
                    with self.assertRaisesRegex(OSError, '^before wrapping$'):
                        module.write_output(output, 'replacement artifact')
                self.assertEqual(len(opened), 2)
                self.assertEqual(fdopen.call_count, 1)
                self.assertEqual(fdopen.call_args.args[0], opened[1])
                self.assertEqual(output.read_text(), 'previous complete artifact')
                self.assertEqual([p.name for p in output.parent.iterdir()], [output.name])
                for fd in opened:
                    with self.subTest(fd=fd):
                        with self.assertRaises(OSError) as closed:
                            module.os.fstat(fd)
                        self.assertEqual(closed.exception.errno, errno.EBADF)
            finally:
                for fd in opened:
                    try:
                        module.os.close(fd)
                    except OSError as exc:
                        if exc.errno != errno.EBADF:
                            raise

    def test_write_refuses_target_swapped_to_symlink_during_fsync(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            module = tool()
            output = write(root, 'dist/source-sbom.cdx.json', 'previous complete artifact')
            saved = root / 'dist/saved.json'
            sentinel = write(root, 'sentinel.txt', 'unchanged')
            original = module.os.fsync

            def swap_then_sync(fd):
                output.rename(saved)
                output.symlink_to(sentinel)
                return original(fd)

            with patch.object(module.os, 'fsync', side_effect=swap_then_sync):
                self.assertEqual(self.run_cli(module, root), 3)
            self.assertTrue(output.is_symlink())
            self.assertEqual(sentinel.read_text(), 'unchanged')
            self.assertEqual(saved.read_text(), 'previous complete artifact')
            self.assertEqual(sorted(p.name for p in output.parent.iterdir()), [saved.name, output.name])

    def test_check_refuses_file_swapped_to_symlink_after_preflight(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            module = tool()
            self.assertEqual(self.run_cli(module, root), 0)
            original = module.output_current
            output = root / 'dist/source-sbom.cdx.json'
            saved = root / 'dist/saved.json'

            def swap_then_check(path, text):
                if path == output:
                    output.rename(saved)
                    output.symlink_to(saved)
                return original(path, text)

            with patch.object(module, 'output_current', side_effect=swap_then_check):
                self.assertEqual(self.run_cli(module, root, '--check'), 3)
            self.assertTrue(output.is_symlink())

    def test_special_or_hardlinked_output_is_rejected_before_any_replacement(self):
        import os
        for kind in ('directory', 'fifo', 'hardlink'):
            for check in (False, True):
                with self.subTest(kind=kind, check=check), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    fixture_repo(root)
                    output = root / 'dist/source-sbom.cdx.json'
                    output.parent.mkdir()
                    sentinel = write(root, 'sentinel.txt', 'unchanged')
                    if kind == 'directory':
                        output.mkdir()
                    elif kind == 'fifo':
                        os.mkfifo(output)
                    else:
                        os.link(sentinel, output)
                    args = ['--check'] if check else []
                    self.assertEqual(self.run_cli(tool(), root, *args), 3)
                    self.assertEqual(sentinel.read_text(), 'unchanged')
                    self.assertFalse((root / 'docs/third-party-notices.md').exists())

    def test_fsync_failure_preserves_previous_output_and_removes_partial_file(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            module = tool()
            previous = write(root, 'dist/source-sbom.cdx.json', 'previous complete artifact')
            with patch.object(module.os, 'fsync', side_effect=OSError('synthetic failure')):
                self.assertEqual(self.run_cli(module, root), 3)
            self.assertEqual(previous.read_text(), 'previous complete artifact')
            self.assertEqual([p.name for p in previous.parent.iterdir()], [previous.name])
            self.assertFalse((root / 'docs/third-party-notices.md').exists())

    def test_uuid_failure_closes_destination_directory_and_returns_path_free_io_error(self):
        import errno
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            module = tool()
            original_open = module.os.open
            directories = []

            def track_open(path, flags, *args, **kwargs):
                fd = original_open(path, flags, *args, **kwargs)
                if path == root / 'dist' and flags & module.os.O_DIRECTORY:
                    directories.append(fd)
                return fd

            errors = io.StringIO()
            try:
                with patch.object(module.os, 'open', side_effect=track_open), \
                        patch.object(module.uuid, 'uuid4', side_effect=OSError(str(root / 'secret'))), \
                        contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
                    self.assertEqual(module.main(['--root', str(root)]), 3)
                self.assertEqual(errors.getvalue(),
                                 'error: I/O failure writing or reading outputs (OSError); details suppressed\n')
                self.assertEqual(len(directories), 1)
                with self.assertRaises(OSError) as closed:
                    module.os.fstat(directories[0])
                self.assertEqual(closed.exception.errno, errno.EBADF)
                self.assertEqual(list((root / 'dist').iterdir()), [])
                self.assertFalse((root / 'docs/third-party-notices.md').exists())
            finally:
                for fd in directories:
                    try:
                        module.os.close(fd)
                    except OSError as exc:
                        if exc.errno != errno.EBADF:
                            raise

    def test_output_paths_outside_narrow_artifact_allowlist_are_rejected(self):
        cases = {
            '--output': ['../escaped.json', 'dist/../escaped.json', 'plugin/app/state.json',
                         'verification/dependencies.json', 'dist/.hidden.json', 'dist/nested/sbom.json',
                         'docs/sbom.json', 'dist/sbom.txt', 'DIST/sbom.json'],
            '--notices': ['../escaped.md', 'dist/notices.md', 'plugin/README.md',
                          'docs/../README.md', 'docs/.hidden.md', 'docs/nested/notices.md', 'docs/notices.json'],
        }
        for flag, paths in cases.items():
            for rel in paths:
                with self.subTest(flag=flag, rel=rel), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp) / 'repo'
                    root.mkdir()
                    fixture_repo(root)
                    self.assertEqual(self.run_cli(tool(), root, flag, rel), 3)
                    self.assertFalse((root / 'dist/source-sbom.cdx.json').exists())
                    self.assertFalse((root / 'docs/third-party-notices.md').exists())
                    self.assertFalse((root.parent / 'escaped.json').exists())
                    self.assertFalse((root.parent / 'escaped.md').exists())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            root.mkdir()
            fixture_repo(root)
            destination = Path(tmp) / 'absolute.json'
            self.assertEqual(self.run_cli(tool(), root, '--output', str(destination)), 3)
            self.assertFalse(destination.exists())

    def test_root_reached_through_ancestor_symlink_generates_and_checks_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / 'real'
            root = real / 'repo'
            fixture_repo(root)
            alias = Path(tmp) / 'alias'
            alias.symlink_to(real, target_is_directory=True)
            module = tool()
            aliased_root = alias / 'repo'
            self.assertEqual(self.run_cli(module, aliased_root), 0)
            self.assertTrue((root / 'dist/source-sbom.cdx.json').is_file())
            self.assertTrue((root / 'docs/third-party-notices.md').is_file())
            self.assertEqual(self.run_cli(module, aliased_root, '--check'), 0)

    def test_symlinked_output_directory_is_rejected_before_either_output_is_written(self):
        for directory in ('dist', 'docs'):
            for check in (False, True):
                with self.subTest(directory=directory, check=check), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    fixture_repo(root)
                    outside = root / 'outside'
                    outside.mkdir()
                    (root / directory).symlink_to(outside, target_is_directory=True)
                    args = ['--check'] if check else []
                    self.assertEqual(self.run_cli(tool(), root, *args), 3)
                    self.assertEqual(list(outside.iterdir()), [])
                    self.assertFalse((root / 'dist/source-sbom.cdx.json').exists())
                    self.assertFalse((root / 'docs/third-party-notices.md').exists())

    def test_symlinked_output_file_is_rejected_without_touching_target(self):
        for check in (False, True):
            with self.subTest(check=check), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fixture_repo(root)
                target = write(root, 'sentinel.txt', 'unchanged')
                output = root / 'dist/source-sbom.cdx.json'
                output.parent.mkdir()
                output.symlink_to(target)
                args = ['--check'] if check else []
                self.assertEqual(self.run_cli(tool(), root, *args), 3)
                self.assertEqual(target.read_text(), 'unchanged')
                self.assertTrue(output.is_symlink())
                self.assertFalse((root / 'docs/third-party-notices.md').exists())


if __name__ == '__main__':
    unittest.main()
