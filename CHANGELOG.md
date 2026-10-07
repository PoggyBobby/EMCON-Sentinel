# Changelog

This file records changes, not deployment or validation evidence. No published
release is asserted by this initial entry.

## Unreleased — Argus alpha foundation

### Documentation

- Add source-declared compatibility and an evidence-based release checklist.
- Replace the plugin README template with conditional build, signing,
  installation, and removal instructions for the CIV evaluation target.
- Document security reporting, support gaps, privacy limitations, and legal,
  certification, and export-review gates.

### Development infrastructure

- Add an SDK-independent JDK 17/JUnit runner that compiles current repository
  sources, checks the complete existing-test inventory, and records provenance.
- Remove the empty SDK JAR and dummy-signing CI bootstrap. CI tests the JVM
  subset and generic release tooling; it does not claim APK/ATAK validation.
- Add a stdlib-only, secret-free offline build-prerequisite checker, an explicit
  local configuration template, and regression tests for malformed inputs.
- Pin the Gradle distribution's published SHA-256 and expand secret-file ignores.
- Close descriptor false-success cases with an enforced ASCII properties subset;
  34 checker regression tests and an independent review pass.
- Replace deprecated action versions with official Node.js 24 releases pinned
  to immutable commit SHAs.

### Status and limitations

- Argus Defense Systems is the intended distributor; the implementation remains
  EMCON-Sentinel. These documentation changes do not change runtime behavior.
- The source declares ATAK-CIV 4.6.0, minimum Android API 21, and compile/target
  API 34; these do not establish a tested compatibility range. Other template
  flavors are not supported by evidence here.
- Generic tooling and the SDK-independent JVM test subset are verified. No
  working APK, full SDK build, approved release signing, device validation,
  production readiness, or export classification is established.
- Build configuration's `PLUGIN_VERSION = "1.0"` is not evidence of a shipped
  1.0 release. Release history before this file has not been reconstructed.

See [release readiness](docs/release-readiness.md) for outstanding gates.
