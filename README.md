# EMCON Sentinel

**EMCON Sentinel — an Argus Defense Systems ATAK plugin prototype (ATAK-CIV host target).**

> **Release status: development only.** No installable, host-validated release APK is supplied by this source checkout. The configured target is ATAK-CIV 4.6.0; Android/ATAK compatibility and signing acceptance require device validation. Modeled outputs are not validated predictions, accuracy claims, or safety guarantees. See [release readiness](docs/release-readiness.md), [build prerequisites](plugin/README.md), and [security/privacy limitations](SECURITY.md).
>
> "ATAK-CIV" names the host application distribution this plugin targets. It does **not** make this plugin a civilian product: the prototype models RF detection risk for military drone operators, as described in the [historical section](#historical-prototype-description-unvalidated) below. A separate, genuinely civilian concept is only a [proposal](docs/civilian-product-direction.md).

## Supported verification

These are the checks this repository supports today. All are development checks; none builds an APK or exercises the plugin on a device.

```sh
# Python tool tests (prerequisite checker, support report, and related tooling).
python3 -m unittest discover -s tests -v
# Offline structural prerequisite diagnostics; exits nonzero when blocked.
python3 scripts/release_doctor.py --json
# SDK-independent JVM subset of existing JUnit tests (JAVA_HOME -> JDK 17).
python3 scripts/test_java.py
# Offline, sanitized summary of saved results -> dist/support-report.json.
python3 scripts/support_report.py
```

| Check | What it establishes | What it does not establish |
| --- | --- | --- |
| [Prerequisite checker](scripts/README.md) | Structural presence of JDK 17, Android SDK files, ATAK SDK archive layout, and signing fields | That an APK builds, signs, or loads; SDK authenticity; host compatibility |
| [JVM test runner](verification/README.md) | Existing JUnit tests pass when a selected pure-Java source subset is compiled with JDK 17 | Android/ATAK lifecycle, UI, sensors, networking, permissions, packaging, device behavior, or real-world accuracy |
| [Support report](docs/troubleshooting.md#support-report) | A minimal redacted status/count/version summary of locally saved outputs | Freshness, CI results, or any build/device evidence |
| CI (`.github/workflows/test.yml`) | The above Python and JVM-subset checks for the pushed commit | An APK build or release; see [CI versus APK](docs/troubleshooting.md#ci-versus-apk) |

**Historical recorded results** (a past local run, not a claim about the current commit): 60 existing JUnit tests passed across 14 classes; 15 JVM-infrastructure tests passed; the prerequisite checker's 34 regression tests passed after its descriptor fixes were reviewed. See [verification evidence](docs/verification-evidence.md). Current results come from CI or your own run. No APK build, signing, installation, or device test has been performed.

Having trouble? See [troubleshooting](docs/troubleshooting.md) for missing JDKs, checksum errors, CI-versus-APK questions, and what to share (and not share) when asking for help.

## Installation status

No verified installable APK is supplied here. This is an ATAK plugin, not a standalone Android app. See the [conditional build and installation guide](plugin/README.md) for development prerequisites, signing requirements, evaluation installation, and removal. Do not infer compatibility or production readiness from the original demo.

Use synthetic data in controlled evaluation: the current source enables plaintext network sharing by default. See [known privacy risks](SECURITY.md#known-source-level-data-flows).

## License

Apache 2.0 — see [`LICENSE`](LICENSE). Third-party dependencies and the separately supplied ATAK SDK retain their own terms. Export classification is unverified.

---

## Historical prototype description (unvalidated)

> Everything in this section is the original prototype's own description, retained for context. It has **not** been validated by the supported checks above. Words such as "works", "real", "observed live", and "quantified", and every number, status, and recommendation shown, describe intended or demonstrated prototype behavior — not verified accuracy, field performance, or safety. Do not rely on it operationally.

### 90-second demo

[![EMCON Sentinel — 90-second demo](https://img.youtube.com/vi/LKeLwimOees/maxresdefault.jpg)](https://youtu.be/LKeLwimOees)

▶ **[Watch on YouTube](https://youtu.be/LKeLwimOees)** — problem brief → three-tier sensing → live link-budget math → MOVE NOW with directional displacement → what's different.

### The problem

Drone operators in Ukraine are dying because Russian SIGINT/DF assets locate them via the RF emissions of their drone control links and FPV video. Once triangulated, fires (artillery, Lancet, Shahed, hunter-killer FPV) follow in 3–30 minutes.

Operators today have **zero real-time awareness** of their RF signature relative to known threats. Their only defense is rules of thumb ("don't key more than 10 minutes from one spot") that are radio-agnostic and threat-agnostic.

### The solution

A phone-sized ATAK plugin that gives the operator a live composite-risk number, a plain-English status (SAFE / CAUTION / MOVE NOW), and a quantified displacement recommendation when risk crosses red.

Designed as a plugin for an Android phone running ATAK. Source is provided under Apache 2.0. Export classification and distribution obligations require qualified review; this repository does not establish EAR99 status or unrestricted export.

### How it works

| Input | Source |
|---|---|
| Operator radio (EIRP, freq, duty) | One-tap pick from 10 bundled profiles (or add your own) |
| Operator GPS | Phone GPS via ATAK's self marker |
| Adversary threats | One-tap AOR posture (5 curated worst-case envelopes) **or** S2-fed specific positions |

**Math:** Friis path-loss → per-band detection sigmoid → exponential dwell saturation → 1-minus-product composite across all assets → 5-second smoothed.

**Output:** Risk dial (0–100%) + plain-English status + threat list + displacement candidate routes.

### What you see

| State | HUD shows | What to do |
|---|---|---|
| Green / SAFE | `SAFE — ~90s budget` | Keep working |
| Amber / CAUTION | `CAUTION — fix in ~45s` | Plan to move |
| Red / MOVE NOW | `MOVE NOW` + DISPLACE modal with 3 candidate routes | Move now |

### Why on a phone

Drone operators already run ATAK on phones (Kropyva, Delta, ATAK-CIV). They can't add a laptop to a ruck. This is a $0 capability upgrade.

### What it doesn't do

- Doesn't jam, deceive, or hide your signal
- Doesn't protect against incoming rounds
- Doesn't tell you where the adversary is (use the worst-case posture or feed your own intel)
- Assumes ATAK is already running and the phone has GPS

### What's real vs. what's modeled

Be honest: the tool today is a **planning aid + applied-physics calculator with one real sensor input** (the phone's own radios). It is not a full-spectrum RF detector.

| Signal | How it's sourced | Real or modeled? |
|---|---|---|
| Operator's drone radio EIRP / freq / duty | Vendor datasheets (bundled radio profiles) | **Real parameters, modeled emission** — you tap "START KEYING" to assert "I am transmitting now" |
| Operator's phone-side emissions (cellular/WiFi/BT) | Android `TelephonyManager` + `WifiManager` + `BluetoothAdapter` polled every 5 s | **Real, observed live** — `PhoneEmitterMonitor` reads system services |
| Adversary positions | Operator-placed OR AOR posture template OR ARGUS-revealed | **Either operator-asserted or template** (no RF detection of passive DF receivers) |
| Adversary parameters (sensitivity, antenna gain, freq range) | Sprotyv G7 / CSIS / RUSI / Janes catalogs | **Real published numbers** |
| Path loss | Friis equation (free-space) — CloudRF stub for terrain | **Real physics** |
| Detection probability | Logistic sigmoid on link margin | **Real detection theory** |
| Dwell time | Local timer, gated by 50 m radius | **Real, observed** — but presupposes you accurately tagged keying start/stop |
| C2 radio TX state (LR900-F etc.) | `tools/c2_bridge.py` reads MAVLink RADIO_STATUS from ground-side radio | **Real when both ground+air radios are paired** (SiK firmware needs a peer to emit diagnostics) |

**Three sensing tiers:**

1. **Today (works):** phone-side `PhoneEmitterMonitor` — your phone IS at the operator's location and is itself a high-EIRP emitter; DF locks those bands too. The risk loop merges phone bands with the chosen drone radio so the dial reflects the FULL operator signature.
2. **Today (works if both radios paired):** `tools/c2_bridge.py` reads MAVLink RADIO_STATUS from the ground-side LR900-F. When the air-side is also powered, the bridge gets real TX/RX/RSSI. When jammed, the local diagnostic packets keep flowing — it's the radio talking about itself, not derived from receiving the drone.
3. **Roadmap (needs hardware):** RTL-SDR via USB-OTG for direct ambient-RF measurement. Detect adversary jammers turning on, confirm own-radio TX, see what's actually in the spectrum. ~1-2 weeks of work + needs SDR hardware.

The strongest claim today is **"the phone radios feeding the dial are observed live, and the math is real."** Everything else above is real-physics modeling on top of operator-asserted state.

### Architecture

```
plugin/app/src/main/
├── assets/
│   ├── adversary_df_systems.json   # 15 published OSINT systems (Sprotyv, CSIS, RUSI)
│   ├── radio_profiles.json         # 10 operator radios (Crossfire, DJI, Skydio, MicoAir, etc.)
│   ├── aor_postures/               # 5 curated worst-case AOR envelopes
│   ├── demo_scenarios/             # Named historical scenarios (Pokrovsk / Pacific island / Hormuz)
│   └── mobac/                      # ESRI World Imagery + OSM tile sources
└── java/com/emconsentinel/
    ├── data/                       # POJO + JSON loaders
    ├── prop/                       # Path-loss engines (Friis, CloudRF stub)
    ├── risk/                       # RiskScorer, DwellClock, DisplacementSearch
    ├── ui/                         # TopHudStrip, BottomSheetController, tabs, modals
    ├── argus/                      # Simulated friendly UAS that scan for hidden threats
    ├── cot/                        # CoT (Cursor-on-Target) federation over multicast
    └── c2/                         # MAVLink telemetry bridge for real RF detection
```

### OSINT sources

Every adversary number traces to public reporting (Sprotyv G7, CSIS, RUSI, Conflict Armament Research, Janes, Telegram milblogger reporting). See [`docs/osint_sources.md`](docs/osint_sources.md) for the citation table.

The repository describes its inputs as public-source information. This is not a legal determination of classification, ITAR/EAR applicability, or distribution rights. Verify source licenses and SDK redistribution terms before publishing a download.
