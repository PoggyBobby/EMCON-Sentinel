# Security and privacy

## Support status

EMCON-Sentinel is an unreleased alpha foundation for the intended Argus product.
No supported production version, security audit, certification, response-time
commitment, or guaranteed update policy is established. Source availability and
an ATAK compatibility declaration are not security assurances.

## Reporting

No dedicated private security contact or verified disclosure channel is
currently documented. Do not place vulnerability details, credentials, real
locations, personal data, or unredacted logs in public issues. If this repository
provides a private vulnerability-reporting option, use it; otherwise first
request a private reporting route from the repository maintainers without
including sensitive details. Availability of that option is not assumed.

A sanitized report should identify the source commit or artifact digest, exact
host/Android versions, affected component, impact, and minimal reproduction
using synthetic data. Maintainers must establish and publish a private channel,
triage ownership, and a support policy before distribution.

## Privacy boundaries

- The source manifest requests `INTERNET`, `ACCESS_WIFI_STATE`,
  `CHANGE_WIFI_MULTICAST_STATE`, `READ_PHONE_STATE`, and `BLUETOOTH_CONNECT`.
  Review the final merged manifest and permission behavior on each claimed
  device; declaration alone does not establish how access behaves at runtime.
- Network-capable code, multicast communication, external map sources, and
  Android logging exist in the source. Do not assume offline-only operation,
  authenticated peers, encrypted traffic, or that logs are free of sensitive
  data. Actual traffic and data handling remain unaudited.
- The plugin interacts with ATAK-owned storage and preferences. Source code
  installs a map-source file outside the plugin's private storage. The source
  manifest sets `allowBackup="false"`, but that is not proof that host data,
  logs, caches, or external copies are excluded from backups or deleted.
- No validated data inventory, retention schedule, deletion guarantee, privacy
  compliance assessment, or third-party processor review is provided. Host and
  external-service behavior needs separate review.

Use synthetic data and a controlled evaluation environment until these
boundaries are assessed. Disable the plugin and stop the host before removal;
follow the [removal notes](plugin/README.md#removal). Uninstalling the APK does
not establish removal of host-owned files or copies already transmitted.

## Known source-level data flows

These are static source findings, not a runtime traffic capture. They are
unresolved distribution risks; no network/privacy behavior was changed by this
release-foundation work.

- [`CotEmitter`](plugin/app/src/main/java/com/emconsentinel/cot/CotEmitter.java)
  defaults to enabled and sends ordinary UDP multicast to `239.2.3.1:6969`.
  [`RiskTickLoop`](plugin/app/src/main/java/com/emconsentinel/ui/RiskTickLoop.java)
  constructs periodic events containing coordinates, identity, and status;
  [`CotXml`](plugin/app/src/main/java/com/emconsentinel/cot/CotXml.java)
  serializes them as plaintext XML. A multicast TTL is not encryption or an
  access-control boundary. This is not a private/offline-by-default design.
- [`EmconSentinelMapComponent`](plugin/app/src/main/java/com/emconsentinel/EmconSentinelMapComponent.java)
  starts the emitter and network listeners when initialized. The C2 and SDR
  listeners parse received UDP payloads without sender authentication in their
  receive paths. Production network/data handling requires a separate review.
- The plugin installs an external map-source configuration under ATAK-owned
  storage. Map-provider requests and host caches need their own privacy and
  license assessment. Uninstalling the plugin does not retract transmitted
  data or prove deletion of host-owned files.

Do not use real personal or operational data during alpha evaluation. These
findings must be resolved and the actual release artifact tested before a
private/offline or secure-transport claim can be made.

## Release security gates

Protect signing keys and repository credentials; do not commit them, attach
local configuration to issues, or print secrets in build logs. Keep debug/test
keys separate from approved release signing. Review dependencies, inputs,
exported components, permissions, network flows, and artifact provenance;
validate the exact release artifact, not just its debug counterpart.

Export classification and any required certification or organizational approval
remain unresolved legal/release gates. No EAR99, unrestricted-export, or
certification claim is made. See the [release checklist](docs/release-readiness.md).
