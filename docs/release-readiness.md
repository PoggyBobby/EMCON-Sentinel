# Argus release readiness

**Status: unreleased alpha foundation; distribution blocked pending evidence.**
The selected download format is an ATAK-CIV Android plugin, not a standalone
app. A local ATAK SDK and approved signing setup have not been supplied.
The implementation remains EMCON-Sentinel, intended for distribution by Argus
Defense Systems. Branding is not evidence of a renamed package, validated binary,
or changed runtime.

This document records source configuration and release gates, not test results.
The source baseline inspected was `f78a6d6e533f61004aca605baa894e39bb929c6a`.
No working APK, SDK access, signing approval, device validation, production
readiness, or certification is established here. Existing demo and marketing
claims are not release evidence.

## Compatibility: declared versus validated

| Item | Verified in source | Still unverified |
| --- | --- | --- |
| Host | `ATAK_VERSION = "4.6.0"`; CIV flavor declares `com.atakmap.app@4.6.0.CIV` | Loading and operation on any exact ATAK-CIV patch/build |
| Android | Minimum API 21; compile/target API 34 | Any Android version or device compatibility |
| Java/build | Java 17 source/target; Gradle wrapper 7.6.4; Android Gradle Plugin 7.4.2 | End-to-end compatibility with the authorized TAK development kit |
| ABI filters | `armeabi-v7a`, `arm64-v8a`, `x86` | Native packaging and operation on these ABIs; no x86_64 claim |
| Other flavors | Additional template flavors exist; MIL is the template default | No support commitment for non-CIV hosts |

Evidence: [`app/build.gradle`](../plugin/app/build.gradle),
[`AndroidManifest.xml`](../plugin/app/src/main/AndroidManifest.xml), and
[`gradle-wrapper.properties`](../plugin/gradle/wrapper/gradle-wrapper.properties).
An API declaration, manifest comment, or successful Java-only check cannot
establish host compatibility. Record exact host version, Android build, device,
ABI, artifact digest, signer identity, commands, and results for each validation.

## Build and signing gates

See the [plugin build guide](../plugin/README.md). Obtain authorized ATAK-CIV
4.6.0 development-kit components and follow their version-specific setup and
license terms. Neither signing approval nor redistribution rights are assumed. The
repository supports a TAK artifact repository or a local TAK Gradle plugin JAR;
these are real dependencies, not replaceable with empty stubs for an APK build.

Both debug and release signing configurations are evaluated during Gradle
configuration and require key-file settings. Debug signing is for controlled
development only. Release builds enable minification and need separately
approved signing credentials and host acceptance testing. Never distribute a
release signed with a test key. Keep keys, passwords, repository credentials,
and `local.properties` out of source control and shared logs.

The TAK repository dependency uses a dynamic `2.+` version. Record the resolved
version and dependency inventory; address reproducibility before distribution.
No build command in these docs is represented as having succeeded.

## Release checklist

Leave a gate unchecked until its evidence is reviewed for the release commit.

- [ ] Assign release, security, support, and signing owners; publish verified
  contact routes and supported-version policy.
- [ ] Approve the Argus name, licensing, dependencies, bundled content, map-source
  terms, SDK usage, and redistribution permissions.
- [ ] Resolve build prerequisites; record toolchain and dependency versions;
  build the explicit CIV debug and release variants from a clean checkout.
- [ ] Run applicable automated checks and review actual logs/results. State test
  scope and exclusions; Java-only checks do not validate an Android plugin.
- [ ] Review the merged manifest, exported components, permissions, network
  traffic, input handling, logs, retention, and host-owned storage.
- [ ] Validate the signed, minified release on each claimed host/device
  combination: install, discovery/load, permission denial, restart, upgrade,
  signature mismatch handling, disable, uninstall, and residual-data cleanup.
- [ ] Verify release signature and checksum; retain provenance, dependency
  inventory, license notices, and a recoverable signing/rollback procedure.
- [ ] Complete privacy review and publish accurate data-flow and retention
  disclosures. Do not claim offline-only operation or secure transport without
  evidence.
- [ ] Obtain qualified legal review of applicable export controls, sanctions,
  end-user/end-use restrictions, and distribution jurisdictions. Classification
  is undetermined: do not assert EAR99 or unrestricted export. Any legacy
  statement to that effect is not an approved classification.
- [ ] Determine required organizational authorization, certification, and
  distribution approvals; obtain them where required. ATAK-CIV targeting or
  open-source availability does not establish certification or authorization.
- [ ] Publish only evidence-backed compatibility, limitations, install/removal
  instructions, and release notes; clearly label remaining alpha limitations.

Until these gates are met, use only controlled evaluation with synthetic data;
there is no production support or safety assurance. See [SECURITY.md](../SECURITY.md)
for reporting and privacy limitations.
