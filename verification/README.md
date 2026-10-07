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
checksum failures, version mismatch, and subprocess timeouts exit nonzero.

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
  lock, and runner; dependency SHA-1 and actual SHA-256 digests.
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
tests exercise checksum rejection, empty/drifting/malformed inventories, CLI
operation, real compilation and assertion failures, fresh recompilation,
inventory removal, bootstrap failures, and real compiler/JUnit subprocess
timeouts using temporary **generic infrastructure fixtures**. Timeout tests
shorten only the subprocess deadline, not its output or exit behavior. Reused
report-directory tests prove old success logs and unrelated files survive
unchanged but cannot be attributed to a later failed or reduced-inventory run.

## Dependencies and integrity

`dependencies.json` pins official Maven Central HTTPS URLs and the SHA-1 hashes
published at those URLs with `.sha1` appended, for JUnit 4.13.2, Hamcrest Core
1.3, and Gson 2.10.1. New downloads and cached bytes are checked before being
used. A corrupt cache fails closed instead of being silently trusted. SHA-1 is
the publisher's legacy checksum, not a signature; the report additionally
records SHA-256 digests. No Maven credentials or private repository access is
needed.

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
