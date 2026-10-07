# Dependency inventory (source-observed SBOM)

`scripts/dependency_inventory.py` produces two artifacts from checked-in files only:

| Output | Tracked? | Contents |
|---|---|---|
| `dist/source-sbom.cdx.json` | No (`/dist/` is git-ignored) | CycloneDX 1.6 JSON, source-observed inventory |
| `docs/third-party-notices.md` | Yes | Generated third-party notices with limitations |

```sh
python3 scripts/dependency_inventory.py           # write both outputs, print JSON counts
python3 scripts/dependency_inventory.py --check   # exit 1 if either output is stale or missing; writes nothing
python3 -m unittest tests.test_dependency_inventory -v
```

Exit codes:

| Code | Meaning |
|---|---|
| `0` | OK |
| `1` | Stale or missing output (`--check`) |
| `2` | Malformed, disallowed, unreadable or drifted input (also argparse usage errors) |
| `3` | Unsafe output location or I/O failure writing or reading outputs |
| `4` | Unexpected internal error |

Code 2 messages name repository-relative paths only. Codes 3 and 4 print only the exception type; details are suppressed so local paths never reach logs. No traceback is printed.

## Output path and publication policy

- `--output` accepts only a direct child `dist/<name>.json`; `--notices` accepts only a direct child `docs/<name>.md`. Names start with an ASCII letter, digit or underscore and contain only letters, digits, underscores, dots or hyphens. Absolute paths, traversal, hidden names, nested directories and other repository locations are rejected with exit 3. These restrictions apply in write and check modes.
- Both destinations are preflighted before either artifact is written. Existing symlinked directories/files (including dangling links), special files and multiply linked files are rejected. Missing artifacts are stale in check mode, not successful verification.
- Each write uses an exclusive, mode-0600 temporary file in the destination directory, flushes and fsyncs it, then publishes with directory-relative `os.replace`. Failure before replacement leaves that artifact's previous contents intact and removes the temporary file. Each artifact is atomic individually; the SBOM and notices are **not a two-file transaction**. If the second publication fails, rerun generation before checking the pair.
- Check mode opens the output directory and final file with `O_NOFOLLOW`, verifies a singly linked regular file, and compares at most the expected byte length plus one. Publication rechecks the destination type before replacement. Directory-relative operations avoid following a final-file symlink; this is not a guarantee against hostile users with write access to the repository concurrently renaming directories or temporary files.
- This output implementation targets macOS/Linux POSIX filesystem APIs. The explicitly selected repository root and its ownership are trusted; keep it private from untrusted local writers. No Windows output compatibility or crash-durable two-file transaction is claimed.

These output checks do **not** fix the remaining draft PR's Gradle-parser, evidence-input/provenance or clean-checkout drift-gate findings. This remains a development inventory, not a releasable SBOM.

## What it is — and is not

This is a **source-observed, explicitly incomplete inventory**. It is **not** a release-artifact SBOM. The metadata says so in `emcon:sbom:kind`, `emcon:sbom:completeness=incomplete`, `emcon:sbom:scope` and a `compositions` entry with `aggregate: incomplete`.

What gets inventoried:

