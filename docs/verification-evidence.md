# Argus development handoff — verification evidence

> Historical verification record: publication statements and unresolved checker findings below describe the original local handoff. The descriptor fixes subsequently passed independent review and all 34 checker regression tests; the tool remains structural diagnostics only. New branch pushes or attribution changes do not themselves establish APK readiness or CI success.

**Status: unreleased development source, not an installable or customer-ready product.**

Intended format: the existing ATAK-CIV Android plugin, with Argus Defense Systems as intended distributor. No APK was produced. No GitHub branch, pull request, or release was published.

## What changed

- Replaced CI's empty SDK JAR and dummy-signing bootstrap with real SDK-independent JVM compilation/JUnit execution. The unchanged simulator structure check remains; it is not functional validation.
- Added an explicit source/test inventory, dependency integrity checks, current-input provenance, per-run logs, and regression tests for compiler/assertion/bootstrap/timeout failures.
- Added an experimental stdlib-only build-prerequisite diagnostic tool and isolated regression tests. **Its independent review has not passed; it must not be used as a release gate.**
- Added release/install/support/security documentation, placeholder-only local signing configuration, additional secret-file ignores, and the published Gradle distribution checksum.
- Replaced unsupported unrestricted-export assertions with explicit legal/source-license review requirements.
- Production Java, existing Java test assertions, application assets, runtime network behavior, and application algorithms were not changed.

## Actual local execution

Verified on 2026-10-07 UTC, using Python 3.14 and a checksum-verified official OpenJDK 17.0.2 installation in local scratch. This JDK was used only for development verification; production/runtime support is not established. CI is configured to obtain Temurin JDK 17 separately, but GitHub Actions has not been executed for these changes.

| Check | Actual result | Boundary |
|---|---|---|
| Existing JUnit tests | **60 passed across 14 classes; 0 test classes excluded** | Selected pure-Java production source subset only |
| JVM verification infrastructure | **15 passed** | Includes intentionally failing fixtures to prove failure propagation |
| Prerequisite-checker regression suite | **27 passed, no skips on Python 3.14** | Passing tests do not resolve its independent-review findings |
| Current JUnit report provenance | **55 input hashes matched; 15 referenced logs belonged to the current run** | No stale-log attribution in the verified run |
| Python syntax compilation | Passed | New Python scripts and tests |
| Workflow YAML parsing | Passed; read-only permissions checked | Not remote CI execution or a build |
| `git diff --check` | Passed | Whitespace check only |
| APK build / signing / device installation | **Not performed** | Not verified |

Commands executed from the repository root:

```sh
python3.14 -m unittest discover -s tests -v

# JAVA_HOME pointed to the locally verified JDK 17 installation.
# JAVA_TEST_CACHE pointed to the verified dependency cache.
python3.14 -m unittest discover -s verification -p 'test_*.py' -v
python3.14 scripts/test_java.py

python3.14 -m py_compile scripts/release_doctor.py scripts/test_java.py \
  tests/test_release_doctor.py verification/test_test_java.py
git diff --check
```

JUnit dependencies were checked against pinned Maven Central publisher SHA-1 digests; SHA-256 values are additionally recorded as provenance, not pinned verification hashes. Stronger digest pinning remains a hardening suggestion.

## Independent review

Fresh Claude Opus 5.5 high-effort reviews inspected the generic tooling. These were code inspections, not independent device tests.

- **JVM runner: passed** after fixing stale evidence/report attribution. Nonblocking hardening suggestions remain, including SHA-256 pinning, result-count parsing, interruption handling, and stricter manifest validation.
- **Prerequisite checker: failed final review.** Descriptor parsing can report false success with CR-only line separators, escaped property keys, or continuation lines. Two bounded fix/review cycles were completed; further fixes are not represented as approved. See [the checker warning](../scripts/README.md).

## Still blocking a customer download

1. Acquire and validate the genuine SDK/toolchain and exact supported ATAK host pairing. An official public [ATAK-CIV 4.6.0.5 SDK release](https://github.com/deptofdefense/AndroidTacticalAssaultKit-CIV/releases/tag/4.6.0.5) was located, but its availability does not establish compatibility or redistribution rights.
2. Establish an authorized host-compatible signing identity. No signing keys were supplied or generated as a substitute for that authorization.
3. Build an actual APK, verify its signature/checksum, and test installation, loading, lifecycle, permissions, and uninstall on the exact host/device combination.
4. Resolve the source-level privacy/security findings: default plaintext location/identity/status multicast and automatically started unauthenticated UDP receivers. Documentation is disclosure, **not remediation**. Do not describe this prototype as private/offline or use sensitive real-world location data on the strength of this handoff.
5. Complete SDK/dependency licensing, source-data, export, support, and release-policy reviews.
6. Resolve the experimental checker's remaining review findings before considering it for automated gates.
7. Authenticate GitHub publishing separately, then run exact-head CI and a verified release-producing workflow. The local Git push preflight failed for missing HTTPS authentication.

See [release readiness](release-readiness.md), [security](../SECURITY.md), and [plugin build/install documentation](../plugin/README.md).

## Files delivered

The source ZIP is a snapshot of the updated development source, not an APK. Its `handoff/` directory includes the actual JUnit logs/summary, relevant review verdicts, and this report. Local absolute paths in the packaged summary are tokenized for privacy and portability; counts, statuses, hashes, relative log paths, and actual log output are preserved. A separate patch applies the source changes to the original Git baseline; generated handoff evidence is not part of that patch.

Private signing keys, local properties, credentials, dependency caches, and the development JDK are not included. Changes remain on the local `product/argus-release-foundation` branch without a commit or remote publication.

Claude Opus 5.5 is configured as the Hermes fallback with a per-model `high` reasoning override, and live reviews using that model/effort succeeded. An automatic credits-exhausted failover was not exercised. The active desktop chat model and the separately reported CLI startup model configuration should not be conflated.
