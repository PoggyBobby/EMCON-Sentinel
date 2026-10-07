"""Offline association regressions, using isolated synthetic repository fixtures."""
import tempfile
import unittest
from pathlib import Path

from test_dependency_inventory import fixture_repo, mutate_evidence, tool


class AssociationTests(unittest.TestCase):
    def test_maven_group_segments_cannot_create_empty_or_dot_paths(self):
        import json
        for group in ('x..y', 'x.', 'x.-y'):
            with self.subTest(group=group), tempfile.TemporaryDirectory() as tmp:
                ev = fixture_repo(tmp)
                coordinate = f'{group}:sample:1'
                base = 'https://repo.maven.apache.org/maven2/' + group.replace('.', '/') + '/sample/1/sample-1'
                ev['maven'] = {coordinate: {
                    'artifact': {'url': base + '.jar'},
                    'licenseEvidence': [{
                        'relation': 'self', 'pomCoordinate': coordinate,
                        'url': base + '.pom', 'retrievedAtUtc': '2026-10-07T05:54:00Z',
                        'declaredLicenses': [{'name': 'Synthetic license'}],
                    }],
                }}
                with self.assertRaisesRegex(ValueError, 'Maven group segments'):
                    tool().load_evidence(json.dumps(ev), 'verification/license-evidence.json')

    def test_observed_license_metadata_matches_narrow_npm_identity(self):
        cases = (
            {'url': 'https://registry.npmjs.org/other/1.9.4'},
            {'url': 'https://registry.npmjs.org/leaflet/1.9.3'},
            {'url': 'https://example.org/leaflet/1.9.4'},
            {'relation': 'self'},
            {'pomCoordinate': 'junit:junit:4.13.2'},
            {'parentCoordinate': 'junit:junit:4.13.2'},
            {'purl': 'pkg:npm/other@1.9.4'},
            {'version': None},
            {'name': '@scope/leaflet'},
        )
        for fields in cases:
            with self.subTest(fields=fields), tempfile.TemporaryDirectory() as tmp:
                ev = fixture_repo(tmp)
                def change(data):
                    item = data['observed'][0]
                    for key, value in fields.items():
                        if key in ('purl', 'name', 'version'):
                            if value is None:
                                item.pop(key)
                            else:
                                item[key] = value
                        else:
                            item['licenseEvidence'][0][key] = value
                mutate_evidence(tmp, ev, change)
                with self.assertRaisesRegex(ValueError, 'observed license evidence'):
                    tool().build(Path(tmp), Path(tmp) / 'verification/license-evidence.json')

    def test_observed_npm_selectors_fail_even_when_identity_fields_agree(self):
        for version in ('latest', 'next', '1', '1.9', '1.x', '01.9.4'):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                ev = fixture_repo(tmp)
                module = tool()
                module.build(Path(tmp), Path(tmp) / 'verification/license-evidence.json')
                def change(data):
                    item = data['observed'][0]
                    item['version'] = version
                    item['purl'] = f'pkg:npm/leaflet@{version}'
                    item['licenseEvidence'][0]['url'] = f'https://registry.npmjs.org/leaflet/{version}'
                mutate_evidence(tmp, ev, change)
                with self.assertRaisesRegex(ValueError, 'observed license evidence'):
                    module.build(Path(tmp), Path(tmp) / 'verification/license-evidence.json')

    def test_observed_stable_npm_versions_preserve_license_association(self):
        for version in ('0.0.0', '1.9.4'):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                ev = fixture_repo(tmp)
                def change(data):
                    item = data['observed'][0]
                    item['version'] = version
                    item['purl'] = f'pkg:npm/leaflet@{version}'
                    item['licenseEvidence'][0]['url'] = f'https://registry.npmjs.org/leaflet/{version}'
                mutate_evidence(tmp, ev, change)
                sbom, notices = tool().build(Path(tmp), Path(tmp) / 'verification/license-evidence.json')
                leaflet = next(c for c in sbom['components'] if c['name'] == 'leaflet')
                self.assertEqual(leaflet['version'], version)
                self.assertEqual(leaflet['purl'], f'pkg:npm/leaflet@{version}')
                self.assertEqual(leaflet['licenses'], [{'license': {'name': 'BSD-2-Clause', 'acknowledgement': 'declared'}}])
                self.assertIn(f'https://registry.npmjs.org/leaflet/{version}', notices)

    def test_parent_coordinate_has_maven_token_type_and_format(self):
        for value in (None, [], {}, 7, 'junit:junit', 'junit:junit:4.13.2 ', '/Users/example/private'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                ev = fixture_repo(tmp)
                mutate_evidence(tmp, ev, lambda d: d['maven']['junit:junit:4.13.2']['licenseEvidence'][0].update(parentCoordinate=value))
                import contextlib
                import io
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    code = tool().main(['--root', tmp])
                self.assertEqual(code, 2, err.getvalue())
                self.assertIn('parentCoordinate must be group:artifact:version', err.getvalue())
                self.assertNotIn(tmp, err.getvalue())

    def test_parent_evidence_must_follow_recorded_links_from_one_self_entry(self):
        parent = {
            'relation': 'parent', 'pomCoordinate': 'example:parent:1',
            'url': 'https://repo.maven.apache.org/maven2/example/parent/1/parent-1.pom',
            'retrievedAtUtc': '2026-10-07T05:54:00Z',
            'declaredLicenses': [{'name': 'Synthetic inherited license'}],
        }
        cases = ('missing-self', 'duplicate-self', 'unlinked-parent', 'self-as-parent')
        for defect in cases:
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                ev = fixture_repo(tmp)
                def change(data):
                    entries = data['maven']['junit:junit:4.13.2']['licenseEvidence']
                    if defect == 'missing-self':
                        entries[:] = [dict(parent)]
                    elif defect == 'duplicate-self':
                        entries.append(dict(entries[0]))
                    elif defect == 'unlinked-parent':
                        entries.append(dict(parent))
                    else:
                        entries[0]['relation'] = 'parent'
                mutate_evidence(tmp, ev, change)
                with self.assertRaisesRegex(ValueError, 'Maven evidence'):
                    tool().build(Path(tmp), Path(tmp) / 'verification/license-evidence.json')

    def test_self_pom_requires_matching_coordinate_and_canonical_url(self):
        cases = (
            {'url': 'https://repo.maven.apache.org/maven2/x/y/1/y-1.pom'},
            {'url': 'https://example.org/junit/junit/4.13.2/junit-4.13.2.pom'},
            {'url': 'https://repo.maven.apache.org/maven2/junit/junit/4.13.2/junit-4.13.2.jar'},
            {'pomCoordinate': 'x:y:1', 'url': 'https://repo.maven.apache.org/maven2/x/y/1/y-1.pom'},
            {'relation': 'registry-metadata'},
            {'pomCoordinate': None},
            {'selfNotRoot': True},
        )
        for fields in cases:
            with self.subTest(fields=fields), tempfile.TemporaryDirectory() as tmp:
                ev = fixture_repo(tmp)
                def change(data):
                    entries = data['maven']['junit:junit:4.13.2']['licenseEvidence']
                    entry = entries[0]
                    if 'selfNotRoot' in fields:
                        entry.update(relation='parent', parentCoordinate='x:y:1')
                        entries.append({
                            **entry, 'relation': 'self', 'pomCoordinate': 'x:y:1',
                            'url': 'https://repo.maven.apache.org/maven2/x/y/1/y-1.pom',
                        })
                        del entries[-1]['parentCoordinate']
                        return
                    entry.update(fields)
                    if entry.get('pomCoordinate') is None:
                        del entry['pomCoordinate']
                mutate_evidence(tmp, ev, change)
                with self.assertRaisesRegex(ValueError, 'Maven evidence'):
                    tool().build(Path(tmp), Path(tmp) / 'verification/license-evidence.json')

    def test_linked_parent_chain_preserves_inherited_licenses_independent_of_entry_order(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse), tempfile.TemporaryDirectory() as tmp:
                ev = fixture_repo(tmp)
                def change(data):
                    entries = data['maven']['junit:junit:4.13.2']['licenseEvidence']
                    entries[0]['declaredLicenses'] = []
                    entries[0]['parentCoordinate'] = 'example:parent:1'
                    entries.append({
                        'relation': 'parent', 'pomCoordinate': 'example:parent:1',
                        'url': 'https://repo.maven.apache.org/maven2/example/parent/1/parent-1.pom',
                        'retrievedAtUtc': '2026-10-07T05:54:00Z',
                        'declaredLicenses': [{'name': 'Synthetic inherited license'}],
                    })
                    if reverse:
                        entries.reverse()
                mutate_evidence(tmp, ev, change)
                sbom, notices = tool().build(Path(tmp), Path(tmp) / 'verification/license-evidence.json')
                junit = next(c for c in sbom['components'] if c['name'] == 'junit')
                self.assertEqual(junit['licenses'], [{'license': {'name': 'Synthetic inherited license', 'acknowledgement': 'declared'}}])
                self.assertIn('Synthetic inherited license', notices)

    def test_parent_chain_rejects_duplicate_parent_and_cycle(self):
        for defect in ('duplicate', 'cycle'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                ev = fixture_repo(tmp)
                def change(data):
                    entries = data['maven']['junit:junit:4.13.2']['licenseEvidence']
                    entries[0]['parentCoordinate'] = 'example:parent:1'
                    entries.append({
                        'relation': 'parent', 'pomCoordinate': 'example:parent:1',
                        'url': 'https://repo.maven.apache.org/maven2/example/parent/1/parent-1.pom',
                        'retrievedAtUtc': '2026-10-07T05:54:00Z',
                        'declaredLicenses': [{'name': 'Synthetic license'}],
                    })
                    if defect == 'duplicate':
                        entries.append(dict(entries[-1]))
                    else:
                        entries[-1]['parentCoordinate'] = 'junit:junit:4.13.2'
                mutate_evidence(tmp, ev, change)
                with self.assertRaisesRegex(ValueError, 'Maven evidence'):
                    tool().build(Path(tmp), Path(tmp) / 'verification/license-evidence.json')

    def test_gradle_only_artifact_url_must_match_its_maven_coordinate(self):
        urls = (
            'https://repo.maven.apache.org/maven2/x/y/1/y-1.jar',
            'https://example.org/com/google/code/gson/gson/2.10.1/gson-2.10.1.jar',
            'https://repo.maven.apache.org/maven2/com/google/code/gson/gson/2.10.1/gson-2.10.1-sources.jar',
        )
        for url in urls:
            with self.subTest(url=url), tempfile.TemporaryDirectory() as tmp:
                ev = fixture_repo(tmp)
                def change(data):
                    data['maven']['com.google.code.gson:gson:2.10.1'] = {
                        'artifact': {'url': url},
                        'licenseEvidence': [{
                            'relation': 'self', 'pomCoordinate': 'com.google.code.gson:gson:2.10.1',
                            'url': 'https://repo.maven.apache.org/maven2/com/google/code/gson/gson/2.10.1/gson-2.10.1.pom',
                            'retrievedAtUtc': '2026-10-07T05:54:00Z',
                            'declaredLicenses': [{'name': 'Synthetic license'}],
                        }],
                    }
                mutate_evidence(tmp, ev, change)
                with self.assertRaisesRegex(ValueError, 'artifact URL must match Maven coordinate'):
                    tool().build(Path(tmp), Path(tmp) / 'verification/license-evidence.json')
