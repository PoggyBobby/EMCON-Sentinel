# EMCON Sentinel

**Real-time DF-risk dashboard for drone operators, in ATAK.**

EMCON Sentinel is an open-source ATAK-CIV plugin that tells a drone operator when accumulated stay-time has made them locatable by adversary direction-finding assets. When risk crosses threshold it proactively suggests displacement positions — one tap drops a route to the chosen hide via ATAK's native route engine and resets the timer.

Apache-2.0. EAR99. Public OSINT only.

## Try it now (no install)

Open [`sim/index.html`](sim/index.html) in any browser. Single self-contained file with the same math, same OSINT data, and same UI behavior as the ATAK plugin — running on a Leaflet/OpenStreetMap base layer instead of ATAK's native MapView. Tap **Load demo scenario** → long-press the dial → tap **START KEYING** → watch the dial climb from green to red over ~25 s.

---

## The 30-second pitch

**The category — operator-side EMCON awareness — is empty.** Every adjacent commercial product (DroneShield, Anduril Pulsar, CRFS RFeye, CloudRF SOOTHSAYER) either looks at the **enemy's** emissions or models **friendly** coverage. None closes the loop on the **friendly operator's own behavioral risk**: how locatable am *I* right now, given how long I've been keying, on what band, with what adversary DF in range?

EMCON Sentinel does. It's a fuel gauge for getting killed: when stay-time on a contested band crosses the locate-and-strike threshold, the dial turns red and the plugin proactively suggests displacement positions in tactical reach.

The most acute current proof point is **Russian counter-drone DF in Ukraine** — Rubicon teams running sensor-to-shooter cycles under two minutes. The same problem applies wherever a small-UAS operator keys a radio in contested EW: PRC SIGINT against US/allied forces in INDOPACOM, IRGC EW in CENTCOM, peer-templated threats in CONUS Red Team exercises, NATO partners on the Eastern Flank. Same math, swap the adversary library.

**Audience:** Army drone operators (159th, 160th SOAR, Ranger Regt, conventional MFE), MARSOC, NSW, AFSOC, partner-nation forces using ATAK-CIV, civilian critical-infrastructure inspection teams in unfriendly airspace.

---

## How it works

```
┌─────────────────────────────────────────────────────────────────┐
│  ATAK-CIV (Android tablet, dev-ATAK 4.6.0.5)                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ EMCON Sentinel Plugin — com.emconsentinel.plugin         │   │
│  │                                                          │   │
│  │  UI Layer (Phase 4)                                      │   │
│  │   • DropDown setup pane   (radio profile, Add Asset,     │   │
│  │                            Start/Stop Keying, About)     │   │
│  │   • RiskDialView          floating bottom-right          │   │
│  │   • ThreatCircleRenderer  per-adversary translucent      │   │
│  │                            DrawingCircles, alpha=P_lock  │   │
│  │   • DisplaceBanner        top-of-map at risk≥0.5         │   │
│  │   • Route handoff         ATAK Route engine, persisted   │   │
│  │           ▲                                              │   │
│  │   1 Hz    │ updates                                      │   │
│  │  ┌────────┴────────┐   ┌──────────────────┐              │   │
│  │  │ RiskScorer      │←──│ Propagation      │              │   │
│  │  │  (Phase 3)      │   │ Engine (Phase 2) │              │   │
│  │  │ • DwellClock    │   │ • CloudRF API    │              │   │
│  │  │   (50 m radius) │   │ • FSPL fallback  │              │   │
│  │  │ • per-asset     │   │ • Friis + sigmoid│              │   │
│  │  │   P_lock(t)     │   │ • per-band detect│              │   │
│  │  │ • composite     │   │                  │              │   │
│  │  │ • 5-s smoothing │   │                  │              │   │
│  │  └────────┬────────┘   └──────────┬───────┘              │   │
│  │           │                       │                      │   │
│  │  ┌────────┴───────────────────────┴───────┐              │   │
│  │  │ Data Layer (Phase 1)                   │              │   │
│  │  │ • adversary_df_systems.json (5 OSINT)  │              │   │
│  │  │ • radio_profiles.json (6 presets)      │              │   │
│  │  │ • demo_scenarios/rubicon_pokrovsk.json │              │   │
│  │  └────────────────────────────────────────┘              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
       ↑                             ↑
   GPS / map                    HTTPS → api.cloudrf.com
   (from ATAK)                  (with FSPL fallback if unreachable)
```

The math: per adversary `i`,

```
P_lock_i(t) = P_detect_i × (1 − exp(−t / τ_i))
P_compromise = 1 − Π_i (1 − P_lock_i)
displayed = MovingAverage(5 s).push(P_compromise)
```

`P_detect_i` is a sigmoid on the link-budget margin in dB:

```
margin = (operator EIRP − path loss + adversary antenna gain) − adversary sensitivity
P_detect = 1 / (1 + exp(−0.2 × margin))
```

