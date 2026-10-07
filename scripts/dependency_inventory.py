#!/usr/bin/env python3
"""Offline, stdlib-only source-observed dependency inventory and notices generator.

This tool inventories only what checked-in files directly state: the Maven
artifacts pinned in the verification manifest, Maven coordinates literally
declared in configured Gradle build files, the Gradle wrapper distribution and
externally loaded items listed in checked-in license evidence. It never runs
Gradle, never resolves transitive dependencies, never fetches from the network
and never reads local.properties or other secret-bearing files. License data
comes only from checked-in evidence of what upstream metadata *declares*; it is
not a legal determination.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import NoReturn
from urllib.parse import quote, urlsplit, urlunsplit

TOKEN = r'[A-Za-z0-9_][A-Za-z0-9_.-]*'
HEX = {'sha1': ('SHA-1', 40), 'sha256': ('SHA-256', 64)}
KIND = 'source-observed-inventory; not a release artifact SBOM'
SCOPE = ('Directly observed verification-manifest artifacts and directly declared Gradle coordinates only; '
         'no Gradle resolution, no transitive dependencies, no SDK contents, no built APK contents.')
TOOL_NAME = 'emcon-dependency-inventory'
TOOL_VERSION = '1.0.0'
# Characters RFC 3986/3987 forbid in a URI/IRI reference (URI templates such as {z} fall here).
URI_UNSAFE = re.compile(r'[\s{}<>"\\^`|]')
# Strict RFC 3986 character set (no whitespace, controls, quotes, backslashes, brackets or non-ASCII).
URL_CHARS = re.compile(r"[A-Za-z0-9\-._~:/?#@!$&'()*+,;=%]+")
BAD_PERCENT = re.compile(r'%(?![0-9A-Fa-f]{2})')
TEMPLATE_VAR = re.compile(r'\{[a-z]+\}')
HOST_PORT = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*(?::[0-9]{1,5})?')

# Input paths: plain repository-relative POSIX paths, one exact on-disk spelling, no symlinks, per-role allowlist.
SAFE_REL = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)*')
FORBIDDEN_DIRS = frozenset(('sdk', '.git', '.gradle', '.ssh', '.aws', '.gnupg'))
FORBIDDEN_NAMES = frozenset(('local.properties', 'gradle.properties', 'keystore.properties', 'signing.properties',
                             '.netrc', '_netrc', '.npmrc', '.pypirc', 'google-services.json', 'googleservice-info.plist',
                             'credentials.json', 'secrets.json'))
FORBIDDEN_PREFIXES = ('.env', 'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519')
FORBIDDEN_SUFFIXES = ('.keystore', '.jks', '.bks', '.p12', '.pfx', '.key', '.pem', '.p8', '.ppk', '.gpg', '.asc')
OBSERVED_SUFFIXES = ('.html', '.htm', '.xml', '.java', '.kt', '.js', '.py')
ROLES = {
    'license': lambda name: name == 'LICENSE',
    'manifest': lambda name: name.endswith('.json'),
    'evidence': lambda name: name.endswith('.json'),
    'gradle': lambda name: name.endswith('.gradle'),  # Groovy DSL only; Kotlin DSL is not parsed
    'wrapper': lambda name: name == 'gradle-wrapper.properties',
    'observed': lambda name: name.endswith(OBSERVED_SUFFIXES),
}
ID = re.compile(r'[a-z0-9][a-z0-9.-]{0,63}')
PURL = re.compile(r'pkg:[a-z][a-z0-9.+-]*/[A-Za-z0-9._~%@/+:-]+')
OBSERVED_VERSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}')
COORDINATE = re.compile(f'{TOKEN}:{TOKEN}:{TOKEN}')


class InventoryError(ValueError):
    """Expected, path-free input/validation failure (exit code 2)."""


def fail(message) -> NoReturn:
    raise InventoryError(message)


def strict_json_text(text, label):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                fail('duplicate JSON key')
            result[key] = value
        return result

    def constant(_):
        fail('nonfinite JSON number')
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except json.JSONDecodeError as exc:
        raise InventoryError(f'malformed JSON input: {label}') from exc


def strict_json(path):
    try:
        text = Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        raise InventoryError(f'unreadable JSON input: {Path(path).name}') from exc
    return strict_json_text(text, Path(path).name)


def maven_purl(group, name, version):
    return f'pkg:maven/{quote(group, safe=".")}/{quote(name, safe=".")}@{quote(version, safe=".")}'


def check_digest(key, value):
    if key not in HEX or not isinstance(value, str) or not re.fullmatch('[0-9a-f]{%d}' % HEX[key][1], value):
        fail(f'malformed {key} digest')
    return {'alg': HEX[key][0], 'content': value}


def checked_url(value, what, schemes=('https',), template=False):
    """Validate the exact string that will be emitted; reject anything urlsplit would silently normalise."""
    if not isinstance(value, str) or not value or len(value) > 2000:
        fail(f'{what} must be a nonempty string URL')
    probe = TEMPLATE_VAR.sub('x', value) if template else value
    if not URL_CHARS.fullmatch(probe) or BAD_PERCENT.search(probe):
        fail(f'{what} contains characters outside the strict URL character set')
    parsed = urlsplit(probe)
    if urlunsplit(parsed) != probe:
        fail(f'{what} is not in canonical form')
    if (parsed.scheme not in schemes or not HOST_PORT.fullmatch(parsed.netloc) or '?' in probe or '#' in probe):
        fail(f'{what} must be a credential-free, query-free {"/".join(s.upper() for s in schemes)} URL')
    return value


def https_url(value, what, template=False):
    return checked_url(value, what, ('https',), template)


def parse_verification(rows):
    if not isinstance(rows, list) or not rows:
        fail('manifest must be a nonempty array')
    found, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'url', 'sha1', 'sha256'} or 'url' not in row or not {'sha1', 'sha256'} & set(row):
            fail('invalid manifest fields')
        url = https_url(row['url'], 'manifest url')
        parsed = urlsplit(url)
        if parsed.netloc != 'repo.maven.apache.org' or not parsed.path.startswith('/maven2/'):
            fail('manifest requires canonical Maven Central HTTPS URL')
        parts = parsed.path[len('/maven2/'):].split('/')
        if len(parts) < 4 or any(not re.fullmatch(TOKEN, p) for p in parts[:-1]):
            fail('invalid Maven path')
        group, name, version = '.'.join(parts[:-3]), parts[-3], parts[-2]
        if parts[-1] != f'{name}-{version}.jar':
            fail('manifest requires unclassified Maven JAR')
        coordinate = f'{group}:{name}:{version}'
        if coordinate in seen:
            fail('duplicate manifest coordinate')
        seen.add(coordinate)
        hashes = [check_digest(key, row[key]) for key in ('sha1', 'sha256') if key in row]
        found.append({'coordinate': coordinate, 'purl': maven_purl(group, name, version), 'url': url, 'hashes': hashes})
    return found


def load_verification(path):
    return parse_verification(strict_json(path))


# ---------------------------------------------------------------------------------------------------------------
# Gradle (Groovy DSL) scanning. This is NOT a Groovy evaluator: a small lexer removes comments while respecting
# string literals, then only exact, recognised statement shapes inside `dependencies { }` blocks are parsed.
# Everything else that looks like a dependency statement is surfaced as `unparsed`, never silently dropped.
# ---------------------------------------------------------------------------------------------------------------
CONFIGS = frozenset((
    'classpath', 'implementation', 'api', 'compileOnly', 'runtimeOnly',
    'testImplementation', 'testCompileOnly', 'testRuntimeOnly',
    'androidTestImplementation', 'androidTestCompileOnly', 'androidTestRuntimeOnly', 'androidTestUtil',
    'annotationProcessor', 'testAnnotationProcessor', 'androidTestAnnotationProcessor',
    'kapt', 'kaptTest', 'kaptAndroidTest', 'ksp', 'kspTest', 'kspAndroidTest',
    'debugImplementation', 'releaseImplementation', 'debugApi', 'releaseApi',
    'debugCompileOnly', 'releaseCompileOnly', 'debugRuntimeOnly', 'releaseRuntimeOnly',
    'coreLibraryDesugaring', 'lintChecks', 'lintPublish',
    'compile', 'testCompile', 'androidTestCompile', 'provided', 'runtime'))
MASK = '\x01'  # replaces string-literal contents in the scanned code view (not a word, space or syntax char)
CONTROL = re.compile(r'(?:else\s+)?(?:if|for|while|catch)\s*\(')
DYNAMIC = re.compile(r'[+\[\](),]|^latest\.|(?i:-snapshot)$')
DYNAMIC_CHARS = re.compile(r'[A-Za-z0-9_.+\-\[\](),]+')
UNRESOLVED_CHARS = re.compile(r'[A-Za-z0-9_.+\-\[\](),${}]+')
VARIABLE_VALUE = re.compile(r'[A-Za-z0-9_.+\-\[\](),]+')
GSTRING_REF = re.compile(r'\$\{([^}]*)\}|\$([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)')
ASSIGNMENT = re.compile(r'(?<![\w.$])([A-Za-z_]\w*)\s*(?:[-+*/%&|^]|<<|>>|\?)?=(?![=~])')


def scan_groovy(text):
    """Return (code, strings): comments blanked, string contents masked, offsets preserved; fail on ambiguity."""
    out = list(text)
    strings = {}
    i, n, last = 0, len(text), ''

    def blank(a, b):
        for k in range(a, b):
            if out[k] != '\n':
                out[k] = ' '
    while i < n:
        c, two = text[i], text[i:i + 2]
        if two == '//':
            j = text.find('\n', i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if two == '/*':
            j = text.find('*/', i + 2)
            if j < 0:
                fail('unterminated block comment in Gradle file')
            blank(i, j + 2)
            i = j + 2
            continue
        if two == '$/':
            fail('dollar-slashy strings are not supported in Gradle files')
        if c == '/':
            if not (last.isalnum() or last in '_)]'):
                fail('slashy strings/regex literals are not supported in Gradle files')
            last = c
            i += 1
            continue
        if c in '\'"':
            quote_ = c * 3 if text.startswith(c * 3, i) else c
            j = i + len(quote_)
            while True:
                if j >= n:
                    fail('unterminated string literal in Gradle file')
                ch = text[j]
                if ch == '\\':
                    j += 2
                    continue
                if len(quote_) == 1 and ch == '\n':
                    fail('unterminated string literal in Gradle file')
                if text.startswith(quote_, j):
                    break
                if c == '"' and text.startswith('${', j):
                    k = text.find('}', j)
                    if k < 0 or not re.fullmatch(r'[A-Za-z_][\w.]*', text[j + 2:k]):
                        fail('unsupported GString interpolation in Gradle file')
                    j = k + 1
                    continue
                j += 1
            content_start = i + len(quote_)
            strings[i] = (quote_, text[content_start:j])
            for k in range(content_start, j):
                if out[k] != '\n':
                    out[k] = MASK
            i = j + len(quote_)
            last = c
            continue
        if not c.isspace():
            last = c
        i += 1
    return ''.join(out), strings


def match_close(code, open_index, limit, pair='()'):
    depth = 0
    for k in range(open_index, limit):
        if code[k] == pair[0]:
            depth += 1
        elif code[k] == pair[1]:
            depth -= 1
            if depth == 0:
                return k + 1
    return None


def gradle_variables(code, strings):
    counts = {}
    for m in ASSIGNMENT.finditer(code):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    variables = {}
    for m in re.finditer(r'(?<![\w.$])def\s+([A-Za-z_]\w*)\s*=\s*', code):
        name, p = m.group(1), m.end()
        if counts.get(name) != 1 or p not in strings or strings[p][0] != "'":
            continue
        content = strings[p][1]
        if not re.match(r'[ \t]*(?:[;\n}]|\Z)', code[p + len(content) + 2:]) or not VARIABLE_VALUE.fullmatch(content):
            continue
        variables[name] = content
    return variables


def coordinate_item(config, quote_, content, where, variables):
    if '\\' in content:
        fail(f'unsupported escape in Gradle coordinate at {where}')
    unresolved = False
    coordinate = content
    if quote_ == '"':
        def expand(match):
            nonlocal unresolved
            name = match.group(1) if match.group(1) is not None else match.group(2)
            if name in variables:
                return variables[name]
            unresolved = True
            return match.group(0)
        coordinate = GSTRING_REF.sub(expand, content)
    parts = coordinate.split(':')
    if len(parts) != 3 or not all(parts):
        fail(f'unsupported Gradle coordinate notation at {where}')
    group, name, version = parts
    if not re.fullmatch(TOKEN, group) or not re.fullmatch(TOKEN, name):
        fail(f'unsupported Gradle coordinate group/name characters at {where}')
    item = {'configuration': config, 'coordinate': coordinate, 'source': where}
    if unresolved:
        if not UNRESOLVED_CHARS.fullmatch(version):
            fail(f'unsupported Gradle version characters at {where}')
        item['status'] = 'declared-variable-unresolved'
    elif DYNAMIC.search(version):
        if not DYNAMIC_CHARS.fullmatch(version):
            fail(f'unsupported Gradle version characters at {where}')
        item['status'] = 'declared-dynamic-unresolved'
    elif re.fullmatch(TOKEN, version):
        item['status'] = 'declared-static'
        item['purl'] = maven_purl(group, name, version)
    else:
        fail(f'unsupported Gradle version characters at {where}')
    return item


def unparsed_item(config, form, where):
    label = config if isinstance(config, str) and re.fullmatch(r'[A-Za-z_]\w{0,63}', config) else '?'
    return {'configuration': label, 'status': 'unparsed', 'form': form, 'source': where}


def parse_statement(code, strings, s, e, variables, where):
    stmt = code[s:e]
    if stmt in ('else', 'try', 'finally'):
        return None
    control = CONTROL.match(stmt)
    if control:
        close = match_close(code, s + control.end() - 1, e)
        return None if close is not None and not code[close:e].strip() else unparsed_item(None, 'other', where)
    head = re.match(r'([A-Za-z_]\w*)\s*(\(\s*)?', stmt)
    if not head:
        return unparsed_item(None, 'other', where)
    config, tail = head.group(1), r'\s*\)\s*' if head.group(2) else r'\s*'
    p = s + head.end()
    if p in strings:
        quote_, content = strings[p]
        after = p + 2 * len(quote_) + len(content)
        if quote_ not in ("'", '"') or after > e or not re.fullmatch(tail, code[after:e]):
            return unparsed_item(config, 'other', where)
        if config not in CONFIGS:
            return unparsed_item(config, 'unknown-configuration', where)
        return coordinate_item(config, quote_, content, where, variables)
    rest = code[p:e]
    local = re.match(r'(files|fileTree)\s*\(', rest)
    if local:
        close = match_close(code, p + local.end() - 1, e)
        if close is None or not re.fullmatch(tail, code[close:e]):
            return unparsed_item(config, 'other', where)
        if config not in CONFIGS:
            return unparsed_item(config, 'unknown-configuration', where)
        return {'configuration': config, 'status': 'local-file-unresolved', 'kind': local.group(1), 'source': where}
    if re.match(r'(?:platform|enforcedPlatform)\s*\(', rest):
        form = 'platform'
    elif re.match(r'project\s*\(', rest):
        form = 'project'
    elif re.match(r'[A-Za-z_]\w*\s*:', rest):
        form = 'map-notation'
    elif re.match(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+', rest):
        form = 'property-or-catalog'
    else:
        form = 'other'
    return unparsed_item(config, form, where)


def parse_gradle_text(text, source):
    code, strings = scan_groovy(text)

    def where(pos):
        return f'{source}:{text.count(chr(10), 0, pos) + 1}'
    variables = gradle_variables(code, strings)
    found, blocks = [], []
    for m in re.finditer(r'(?<![\w$])dependencies\s*\{', code):
        if blocks and m.start() < blocks[-1][1]:
            continue  # nested inside an earlier block; its statements are scanned with that block
        close = match_close(code, m.end() - 1, len(code), '{}')
        if close is None:
            fail(f'unbalanced dependencies block at {where(m.start())}')
        blocks.append((m.end(), close - 1))
    for start, end in blocks:
        for seg in re.finditer(r'[^\n;{}]+', code[start:end]):
            s, e = start + seg.start(), start + seg.end()
            while s < e and code[s].isspace():
                s += 1
            while e > s and code[e - 1].isspace():
                e -= 1
            if s < e:
                item = parse_statement(code, strings, s, e, variables, where(s))
                if item:
                    found.append((s, item))

    def outside(pos):
        return not any(a <= pos < b for a, b in blocks)
    for m in re.finditer(r'(?<![\w.$])substitute\b', code):
        stop = re.compile(r'[\n;{}]').search(code, m.end())
        e = stop.start() if stop else len(code)
        target = re.compile(r'(?<![\w.$])(?:with|using)\s+module\s*\(\s*').search(code, m.end(), e)
        item = None
        if target and target.end() in strings:
            quote_, content = strings[target.end()]
            after = target.end() + 2 * len(quote_) + len(content)
            if quote_ in ("'", '"') and after <= e and re.fullmatch(r'\s*\)\s*', code[after:e]):
                item = coordinate_item('dependencySubstitution', quote_, content, where(m.start()), variables)
        found.append((m.start(), item or unparsed_item('substitute', 'substitution', where(m.start()))))
    for m in re.finditer(r'(?<![\w.$])(force|useTarget|useVersion)\s*[(\'"]', code):
        if outside(m.start()):
            found.append((m.start(), unparsed_item(m.group(1), 'resolution-strategy', where(m.start()))))
    for m in re.finditer(r'(?<![\w.$])([A-Za-z_]\w*)\s*\(?\s*[\'"]', code):
        if m.group(1) in CONFIGS and outside(m.start()):
            found.append((m.start(), unparsed_item(m.group(1), 'outside-dependencies-block', where(m.start()))))
    for m in re.finditer(r'(?<![\w$])dependencies\b(?!\s*\{)', code):
        found.append((m.start(), unparsed_item('dependencies', 'dependencies-reference', where(m.start()))))
    return [item for _, item in sorted(found, key=lambda pair: pair[0])]


def safe_input(root, rel, role):
    """Resolve an input under a per-role allowlist; exact on-disk spelling, no symlinks, no credential carriers."""
    if not isinstance(rel, str) or len(rel) > 300 or not SAFE_REL.fullmatch(rel):
        fail('input paths must be plain repository-relative POSIX paths')
    folded = rel.casefold().split('/')
    name = folded[-1]
    if (any(part in FORBIDDEN_DIRS for part in folded[:-1]) or name in FORBIDDEN_NAMES
            or name.startswith(FORBIDDEN_PREFIXES) or name.endswith(FORBIDDEN_SUFFIXES)):
        fail(f'input path not allowed (secret-bearing or excluded location): {rel}')
    if not ROLES[role](rel.rsplit('/', 1)[-1]):
        fail(f'input path not allowed for {role} input: {rel}')
    current = Path(root).resolve()
    for part in rel.split('/'):
        try:
            names = os.listdir(current)
        except OSError:
            fail(f'missing input file: {rel}')
        if part not in names:
            fail(f'missing input file (exact on-disk spelling required): {rel}')
        current = current / part
        if current.is_symlink():
            fail(f'symlinked input not allowed: {rel}')
    if not current.is_file():
        fail(f'missing input file: {rel}')
    return current


def read_input(path, rel):
    """Read relative to the validated, trusted root, never following input-directory symlinks."""
    parts = rel.split('/')
    opened = []
    try:
        directory = os.open(Path(path).parents[len(parts) - 1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        opened.append(directory)
        for part in parts[:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            opened.append(directory)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        opened.append(fd)
        with os.fdopen(fd, 'rb', closefd=False) as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                fail(f'input must be a singly linked regular file: {rel}')
            data = handle.read(4 * 1024 * 1024 + 1)
            if len(data) > 4 * 1024 * 1024:
                fail(f'input exceeds 4 MiB limit: {rel}')
            return data
    except OSError:
        fail(f'unreadable input file: {rel}')
    finally:
        for fd in reversed(opened):
            os.close(fd)


def decode_input(data, rel):
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        fail(f'input file is not valid UTF-8: {rel}')


def require_keys(obj, required, optional=(), what='object'):
    if not isinstance(obj, dict):
        fail(f'{what} must be an object')
    missing, extra = set(required) - set(obj), set(obj) - set(required) - set(optional)
    if missing or extra:
        fail(f'{what} has missing {sorted(missing)} or unknown {sorted(extra)} keys')
    return obj


def text_field(obj, key, what):
    value = obj[key]
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        fail(f'{what}.{key} must be a nonempty string')
    if re.search(r'(^|[\s"\'(])(/Users/|/home/|[A-Za-z]:\\)', value):
        fail(f'{what}.{key} must not contain local absolute paths')
    return value


def check_license_evidence(entries, what):
    if not isinstance(entries, list) or not entries:
        fail(f'{what}.licenseEvidence must be a nonempty array')
    for i, entry in enumerate(entries):
        where = f'{what}.licenseEvidence[{i}]'
        require_keys(entry, ('relation', 'url', 'retrievedAtUtc', 'declaredLicenses'), ('pomCoordinate', 'sha256'), where)
        https_url(entry['url'], f'{where}.url')
        if not isinstance(entry['relation'], str) or entry['relation'] not in {'self', 'parent', 'registry-metadata'}:
            fail(f'{where}.relation is unsupported')
        stamp = entry['retrievedAtUtc']
        try:
            ok = isinstance(stamp, str) and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', stamp) and datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%SZ')
        except ValueError:
            ok = False
        if not ok:
            fail(f'{where}.retrievedAtUtc must be UTC ISO-8601')
        if 'pomCoordinate' in entry and (not isinstance(entry['pomCoordinate'], str) or not COORDINATE.fullmatch(entry['pomCoordinate'])):
            fail(f'{where}.pomCoordinate must be group:artifact:version')
        if 'sha256' in entry:
            check_digest('sha256', entry['sha256'])
        if not isinstance(entry['declaredLicenses'], list):
            fail(f'{where}.declaredLicenses must be an array')
        for lic in entry['declaredLicenses']:
            require_keys(lic, ('name',), ('url',), f'{where}.declaredLicenses[]')
            text_field(lic, 'name', where)
            if 'url' in lic:
                checked_url(lic['url'], f'{where} declared license url', ('http', 'https'))
    if not any(e['declaredLicenses'] for e in entries):
        fail(f'{what} has evidence entries but no declared license; omit it to mark unknown')


def load_evidence(text, rel):
    ev = require_keys(strict_json_text(text, rel), ('schema', 'disclaimer', 'inputs', 'project', 'maven', 'observed', 'unknown'), (), 'evidence')
    if ev['schema'] != 'emcon-sentinel.license-evidence.v1':
        fail('unsupported evidence schema')
    text_field(ev, 'disclaimer', 'evidence')
    inputs = require_keys(ev['inputs'], ('verificationManifest', 'gradleBuildFiles', 'gradleWrapperProperties'), (), 'inputs')
    rels = inputs['gradleBuildFiles']
    if not isinstance(rels, list) or not rels or not all(isinstance(r, str) for r in rels):
        fail('inputs.gradleBuildFiles must be a nonempty array of strings')
    if len(set(rels)) != len(rels):
        fail('inputs.gradleBuildFiles must be unique')
    for key in ('verificationManifest', 'gradleWrapperProperties'):
        if not isinstance(inputs[key], str):
            fail(f'inputs.{key} must be a string')
    project = require_keys(ev['project'], ('name', 'licenseId', 'licenseFile', 'licenseFileSha256', 'basis'), (), 'project')
    for key in ('name', 'licenseId', 'licenseFile', 'basis'):
        text_field(project, key, 'project')
    check_digest('sha256', project['licenseFileSha256'])
    if not isinstance(ev['maven'], dict):
        fail('evidence.maven must be an object')
    for coordinate, item in ev['maven'].items():
        if not COORDINATE.fullmatch(coordinate):
            fail('evidence.maven keys must be group:artifact:version')
        require_keys(item, ('artifact', 'licenseEvidence'), (), f'maven[{coordinate}]')
        artifact = require_keys(item['artifact'], ('url',), ('sha1', 'sha256'), f'maven[{coordinate}].artifact')
        https_url(artifact['url'], 'artifact url')
        for key in ('sha1', 'sha256'):
            if key in artifact:
                check_digest(key, artifact[key])
        check_license_evidence(item['licenseEvidence'], f'maven[{coordinate}]')
    ids = set()
    for kind in ('observed', 'unknown'):
        if not isinstance(ev[kind], list):
            fail(f'evidence.{kind} must be an array')
        for item in ev[kind]:
            if kind == 'observed':
                require_keys(item, ('id', 'type', 'name', 'source', 'markers'), ('version', 'purl', 'licenseEvidence', 'note', 'endpoints'), 'observed[]')
            else:
                require_keys(item, ('id', 'name', 'note'), (), 'unknown[]')
            for key in ('id', 'name') + (('note',) if 'note' in item else ()):
                text_field(item, key, kind)
            if not ID.fullmatch(item['id']):
                fail(f'{kind}[].id must be a lowercase identifier')
            if item['id'] in ids:
                fail('duplicate evidence id')
            ids.add(item['id'])
            if kind == 'unknown':
                continue
            where = f"observed[{item['id']}]"
            if not isinstance(item['type'], str) or item['type'] not in {'library', 'service'}:
                fail(f'{where}.type must be library or service')
            if not isinstance(item['markers'], list) or not item['markers'] or not all(isinstance(m, str) and m for m in item['markers']):
                fail(f'{where}.markers must be nonempty strings')
            if item['type'] == 'service':
                if {'version', 'purl', 'licenseEvidence'} & set(item):
                    fail(f'{where}: services must not carry version, purl or licenseEvidence')
                endpoints = item.get('endpoints', [])
                if not isinstance(endpoints, list) or ('endpoints' in item and not endpoints):
                    fail(f'{where}.endpoints must be a nonempty array')
                for url in endpoints:
                    https_url(url, f'{where} endpoint', template=True)
                continue
            if 'endpoints' in item:
                fail(f'{where}: libraries must not carry endpoints')
            if 'version' in item and (not isinstance(item['version'], str) or not OBSERVED_VERSION.fullmatch(item['version'])):
                fail(f'{where}.version is malformed')
            if 'purl' in item and (not isinstance(item['purl'], str) or not PURL.fullmatch(item['purl'])):
                fail(f'{where}.purl must be a pkg: URL')
            if 'licenseEvidence' in item:
                check_license_evidence(item['licenseEvidence'], where)
    return ev


def read_wrapper(text, rel):
    """Parse a narrow ASCII Java-properties subset; unsupported syntax fails closed."""
    if re.search(r'[^\x20-\x7e\t\f\r\n]', text):
        fail('unsupported wrapper property character')
    props = {}
    for line in re.split(r'\r\n|\r|\n', text):
        if line.strip(' \t\f') and not line.lstrip(' \t\f').startswith(('#', '!')):
            key, sep, value = line.partition('=')
            if not sep:
                fail(f'malformed properties line in {rel}')
            key = key.strip()
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*', key):
                fail('unsupported wrapper property key syntax')
            if key in props:
                fail('duplicate wrapper property')
            if re.search(r'\\(?!:)', value):
                fail('unsupported wrapper property value escape or continuation')
            props[key] = value.lstrip(' \t\f').replace('\\:', ':')
    url = https_url(props.get('distributionUrl'), 'distributionUrl')
    match = re.fullmatch(r'https://services\.gradle\.org/distributions/(gradle-([0-9][0-9A-Za-z.-]*)-(bin|all)\.zip)', url)
    if not match:
        fail('unsupported Gradle distributionUrl')
    item = {'name': match.group(1), 'version': match.group(2), 'url': url, 'source': rel}
    if 'distributionSha256Sum' in props:
        item['hashes'] = [check_digest('sha256', props['distributionSha256Sum'])]
    return item


def license_objects(entries):
    seen, out = set(), []
    for entry in entries:
        for lic in entry['declaredLicenses']:
            key = (lic['name'], lic.get('url'))
            if key not in seen:
                seen.add(key)
                obj = {'name': lic['name']}
                if 'url' in lic:
                    obj['url'] = lic['url']
                obj['acknowledgement'] = 'declared'
                out.append({'license': obj})
    return out


def prop(name, value):
    return {'name': name, 'value': str(value)}


def finish_props(props):
    return sorted({(p['name'], p['value']): p for p in props}.values(), key=lambda p: (p['name'], p['value']))


def add_license(component, entries, evidence_by_ref):
    if entries:
        if component['bom-ref'] in evidence_by_ref:
            fail('duplicate bom-ref with license evidence')
        evidence_by_ref[component['bom-ref']] = entries
        component['licenses'] = license_objects(entries)
        component['properties'] += [prop('emcon:license:status', 'upstream-declared-evidence-checked-in')]
        component['properties'] += [prop('emcon:license:evidence', e['url']) for e in entries]
        component['properties'] += [prop('emcon:license:evidence-relation', f"{e['relation']} {e.get('pomCoordinate', '')}".strip()) for e in entries]
    else:
        component['properties'].append(prop('emcon:license:status', 'unknown-no-checked-in-evidence'))


def build(root, evidence_path):
    root = Path(root)
    used_inputs = {}

    def use(rel, role):
        data = read_input(safe_input(root, rel, role), rel)
        digest = hashlib.sha256(data).hexdigest()
        if used_inputs.setdefault(rel, digest) != digest:
            fail(f'input changed while reading: {rel}')
        return decode_input(data, rel)

    rel = evidence_rel(root, evidence_path)
    ev = load_evidence(use(rel, 'evidence'), rel)
    inputs = ev['inputs']
    project = ev['project']
    license_text = use(project['licenseFile'], 'license')
    if used_inputs[project['licenseFile']] != project['licenseFileSha256']:
        fail('project license file drifted from checked-in evidence digest')
    if project['licenseId'] == 'Apache-2.0' and not re.match(r'\s*Apache License\s+Version 2\.0', license_text):
        fail('project license file is not Apache License 2.0 text')

    manifest_rel = inputs['verificationManifest']
    manifest = parse_verification(strict_json_text(use(manifest_rel, 'manifest'), manifest_rel))
    components = {}
    evidence_by_ref = {}

    def entry(key, group, name, version=None, purl=None):
        if key not in components:
            comp = {'type': 'library', 'bom-ref': purl or f'gradle-declared:{key}', 'group': group, 'name': name}
            if version:
                comp['version'] = version
            if purl:
                comp['purl'] = purl
            comp['properties'] = []
            components[key] = comp
        return components[key]

    for item in manifest:
        group, name, version = item['coordinate'].split(':')
        comp = entry(item['coordinate'], group, name, version, item['purl'])
        comp['hashes'] = item['hashes']
        comp['externalReferences'] = [{'type': 'distribution', 'url': item['url']}]
        comp['properties'].append(prop('emcon:observed', manifest_rel))
        comp['properties'].append(prop('emcon:digest:algorithms', ','.join(h['alg'] for h in item['hashes'])))

    local_files, unparsed = 0, []
    for rel in inputs['gradleBuildFiles']:
        for decl in parse_gradle_text(use(rel, 'gradle'), rel):
            if decl['status'] == 'local-file-unresolved':
                local_files += 1
                continue
            if decl['status'] == 'unparsed':
                unparsed.append(decl)
                continue
            group, name, version = decl['coordinate'].split(':')
            static = decl['status'] == 'declared-static'
            comp = entry(decl['coordinate'], group, name, version if static else None, decl.get('purl'))
            comp['properties'].append(prop('emcon:observed', f"{decl['source']} {decl['configuration']}"))
            comp['properties'].append(prop('emcon:resolution', decl['status']))
            if not static:
                comp['properties'].append(prop('emcon:declared-version', version))

    for coordinate, item in ev['maven'].items():
        if coordinate not in components:
            fail(f'stale license evidence for undeclared coordinate {coordinate}')
        comp = components[coordinate]
        for h in comp.get('hashes', []):
            key = {'SHA-1': 'sha1', 'SHA-256': 'sha256'}[h['alg']]
            if item['artifact'].get(key) != h['content']:
                fail(f'{coordinate} {h["alg"]} digest drifted from checked-in license evidence')
        manifest_url = next((r['url'] for r in comp.get('externalReferences', [])), None)
        if manifest_url and manifest_url != item['artifact']['url']:
            fail(f'{coordinate} artifact URL drifted from checked-in license evidence')
    for coordinate, comp in components.items():
        add_license(comp, ev['maven'].get(coordinate, {}).get('licenseEvidence'), evidence_by_ref)

    wrapper_rel = inputs['gradleWrapperProperties']
    wrapper = read_wrapper(use(wrapper_rel, 'wrapper'), wrapper_rel)
    wcomp = {'type': 'application', 'bom-ref': f"gradle-wrapper-distribution:{wrapper['name']}", 'name': wrapper['name'],
             'version': wrapper['version'], 'externalReferences': [{'type': 'distribution', 'url': wrapper['url']}],
             'properties': [prop('emcon:observed', f'{wrapper_rel} distributionUrl'), prop('emcon:resolution', 'declared-static')]}
    if 'hashes' in wrapper:
        wcomp['hashes'] = wrapper['hashes']
    add_license(wcomp, None, evidence_by_ref)
    components['gradle-wrapper:' + wrapper['name']] = wcomp

    services = []
    for item in ev['observed']:
        text = use(item['source'], 'observed')
        for marker in item['markers']:
            if marker not in text:
                fail(f"observed marker for {item['id']} no longer present in {item['source']}")
        props = [prop('emcon:observed', item['source'])]
        if item['type'] == 'service':
            svc = {'bom-ref': f"service:{item['id']}", 'name': item['name'], 'properties': props + [
                prop('emcon:license:status', 'external-service-or-data-terms-not-licensed-by-this-repository')]}
            if 'endpoints' in item:
                concrete = [u for u in item['endpoints'] if not URI_UNSAFE.search(u)]
                svc['properties'] += [prop('emcon:endpoint-template', u) for u in item['endpoints'] if URI_UNSAFE.search(u)]
                if concrete:
                    svc['endpoints'] = concrete
            if 'note' in item:
                svc['description'] = item['note']
            svc['properties'] = finish_props(svc['properties'])
            services.append(svc)
            continue
        comp = {'type': 'library', 'bom-ref': item.get('purl') or f"observed:{item['id']}", 'name': item['name'], 'properties': props}
        if 'version' in item:
            comp['version'] = item['version']
        if 'purl' in item:
            comp['purl'] = item['purl']
        if 'note' in item:
            comp['description'] = item['note']
        add_license(comp, item.get('licenseEvidence'), evidence_by_ref)
        components['observed:' + item['id']] = comp

    ordered = sorted(components.values(), key=lambda c: (c.get('group', ''), c['name'], c.get('version', ''), c['bom-ref']))
    refs = [c['bom-ref'] for c in ordered] + [s['bom-ref'] for s in services]
    if len(set(refs)) != len(refs):
        fail('duplicate bom-ref after merge')
    for comp in ordered:
        comp['properties'] = finish_props(comp['properties'])
    services.sort(key=lambda s: s['bom-ref'])
    unparsed_labels = [f"{u['source']} {u['configuration']} {u['form']}" for u in unparsed]
    unknown_names = '; '.join(u['name'] for u in sorted(ev['unknown'], key=lambda u: u['id']))
    meta_props = [prop('emcon:sbom:kind', KIND), prop('emcon:sbom:completeness', 'incomplete'), prop('emcon:sbom:scope', SCOPE),
                  prop('emcon:unresolved:local-file-dependencies', local_files), prop('emcon:not-inventoried', unknown_names),
                  prop('emcon:unparsed:gradle-declarations', len(unparsed)),
                  prop('emcon:license:disclaimer', ev['disclaimer'])]
    meta_props += [prop('emcon:unparsed:gradle-declaration', label) for label in unparsed_labels]
    meta_props += [prop('emcon:input', f'{rel} sha256:{digest}') for rel, digest in used_inputs.items()]
    sbom = {
        'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1,
        'metadata': {
            'tools': {'components': [{'type': 'application', 'name': TOOL_NAME, 'version': TOOL_VERSION}]},
            'component': {'type': 'application', 'bom-ref': 'project:' + project['name'], 'name': project['name'],
                          'licenses': [{'license': {'id': project['licenseId'], 'acknowledgement': 'declared'}}]},
            'properties': finish_props(meta_props),
        },
        'components': ordered,
        'services': services,
        'compositions': [{'aggregate': 'incomplete', 'assemblies': ['project:' + project['name']]}],
    }
    canonical = json.dumps(sbom, sort_keys=True, separators=(',', ':')).encode()
    sbom = {'bomFormat': 'CycloneDX', 'specVersion': '1.6',
            'serialNumber': 'urn:uuid:' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'emcon-source-sbom:' + hashlib.sha256(canonical).hexdigest())),
            **{k: v for k, v in sbom.items() if k not in {'bomFormat', 'specVersion'}}}
    return sbom, render_notices(ev, ordered, services, local_files, unparsed_labels, evidence_by_ref)


def evidence_rel(root, evidence_path):
    """Keep lexical path segments for allowlist validation; never resolve an evidence symlink."""
    try:
        return Path(evidence_path).absolute().relative_to(Path(root).absolute()).as_posix()
    except ValueError:
        fail('evidence input must be inside the selected repository root')


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def render_notices(ev, components, services, local_files, unparsed_labels, evidence_by_ref):
    lines = ['# Third-party notices (source-observed)', '',
             '<!-- Generated by scripts/dependency_inventory.py from checked-in files. Do not edit by hand. -->', '',
             f"> {ev['disclaimer']}", '',
             'This file lists what the repository\'s checked-in files directly reference. It is **not** a release-artifact '
             'notice file: no Gradle resolution, transitive closure, SDK content or built APK content is covered. '
             'License names are reproduced as upstream metadata declares them; this is not a legal determination.', '',
             '## Project license', '',
             f"{ev['project']['name']} source is distributed under `{ev['project']['licenseId']}` per `{ev['project']['licenseFile']}` "
             f"(sha256 `{ev['project']['licenseFileSha256']}`). {ev['project']['basis']}", '',
             '## Components with checked-in upstream license evidence', '',
             '| Component | Version | Upstream-declared license(s) | Evidence (retrieved UTC) | Observed in |', '|---|---|---|---|---|']
    unknown_rows = []
    for comp in components:
        props = {}
        for p in comp['properties']:
            props.setdefault(p['name'], []).append(p['value'])
        label = ':'.join(x for x in (comp.get('group'), comp['name']) if x)
        version = comp.get('version') or 'unresolved (declared `' + ', '.join(props.get('emcon:declared-version', ['?'])) + '`)'
        observed = '; '.join(props.get('emcon:observed', []))
        if 'licenses' in comp:
            names = '; '.join(l['license']['name'] + (f" (<{l['license']['url']}>)" if 'url' in l['license'] else '') for l in comp['licenses'])
            evidence = [f"{e['relation']}: <{e['url']}> ({e['retrievedAtUtc']})" for e in evidence_by_ref[comp['bom-ref']]]
            lines.append(f'| `{cell(label)}` | {cell(version)} | {cell(names)} | {cell("; ".join(evidence))} | {cell(observed)} |')
        else:
            unknown_rows.append(f'| `{cell(label)}` | {cell(version)} | UNKNOWN — no checked-in evidence | {cell(observed)} |')
    lines += ['', '## Components with UNKNOWN license', '',
              'Declared or observed, but no upstream license evidence is checked in. Treat as unreviewed.', '',
              '| Component | Version | License | Observed in |', '|---|---|---|---|'] + unknown_rows
    lines += ['', '## External services and data (not licensed by this repository)', '',
              'These are referenced endpoints, not bundled software. Their terms of service, data licenses and attribution '
              'requirements apply independently; this repository\'s license grants no rights to them.', '']
    lines += [f"- **{s['name']}** — referenced in `{[p['value'] for p in s['properties'] if p['name'] == 'emcon:observed'][0]}`. "
              f"{s.get('description', '')}".rstrip() for s in services]
    lines += ['', '## Not inventoried — license and redistribution status unknown', '']
    lines += [f"- **{u['name']}** — {u['note']}" for u in sorted(ev['unknown'], key=lambda u: u['id'])]
    lines += ['', '## Limitations', '',
              f'- Local file dependencies (`files(...)` / `fileTree(...)`) declared but not enumerated: {local_files}.',
              f'- Gradle dependency statements detected but not parsed: {len(unparsed_labels)}.'
              + (' They are listed below and are NOT represented as components.' if unparsed_labels else '')]
    lines += [f'  - `{label}`' for label in unparsed_labels]
    lines += ['- Only literal `group:artifact:version` strings in recognised configurations are parsed; map notation, '
              '`platform(...)`, `project(...)`, version-catalog and other forms are counted as unparsed; Kotlin DSL build files are rejected as inputs.',
              '- Transitive dependencies, Android Gradle Plugin internals, ProGuard/R8 output and SDK-provided classes are not listed.',
              '- Digests are carried only where a checked-in manifest pins them; algorithm names reflect the manifest field (SHA-1 legacy or SHA-256).',
              '- Upstream license metadata can be incomplete or wrong; full license texts and NOTICE files must be reviewed before redistribution.',
              '']
    return '\n'.join(lines)


def output_current(path, text):
    """Compare bounded bytes without following output-directory or final-file symlinks."""
    try:
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return False
    try:
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return False
        try:
            with os.fdopen(fd, 'rb', closefd=False) as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise OSError('unsafe output file type')
                expected = text.encode('utf-8')
                return handle.read(len(expected) + 1) == expected
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def write_output(path, text):
    """Replace one artifact atomically; keep the previous artifact on pre-replace failure."""
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        temporary = '.inventory-' + uuid.uuid4().hex
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        try:
            try:
                with os.fdopen(fd, 'wb', closefd=False) as handle:
                    handle.write(text.encode('utf-8'))
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                os.close(fd)
            try:
                info = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                info = None
            if info is not None and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise OSError('unsafe output file type')
            os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
    finally:
        os.close(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generate the offline source-observed CycloneDX inventory and third-party notices.')
    parser.add_argument('--root', default='.')
    parser.add_argument('--evidence', default='verification/license-evidence.json')
    parser.add_argument('--output', default='dist/source-sbom.cdx.json')
    parser.add_argument('--notices', default='docs/third-party-notices.md')
    parser.add_argument('--check', action='store_true', help='verify outputs are current; write nothing')
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if not SAFE_REL.fullmatch(args.evidence) or len(args.evidence) > 300:
            fail('evidence input must be a plain repository-relative POSIX path')
        sbom, notices = build(root, root / args.evidence)
        sbom_text = json.dumps(sbom, indent=2, sort_keys=False) + '\n'
        if (not re.fullmatch(r'dist/[A-Za-z0-9_][A-Za-z0-9_.-]*\.json', args.output)
                or not re.fullmatch(r'docs/[A-Za-z0-9_][A-Za-z0-9_.-]*\.md', args.notices)):
            raise OSError('output path outside artifact allowlist')
        outputs = {root / args.output: sbom_text, root / args.notices: notices}
        if any(path.is_symlink() or any(parent.is_symlink() for parent in path.parents
                                        if parent != root and parent.is_relative_to(root))
               for path in outputs):
            raise OSError('unsafe output location')
        for path in outputs:
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise OSError('unsafe output file type')
        if args.check:
            stale = [p.relative_to(root).as_posix() if p.is_relative_to(root) else p.name for p, text in outputs.items()
                     if not output_current(p, text)]
            if stale:
                print('error: generated output is stale: ' + ', '.join(stale), file=sys.stderr)
                return 1
        else:
            for path, text in outputs.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                write_output(path, text)
    except InventoryError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    except OSError as exc:
        print(f'error: I/O failure writing or reading outputs ({type(exc).__name__}); details suppressed', file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 - deliberate path-free last resort
        print(f'error: internal failure ({type(exc).__name__}); details suppressed to avoid leaking local paths', file=sys.stderr)
        return 4
    comps = sbom['components']
    summary = {
        'components': len(comps), 'services': len(sbom['services']),
        'with_hashes': sum('hashes' in c for c in comps), 'with_purl': sum('purl' in c for c in comps),
        'with_declared_license_evidence': sum('licenses' in c for c in comps),
        'license_unknown': sum('licenses' not in c for c in comps),
        'unresolved_versions': sum('version' not in c for c in comps),
        'serialNumber': sbom['serialNumber'], 'checked': args.check,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
