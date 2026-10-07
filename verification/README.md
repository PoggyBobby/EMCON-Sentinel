# SDK-independent JVM verification

This is a **JVM source subset**, not an Android/ATAK build or release gate.
It compiles actual, unchanged repository Java sources with JDK 17 and invokes
JUnit 4.13.2's `org.junit.runner.JUnitCore`. It does not fabricate SDK JARs,
load Android Gradle plugins, change test assertions, or copy product logic.
The runner does not use or modify the Gradle 7.6.4 wrapper; the full plugin build remains
in `plugin/` and requires the real licensed ATAK SDK and signing configuration.

## Run

Prerequisites: Python 3.9+ and a real JDK 17 (`java` **and** `javac`).

```sh
export JAVA_HOME=/absolute/path/to/jdk-17
python3 -m unittest discover -s verification -p 'test_*.py' -v
python3 scripts/test_java.py --list
python3 scripts/test_java.py
```

Optional arguments: `--java-home PATH`, `--cache-dir PATH`, `--report-dir PATH`,
`--repo PATH`. `--list` needs neither Java nor an SDK. Default dependency cache:
`~/.hermes/cache/scratch/emcon-java-tests/dependencies`. Override it with
`JAVA_TEST_CACHE`; override report location with `JAVA_TEST_REPORT_DIR`.
Infrastructure-test scratch location defaults to `~/.hermes/cache/scratch` and
can be overridden with `JAVA_TEST_SCRATCH`. Its real execution tests require
`JAVA_HOME`; without it those infrastructure tests are explicitly skipped, but
the actual JVM suite refuses to run successfully without JDK 17. CI supplies
JDK 17 and executes the infrastructure tests, not their skip branches.

Every invocation creates a fresh class output directory. `javac --release 17`
compiles the manifest's production and test files directly. JUnit runs with
`plugin/app` as its working directory, preserving existing asset-file paths.
Compilation failures, JUnit failures, missing tests, empty JUnit execution,
SHA-256 failures, malformed manifests, version mismatch, and subprocess timeouts exit nonzero.

## Exact existing-test inventory

`java-tests.json` accounts for **every** Java file under
`plugin/app/src/test/java`. Any added, deleted, duplicated, or overlapping test
entry fails inventory validation; an exclusion must have a nonempty reason.
Current existing suite: **14 included classes, 60 JUnit test cases, no excluded
classes**. All tests and assertions remain unchanged.

| Included class | Cases observed |
| --- | ---: |
| `com.atakmap.android.test.ExampleTest` | 1 |
| `com.emconsentinel.c2.C2MessageTest` | 4 |
| `com.emconsentinel.cot.CotXmlTest` | 5 |
| `com.emconsentinel.data.AssetLibraryTest` | 3 |
| `com.emconsentinel.data.DemoScenarioTest` | 2 |
| `com.emconsentinel.prop.CloudRfEngineTest` | 3 |
| `com.emconsentinel.prop.FreeSpaceEngineTest` | 4 |
| `com.emconsentinel.prop.LinkBudgetTest` | 10 |
| `com.emconsentinel.risk.DisplacementSearchTest` | 4 |
| `com.emconsentinel.risk.DwellClockTest` | 5 |
| `com.emconsentinel.risk.HopCoachTest` | 5 |
| `com.emconsentinel.risk.MovingAverageTest` | 3 |
| `com.emconsentinel.risk.RiskScorerTest` | 6 |
| `com.emconsentinel.util.GeoTest` | 5 |

Despite the `com.atakmap.android.test` package name, `ExampleTest` only requires
JUnit, so it is included rather than silently discarded. The existing
`CloudRfEngineTest` includes invalid-key requests to a network service. These
run unchanged and test fallback/circuit behavior, not successful service
integration; no real API key is requested, injected, or stored.

The manifest explicitly selects 27 production source files and their existing
JUnit consumers. Other production files are outside this verification subset.
The report enumerates every omitted production source; it is not evidence for
Android/ATAK lifecycle, UI, bridge/sensor integration, APK packaging, signing,
or on-device behavior. No simulator, sensor, bridge, or production Java code
is changed by this infrastructure.