`τ_i` is the adversary's published time-to-fix (Zhitel ≈ 90 s, Borisoglebsk-2 ≈ 120 s, Leer-3/Orlan-10 ≈ 45 s).

---

## What's in the box

```
emcon-sentinel/
├── plugin/                                      Android plugin module (Apache-2.0)
│   └── app/src/main/
│       ├── assets/
│       │   ├── adversary_df_systems.json        5 systems, every entry cited to OSINT
│       │   ├── radio_profiles.json              6 presets (Mavic 3, FPV+Crossfire, …)
│       │   └── demo_scenarios/rubicon_pokrovsk.json
│       └── java/com/emconsentinel/
│           ├── data/         JSON loaders + POJOs
│           ├── prop/         FSPL + CloudRF + sigmoid link budget
│           ├── risk/         DwellClock + RiskScorer + DisplacementSearch
│           ├── ui/           RiskDialView + ThreatCircleRenderer + DisplaceBanner
│           └── util/         Geo (haversine, bearing, destination)
├── docs/
│   ├── plans/2026-05-02-emcon-sentinel.md       implementation plan
│   ├── demo_script.md                           3-minute spoken script for the demo video
│   ├── osint_sources.md                         every adversary parameter, with citation
│   └── ATAK_Plugin_Structure_Guide.pdf          (gitignored — DoD-distributed)
└── LICENSE                                      Apache-2.0
```

---

## Build

**Prereqs (macOS):**

```bash
brew install openjdk@17 gradle
brew install --cask android-commandlinetools
yes | sdkmanager --licenses
sdkmanager --install "platform-tools" "platforms;android-34" "build-tools;34.0.0" \
  "emulator" "system-images;android-34;google_apis;arm64-v8a"
```

**Get the public ATAK-CIV SDK** (no TAK.gov account needed — DoD publishes it):

```bash
mkdir -p ~/Desktop/EmconSentinel/sdk
curl --retry 5 -L \
  https://github.com/deptofdefense/AndroidTacticalAssaultKit-CIV/releases/download/4.6.0.5/atak-civ-sdk-4.6.0.5.zip \
  -o ~/Desktop/EmconSentinel/sdk/atak-civ-sdk-4.6.0.5.zip
cd ~/Desktop/EmconSentinel/sdk
python3 -c "import zipfile; zipfile.ZipFile('atak-civ-sdk-4.6.0.5.zip').extractall('.')"
```

**Generate a debug keystore** (used to sign both the plugin and the dev-ATAK so signature trust passes):

```bash
keytool -genkey -v \
  -keystore ~/Desktop/EmconSentinel/plugin/debug.keystore \
  -alias androiddebugkey -storepass android -keypass android \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -dname "CN=EMCON Sentinel Debug, O=EMCON Sentinel, C=US"
```

**Local config** — create `plugin/local.properties` (gitignored):

```properties
sdk.dir=/opt/homebrew/share/android-commandlinetools
sdk.path=/Users/<you>/Desktop/EmconSentinel/sdk/atak-civ
takdev.plugin=/Users/<you>/Desktop/EmconSentinel/sdk/atak-civ/atak-gradle-takdev.jar
takDebugKeyFile=/Users/<you>/Desktop/EmconSentinel/plugin/debug.keystore
takDebugKeyFilePassword=android
takDebugKeyAlias=androiddebugkey
takDebugKeyPassword=android
takReleaseKeyFile=/Users/<you>/Desktop/EmconSentinel/plugin/debug.keystore
takReleaseKeyFilePassword=android
takReleaseKeyAlias=androiddebugkey
takReleaseKeyPassword=android
```

**Build:**

```bash
cd ~/Desktop/EmconSentinel/plugin
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
  ./gradlew :app:testCivDebugUnitTest :app:assembleCivDebug \
  -Dorg.gradle.java.home="$JAVA_HOME"
```

Outputs `app/build/outputs/apk/civ/debug/ATAK-Plugin-EmconSentinel-1.0-*-civ-debug.apk` (~170 KB).

---

## Run

