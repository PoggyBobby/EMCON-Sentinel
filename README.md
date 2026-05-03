# EMCON Sentinel

**Real-time RF detectability dashboard for drone operators. ATAK-CIV plugin.**

> Converts *"I don't know if I'm exposed"* into *"I have 45 seconds to move 200m NW."*

---

## The problem

Drone operators in Ukraine are dying because Russian SIGINT/DF assets locate them via the RF emissions of their drone control links and FPV video. Once triangulated, fires (artillery, Lancet, Shahed, hunter-killer FPV) follow in 3–30 minutes.

Operators today have **zero real-time awareness** of their RF signature relative to known threats. Their only defense is rules of thumb ("don't key more than 10 minutes from one spot") that are radio-agnostic and threat-agnostic.

## The solution

A phone-sized ATAK plugin that gives the operator a live composite-risk number, a plain-English status (SAFE / CAUTION / MOVE NOW), and a quantified displacement recommendation when risk crosses red.

Runs on the same Android phone an operator already carries for ATAK. Free. Open source. EAR99 — no export restrictions.

## How it works

| Input | Source |
|---|---|
| Operator radio (EIRP, freq, duty) | One-tap pick from 10 bundled profiles (or add your own) |
| Operator GPS | Phone GPS via ATAK's self marker |
| Adversary threats | One-tap AOR posture (5 curated worst-case envelopes) **or** S2-fed specific positions |

**Math:** Friis path-loss → per-band detection sigmoid → exponential dwell saturation → 1-minus-product composite across all assets → 5-second smoothed.

**Output:** Risk dial (0–100%) + plain-English status + threat list + displacement candidate routes.

## What you see

| State | HUD shows | What to do |
|---|---|---|
| Green / SAFE | `SAFE — ~90s budget` | Keep working |
| Amber / CAUTION | `CAUTION — fix in ~45s` | Plan to move |
| Red / MOVE NOW | `MOVE NOW` + DISPLACE modal with 3 candidate routes | Move now |

## Quick start

1. Install ATAK-CIV 4.6.0 on an Android phone (one of the public DoD GitHub releases)
2. Sideload `app-civ-debug.apk`: `adb install -r ATAK-Plugin-EmconSentinel-*-civ-debug.apk`
3. Open ATAK → hamburger → **Plugins** → enable **EMCON Sentinel** → restart ATAK
4. Tile shows up in Tools menu. Tap to open the bottom sheet.

The plugin auto-applies a worst-case threat posture around your GPS — so the dial works from minute zero with no S2 brief.

## Why on a phone

Drone operators already run ATAK on phones (Kropyva, Delta, ATAK-CIV). They can't add a laptop to a ruck. This is a $0 capability upgrade.

## What it doesn't do

- Doesn't jam, deceive, or hide your signal
- Doesn't protect against incoming rounds
- Doesn't tell you where the adversary is (use the worst-case posture or feed your own intel)
- Assumes ATAK is already running and the phone has GPS

## What's real vs. what's modeled

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

## Architecture

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

## OSINT sources

Every adversary number traces to public reporting (Sprotyv G7, CSIS, RUSI, Conflict Armament Research, Janes, Telegram milblogger reporting). See [`docs/osint_sources.md`](docs/osint_sources.md) for the citation table.

No classified data. No FOUO/CUI. No ITAR. No proprietary vendor info beyond public datasheets.

## License

Apache 2.0 — see [`LICENSE`](LICENSE). EAR99 export classification.