## Reports and provenance

Default output: `verification/build/jvm/` (ignored by the existing `**/build/`
rule). Each execution creates a unique `run-<id>/` directory; the root
`summary.json` is the canonical **latest-run** report, atomically replaced at
startup and finalized on success or failure. Its `run_dir` identifies that
run's evidence. The matching `run-<id>/summary.json` retains its snapshot.
`summary.json` includes:

- Exact included/excluded test inventory and omitted production-source paths.
- Actual JDK/compiler versions, compiler status, executed commands, and per-class
  JUnit counts/exit codes/status. `compile_log` and each class's `log` are explicit
  paths **relative to the report root**, always inside the identified `run_dir`.
- SHA-256 digests of production/test inputs, JSON assets, inventory, dependency
  lock, and runner; each dependency's URL, verified SHA-256, and SHA-1 provenance.
- Explicit `passed` / `failed` final status, start/finish times, and the coverage
  boundary. Bootstrap failures retain the metadata collected before the error.

Within that run directory, `compile.log` contains actual compiler output and
one log per attempted class contains actual JUnitCore output. Output goes
directly to these files, so a timeout preserves partial output, preceding
completed-class results, and their counts. A timed-out command has status
`timed_out` and a null exit code; its unfinished class contributes zero completed
tests. Inventory classes absent from `test_classes` were **not attempted**.
A pre-compilation bootstrap failure has no `compile_log`; a compilation
failure has no attempted-class results. Neither is evidence that tests passed.
Temporary compiled classes are removed after execution.

Historical run directories and legacy root-level logs are intentionally left
untouched, as are unrelated files in a user-supplied `--report-dir`. **Do not
glob all logs or use legacy root-level `compile.log` / class logs as latest-run
evidence.** Read the canonical summary and follow only its current-run paths.
The runner never recursively clears the report directory. Callers can manage
historical retention separately.

Direct `run_suite` calls finalize a failed report before rethrowing bootstrap,
timeout, malformed-input, or interruption errors; normal compiler/JUnit failures
return nonzero. The CLI returns nonzero without replacing partial results with
a bare error object. Failed `--list` inventory validation also records a failed
snapshot; a successful listing does not create execution evidence. Reports
require a writable report location; an I/O failure or forced process termination
cannot guarantee a finalized report and must never be treated as success.

CI uploads reports on success and failure. The stdlib Python infrastructure
tests exercise SHA-256 download/cache rejection, reviewed-URL and digest-format
validation, bounded/atomic/timeout-safe downloads, redirect and symlinked-cache
refusal, fail-closed lock and manifest schemas, path traversal and symlink
escapes, empty/drifting inventories, CLI
operation, real compilation and assertion failures, fresh recompilation,
inventory removal, bootstrap failures, and real compiler/JUnit subprocess
timeouts using temporary **generic infrastructure fixtures**. Network behavior in
these unit tests is simulated with an in-memory `urlopen` stand-in; real Maven
Central downloads are exercised by running the suite with an empty
`--cache-dir`. Timeout tests
shorten only the subprocess deadline, not its output or exit behavior. Reused
report-directory tests prove old success logs and unrelated files survive
unchanged but cannot be attributed to a later failed or reduced-inventory run.

## Dependencies and integrity

`dependencies.json` is a fail-closed lock: a nonempty list whose entries contain
exactly `url`, `sha256`, and optional `sha1`. Verification uses **SHA-256 only**;
`sha1` is retained solely as publisher-checksum provenance. The runner rejects,
before any network or cache I/O, a malformed lock, unknown keys, digests that are
not 64 lowercase hex characters, duplicate cache file names, and any URL that is
not `https://repo.maven.apache.org/maven2/...jar` (plain HTTP, other hosts,
ports, credentials/userinfo, queries, fragments, percent-encoding, and `.`/`..`
segments are refused). A download that redirects away from the reviewed URL is
refused.

