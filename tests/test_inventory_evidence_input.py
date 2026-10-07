"""Isolated evidence input regressions; never read developer configuration."""
import contextlib
import io
import hashlib
import json
import os
from unittest import mock
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path

from test_dependency_inventory import fixture_repo, tool, write


class EvidenceInputTests(unittest.TestCase):
    def test_evidence_path_policy_rejects_outside_and_credential_carriers_before_read(self):
        module = tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            ev = fixture_repo(root)
            candidates = ('credentials.json', 'Secrets.JSON', 'google-services.json',
                          'local.properties', 'sdk/license-evidence.json', 'bad:name.json')
            for rel in candidates:
                with self.subTest(rel=rel):
                    candidate = write(root, rel, json.dumps(ev))
                    with self.assertRaises(module.InventoryError):
                        module.build(root, candidate)
            outside = write(tmp, 'outside.json', json.dumps(ev))
            for candidate in (outside, root / '../outside.json'):
                with self.subTest(outside=True), self.assertRaises(module.InventoryError):
                    module.build(root, candidate)
            # CLI must validate the literal token before pathlib normalises it.
            for rel in ('../outside.json', '/outside.json', './verification/license-evidence.json',
                        'verification//license-evidence.json', 'verification/../verification/license-evidence.json'):
                err = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                    code = module.main(['--root', str(root), '--evidence', rel])
                self.assertEqual(code, 2, err.getvalue())
                self.assertNotIn(tmp, err.getvalue())
            self.assertFalse((root / 'dist').exists())

    def test_evidence_digest_identifies_the_single_parsed_snapshot(self):
        module = tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ev = fixture_repo(root)
            rel = 'verification/license-evidence.json'
            path = root / rel
            original = path.read_bytes()
            parse = module.strict_json_text

            def replace_after_parse(text, label):
                result = parse(text, label)
                if label in (rel, path.name):
                    write(root, rel, json.dumps({**ev, 'disclaimer': 'Different subsequent evidence snapshot.'}))
                return result

            with mock.patch.object(module, 'strict_json_text', replace_after_parse), \
                    mock.patch.object(module, 'read_input', wraps=module.read_input) as reads:
                sbom, notices = module.build(root, path)
            props = sbom['metadata']['properties']
            self.assertIn({'name': 'emcon:input', 'value': rel + ' sha256:' + hashlib.sha256(original).hexdigest()}, props)
            self.assertNotEqual(original, path.read_bytes())
            self.assertIn(ev['disclaimer'], notices)
            self.assertEqual(sum(call.args[1] == rel for call in reads.call_args_list), 1)

    def test_evidence_hardlink_is_rejected(self):
        module = tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            fixture_repo(root)
            path = root / 'verification/license-evidence.json'
            os.link(path, Path(tmp) / 'linked.json')
            with self.assertRaises(module.InventoryError):
                module.build(root, path)

    def test_directory_symlink_swap_after_validation_cannot_redirect_evidence_read(self):
        module = tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            ev = fixture_repo(root)
            external = Path(tmp) / 'external'
            write(external, 'license-evidence.json', json.dumps(ev))
            rel = 'verification/license-evidence.json'
            validated = module.safe_input(root, rel, 'evidence')
            (root / 'verification').rename(root / 'saved-verification')
            (root / 'verification').symlink_to(external, target_is_directory=True)
            with self.assertRaises(module.InventoryError):
                module.read_input(validated, rel)

    def test_fifo_swap_is_rejected_without_blocking(self):
        module = tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            rel = 'verification/license-evidence.json'
            validated = module.safe_input(root, rel, 'evidence')
            validated.unlink()
            os.mkfifo(validated)
            worker = write(root, 'read_worker.py',
                'import sys\nimport importlib.util\nfrom pathlib import Path\n'
                'spec = importlib.util.spec_from_file_location("inventory", sys.argv[3])\n'
                'm = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(m)\n'
                'try:\n    m.read_input(Path(sys.argv[1]), sys.argv[2])\n'
                'except m.InventoryError:\n    sys.exit(0)\nsys.exit(1)\n')
            assert module.__file__ is not None
            try:
                result = subprocess.run([sys.executable, '-B', str(worker), str(validated), rel, module.__file__],
                                        capture_output=True, timeout=3)
            except subprocess.TimeoutExpired:
                self.fail('input reader blocked opening the substituted FIFO')
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_oversized_evidence_is_rejected(self):
        module = tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            path = root / 'verification/license-evidence.json'
            original = path.read_bytes()
            path.write_bytes(original + b' ' * (4 * 1024 * 1024 + 1 - len(original)))
            with self.assertRaises(module.InventoryError):
                module.build(root, path)

    def test_preexisting_symlinks_and_case_aliases_are_rejected(self):
        module = tool()
        for kind in ('file', 'directory', 'case'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ev = fixture_repo(root)
                if kind == 'file':
                    write(root, 'verification/other.json', json.dumps(ev))
                    path = root / 'verification/license-evidence.json'
                    path.unlink()
                    path.symlink_to('other.json')
                elif kind == 'directory':
                    (root / 'alias').symlink_to('verification', target_is_directory=True)
                    path = root / 'alias/license-evidence.json'
                else:
                    path = root / 'Verification/license-evidence.json'
                with self.assertRaises(module.InventoryError):
                    module.build(root, path)

    def test_read_descriptor_ownership_survives_fdopen_failure(self):
        module = tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            rel = 'verification/license-evidence.json'
            path = module.safe_input(root, rel, 'evidence')
            real_open = os.open
            acquired = []

            def acquire(*args, **kwargs):
                fd = real_open(*args, **kwargs)
                acquired.append(fd)
                return fd

            with mock.patch.object(module.os, 'open', acquire), \
                    mock.patch.object(module.os, 'fdopen', side_effect=OSError('fixture')):
                with self.assertRaises(module.InventoryError):
                    module.read_input(path, rel)
            self.assertEqual(len(acquired), 3)
            for fd in acquired:
                with self.assertRaises(OSError):
                    os.fstat(fd)

    def test_exact_size_limit_is_supported(self):
        module = tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_repo(root)
            path = root / 'verification/license-evidence.json'
            original = path.read_bytes()
            data = original + b' ' * (4 * 1024 * 1024 - len(original))
            path.write_bytes(data)
            sbom, _ = module.build(root, path)
            self.assertIn({'name': 'emcon:input', 'value': 'verification/license-evidence.json sha256:' + hashlib.sha256(data).hexdigest()},
                          sbom['metadata']['properties'])


if __name__ == '__main__':
    unittest.main()
