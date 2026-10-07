# Civilian product direction: own-device diagnostics

**Status: proposal only.** Nothing in this document is implemented, built, or
validated. The existing EMCON-Sentinel plugin is **not** a civilian product and
must not be described as one; its historical design is described in the
[README](../README.md#historical-prototype-description-unvalidated). This
document specifies a *separate*, genuinely civilian product that could reuse the
repository's generic engineering tooling but none of the plugin's
threat-modeling features.

## Purpose

A standalone, offline Android app that helps an ordinary person **understand and
manage their own device**: which radios and connectivity features are switched
on, which permissions the app holds, and what common settings mean. Typical users
include people learning how their phone works, privacy-conscious users auditing
their settings, educators, and support staff helping someone troubleshoot.

It answers "what is my phone configured to do?" It does not detect, locate,
predict, or advise about anyone else.

## Explicit non-goals (hard exclusions)

The civilian product must not contain, and reviews must reject, any of:

- Adversary, threat, or "detector" profiles, catalogs, or postures of any kind.
- Detection-risk, exposure, or survivability scoring; combat or engagement
  prediction; countdowns tied to being found.
- Movement, displacement, relocation, route, or timing recommendations.
- UAV/drone control, telemetry, C2 bridges, or radio-link tooling.
- Map overlays of threats, scenario packs drawn from real conflicts, or tactical
  data formats and federation (for example CoT/multicast sharing).
- Spectrum scanning of other parties' emissions, direction finding, or
  ambient-signal inventories.
- Background location collection or any upload of device data.

None of the plugin's risk, propagation-for-threat, displacement, adversary-asset,
demo-scenario, CoT, C2, or SDR components should be ported. The civilian app is
a new codebase with its own manifest and permissions.

## Product requirements

### R1. Own-device configuration and permission status

- Show the on/off state of the device's own Wi-Fi, Bluetooth, mobile data,
  airplane mode, and NFC, using only public Android APIs that need no special
  permission or whose permission the user grants explicitly with a stated reason.
- Show which runtime permissions this app holds, each with a plain-language
  explanation and a button that opens the relevant system settings page. The app
  never changes a setting itself.
- Degrade gracefully: if an API is unavailable or a permission is denied, show
  "Not available on this device" or "Permission not granted" with a next step,
  never a blank screen or a guessed value.

### R2. Offline learning

- Bundled, versioned explainers (for example "What does Bluetooth discoverable
  mean?", "Why do apps ask for nearby-devices permission?", "What does airplane
  mode switch off?") that work with no network connection.
- Content cites public, general references and is reviewed for accuracy before
  release; it gives no operational guidance about avoiding observation by others.

### R3. Synthetic examples only

- Tutorials, screenshots, store listings, tests, and demo modes use clearly
  labeled synthetic data. No real people, places, coordinates, device
  identifiers, or events from real conflicts.

### R4. Location: none by default

- The app requests no location permission. Location may be added only for a
  concrete, user-visible civilian purpose that cannot be met otherwise (for
  example, explaining why a system setting depends on location services), and
  then: foreground-only, user-initiated, approximate where possible, processed on
  the device, never stored or transmitted, and covered by an updated privacy
  review before release.

### R5. Privacy and data handling

- No network permission in the first release; no analytics, advertising, crash
  upload, or remote configuration. If a network feature is ever proposed, it
  requires a documented purpose, opt-in, and privacy review first.
- No persistent storage of device state beyond user preferences; a "Clear app
  data" control and an accurate data-inventory statement.
- Diagnostics export, if offered, follows the same model as
  `scripts/support_report.py`: a user-initiated, allowlisted, redacted,
  human-readable file that the user reviews and shares themselves.

### R6. Clear error handling

- Every error states what happened, why (if known), and one next step, in plain
  language without stack traces or internal identifiers.
- Unknown or unsupported states are shown as unknown, never as "OK".
- Failures in one panel do not hide the others.

### R7. Accessibility

- Target WCAG 2.2 AA: TalkBack labels for every control and status, logical focus
  order, touch targets of at least 48 dp, support for system font scaling up to
  200% without clipping, and contrast of at least 4.5:1 for text.
- Status is never conveyed by color alone; each state has text and an icon.
- Respect reduce-motion and dark-mode settings; no time-limited interactions.

## Acceptance and verification plan

A requirement is met only with recorded evidence for the exact release build:

| Area | Evidence required |
| --- | --- |
| Exclusions | Code review checklist confirming none of the non-goals exist; manifest review |
| Permissions | Merged-manifest inventory; runtime grant/deny/revoke tests on each claimed Android version |
| Offline | Test run with networking disabled; manifest shows no `INTERNET` permission |
| Errors | Unit tests for each unavailable/denied/unknown state; UI tests that no panel shows a guessed value |
| Accessibility | Automated accessibility scans plus a manual TalkBack and 200% font pass, recorded per release |
| Privacy | Data inventory, retention statement, and privacy review sign-off |
| Device behavior | Results for each claimed device/OS version; no claim beyond tested combinations |

Until that evidence exists the product is unvalidated and makes no accuracy,
compatibility, privacy, or safety claims.

## Reusable engineering practices from this repository

These generic tools and habits carry over; the plugin's domain logic does not:

- Offline, value-free prerequisite checks that fail closed
  ([`scripts/release_doctor.py`](../scripts/README.md)).
- An explicit test inventory with no silent exclusions and current-run
  provenance ([JVM verification](../verification/README.md)).
- An allowlisted, redacted support report with tests that inject synthetic
  secrets and verify their absence ([troubleshooting](troubleshooting.md#support-report)).
- Pinned dependency and toolchain checksums, read-only CI permissions, and
  honest scope statements in every report.

## Tooling improvement backlog (generic)

Suggested next steps for the development tooling itself, independent of any
product direction:

1. **Support-report freshness:** record whether the saved JVM summary's input
   hashes match the current checkout, so stale results are labeled `stale`
   rather than shown as current.
2. **Dependency pinning:** SHA-256 pins for the JVM dependency lock are being
   added in separate work; confirm both fresh and cached downloads are checked
   against them before treating SHA-1 as legacy-only.
3. **Machine-readable schema:** publish a JSON Schema for
   `dist/support-report.json` and validate it in tests.
4. **Windows support:** the collector currently relies on POSIX `dir_fd` and
   `O_NOFOLLOW`; add an equivalent safe-open path or document a WSL route.
5. **Single entry point:** one `make check`-style command that runs the
   checker, the JVM subset, and the collector, and prints the scope boundary.
6. **CI artifact parity:** have CI run the collector on its own outputs and
   upload the sanitized report next to the raw JVM report.