Downloads stream in bounded 64 KiB reads with a 60-second socket timeout and a
16 MiB per-artifact limit, hashing as they write to a temporary file in the cache
directory. Only a SHA-256 match is fsynced and atomically renamed into place; a
mismatch, oversize body, redirect, timeout, or interruption leaves no installed
artifact and removes the temporary file. Cached artifacts are re-hashed on every
run; a mismatched cache fails closed and is **not** overwritten or deleted, and a
symlinked cache entry is refused. Stale `.download-*` leftovers are never read.

### SHA-256 provenance (derived, not publisher-signed)

Maven Central publishes `<artifact URL>.sha1` files for these artifacts but
returned **HTTP 404 for `<artifact URL>.sha256`** for all three on
2026-10-07 (UTC). The SHA-256 pins were therefore **derived locally**:

1. Fetched `<artifact URL>.sha1` and the artifact itself over HTTPS from
   `repo.maven.apache.org` (no redirect; final URL equal to the pinned URL).
2. Confirmed the artifact's SHA-1 equals both the published `.sha1` and the
   SHA-1 previously pinned in this repository.
3. Computed SHA-256 of those exact bytes; a second, independent fresh download
   into an empty cache by `scripts/test_java.py` reproduced the same digests.

| Artifact | Bytes | Publisher SHA-1 (checked) | Derived SHA-256 (pinned) |
| --- | ---: | --- | --- |
| `junit-4.13.2.jar` | 384581 | `8ac9e16d933b6fb43bc7f576336b8f4d7eb5ba12` | `8e495b634469d64fb8acfa3495a065cbacc8a0fff55ce1e31007be4c16dc57d3` |
| `hamcrest-core-1.3.jar` | 45024 | `42a25dc3219429f0e5d060061f71acb49bf010a0` | `66fdef91e9739348df7a096aa384a5685f4e875584cce89386a7a47251c4d8e9` |
| `gson-2.10.1.jar` | 283367 | `b3add478d4382b78ea20b1671390a858002feb6c` | `4241c14a7727c34feea6507ec801318a3d4a90f070e4525681079fb94ee4c593` |

The SHA-256 pin therefore attests "same bytes as the artifact whose SHA-1 Maven
Central published", trusting HTTPS transport and that SHA-1 match at derivation
time. **No PGP/`.asc` signature was verified**; these are checksums, not
signatures. No Maven credentials or private repository access is needed.

## Manifest path safety

`java-tests.json` must contain exactly `included_tests`, `excluded_tests`
(path → nonempty reason), and `included_sources`. Every included test/source path
must be a unique relative POSIX `.java` path (letters, digits, `_`, `$`, `-`,
separated by `/`) that resolves to an existing regular file inside
`plugin/app/src/test/java` or `plugin/app/src/main/java`. Absolute paths, `.`/`..`
segments, backslashes, and any symlinked path component are rejected before
compilation. Failures are `ValueError`s recorded in a failed run report.

## Local JDK provisioning used for verification

No system Java was installed or altered. On macOS ARM64 the local test run used
OpenJDK 17.0.2 from Oracle's official OpenJDK archive:

- Discovery: <https://jdk.java.net/archive/>
- Archive: <https://download.java.net/java/GA/jdk17.0.2/dfd4a8d0985749f896bed50d7138ee7f/8/GPL/openjdk-17.0.2_macos-aarch64_bin.tar.gz>
- Official checksum: the archive URL with `.sha256` appended.
- Verified SHA-256: `602d7de72526368bb3f80d95c4427696ea639d2e0cc40455f53ff0bbb18c27c8`.
- Local `JAVA_HOME`: `~/.hermes/cache/scratch/emcon-java17/jdk-17.0.2.jdk/Contents/Home`.

The SHA-256 matched **before extraction** into the scratch directory.
This archived JDK is old and not for production use. CI uses the maintained
Temurin JDK 17 line through `actions/setup-java`; developers should normally
use a maintained JDK 17 distribution. Adoptium API discovery was blocked by an
HTTP 403 on the local machine, so the verified official OpenJDK archive was
used solely to execute these tests.