1. **Verification manifest**: every row of `verification/dependencies.json`, a canonical Maven Central HTTPS JAR URL, becomes a `pkg:maven` component. Hashes are copied from the manifest field as-is: `sha1` → `SHA-1` (legacy), `sha256` → `SHA-256`. A row can carry both.
2. **Gradle declarations** (Groovy DSL `*.gradle` only): literal `group:artifact:version` strings under known configurations (`classpath`, `implementation`, `api`, `testImplementation`, `testRuntimeOnly`, `coreLibraryDesugaring`, `ksp`, …) inside `dependencies { }` blocks, and `substitute … with|using module('…')` targets.
   - A small lexer removes `//` and `/* */` comments while respecting `'…'`, `"…"` and triple-quoted strings, so `fileTree(include: ['**/*.jar'])` cannot open a fake comment. Unterminated strings or comments, slashy/dollar-slashy strings and complex `${…}` expressions fail closed.
   - Only these statement shapes are parsed: `config 'g:a:v'`, `config('g:a:v')`, `config files(...)` and `config fileTree(...)`. Everything else in a `dependencies` block is **surfaced, not dropped**. That covers map notation, `platform()`/`enforcedPlatform()`, `project()`, version-catalog or property references, unknown or flavor-specific configurations, multi-argument or multi-line calls and `if (…) decl` one-liners. So do declarations outside a `dependencies` block, non-`module` substitution targets, `force`/`useTarget`/`useVersion` and other `dependencies` references. Each one is listed under `emcon:unparsed:gradle-declaration` (`file:line configuration form`, never its arguments) and counted in `emcon:unparsed:gradle-declarations` and in the notices. Closure bodies such as `exclude group: …` are reported too, so this over-reports rather than under-reports. The current repository has 0.
   - Group and name are always validated. Versions are checked by status. Unsupported characters or anything other than three parts fail closed.
   - Static versions get a purl.
   - Dynamic versions get **no version and no purl**: ranges, `+`, `latest.*` and `-SNAPSHOT`. The declared text is recorded as `emcon:declared-version`.
   - `$var` and `${var}` are expanded only inside double-quoted strings. The variable must be assigned exactly once in the file, as `def var = '<literal>'` with a single-quoted literal and nothing else on the statement. Concatenations, double-quoted values, reassigned or duplicate names and `${a.b}` stay `declared-variable-unresolved`. Single-quoted `'${v}'` is never interpolated, and a `$` in a coordinate fails closed.
   - `files(...)` and `fileTree(...)` are counted but not enumerated, and their arguments (which may be local paths) are never emitted.
3. **Gradle wrapper**: the `distributionUrl` from `gradle-wrapper.properties`, plus its `distributionSha256Sum` if present.
4. **Observed external items** listed in `verification/license-evidence.json`:
   - Leaflet loaded from a CDN by `sim/index.html` becomes a component.
   - External tile and API endpoints become `services`. URI templates such as `{z}` are not valid CycloneDX IRIs, so they go into `emcon:endpoint-template`.

What is **never** done: running Gradle, resolving transitive dependencies, listing SDK packages, inspecting APKs or network access.

### Input path policy

Every input named in the evidence file must pass all of these checks. Otherwise generation stops with exit code 2.

- **Plain path**: a repository-relative POSIX path made only of `[A-Za-z0-9_.-]` segments. No leading dots, `..`, `:`, backslashes or absolute paths.
- **Exact spelling**: each segment must match the on-disk directory entry exactly. Case variants such as `PLUGIN/build.gradle` or `Local.Properties` are rejected even on case-insensitive filesystems.
- **No symlinks**: no segment may be a symlink. The final file is opened with `O_NOFOLLOW`.
- **Not a credential carrier** (casefolded): no `local.properties`, `gradle.properties`, `keystore.properties`, `signing.properties`, `.netrc`, `.npmrc`, `.pypirc`, `google-services.json`, `credentials.json`, `secrets.json`, `.env*` or `id_rsa*`/`id_ed25519*`. No `*.keystore`, `*.jks`, `*.bks`, `*.p12`, `*.pfx`, `*.key`, `*.pem`, `*.p8`, `*.ppk`, `*.gpg` or `*.asc`. Nothing under `sdk/`, `.git/`, `.gradle/`, `.ssh/`, `.aws/` or `.gnupg/`.
- **Per-role allowlist**:

  | Role | Allowed |
  |---|---|
  | Project license | exactly `LICENSE` |
  | Verification manifest | `*.json` |
  | Gradle build files | `*.gradle` (Kotlin DSL `*.gradle.kts` is rejected, not mis-parsed) |
  | Wrapper | exactly `gradle-wrapper.properties` |
  | Observed-marker sources | `*.html`, `*.htm`, `*.xml`, `*.java`, `*.kt`, `*.js`, `*.py` |

Only the input's SHA-256 and the presence of the listed markers are used; file contents are never emitted.

## License evidence (`verification/license-evidence.json`)

This file is checked in and used offline. It records what upstream metadata **declares**: Maven POMs (`self` and, if the license is inherited, `parent`) and npm registry metadata. Each entry has its official HTTPS URL, the POM's SHA-256 and the UTC retrieval time. It is not a legal determination.