**Re-sign the bundled dev-ATAK with your debug keystore** (so its signature matches the plugin's — required for plugin trust):

```bash
APKSIGNER=/opt/homebrew/share/android-commandlinetools/build-tools/34.0.0/apksigner
cp ~/Desktop/EmconSentinel/sdk/atak-civ/atak.apk ~/Desktop/EmconSentinel/sdk/atak-civ/atak-resigned.apk
$APKSIGNER sign --ks ~/Desktop/EmconSentinel/plugin/debug.keystore \
  --ks-pass pass:android --ks-key-alias androiddebugkey --key-pass pass:android \
  ~/Desktop/EmconSentinel/sdk/atak-civ/atak-resigned.apk
```

**Boot emulator + install:**

```bash
echo no | avdmanager create avd -n EmconTablet -k "system-images;android-34;google_apis;arm64-v8a" --force
$ANDROID_HOME/emulator/emulator -avd EmconTablet -no-window -no-snapshot -no-audio &
adb wait-for-device
until [ "$(adb shell getprop sys.boot_completed | tr -d '\r')" = "1" ]; do sleep 3; done
adb shell wm size 1280x800

adb install -r ~/Desktop/EmconSentinel/sdk/atak-civ/atak-resigned.apk
adb install -r ~/Desktop/EmconSentinel/plugin/app/build/outputs/apk/civ/debug/ATAK-Plugin-EmconSentinel-*-civ-debug.apk
adb shell am start -n com.atakmap.app.civ/com.atakmap.app.ATAKActivity
```

(Or just sideload onto a real Android tablet via `adb install`. ATAK 4.6.0.5 first run is a EULA + permissions + filesystem-access toggle + encryption-passphrase wizard — accept all to reach the map view.)

**Once on the map:**

1. Tap the EMCON Sentinel toolbar button.
2. Pick a radio profile (top of the pane).
3. Tap **Load Demo Scenario** to drop the Rubicon-Pokrovsk three-asset scenario.
4. (Optional) Long-press the risk dial in the bottom-right to flip **DEMO MODE 10×**.
5. Tap **START KEYING**. The dial climbs amber → red over ~25 s (10×) or ~4 min (real-time). Threat circles deepen as per-asset lock probability grows.
6. When the **DISPLACE — risk 0.62** banner appears at top-of-map, tap it. Pick one of the three candidates. ATAK drops a route to that hide.
7. Manually drag the operator marker to the candidate. Tap **START KEYING** again. Dial stays green.

---

## Run the demo scenario

`assets/demo_scenarios/rubicon_pokrovsk.json` ships with the plugin. **Load Demo Scenario** in the setup pane drops three adversaries on a fictional eastern-Ukraine grid:

| Asset | Distance | Bearing | τ (time to fix) |
|---|---|---|---|
| R-330Zh Zhitel | 8 km | E | 90 s |
| Borisoglebsk-2 (RB-301B) | 14 km | SE | 120 s |
| Leer-3 (Orlan-10 RB-341V) | 12 km | NE airborne | 45 s |

In DEMO MODE 10×, total time to red is ~60 s. Without 10× it's ~4–5 min, mirroring real Rubicon sensor-to-shooter cycles.

---

## Limitations

- **No real SDR ingestion.** Keying is a synthetic toggle the operator drives by hand. v2 stretch goal is HackRF One + Python sidecar publishing detections.
- **OSINT-only adversary parameters.** Sensitivity, antenna gain, and time-to-fix come from the Sprotyv G7 Russian EW Systems Analytic Insight Report (Nov 2023), CSIS, RUSI, Conflict Armament Research, and open Russian milblogger reporting. They are conservative first-order estimates, not ground-truth performance data.
- **Free-space fallback when CloudRF is unreachable or unkeyed.** The dial shows a "FREE-SPACE FALLBACK — TERRAIN NOT MODELED" banner whenever the propagation engine is in FSPL mode. Free-space is the **optimistic** case for the adversary (no terrain blockage), so risk numbers in fallback mode are upper bounds.
- **Linear sigmoid detection model.** `k = 0.2`, midpoint 0 dB. 50% detection at the noise floor, 88% at +10 dB margin, 12% at −10 dB. Tunable but not learned. No ML.
- **Hackathon signing.** Both ATAK and the plugin are debug-signed with the same self-generated keystore so signature trust passes locally. For Play-Store production distribution you'd need a TAK.gov user-build-portal certificate.

---

## Roadmap

1. Real SDR ingestion (HackRF One + Python sidecar via local socket → bypass propagation calc when band is confirmed-detected)
2. ML-based emitter classification (modulation type → finer per-band detection probabilities)
3. CoT federation of risk score (each operator's plugin emits a custom CoT every 5 s with current risk; team-lead WinTAK shows the formation color-coded)
4. Offline SPLAT! propagation (bundle SPLAT! binaries + SRTM tiles for one geographic area, demo works fully offline)
5. DELTA / Kropyva ports

---

## Citations & OSINT sources

See `docs/osint_sources.md` for the full list. Primary sources:

- **Sprotyv G7** — *Russian EW Systems Analytic Insight Report*, November 2023. (Public release.)
- **CSIS** — Russian electronic-warfare capability briefs (open).
- **RUSI** — Russia electronic-warfare assessments (open).
- **Conflict Armament Research** — Orlan-10 teardown analysis (2022, public).
- **Open Telegram milblogger reporting** (2024) — for Pole-21 and Shipovnik-Aero usage patterns.

---

## License

Apache 2.0. See [LICENSE](LICENSE).

---

## Acknowledgements

Built on the **public** ATAK-CIV SDK 4.6.0.5 from `deptofdefense/AndroidTacticalAssaultKit-CIV`, which made this 48-hour build possible without TAK.gov gating. SOOTHSAYER (Cloud-RF) was the reference for how RF/propagation plugins integrate with the ATAK MapView.
