# EMCON-Sentinel plugin — Argus alpha foundation

Unreleased evaluation source, not a validated APK. Argus Defense Systems is the intended distributor;
the current package remains `com.emconsentinel.plugin`. No runtime behavior
or package identity is changed by this documentation.

## Compatibility and prerequisites

The [build file](app/build.gradle) declares ATAK 4.6.0 with a CIV flavor, Android
minimum API 21 and compile/target API 34, Java 17, and ABI filters
`armeabi-v7a`, `arm64-v8a`, `x86`. The wrapper specifies Gradle 7.6.4 and the build
uses Android Gradle Plugin 7.4.2. These are source settings, not validated host,
device, Android-version, or ABI support. Other template flavors are unverified;
select CIV explicitly because the template defaults to MIL.

Before building, provide:

1. JDK 17, Android SDK platform 34, compatible build tools, and access to the
   Gradle distribution and required dependency repositories. Validate the
   complete toolchain against the authorized TAK development kit.
2. ATAK-CIV 4.6.0 development-kit components and version-specific setup
   instructions. The [official 4.6.0.5 release](https://github.com/deptofdefense/AndroidTacticalAssaultKit-CIV/releases/tag/4.6.0.5)
   currently lists `atak-civ-sdk-4.6.0.5.zip`. Downloading a public archive does
   not establish its compatibility, signing approval, or SDK redistribution
   permission; review the archive's terms and provenance before using it.
3. Local `plugin/local.properties` with `sdk.dir` and either approved
   `takrepo.url`, `takrepo.user`, `takrepo.password` settings, or `takdev.plugin`
   pointing to the real local TAK Gradle plugin JAR. Follow the kit's additional
   SDK-path requirements. The template defaults to the local-JAR route and uses
   explicit absolute-path placeholders. Fill them locally; the placeholders
   are not usable configuration.
4. Both signing configurations: `takDebugKeyFile`,
   `takDebugKeyFilePassword`, `takDebugKeyAlias`, `takDebugKeyPassword`, and the
   corresponding `takReleaseKeyFile`, `takReleaseKeyFilePassword`,
   `takReleaseKeyAlias`, `takReleaseKeyPassword`. Both key-file checks run during
   Gradle configuration, including for debug tasks. Use valid local paths and
   separately controlled keys; do not publish keys or credentials.

`local.properties`, keystores, and APKs are ignored by source control; ignoring
files is not a substitute for access controls. Do not attach them to reports.
The TAK repository route resolves `2.+`; record the actual resolved version.

## Conditional build commands

Run from `plugin/` only after completing the prerequisites:

```sh
./gradlew :app:assembleCivDebug
./gradlew :app:testCivDebugUnitTest
./gradlew :app:assembleCivRelease
```

These commands are instructions, not successful execution results. Empty TAK
stubs cannot establish a usable APK. Locate the actual output under
`app/build/outputs/apk/`; do not assume a prebuilt file or a fixed APK filename.

Debug builds are debuggable and for controlled development. Release builds
have minification enabled and use the release signing configuration. A debug
build, isolated unit checks, or a release filename does not establish release
quality. Verify the final APK signature, manifest, digest, signer acceptance,
and host/device behavior before any distribution.

## Evaluation installation

Only proceed with an independently verified, correctly signed CIV artifact and
an authorized test device with the exact host version being evaluated.

1. Record the APK digest and signer, source commit, host build, and Android/device
   details; back up host data before evaluation.
2. Enable USB debugging only for the controlled installation session. Replace
   the placeholder below with the exact verified artifact path:
   ```sh
   adb install -r /absolute/path/to/verified-civ.apk
   ```
3. Open ATAK's plugin-management screen, locate EMCON-Sentinel, and enable it if
   offered; restart the host if requested. Menu labels vary by host build.
4. Confirm discovery and load using sanitized diagnostics. Stop on signature,
   version, permission, or load errors; do not bypass host security checks.
   Installation and loading have not been verified by these docs.

Updates require compatible signing and host policy. A signature mismatch may
require removal of the old package, with potential data loss; do not uninstall
blindly. Do not substitute a debug APK for an approved release.

## Removal

Disable the plugin in ATAK, stop ATAK, and remove the plugin via Android's app
settings or:

```sh
adb uninstall com.emconsentinel.plugin
```

Restart ATAK and confirm the plugin is no longer listed or loaded. Uninstall and
cleanup behavior remain unverified. ATAK-owned preferences, logs, map sources,
and caches may remain. The source installs
`mobac/mapsources/esri_world_imagery.xml` beneath ATAK's storage root; inspect
ownership before removing it through supported host controls. Do not delete
shared host directories or assume uninstallation retracts transmitted data.

## Support, privacy, and release limits

There is no production-support commitment or verified private reporting contact.
Do not publish secrets, real locations, or unredacted logs. Network permissions,
multicast code, logging, and external map sources mean offline-only operation
and secure data handling cannot be assumed. Evaluation should use synthetic
data and a controlled environment.

Read [SECURITY.md](../SECURITY.md) and the
[release-readiness checklist](../docs/release-readiness.md). Certification,
organizational authorization, SDK licensing, and export/end-user legal review
remain release gates. No EAR99 or unrestricted-export classification is claimed.