- Evidence fields are type-checked before use:
  - `relation` must be one of `self`, `parent` or `registry-metadata`.
  - `retrievedAtUtc` must be a real UTC timestamp.
  - `pomCoordinate` must be `group:artifact:version`.
  - Observed `id` must be a lowercase identifier.
  - An observed library `version` must be a version token, and its `purl` must be a `pkg:` URL.
  - Services must not carry `version`, `purl` or `licenseEvidence`, and libraries must not carry `endpoints`.
- Every URL (manifest, artifact, evidence, declared-license, endpoint) must use a strict RFC 3986 character set and round-trip exactly through `urlsplit`/`urlunsplit`, so tabs, newlines, spaces, quotes and non-canonical forms are rejected rather than normalised. Endpoint URI templates may contain only `{lowercase}` placeholders.
- License evidence is attached to each component's `bom-ref` while the SBOM is built. The notices render from that map; nothing is re-matched by id or name.
- Licenses appear in the SBOM as `license.name` with `acknowledgement: "declared"`. Upstream names are kept verbatim, with no SPDX mapping.
- The root project license is `Apache-2.0`. The generator checks that the `LICENSE` file's SHA-256 matches the evidence and that the text is Apache License 2.0.
- Components without evidence get `emcon:license:status=unknown-no-checked-in-evidence` and appear as **UNKNOWN** in the notices.
- Services get `external-service-or-data-terms-not-licensed-by-this-repository`. This repository's license grants no rights to external services or data.
- The `unknown` list covers things this inventory does not enumerate: the ATAK SDK, whose license and redistribution terms are unknown, the Android SDK platform, and unpinned Python tools.

### Fail-closed drift checks

Generation stops with exit code 2 if any of these happen:

- The manifest digest or URL no longer matches the evidence artifact.
- The `LICENSE` file changes.
- An observed marker string disappears from its source file.
- Evidence refers to a coordinate that is no longer declared.
- JSON is malformed or has duplicate keys.
- A schema key is unknown.
- An evidence URL is not HTTPS.
- Gradle notation is unsupported.
- A configured input file is missing.
- An input path violates the input path policy above.
- An input file is unreadable or not UTF-8.
- A URL or evidence field has the wrong type or format.
- The Gradle lexer hits an unsupported construct, or a coordinate has invalid characters.

### Refreshing evidence (manual, outside the generator)

When a dependency changes, fetch the matching `.pom` (and parent `.pom` if the license is inherited) from `https://repo.maven.apache.org/maven2/` and record the following in the evidence file:

- the `<licenses>` entries exactly as declared
- the SHA-256 of the POM
- the artifact's SHA-1 and SHA-256
- the UTC retrieval time

Then run the generator and commit the regenerated notices.

**After the verification manifest moves from SHA-1 to SHA-256**, run `python3 scripts/dependency_inventory.py`. The SBOM's hash algorithm follows whatever the manifest uses. Evidence already stores both digests, so the drift check works before and after the move.

## Validation

The SBOM was checked against the CycloneDX 1.6 JSON schema in a scratch virtualenv, not installed globally, using two methods:

- `cyclonedx-python-lib` `JsonStrictValidator(SchemaVersion.V1_6)`
- `jsonschema` (Draft 7, with format checking) against `https://raw.githubusercontent.com/CycloneDX/specification/1.6/schema/bom-1.6.schema.json` and its `spdx` and `jsf` references

Re-run either method independently to confirm.

## Known coverage gaps

- No transitive dependencies. For example, `hamcrest-core` is listed only because the verification manifest pins it.
- Not covered: Android Gradle Plugin internals, ProGuard/R8 output, Android SDK, ATAK SDK classes and APK contents.
- License evidence exists only for the three Maven verification artifacts and Leaflet. AGP, `atak-gradle-takdev`, `proguard-gradle` and the Gradle distribution are UNKNOWN.
- The checked-in `gradle-wrapper.jar` binary and the unpinned Python tools are not components.
- The Gradle parser is a conservative lexer plus exact statement shapes. It does not evaluate Groovy. Unsupported lexical forms and coordinate notation fail closed, and other dependency-like statements are surfaced as unparsed rather than omitted.
