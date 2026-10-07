"""Stdlib-only source inventory tests; fixtures never resolve Gradle."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/dependency_inventory.py'


def tool():
    spec = importlib.util.spec_from_file_location('dependency_inventory', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ManifestTests(unittest.TestCase):
    def test_observed_maven_manifest_preserves_legacy_and_new_algorithms(self):
        self.assertTrue(SCRIPT.exists(), 'source inventory implementation is missing')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'dependencies.json'
            rows = [
                {'url': 'https://repo.maven.apache.org/maven2/junit/junit/4.13.2/junit-4.13.2.jar', 'sha1': 'a' * 40},
                {'url': 'https://repo.maven.apache.org/maven2/com/google/code/gson/gson/2.10.1/gson-2.10.1.jar', 'sha256': 'b' * 64},
            ]
            path.write_text(json.dumps(rows))
            found = tool().load_verification(path)
            self.assertEqual([r['coordinate'] for r in found], ['junit:junit:4.13.2', 'com.google.code.gson:gson:2.10.1'])
            self.assertEqual(found[0]['hashes'], [{'alg': 'SHA-1', 'content': 'a' * 40}])
            self.assertEqual(found[1]['hashes'], [{'alg': 'SHA-256', 'content': 'b' * 64}])
            self.assertEqual(found[0]['purl'], 'pkg:maven/junit/junit@4.13.2')


    def test_malformed_manifest_fails_closed(self):
        module = tool()
        good = {'url': 'https://repo.maven.apache.org/maven2/junit/junit/4.13.2/junit-4.13.2.jar', 'sha256': 'a' * 64}
        invalid = [[], {}, [good, good], [{**good, 'secret': 'never-export'}],
                   [{**good, 'sha256': 'bad'}], [{'url': good['url']}],
                   [{**good, 'url': good['url'].replace('https:', 'http:')}],
                   [{**good, 'url': good['url'] + '?token=secret'}],
                   [{**good, 'url': good['url'].replace('junit-4.13.2.jar', 'wrong.jar')}],
                   [{**good, 'url': good['url'].replace('repo.maven.apache.org', 'evil.invalid')}]]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'dependencies.json'
            for value in invalid:
                with self.subTest(value=value):
                    path.write_text(json.dumps(value))
                    with self.assertRaises(ValueError):
                        module.load_verification(path)
            path.write_text('[{"url": "https://repo.maven.apache.org/x", "url": "https://repo.maven.apache.org/y"}]')
            with self.assertRaises(ValueError):
                module.load_verification(path)


class GradleTests(unittest.TestCase):
    def test_direct_gradle_declarations_without_resolving_dynamic_or_local_paths(self):
        text = """
        buildscript { def takdevVersion = '2.+'
          dependencies {
            classpath 'com.android.tools.build:gradle:7.4.2'
            if (x) { classpath "com.atakmap.gradle:atak-gradle-takdev:${takdevVersion}" } else { classpath files(takdevPlugin) }
          }
        }
        // implementation 'commented.out:ignored:1.0'
        dependencies {
          implementation fileTree(dir: 'libs', include: '*.jar')
          implementation 'com.google.code.gson:gson:2.10.1'
          testImplementation 'junit:junit:4.13.2'
        }
        """
        found = tool().parse_gradle_text(text, 'plugin/app/build.gradle')
        self.assertEqual([(f['configuration'], f.get('coordinate'), f['status']) for f in found], [
            ('classpath', 'com.android.tools.build:gradle:7.4.2', 'declared-static'),
            ('classpath', 'com.atakmap.gradle:atak-gradle-takdev:2.+', 'declared-dynamic-unresolved'),
            ('classpath', None, 'local-file-unresolved'),
            ('implementation', None, 'local-file-unresolved'),
            ('implementation', 'com.google.code.gson:gson:2.10.1', 'declared-static'),
            ('testImplementation', 'junit:junit:4.13.2', 'declared-static'),
        ])
        self.assertEqual(found[0]['purl'], 'pkg:maven/com.android.tools.build/gradle@7.4.2')
        self.assertNotIn('purl', found[1])
        self.assertTrue(all(f['source'].startswith('plugin/app/build.gradle:') for f in found))
        self.assertNotIn('takdevPlugin', json.dumps(found))
        self.assertNotIn('/Users/', json.dumps(found))


LICENSE_TEXT = '                                 Apache License\n                           Version 2.0, January 2004\nfixture\n'
JAR = 'https://repo.maven.apache.org/maven2/junit/junit/4.13.2/junit-4.13.2.jar'
POM = JAR[:-4] + '.pom'


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def fixture_repo(root, manifest_digest=('sha1', 'a' * 40)):
    import hashlib
    write(root, 'LICENSE', LICENSE_TEXT)
    write(root, 'plugin/local.properties', 'takrepo.password=SUPERSECRET\n')
    write(root, 'verification/dependencies.json', json.dumps([{'url': JAR, manifest_digest[0]: manifest_digest[1]}]))
    write(root, 'plugin/build.gradle', "buildscript { dependencies { classpath 'com.android.tools.build:gradle:7.4.2' } }\n"
          "configurations.all { resolutionStrategy { dependencySubstitution { substitute module('net.sf.proguard:proguard-gradle') with module('com.guardsquare:proguard-gradle:7.1.1') } } }\n")
    write(root, 'plugin/app/build.gradle', "def v = '2.+'\nbuildscript { repositories { maven { credentials { password = takrepoPassword } } }\n"
          "dependencies { classpath \"com.atakmap.gradle:atak-gradle-takdev:${v}\"\n classpath files(takdevPlugin) } }\n"
          "dependencies { testImplementation 'junit:junit:4.13.2'\n implementation 'com.google.code.gson:gson:2.10.1' }\n")
    write(root, 'plugin/gradle/wrapper/gradle-wrapper.properties',
          'distributionUrl=https\\://services.gradle.org/distributions/gradle-7.6.4-all.zip\ndistributionSha256Sum=' + 'c' * 64 + '\n')
    write(root, 'sim/index.html', '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script> tile.openstreetmap.org\n')
    evidence = {
        'schema': 'emcon-sentinel.license-evidence.v1',
        'disclaimer': 'Upstream-declared metadata only; not a legal determination.',
        'inputs': {'verificationManifest': 'verification/dependencies.json',
                   'gradleBuildFiles': ['plugin/build.gradle', 'plugin/app/build.gradle'],
                   'gradleWrapperProperties': 'plugin/gradle/wrapper/gradle-wrapper.properties'},
        'project': {'name': 'EMCON-Sentinel', 'licenseId': 'Apache-2.0', 'licenseFile': 'LICENSE',
                    'licenseFileSha256': hashlib.sha256(LICENSE_TEXT.encode()).hexdigest(), 'basis': 'fixture'},
        'maven': {'junit:junit:4.13.2': {
            'artifact': {'url': JAR, 'sha1': 'a' * 40, 'sha256': 'b' * 64},
            'licenseEvidence': [{'relation': 'self', 'pomCoordinate': 'junit:junit:4.13.2', 'url': POM, 'sha256': 'd' * 64,
                                 'retrievedAtUtc': '2026-10-07T05:54:00Z',
                                 'declaredLicenses': [{'name': 'Eclipse Public License 1.0', 'url': 'http://www.eclipse.org/legal/epl-v10.html'}]}]}},
        'observed': [
            {'id': 'leaflet', 'type': 'library', 'name': 'leaflet', 'version': '1.9.4', 'purl': 'pkg:npm/leaflet@1.9.4',
             'source': 'sim/index.html', 'markers': ['https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'],
             'licenseEvidence': [{'relation': 'registry-metadata', 'url': 'https://registry.npmjs.org/leaflet/1.9.4', 'retrievedAtUtc': '2026-10-07T05:54:00Z',
                                  'declaredLicenses': [{'name': 'BSD-2-Clause'}]}]},
            {'id': 'osm-tiles', 'type': 'service', 'name': 'OpenStreetMap tile service', 'source': 'sim/index.html',
             'markers': ['tile.openstreetmap.org'], 'endpoints': ['https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'],
             'note': 'External service/data; terms and attribution apply separately.'},
            {'id': 'api', 'type': 'service', 'name': 'Example API', 'source': 'sim/index.html',
             'markers': ['tile.openstreetmap.org'], 'endpoints': ['https://api.example.org/path/'], 'note': 'Service terms apply.'}],
        'unknown': [{'id': 'atak-sdk', 'name': 'ATAK SDK', 'note': 'License and redistribution terms unknown; not inventoried.'}],
    }
    write(root, 'verification/license-evidence.json', json.dumps(evidence, indent=2))
    return evidence


class BuildTests(unittest.TestCase):
    def build(self, root):
        return tool().build(Path(root), Path(root) / 'verification/license-evidence.json')

    def test_sbom_merges_observed_sources_with_declared_license_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture_repo(tmp)
            sbom, notices = self.build(tmp)
            self.assertEqual((sbom['bomFormat'], sbom['specVersion']), ('CycloneDX', '1.6'))
            self.assertRegex(sbom['serialNumber'], r'^urn:uuid:[0-9a-f-]{36}$')
            meta = {p['name']: p['value'] for p in sbom['metadata']['properties']}
            self.assertEqual(meta['emcon:sbom:completeness'], 'incomplete')
            self.assertEqual(meta['emcon:sbom:kind'], 'source-observed-inventory; not a release artifact SBOM')
            self.assertEqual(sbom['metadata']['component']['licenses'], [{'license': {'id': 'Apache-2.0', 'acknowledgement': 'declared'}}])
            comps = {c['bom-ref']: c for c in sbom['components']}
            junit = comps['pkg:maven/junit/junit@4.13.2']
            self.assertEqual(junit['hashes'], [{'alg': 'SHA-1', 'content': 'a' * 40}])
            self.assertEqual(junit['licenses'], [{'license': {'name': 'Eclipse Public License 1.0', 'url': 'http://www.eclipse.org/legal/epl-v10.html', 'acknowledgement': 'declared'}}])
            props = {(p['name'], p['value']) for p in junit['properties']}
            self.assertIn(('emcon:observed', 'verification/dependencies.json'), props)
            self.assertIn(('emcon:observed', 'plugin/app/build.gradle:5 testImplementation'), props)
            self.assertIn(('emcon:license:evidence', POM), props)
            self.assertIn('pkg:npm/leaflet@1.9.4', comps)
            self.assertEqual([s['name'] for s in sbom['services']], ['Example API', 'OpenStreetMap tile service'])
            api, osm = sbom['services']
            self.assertEqual(api['endpoints'], ['https://api.example.org/path/'])
            self.assertNotIn('endpoints', osm)  # URI templates are not valid CycloneDX iri-reference values
            self.assertIn({'name': 'emcon:endpoint-template', 'value': 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'}, osm['properties'])
            self.assertIn('Eclipse Public License 1.0', notices)
            self.assertIn('not a legal determination', notices)

    def test_unknown_licenses_and_unresolved_fields_are_explicit_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture_repo(tmp)
            sbom, notices = self.build(tmp)
            comps = {c['name']: c for c in sbom['components']}
            gson = comps['gson']
            self.assertNotIn('licenses', gson)
            self.assertNotIn('hashes', gson)
            self.assertIn({'name': 'emcon:license:status', 'value': 'unknown-no-checked-in-evidence'}, gson['properties'])
            takdev = comps['atak-gradle-takdev']
            self.assertNotIn('version', takdev)
            self.assertNotIn('purl', takdev)
            self.assertIn({'name': 'emcon:declared-version', 'value': '2.+'}, takdev['properties'])
            self.assertIn({'name': 'emcon:resolution', 'value': 'declared-dynamic-unresolved'}, takdev['properties'])
            self.assertIn('proguard-gradle', comps)
            self.assertEqual(comps['gradle-7.6.4-all.zip']['hashes'], [{'alg': 'SHA-256', 'content': 'c' * 64}])
            meta = {p['name']: p['value'] for p in sbom['metadata']['properties']}
            self.assertEqual(meta['emcon:unresolved:local-file-dependencies'], '1')
            self.assertIn('ATAK SDK', meta['emcon:not-inventoried'])
            self.assertFalse(any(c['name'] in {'hamcrest-core', 'atak-sdk'} for c in sbom['components']))
            self.assertIn('ATAK SDK', notices)
            self.assertIn('UNKNOWN', notices)
            blob = json.dumps(sbom) + notices
            for leak in ['SUPERSECRET', tmp, '/Users/', 'takrepoPassword', 'takdevPlugin']:
                self.assertNotIn(leak, blob)

    def test_output_is_deterministic_and_tracks_digest_algorithm_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture_repo(tmp)
            first = self.build(tmp)
            self.assertEqual(first, self.build(tmp))
            fixture_repo(tmp, ('sha256', 'b' * 64))
            second, _ = self.build(tmp)
            junit = [c for c in second['components'] if c['name'] == 'junit'][0]
            self.assertEqual(junit['hashes'], [{'alg': 'SHA-256', 'content': 'b' * 64}])
            self.assertNotEqual(first[0]['serialNumber'], second['serialNumber'])

    def test_input_drift_and_bad_evidence_fail_closed(self):
        cases = {
            'digest drift': lambda root, ev: write(root, 'verification/dependencies.json', json.dumps([{'url': JAR, 'sha1': 'f' * 40}])),
            'license drift': lambda root, ev: write(root, 'LICENSE', LICENSE_TEXT + 'changed'),
            'marker drift': lambda root, ev: write(root, 'sim/index.html', 'nothing here'),
            'stale evidence': lambda root, ev: write(root, 'verification/license-evidence.json', json.dumps({**ev, 'maven': {**ev['maven'], 'x:y:1': ev['maven']['junit:junit:4.13.2']}})),
            'unknown key': lambda root, ev: write(root, 'verification/license-evidence.json', json.dumps({**ev, 'extra': 1})),
            'absolute input': lambda root, ev: write(root, 'verification/license-evidence.json', json.dumps({**ev, 'inputs': {**ev['inputs'], 'gradleBuildFiles': ['/etc/hosts']}})),
            'secret input': lambda root, ev: write(root, 'verification/license-evidence.json', json.dumps({**ev, 'inputs': {**ev['inputs'], 'gradleBuildFiles': ['plugin/local.properties']}})),
            'http evidence': lambda root, ev: write(root, 'verification/license-evidence.json', json.dumps({**ev, 'maven': {'junit:junit:4.13.2': {**ev['maven']['junit:junit:4.13.2'], 'licenseEvidence': [{**ev['maven']['junit:junit:4.13.2']['licenseEvidence'][0], 'url': POM.replace('https', 'http')}]}}})),
            'gradle notation': lambda root, ev: write(root, 'plugin/build.gradle', "dependencies { implementation 'only:two' }"),
            'missing input': lambda root, ev: (Path(root) / 'plugin/app/build.gradle').unlink(),
        }
        for name, mutate in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                ev = fixture_repo(tmp)
                mutate(tmp, ev)
                with self.assertRaises(ValueError):
                    self.build(tmp)


class CliTests(unittest.TestCase):
    def test_cli_writes_then_checks_outputs_and_reports_errors_without_paths(self):
        import contextlib
        import io
        module = tool()
        with tempfile.TemporaryDirectory() as tmp:
            fixture_repo(tmp)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(module.main(['--root', tmp]), 0)
            summary = json.loads(out.getvalue())
            self.assertEqual(summary['license_unknown'] + summary['with_declared_license_evidence'], summary['components'])
            self.assertTrue((Path(tmp) / 'dist/source-sbom.cdx.json').is_file())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(['--root', tmp, '--check']), 0)
            write(tmp, 'docs/third-party-notices.md', 'hand edited\n')
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(['--root', tmp, '--check']), 1)
            self.assertIn('docs/third-party-notices.md', err.getvalue())
            write(tmp, 'LICENSE', 'changed')
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(module.main(['--root', tmp, '--check']), 2)
            self.assertNotIn(tmp, err.getvalue())


def mutate_evidence(root, ev, change):
    data = json.loads(json.dumps(ev))
    change(data)
    write(root, 'verification/license-evidence.json', json.dumps(data))


def parsed(text):
    return [(f['configuration'], f.get('coordinate'), f['status']) for f in tool().parse_gradle_text(text, 'b.gradle')]


class InputPathSecurityTests(unittest.TestCase):
    def assert_rejected(self, mutate):
        with tempfile.TemporaryDirectory() as tmp:
            ev = fixture_repo(tmp)
            mutate(tmp, ev)
            with self.assertRaises(ValueError):
                tool().build(Path(tmp), Path(tmp) / 'verification/license-evidence.json')

    def test_role_allowlist_rejects_wrong_kinds_and_credential_carriers(self):
        def gradle(rel):
            return lambda root, ev: mutate_evidence(root, ev, lambda d: d['inputs'].update(gradleBuildFiles=[rel]))

        def observed(rel):
            return lambda root, ev: mutate_evidence(root, ev, lambda d: d['observed'][0].update(source=rel))
        cases = {
            'gradle.properties as build file': (gradle('plugin/gradle.properties'), 'plugin/gradle.properties'),
            'case-variant local.properties': (gradle('plugin/Local.Properties'), 'plugin/Local.Properties'),
            'sdk build file': (gradle('plugin/sdk/build.gradle'), 'plugin/sdk/build.gradle'),
            'case-variant .GIT': (observed('.GIT/config.xml'), '.GIT/config.xml'),
            'observed secret marker oracle': (observed('plugin/local.properties'), None),
            'observed json credentials': (observed('app/google-services.json'), 'app/google-services.json'),
            'observed pem': (observed('keys/Release.PEM'), 'keys/Release.PEM'),
            'observed keystore.properties': (observed('keystore.properties'), 'keystore.properties'),
            'wrapper role wrong file': (lambda root, ev: mutate_evidence(root, ev, lambda d: d['inputs'].update(gradleWrapperProperties='plugin/build.gradle')), None),
            'manifest role wrong file': (lambda root, ev: mutate_evidence(root, ev, lambda d: d['inputs'].update(verificationManifest='LICENSE')), None),
            'license role wrong file': (lambda root, ev: mutate_evidence(root, ev, lambda d: d['project'].update(licenseFile='plugin/build.gradle')), None),
            'colon in path': (gradle('plugin/a:b.gradle'), 'plugin/a:b.gradle'),
        }
        for name, (mutate, create) in cases.items():
            with self.subTest(name):
                def both(root, ev, mutate=mutate, create=create):
                    if create:
                        write(root, create, 'takrepo.password=SUPERSECRET tile.openstreetmap.org\n')
                    mutate(root, ev)
                self.assert_rejected(both)

    def test_case_variant_of_allowed_file_is_rejected_even_on_case_insensitive_filesystems(self):
        self.assert_rejected(lambda root, ev: mutate_evidence(root, ev, lambda d: d['inputs'].update(gradleBuildFiles=['PLUGIN/build.gradle'])))

    def test_symlinked_inputs_and_symlinked_directories_are_rejected(self):
        def file_link(root, ev):
            target = Path(root) / 'plugin/app/build.gradle'
            target.unlink()
            target.symlink_to('../local.properties')

        def dir_link(root, ev):
            (Path(root) / 'plugin/linked').symlink_to('app', target_is_directory=True)
            mutate_evidence(root, ev, lambda d: d['inputs'].update(gradleBuildFiles=['plugin/build.gradle', 'plugin/linked/build.gradle']))
        for name, mutate in {'file symlink': file_link, 'directory symlink': dir_link}.items():
            with self.subTest(name):
                self.assert_rejected(mutate)


class CliErrorTests(unittest.TestCase):
    def run_main(self, tmp, *extra):
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = tool().main(['--root', tmp, *extra])
        return code, err.getvalue()

    def test_wrong_typed_evidence_fields_exit_2_without_traceback_or_paths(self):
        cases = {
            'relation list': lambda d: d['maven']['junit:junit:4.13.2']['licenseEvidence'][0].update(relation=['self']),
            'type list': lambda d: d['observed'][0].update(type=['library']),
            'endpoints int': lambda d: d['observed'][1].update(endpoints=5),
            'endpoint list item': lambda d: d['observed'][1].update(endpoints=[['https://x.org/']]),
            'build file list item': lambda d: d['inputs'].update(gradleBuildFiles=[['plugin/build.gradle']]),
            'service with purl': lambda d: d['observed'][2].update(purl='pkg:npm/x@1'),
            'service with license evidence': lambda d: d['observed'][2].update(licenseEvidence=d['observed'][0]['licenseEvidence']),
            'library with endpoints': lambda d: d['observed'][0].update(endpoints=['https://x.org/']),
            'observed version int': lambda d: d['observed'][0].update(version=194),
            'observed version spaces': lambda d: d['observed'][0].update(version='1.9 4'),
            'observed purl not purl': lambda d: d['observed'][0].update(purl='leaflet@1.9.4'),
            'observed purl list': lambda d: d['observed'][0].update(purl=['pkg:npm/leaflet@1.9.4']),
            'pomCoordinate list': lambda d: d['maven']['junit:junit:4.13.2']['licenseEvidence'][0].update(pomCoordinate=['junit']),
            'pomCoordinate path': lambda d: d['maven']['junit:junit:4.13.2']['licenseEvidence'][0].update(pomCoordinate='/Users/x/junit'),
            'pomCoordinate two parts': lambda d: d['maven']['junit:junit:4.13.2']['licenseEvidence'][0].update(pomCoordinate='junit:junit'),
            'retrieved int': lambda d: d['maven']['junit:junit:4.13.2']['licenseEvidence'][0].update(retrievedAtUtc=1),
            'observed id with colon': lambda d: d['observed'][0].update(id='junit:junit:4.13.2'),
            'markers dict': lambda d: d['observed'][0].update(markers={'a': 1}),
        }
        for name, change in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                ev = fixture_repo(tmp)
                mutate_evidence(tmp, ev, change)
                code, err = self.run_main(tmp)
                self.assertEqual(code, 2, err)
                self.assertNotIn('Traceback', err)
                self.assertNotIn(tmp, err)
                self.assertTrue(err.startswith('error: '), err)

    def test_unreadable_or_non_utf8_input_is_reported_relative_with_exit_2(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            fixture_repo(tmp)
            (Path(tmp) / 'plugin/build.gradle').write_bytes(b"dependencies { implementation 'a:b:1' }\xff\n")
            code, err = self.run_main(tmp)
            self.assertEqual(code, 2, err)
            self.assertNotIn(tmp, err)
        if os.geteuid() != 0:
            with tempfile.TemporaryDirectory() as tmp:
                fixture_repo(tmp)
                path = Path(tmp) / 'plugin/build.gradle'
                path.chmod(0)
                try:
                    code, err = self.run_main(tmp)
                finally:
                    path.chmod(0o644)
                self.assertEqual(code, 2, err)
                self.assertNotIn(tmp, err)

    def test_output_write_failure_and_unexpected_errors_have_distinct_path_free_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture_repo(tmp)
            write(tmp, 'dist', 'not a directory')
            code, err = self.run_main(tmp, '--output', 'dist/sbom.json')
            self.assertEqual(code, 3, err)
            self.assertIn('(NotADirectoryError)', err)
            self.assertNotIn(tmp, err)
            self.assertNotIn('Traceback', err)
            module = tool()

            def boom(*_):
                raise RuntimeError(f'{tmp}/secret/internal')
            setattr(module, 'build', boom)
            import contextlib
            import io
            errio = io.StringIO()
            with contextlib.redirect_stderr(errio):
                self.assertEqual(module.main(['--root', tmp]), 4)
            self.assertNotIn(tmp, errio.getvalue())
            self.assertNotIn('secret', errio.getvalue())

    def test_check_treats_missing_or_non_utf8_outputs_as_stale_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture_repo(tmp)
            self.assertEqual(self.run_main(tmp)[0], 0)
            (Path(tmp) / 'docs/third-party-notices.md').write_bytes(b'\xff\xfe')
            code, err = self.run_main(tmp, '--check')
            self.assertEqual(code, 1, err)
            self.assertEqual(self.run_main(tmp)[0], 0)
            (Path(tmp) / 'dist/source-sbom.cdx.json').unlink()
            code, err = self.run_main(tmp, '--check')
            self.assertEqual(code, 1, err)
            self.assertIn('dist/source-sbom.cdx.json', err)


class UrlTests(unittest.TestCase):
    def test_urls_with_whitespace_controls_or_non_round_trip_are_rejected(self):
        module = tool()
        bad = ['https://exa\tmple.org/', 'https://example.org/a\tb', ' https://example.org/', 'https://example.org/\n',
               'https://example.org/a b', 'HTTPS://example.org/', 'https://example.org/a"b', 'https://example.org/%zz',
               'https://example.org/<x>', 'https://example.org/a\\b', 'https://example.org/\x00', 'https://exam\rple.org/',
               'https://{s}.example.org/', 'https://example.org/é', 'https://exa..mple.org/', 'https://-x.org/']
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.https_url(value, 'test')
        self.assertEqual(module.https_url('https://example.org/path/', 'test'), 'https://example.org/path/')
        self.assertEqual(module.https_url('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', 'test', template=True),
                         'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png')
        for value in ['https://{s}.ti\tle.org/{z}', 'https://{s }.tile.org/', 'https://{s}.tile.org/{z']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.https_url(value, 'test', template=True)

    def test_manifest_and_declared_license_urls_with_tabs_fail_closed(self):
        module = tool()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'dependencies.json'
            path.write_text(json.dumps([{'url': JAR.replace('junit/4.13.2', 'jun\tit/4.13.2'), 'sha1': 'a' * 40}]))
            with self.assertRaises(ValueError):
                module.load_verification(path)
        entry = {'relation': 'self', 'url': POM, 'retrievedAtUtc': '2026-10-07T05:54:00Z',
                 'declaredLicenses': [{'name': 'EPL', 'url': 'http://www.eclipse.org/le\tgal/epl-v10.html'}]}
        with self.assertRaises(ValueError):
            module.check_license_evidence([entry], 'x')


class GradleCommentAndStringTests(unittest.TestCase):
    def test_block_comment_delimiter_inside_string_does_not_swallow_later_declarations(self):
        text = ("dependencies {\n  implementation fileTree(dir: 'libs', include: ['**/*.jar'])\n"
                "  implementation 'a.b:c:1.0'\n  /* real block comment */\n  testImplementation 'd.e:f:2.0'\n}\n")
        self.assertEqual(parsed(text), [
            ('implementation', None, 'local-file-unresolved'),
            ('implementation', 'a.b:c:1.0', 'declared-static'),
            ('testImplementation', 'd.e:f:2.0', 'declared-static')])

    def test_line_comment_directly_after_brace_or_semicolon_is_stripped(self):
        text = "dependencies {// implementation 'x.y:z:1'\n implementation 'a.b:c:1.0';// api 'q.r:s:1'\n}\n"
        self.assertEqual(parsed(text), [('implementation', 'a.b:c:1.0', 'declared-static')])

    def test_comment_delimiters_inside_strings_and_triple_quotes_are_preserved(self):
        text = ("def u = 'https://example.org/*'\ndef doc = '''multi /* not\n a comment */ line'''\n"
                "dependencies {\n implementation 'a.b:c:1.0' // trailing\n}\n")
        self.assertEqual(parsed(text), [('implementation', 'a.b:c:1.0', 'declared-static')])

    def test_unsupported_lexical_forms_fail_closed(self):
        for text in ["dependencies { implementation 'a.b:c:1.0' }\n/* unterminated", "def x = 'unterminated\ndependencies {}",
                     "def p = ~/a*/\ndependencies { implementation 'a.b:c:1.0' }", "def p = $/x/$",
                     "dependencies { implementation \"a.b:c:${ v + '}' }\" }"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                tool().parse_gradle_text(text, 'b.gradle')


class GradleUnparsedDeclarationTests(unittest.TestCase):
    def test_unrecognized_declaration_forms_are_surfaced_not_dropped(self):
        forms = {
            "implementation group: 'g.h', name: 'n', version: '1.0'": 'map-notation',
            "implementation platform('g.h:bom:1.0')": 'platform',
            "implementation enforcedPlatform('g.h:bom:1.0')": 'platform',
            "implementation project(':lib')": 'project',
            "implementation libs.gson": 'property-or-catalog',
            "milImplementation 'g.h:n:1.0'": 'unknown-configuration',
            "if (x) implementation 'g.h:n:1.0'": 'other',
            "implementation 'g.h:n:1.0', 'g.h:m:1.0'": 'other',
            "implementation('g.h:n:1.0'\n)": 'other',
        }
        for statement, form in forms.items():
            with self.subTest(statement):
                found = tool().parse_gradle_text('dependencies {\n  ' + statement + '\n}\n', 'b.gradle')
                unparsed = [f for f in found if f['status'] == 'unparsed']
                self.assertTrue(unparsed, found)
                self.assertEqual(unparsed[0]['form'], form)
                self.assertEqual(unparsed[0]['source'], 'b.gradle:2')
                self.assertFalse(any(f.get('status') == 'declared-static' for f in found), found)

    def test_substitution_forms_and_outside_block_declarations(self):
        found = tool().parse_gradle_text(
            "configurations.all { resolutionStrategy { dependencySubstitution {\n"
            "  substitute module('a.b:c') using module('d.e:f:1.0')\n"
            "  substitute module('a.b:x') using project(':y')\n"
            "  force 'k.l:m:1.0'\n} } }\nimplementation 'o.p:q:1.0'\n", 'b.gradle')
        self.assertIn(('dependencySubstitution', 'd.e:f:1.0', 'declared-static'),
                      [(f['configuration'], f.get('coordinate'), f['status']) for f in found])
        self.assertEqual(sorted((f['source'], f['form']) for f in found if f['status'] == 'unparsed'),
                         [('b.gradle:3', 'substitution'), ('b.gradle:4', 'resolution-strategy'), ('b.gradle:6', 'outside-dependencies-block')])

    def test_additional_standard_configurations_are_parsed(self):
        text = "dependencies {\n testRuntimeOnly 'a.b:c:1.0'\n coreLibraryDesugaring 'd.e:f:2.0'\n ksp('g.h:i:3.0')\n}\n"
        self.assertEqual(parsed(text), [('testRuntimeOnly', 'a.b:c:1.0', 'declared-static'),
                                        ('coreLibraryDesugaring', 'd.e:f:2.0', 'declared-static'),
                                        ('ksp', 'g.h:i:3.0', 'declared-static')])

    def test_unparsed_declarations_are_reported_in_sbom_and_notices(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture_repo(tmp)
            write(tmp, 'plugin/build.gradle', "buildscript { dependencies { classpath 'com.android.tools.build:gradle:7.4.2' } }\n"
                  "dependencies {\n implementation platform('g.h:bom:1.0')\n}\n")
            sbom, notices = tool().build(Path(tmp), Path(tmp) / 'verification/license-evidence.json')
            meta = {}
            for p in sbom['metadata']['properties']:
                meta.setdefault(p['name'], []).append(p['value'])
            self.assertEqual(meta['emcon:unparsed:gradle-declarations'], ['1'])
            self.assertEqual(meta['emcon:unparsed:gradle-declaration'], ['plugin/build.gradle:3 implementation platform'])
            self.assertIn('plugin/build.gradle:3 implementation platform', notices)
            self.assertNotIn('g.h:bom', json.dumps(sbom))


class GradleVariableAndVersionTests(unittest.TestCase):
    def test_variables_resolve_only_from_exact_unique_single_quoted_literals(self):
        text = ("def ok = '3.1'\ndef concat = '1.0' + suffix\ndef dq = \"1.0\"\ndef dup = '1.0'\ndef dup = '2.0'\n"
                "def re = '1.0'\nre = '2.0'\n"
                "dependencies {\n implementation \"a.b:c:${ok}\"\n implementation \"a.b:d:$ok\"\n"
                " implementation \"a.b:e:${concat}\"\n implementation \"a.b:f:${dq}\"\n implementation \"a.b:g:${dup}\"\n"
                " implementation \"a.b:h:${re}\"\n implementation \"a.b:i:${ok.x}\"\n}\n")
        self.assertEqual(parsed(text), [
            ('implementation', 'a.b:c:3.1', 'declared-static'), ('implementation', 'a.b:d:3.1', 'declared-static'),
            ('implementation', 'a.b:e:${concat}', 'declared-variable-unresolved'),
            ('implementation', 'a.b:f:${dq}', 'declared-variable-unresolved'),
            ('implementation', 'a.b:g:${dup}', 'declared-variable-unresolved'),
            ('implementation', 'a.b:h:${re}', 'declared-variable-unresolved'),
            ('implementation', 'a.b:i:${ok.x}', 'declared-variable-unresolved')])

    def test_single_quoted_dollar_is_not_interpolated(self):
        with self.assertRaises(ValueError):
            tool().parse_gradle_text("def v = '1.0'\ndependencies { implementation 'a.b:c:${v}' }\n", 'b.gradle')

    def test_group_and_name_are_validated_for_every_status(self):
        for coordinate in ['"a!b:c:${v}"', "'a.b:c<d>:2.+'", "'a b:c:1.0-SNAPSHOT'", "'a.b:c:1.0 beta+'", '"a.b:${n}:1.0"']:
            with self.subTest(coordinate), self.assertRaises(ValueError):
                tool().parse_gradle_text('dependencies { implementation ' + coordinate + ' }', 'b.gradle')

    def test_snapshot_versions_are_dynamic_without_purl(self):
        found = tool().parse_gradle_text("dependencies { implementation 'a.b:c:1.0-SNAPSHOT' }", 'b.gradle')
        self.assertEqual(found[0]['status'], 'declared-dynamic-unresolved')
        self.assertNotIn('purl', found[0])


class NoticesEvidenceMapTests(unittest.TestCase):
    def test_evidence_is_attached_by_bom_ref_not_heuristic_id_matching(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = fixture_repo(tmp)

            def change(d):
                d['observed'][0]['id'] = 'leaflet-cdn'
                del d['observed'][0]['purl']
            mutate_evidence(tmp, ev, change)
            sbom, notices = tool().build(Path(tmp), Path(tmp) / 'verification/license-evidence.json')
            row = [line for line in notices.splitlines() if line.startswith('| `leaflet`')][0]
            self.assertIn('registry-metadata: <https://registry.npmjs.org/leaflet/1.9.4>', row)
            junit = [line for line in notices.splitlines() if line.startswith('| `junit:junit`')][0]
            self.assertIn(POM, junit)
            self.assertNotIn('registry.npmjs.org', junit)


class RepositoryTests(unittest.TestCase):
    ROOT = SCRIPT.parents[1]

    def test_checked_in_evidence_generates_committed_notices(self):
        sbom, notices = tool().build(self.ROOT, self.ROOT / 'verification/license-evidence.json')
        self.assertEqual((self.ROOT / 'docs/third-party-notices.md').read_text(encoding='utf-8'), notices)
        names = {c['name'] for c in sbom['components']}
        self.assertTrue({'junit', 'hamcrest-core', 'gson', 'gradle', 'atak-gradle-takdev', 'proguard-gradle'} <= names)
        licensed = {c['name'] for c in sbom['components'] if 'licenses' in c}
        self.assertEqual(licensed, {'junit', 'hamcrest-core', 'gson', 'leaflet'})

    def test_checked_in_repository_sbom_component_set_and_explicit_unparsed_count(self):
        sbom, notices = tool().build(self.ROOT, self.ROOT / 'verification/license-evidence.json')
        self.assertEqual(sorted(c['bom-ref'] for c in sbom['components']), sorted([
            'pkg:maven/junit/junit@4.13.2', 'pkg:maven/org.hamcrest/hamcrest-core@1.3', 'pkg:maven/com.google.code.gson/gson@2.10.1',
            'pkg:maven/com.android.tools.build/gradle@7.4.2', 'gradle-declared:com.atakmap.gradle:atak-gradle-takdev:2.+',
            'pkg:maven/com.guardsquare/proguard-gradle@7.1.1', 'gradle-wrapper-distribution:gradle-7.6.4-all.zip',
            'pkg:npm/leaflet@1.9.4']))
        self.assertEqual(sorted(s['bom-ref'] for s in sbom['services']),
                         ['service:cloudrf-api', 'service:esri-world-imagery', 'service:openstreetmap-tiles'])
        meta = {p['name']: p['value'] for p in sbom['metadata']['properties']}
        self.assertEqual(meta['emcon:unparsed:gradle-declarations'], '0')
        self.assertEqual(meta['emcon:unresolved:local-file-dependencies'], '2')
        self.assertIn('Gradle dependency statements detected but not parsed: 0.', notices)


if __name__ == '__main__':
    unittest.main()
