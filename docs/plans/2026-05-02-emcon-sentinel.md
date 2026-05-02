# EMCON Sentinel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an open-source ATAK-CIV plugin (`com.emconsentinel.plugin`) that, when a drone operator hits "Start Keying," computes the time-evolving probability that adversary direction-finding (DF) assets within range have located them, displays the score on a colored dial, renders threat envelopes on the ATAK map, and proactively recommends top-3 displacement positions when risk crosses 0.5.

**Architecture:** Pure-Java analytical pipeline. Five layers: (1) JSON-driven data model for adversary DF systems and operator radio profiles, (2) propagation engine (CloudRF API primary + free-space fallback) producing per-asset detection probabilities, (3) risk scorer with stay-time accumulation and composite score across assets, (4) ATAK UI bound through `DropDownReceiver` + map shape overlays + native route engine, (5) demo polish (scenario file, 10× time scaler, sound cues). No ML, no real SDR — synthetic, button-driven.

**Tech Stack:** Java 17, Android Gradle Plugin 4.2.2, ATAK-CIV SDK 4.6.0.5 (public DoD GitHub release — no TAK.gov account required), `atak-gradle-takdev` plugin for compileOnly main.jar, Gson for JSON, JUnit 4 for unit tests, OkHttp for CloudRF HTTP, Android `MediaPlayer`/`SoundPool` for cues. Targets `compileSdkVersion 34`, `minSdkVersion 21` (matches plugintemplate baseline).

---

## File structure

Project root: `~/Desktop/EmconSentinel/`. New repo: `DemonicDeception/emcon-sentinel` (public, Apache-2.0). Inside the repo:

```
emcon-sentinel/
├── LICENSE                                    Apache-2.0
├── README.md                                  judge-facing
├── .gitignore                                 ignores sdk/, tools/reference/, build/, *.keystore, *.apk
├── docs/
│   ├── ATAK_Plugin_Structure_Guide.pdf        copied from SDK zip (gitignored — DoD content)
│   ├── architecture.png                       single-slide pipeline diagram
│   ├── demo_script.md                         3-minute spoken script
│   ├── osint_sources.md                       citations for adversary DF library
│   └── plans/2026-05-02-emcon-sentinel.md     this file
├── sdk/                                       GITIGNORED — local SDK install only
│   └── atak-civ/                              extracted from atak-civ-sdk-4.6.0.5.zip
├── plugin/                                    the actual Android Gradle module
│   ├── build.gradle                           top-level
│   ├── settings.gradle                        rootProject.name = 'EmconSentinel'
│   ├── gradle.properties
│   ├── local.properties                       GITIGNORED — sdk.path, sdk.dir, debug-keystore params
│   ├── debug.keystore                         GITIGNORED — generated locally
│   ├── gradle/wrapper/...                     gradle wrapper
│   └── app/
│       ├── build.gradle                       AGP 4.2.2, takdev plugin, civ flavor
│       ├── proguard-gradle.txt
│       └── src/
│           ├── main/
│           │   ├── AndroidManifest.xml        package="com.emconsentinel.plugin"
│           │   ├── assets/
│           │   │   ├── plugin.xml             registers Lifecycle + Tool extensions
│           │   │   ├── adversary_df_systems.json
│           │   │   ├── radio_profiles.json
│           │   │   └── demo_scenarios/
│           │   │       └── rubicon_pokrovsk.json
│           │   ├── res/
│           │   │   ├── drawable/              ic_launcher + theme drawables
│           │   │   ├── layout/                main_layout.xml + dial + banner + asset_picker
│           │   │   ├── values/                colors, dimens, strings, styles
│           │   │   └── raw/                   chime_amber.ogg, alert_red.ogg
│           │   └── java/com/emconsentinel/
│           │       ├── EmconSentinelMapComponent.java       attaches to MapView
│           │       ├── EmconSentinelDropDownReceiver.java   setup pane
│           │       ├── plugin/
│           │       │   ├── EmconSentinelLifecycle.java      AbstractPluginLifecycle entry
│           │       │   ├── EmconSentinelTool.java           toolbar button (AbstractPluginTool)
│           │       │   ├── PluginNativeLoader.java          (kept from template; unused)
│           │       │   └── support/
│           │       │       ├── AbstractPluginLifecycle.java (kept from template)
│           │       │       └── AbstractPluginTool.java
│           │       ├── data/
│           │       │   ├── AdversarySystem.java             POJO
│           │       │   ├── RadioProfile.java                POJO
│           │       │   ├── RadioBand.java                   POJO
│           │       │   ├── DemoScenario.java                POJO
│           │       │   └── AssetLibrary.java                Gson loader (from /assets)
│           │       ├── prop/
│           │       │   ├── PathLossEngine.java              interface
│           │       │   ├── FreeSpaceEngine.java             FSPL impl (no network)
│           │       │   ├── CloudRfEngine.java               OkHttp impl + circuit breaker → FSPL
│           │       │   ├── PropagationResult.java           {pathLossDb, mode: CLOUDRF|FSPL}
│           │       │   └── LinkBudget.java                  reverse link + sigmoid
│           │       ├── risk/
│           │       │   ├── DwellClock.java                  50 m radius gate
│           │       │   ├── RiskScorer.java                  composite, smoothed
│           │       │   ├── MovingAverage.java               5-s rolling mean
│           │       │   └── DisplacementSearch.java          8 bearings × 3 ranges
│           │       ├── ui/
│           │       │   ├── RiskDialView.java                custom View (Canvas) — colored ring
│           │       │   ├── ThreatCircleRenderer.java        per-asset ATAK Shape circles
│           │       │   ├── DisplaceBanner.java              top-of-map prompt
│           │       │   ├── KeyingButton.java                start/stop toggle
│           │       │   └── AboutFragment.java               OSINT citations
│           │       └── util/
│           │           ├── Geo.java                         haversine, bearing, destinationPoint
│           │           ├── DemoModeFlag.java                10× time scaler
│           │           └── PluginLog.java                   thin wrapper over android.util.Log
│           ├── test/                          JUnit 4 — pure JVM, no Android
│           │   └── java/com/emconsentinel/
│           │       ├── data/AssetLibraryTest.java
│           │       ├── prop/FreeSpaceEngineTest.java
│           │       ├── prop/LinkBudgetTest.java
│           │       ├── risk/DwellClockTest.java
│           │       ├── risk/RiskScorerTest.java
│           │       ├── risk/DisplacementSearchTest.java
│           │       └── util/GeoTest.java
│           └── androidTest/                   instrumentation (only what we can't unit test)
│               └── java/com/emconsentinel/
│                   └── ui/RiskDialViewTest.java
└── tools/
    └── reference/SOOTHSAYER-ATAK-plugin/     cloned, gitignored (study only)
```

---

## Phase ordering and dependencies

```
Phase 0 (env + scaffold)
     │
     ├─→ Phase 1 (data model)          ─┐
     ├─→ Phase 2 (propagation)         │  parallelizable — pure Java, no SDK runtime needed
     │   └─→ Phase 3 (risk scorer)     ─┘
     │
     └─→ Phase 4 (ATAK UI) ─→ Phase 5 (demo polish) ─→ Phase 6 (docs + submit) ─→ Phase 7 (stretch)
```

Phases 1–3 are pure Java + JUnit. They can be developed and tested with `./gradlew :app:test` immediately after Phase 0 succeeds — no emulator, no ATAK install, no device required. Schedule them in parallel if there's a second developer; otherwise they're sequential but very fast (math + JSON, ~6–8 hours of focused work).

Phase 4 is the only phase that requires a working ATAK install on emulator/device.

---

## Phase 0 — Environment + Scaffold

**Files:**
- Create: `~/Desktop/EmconSentinel/` (root)
- Create: `~/Desktop/EmconSentinel/sdk/atak-civ/` (extracted SDK)
- Create: `~/Desktop/EmconSentinel/plugin/` (renamed plugintemplate)
- Create: `~/Desktop/EmconSentinel/plugin/local.properties`
- Create: `~/Desktop/EmconSentinel/plugin/debug.keystore`
- Create: `~/Desktop/EmconSentinel/.gitignore`
- Create: `~/Desktop/EmconSentinel/LICENSE` (Apache 2.0)

- [x] **Step 0.1: Tooling install (15 min)**

```bash
brew install openjdk@17 gradle
brew install --cask android-commandlinetools
yes | sdkmanager --licenses
sdkmanager --install "platform-tools" "platforms;android-34" "build-tools;34.0.0" \
  "emulator" "system-images;android-34;google_apis;arm64-v8a"
# Verify
/opt/homebrew/opt/openjdk@17/bin/java -version    # → 17.0.x
/opt/homebrew/share/android-commandlinetools/platform-tools/adb --version
```

- [x] **Step 0.2: Download + extract public SDK (5 min)**

```bash
mkdir -p ~/Desktop/EmconSentinel/sdk
curl --retry 5 --retry-delay 2 --retry-all-errors -L \
  https://github.com/deptofdefense/AndroidTacticalAssaultKit-CIV/releases/download/4.6.0.5/atak-civ-sdk-4.6.0.5.zip \
  -o ~/Desktop/EmconSentinel/sdk/atak-civ-sdk-4.6.0.5.zip
# Validate size
test "$(stat -f%z ~/Desktop/EmconSentinel/sdk/atak-civ-sdk-4.6.0.5.zip)" -eq 223306255
# Extract (use python — BSD unzip chokes on this archive's central dir)
cd ~/Desktop/EmconSentinel/sdk && python3 -c "import zipfile; zipfile.ZipFile('atak-civ-sdk-4.6.0.5.zip').extractall('.')"
# Confirm artifacts present
ls atak-civ/{main.jar,atak.apk,atak-gradle-takdev.jar,ATAK_Plugin_Structure_Guide.pdf,plugin-examples}
```

- [x] **Step 0.3: Copy plugintemplate, rename packages (10 min)**

```bash
cp -R ~/Desktop/EmconSentinel/sdk/atak-civ/plugin-examples/plugintemplate ~/Desktop/EmconSentinel/plugin
cd ~/Desktop/EmconSentinel/plugin/app/src/main/java
mkdir -p com/emconsentinel
mv com/atakmap/android/plugintemplate/* com/emconsentinel/
rmdir com/atakmap/android/plugintemplate com/atakmap/android com/atakmap

cd ~/Desktop/EmconSentinel/plugin
find app/src -type f \( -name "*.java" -o -name "*.xml" \) -print0 | xargs -0 sed -i '' \
  -e 's|com\.atakmap\.android\.plugintemplate\.plugin\.support|com.emconsentinel.plugin.support|g' \
  -e 's|com\.atakmap\.android\.plugintemplate\.plugin|com.emconsentinel.plugin|g' \
  -e 's|com\.atakmap\.android\.plugintemplate|com.emconsentinel|g' \
  -e 's|PluginTemplateMapComponent|EmconSentinelMapComponent|g' \
  -e 's|PluginTemplateDropDownReceiver|EmconSentinelDropDownReceiver|g' \
  -e 's|PluginTemplateLifecycle|EmconSentinelLifecycle|g' \
  -e 's|PluginTemplateTool|EmconSentinelTool|g' \
  -e 's|PluginTemplate|EmconSentinel|g'

cd app/src/main/java/com/emconsentinel
mv PluginTemplateMapComponent.java EmconSentinelMapComponent.java
mv PluginTemplateDropDownReceiver.java EmconSentinelDropDownReceiver.java
cd plugin
mv PluginTemplateLifecycle.java EmconSentinelLifecycle.java
mv PluginTemplateTool.java EmconSentinelTool.java

# Verify clean rename
grep -rl "plugintemplate\|PluginTemplate" ~/Desktop/EmconSentinel/plugin/app/src && echo "FAIL"
```

- [x] **Step 0.4: Generate debug keystore (1 min)**

```bash
KEYSTORE=~/Desktop/EmconSentinel/plugin/debug.keystore
/opt/homebrew/opt/openjdk@17/bin/keytool -genkey -v \
  -keystore "$KEYSTORE" \
  -alias androiddebugkey -storepass android -keypass android \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -dname "CN=EMCON Sentinel Debug, O=EMCON Sentinel, C=US"
```

- [x] **Step 0.5: Write `local.properties` and `settings.gradle`**

```properties
# ~/Desktop/EmconSentinel/plugin/local.properties (NEVER commit)
sdk.dir=/opt/homebrew/share/android-commandlinetools
sdk.path=/Users/ahmadzaisellab/Desktop/EmconSentinel/sdk/atak-civ
takdev.plugin=/Users/ahmadzaisellab/Desktop/EmconSentinel/sdk/atak-civ/atak-gradle-takdev.jar
takDebugKeyFile=/Users/ahmadzaisellab/Desktop/EmconSentinel/plugin/debug.keystore
takDebugKeyFilePassword=android
takDebugKeyAlias=androiddebugkey
takDebugKeyPassword=android
takReleaseKeyFile=/Users/ahmadzaisellab/Desktop/EmconSentinel/plugin/debug.keystore
takReleaseKeyFilePassword=android
takReleaseKeyAlias=androiddebugkey
takReleaseKeyPassword=android
```

```groovy
// settings.gradle
rootProject.name = 'EmconSentinel'
include ':app'
```

- [ ] **Step 0.6: Update `app/build.gradle` for Java 17 + compileSdk 34**

In `~/Desktop/EmconSentinel/plugin/app/build.gradle`, modify:
- `android { compileSdkVersion 34 ... }` (was 26)
- Remove `buildToolsVersion "30.0.2"` (auto-detected from build-tools 34.0.0)
- Add `compileOptions { sourceCompatibility JavaVersion.VERSION_17; targetCompatibility JavaVersion.VERSION_17 }`
- Bump AGP if needed to handle Java 17: change classpath to `com.android.tools.build:gradle:7.4.2` (verified compatible with takdev 22d11cba)
- Ensure `defaultConfig { minSdkVersion 21; targetSdkVersion 34 }`

Actual diff to paste:

```groovy
android {
    compileSdkVersion 34
    // delete: buildToolsVersion "30.0.2"

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }

    defaultConfig {
        minSdkVersion 21
        targetSdkVersion 34
        ndk {
            abiFilters "armeabi-v7a", "arm64-v8a", "x86"
        }
    }
    // ... rest unchanged
}
```

And in the top-level `buildscript.dependencies`:

```groovy
classpath 'com.android.tools.build:gradle:7.4.2'   // was 4.2.2
```

- [ ] **Step 0.7: First smoke build**

```bash
cd ~/Desktop/EmconSentinel/plugin
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
./gradlew clean assembleCivDebug -Dorg.gradle.java.home="$JAVA_HOME"
```

Expected: BUILD SUCCESSFUL. APK appears at `app/build/outputs/apk/civ/debug/ATAK-Plugin-EmconSentinel-1.0-*-civ-debug.apk`.

If first build fails, common causes (in order of likelihood):
1. `sdk.path` wrong → takdev can't find main.jar
2. AGP/Java version mismatch → bump or downgrade
3. Missing `compileSdkVersion 34` → install via `sdkmanager`
4. Proguard plugin substitution conflict (template uses `com.guardsquare:proguard-gradle:7.1.1`)

- [ ] **Step 0.8: Bring up emulator + sideload**

```bash
# Create AVD if not exists
avdmanager create avd -n EmconTablet -k "system-images;android-34;google_apis;arm64-v8a" -d "pixel_tablet"
# Boot emulator (background)
$ANDROID_HOME/emulator/emulator -avd EmconTablet -no-snapshot-load &
# Wait for it
adb wait-for-device
# Install dev-ATAK and our plugin
adb install ~/Desktop/EmconSentinel/sdk/atak-civ/atak.apk
adb install ~/Desktop/EmconSentinel/plugin/app/build/outputs/apk/civ/debug/ATAK-Plugin-EmconSentinel-*-civ-debug.apk
adb shell monkey -p com.atakmap.app.civ -c android.intent.category.LAUNCHER 1
```

- [ ] **Step 0.9: Verify Phase-0 acceptance**

Open ATAK on the emulator, accept dev permissions, locate the EMCON Sentinel toolbar button, tap it. **Expected:** an empty pane with the title "EMCON Sentinel" appears.

- [ ] **Step 0.10: Init GitHub repo, push initial commit**

```bash
gh repo create DemonicDeception/emcon-sentinel --public --license apache-2.0 \
  --description "ATAK-CIV plugin: real-time DF-risk dashboard for drone operators (open-source, Apache-2.0, public OSINT only)"
cd ~/Desktop/EmconSentinel
git init -b main
git add LICENSE README.md .gitignore plugin/
git commit -m "Phase 0: scaffold renamed plugintemplate as com.emconsentinel.plugin

Apache-2.0 from day 1. Public ATAK-CIV SDK 4.6.0.5 (no TAK.gov account
required). Java 17, AGP 7.4.2, compileSdk 34, minSdk 21. First build
produces a debug APK that loads in dev-ATAK and shows an empty
'EMCON Sentinel' pane on toolbar tap."
git remote add origin git@github.com:DemonicDeception/emcon-sentinel.git
git push -u origin main
```

---

## Phase 1 — Data Model + OSINT Library

(SDK-independent. JUnit only. Run with `./gradlew :app:test`.)

**Files:**
- Create: `plugin/app/src/main/assets/adversary_df_systems.json`
- Create: `plugin/app/src/main/assets/radio_profiles.json`
- Create: `plugin/app/src/main/assets/demo_scenarios/rubicon_pokrovsk.json`
- Create: `plugin/app/src/main/java/com/emconsentinel/data/AdversarySystem.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/data/RadioProfile.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/data/RadioBand.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/data/DemoScenario.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/data/AssetLibrary.java`
- Modify: `plugin/app/build.gradle` (add `testImplementation 'junit:junit:4.13.2'` and `implementation 'com.google.code.gson:gson:2.10.1'`)
- Test: `plugin/app/src/test/java/com/emconsentinel/data/AssetLibraryTest.java`

- [ ] **Step 1.1: Add Gson + JUnit deps to `app/build.gradle`**

In `dependencies { ... }`:
```groovy
implementation 'com.google.code.gson:gson:2.10.1'
testImplementation 'junit:junit:4.13.2'
testImplementation 'org.hamcrest:hamcrest-all:1.3'
```

- [ ] **Step 1.2: Write the adversary library JSON (cite every entry)**

`plugin/app/src/main/assets/adversary_df_systems.json`:
```json
{
  "version": "2026-05-02",
  "systems": [
    {
      "id": "r-330zh-zhitel",
      "display_name": "R-330Zh Zhitel",
      "platform": "ground_vehicle",
      "frequency_min_mhz": 100,
      "frequency_max_mhz": 2000,
      "antenna_gain_dbi": 12.0,
      "sensitivity_dbm": -110,
      "ground_range_km": 25,
      "airborne_range_km": 50,
      "time_to_fix_seconds": 90,
      "source": "Sprotyv G7 Russian EW Systems Analytic Insight Report (Nov 2023); CRFS public datasheets"
    },
    {
      "id": "rb-301b-borisoglebsk-2",
      "display_name": "Borisoglebsk-2 (RB-301B)",
      "platform": "ground_vehicle",
      "frequency_min_mhz": 30,
      "frequency_max_mhz": 3000,
      "antenna_gain_dbi": 10.0,
      "sensitivity_dbm": -107,
      "ground_range_km": 30,
      "airborne_range_km": 60,
      "time_to_fix_seconds": 120,
      "source": "Sprotyv G7 (Nov 2023); CSIS Russian EW capability brief (2024)"
    },
    {
      "id": "pole-21",
      "display_name": "Pole-21",
      "platform": "ground_vehicle",
      "frequency_min_mhz": 1000,
      "frequency_max_mhz": 2500,
      "antenna_gain_dbi": 8.0,
      "sensitivity_dbm": -100,
      "ground_range_km": 15,
      "airborne_range_km": 30,
      "time_to_fix_seconds": 60,
      "source": "Sprotyv G7 (Nov 2023); RUSI Russia EW assessments"
    },
    {
      "id": "shipovnik-aero",
      "display_name": "Shipovnik-Aero",
      "platform": "ground_vehicle",
      "frequency_min_mhz": 100,
      "frequency_max_mhz": 6000,
      "antenna_gain_dbi": 14.0,
      "sensitivity_dbm": -115,
      "ground_range_km": 10,
      "airborne_range_km": 20,
      "time_to_fix_seconds": 75,
      "source": "Sprotyv G7 (Nov 2023); Russian milblogger reporting (open Telegram channels, 2024)"
    },
    {
      "id": "leer-3",
      "display_name": "Leer-3 (Orlan-10 RB-341V)",
      "platform": "airborne",
      "frequency_min_mhz": 800,
      "frequency_max_mhz": 2500,
      "antenna_gain_dbi": 6.0,
      "sensitivity_dbm": -95,
      "ground_range_km": 6,
      "airborne_range_km": 25,
      "time_to_fix_seconds": 45,
      "source": "Sprotyv G7 (Nov 2023); Conflict Armament Research Orlan-10 teardown (2022)"
    }
  ]
}
```

- [ ] **Step 1.3: Write the radio profiles JSON**

`plugin/app/src/main/assets/radio_profiles.json`:
```json
{
  "profiles": [
    {
      "id": "fpv-2.4ghz-crossfire",
      "display_name": "FPV with TBS Crossfire 2.4 GHz",
      "bands": [
        {"freq_mhz": 2400, "eirp_dbm": 20, "duty_cycle": 0.8, "purpose": "control"},
        {"freq_mhz": 5800, "eirp_dbm": 23, "duty_cycle": 1.0, "purpose": "video"}
      ]
    },
    {
      "id": "dji-mavic-3",
      "display_name": "DJI Mavic 3",
      "bands": [
        {"freq_mhz": 2400, "eirp_dbm": 20, "duty_cycle": 1.0, "purpose": "control_video"},
        {"freq_mhz": 5800, "eirp_dbm": 23, "duty_cycle": 1.0, "purpose": "video"}
      ]
    },
    {
      "id": "skydio-x10",
      "display_name": "Skydio X10",
      "bands": [
        {"freq_mhz": 2400, "eirp_dbm": 23, "duty_cycle": 1.0, "purpose": "control_video"},
        {"freq_mhz": 5800, "eirp_dbm": 26, "duty_cycle": 1.0, "purpose": "video"}
      ]
    },
    {
      "id": "silvus-sc4240",
      "display_name": "Silvus SC4240 mesh",
      "bands": [
        {"freq_mhz": 2200, "eirp_dbm": 33, "duty_cycle": 1.0, "purpose": "mesh_data"}
      ]
    },
    {
      "id": "himera-g1-pro",
      "display_name": "HIMERA G1 Pro",
      "bands": [
        {"freq_mhz": 868, "eirp_dbm": 27, "duty_cycle": 0.3, "purpose": "voice_data"}
      ]
    },
    {
      "id": "wifi-gcs-generic",
      "display_name": "Generic Wi-Fi GCS (laptop)",
      "bands": [
        {"freq_mhz": 2412, "eirp_dbm": 20, "duty_cycle": 0.6, "purpose": "wifi_uplink"},
        {"freq_mhz": 5180, "eirp_dbm": 23, "duty_cycle": 0.6, "purpose": "wifi_uplink"}
      ]
    }
  ]
}
```

- [ ] **Step 1.4: Write `RadioBand.java`**

```java
package com.emconsentinel.data;

public final class RadioBand {
    public final double freqMhz;
    public final double eirpDbm;
    public final double dutyCycle;
    public final String purpose;

    public RadioBand(double freqMhz, double eirpDbm, double dutyCycle, String purpose) {
        this.freqMhz = freqMhz;
        this.eirpDbm = eirpDbm;
        this.dutyCycle = dutyCycle;
        this.purpose = purpose;
    }
}
```

- [ ] **Step 1.5: Write `RadioProfile.java`**

```java
package com.emconsentinel.data;

import java.util.Collections;
import java.util.List;

public final class RadioProfile {
    public final String id;
    public final String displayName;
    public final List<RadioBand> bands;

    public RadioProfile(String id, String displayName, List<RadioBand> bands) {
        this.id = id;
        this.displayName = displayName;
        this.bands = Collections.unmodifiableList(bands);
    }
}
```

- [ ] **Step 1.6: Write `AdversarySystem.java`**

```java
package com.emconsentinel.data;

public final class AdversarySystem {
    public enum Platform { GROUND_VEHICLE, AIRBORNE }

    public final String id;
    public final String displayName;
    public final Platform platform;
    public final double frequencyMinMhz;
    public final double frequencyMaxMhz;
    public final double antennaGainDbi;
    public final double sensitivityDbm;
    public final double groundRangeKm;
    public final double airborneRangeKm;
    public final double timeToFixSeconds;
    public final String source;

    public AdversarySystem(String id, String displayName, Platform platform,
                           double frequencyMinMhz, double frequencyMaxMhz,
                           double antennaGainDbi, double sensitivityDbm,
                           double groundRangeKm, double airborneRangeKm,
                           double timeToFixSeconds, String source) {
        this.id = id;
        this.displayName = displayName;
        this.platform = platform;
        this.frequencyMinMhz = frequencyMinMhz;
        this.frequencyMaxMhz = frequencyMaxMhz;
        this.antennaGainDbi = antennaGainDbi;
        this.sensitivityDbm = sensitivityDbm;
        this.groundRangeKm = groundRangeKm;
        this.airborneRangeKm = airborneRangeKm;
        this.timeToFixSeconds = timeToFixSeconds;
        this.source = source;
    }

    public boolean coversFrequency(double freqMhz) {
        return freqMhz >= frequencyMinMhz && freqMhz <= frequencyMaxMhz;
    }
}
```

- [ ] **Step 1.7: Write `AssetLibrary.java` (Gson loader)**

```java
package com.emconsentinel.data;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class AssetLibrary {
    private final List<AdversarySystem> adversarySystems;
    private final List<RadioProfile> radioProfiles;

    private AssetLibrary(List<AdversarySystem> a, List<RadioProfile> r) {
        this.adversarySystems = Collections.unmodifiableList(a);
        this.radioProfiles = Collections.unmodifiableList(r);
    }

    public List<AdversarySystem> adversarySystems() { return adversarySystems; }
    public List<RadioProfile> radioProfiles() { return radioProfiles; }

    public static AssetLibrary load(InputStream adversariesJson, InputStream profilesJson) {
        return new AssetLibrary(parseAdversaries(adversariesJson), parseProfiles(profilesJson));
    }

    private static List<AdversarySystem> parseAdversaries(InputStream is) {
        JsonObject root = JsonParser.parseReader(new InputStreamReader(is, StandardCharsets.UTF_8)).getAsJsonObject();
        JsonArray arr = root.getAsJsonArray("systems");
        List<AdversarySystem> out = new ArrayList<>(arr.size());
        for (JsonElement el : arr) {
            JsonObject o = el.getAsJsonObject();
            out.add(new AdversarySystem(
                o.get("id").getAsString(),
                o.get("display_name").getAsString(),
                AdversarySystem.Platform.valueOf(o.get("platform").getAsString().toUpperCase()),
                o.get("frequency_min_mhz").getAsDouble(),
                o.get("frequency_max_mhz").getAsDouble(),
                o.get("antenna_gain_dbi").getAsDouble(),
                o.get("sensitivity_dbm").getAsDouble(),
                o.get("ground_range_km").getAsDouble(),
                o.get("airborne_range_km").getAsDouble(),
                o.get("time_to_fix_seconds").getAsDouble(),
                o.get("source").getAsString()
            ));
        }
        return out;
    }

    private static List<RadioProfile> parseProfiles(InputStream is) {
        JsonObject root = JsonParser.parseReader(new InputStreamReader(is, StandardCharsets.UTF_8)).getAsJsonObject();
        JsonArray arr = root.getAsJsonArray("profiles");
        List<RadioProfile> out = new ArrayList<>(arr.size());
        for (JsonElement el : arr) {
            JsonObject p = el.getAsJsonObject();
            JsonArray bands = p.getAsJsonArray("bands");
            List<RadioBand> bandList = new ArrayList<>(bands.size());
            for (JsonElement b : bands) {
                JsonObject bo = b.getAsJsonObject();
                bandList.add(new RadioBand(
                    bo.get("freq_mhz").getAsDouble(),
                    bo.get("eirp_dbm").getAsDouble(),
                    bo.get("duty_cycle").getAsDouble(),
                    bo.get("purpose").getAsString()
                ));
            }
            out.add(new RadioProfile(
                p.get("id").getAsString(),
                p.get("display_name").getAsString(),
                bandList
            ));
        }
        return out;
    }
}
```

- [ ] **Step 1.8: Write `AssetLibraryTest.java`**

```java
package com.emconsentinel.data;

import org.junit.Test;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import static org.junit.Assert.*;

public class AssetLibraryTest {
    private static final String ADV_JSON = "{\"systems\":[{" +
        "\"id\":\"x\",\"display_name\":\"X\",\"platform\":\"ground_vehicle\"," +
        "\"frequency_min_mhz\":100,\"frequency_max_mhz\":2000," +
        "\"antenna_gain_dbi\":12.0,\"sensitivity_dbm\":-110," +
        "\"ground_range_km\":25,\"airborne_range_km\":50," +
        "\"time_to_fix_seconds\":90,\"source\":\"test\"}]}";

    private static final String PROF_JSON = "{\"profiles\":[{" +
        "\"id\":\"p\",\"display_name\":\"P\"," +
        "\"bands\":[{\"freq_mhz\":2400,\"eirp_dbm\":20,\"duty_cycle\":0.8,\"purpose\":\"ctrl\"}]" +
        "}]}";

    @Test public void parsesAdversariesAndProfiles() {
        AssetLibrary lib = AssetLibrary.load(
            new ByteArrayInputStream(ADV_JSON.getBytes(StandardCharsets.UTF_8)),
            new ByteArrayInputStream(PROF_JSON.getBytes(StandardCharsets.UTF_8))
        );
        assertEquals(1, lib.adversarySystems().size());
        AdversarySystem a = lib.adversarySystems().get(0);
        assertEquals("x", a.id);
        assertEquals(AdversarySystem.Platform.GROUND_VEHICLE, a.platform);
        assertEquals(-110.0, a.sensitivityDbm, 1e-9);
        assertTrue(a.coversFrequency(900));
        assertFalse(a.coversFrequency(3000));

        assertEquals(1, lib.radioProfiles().size());
        RadioProfile p = lib.radioProfiles().get(0);
        assertEquals(1, p.bands.size());
        assertEquals(2400.0, p.bands.get(0).freqMhz, 1e-9);
    }
}
```

- [ ] **Step 1.9: Run tests**

```bash
cd ~/Desktop/EmconSentinel/plugin && ./gradlew :app:testCivDebugUnitTest
```

Expected: `1 test passed`. Phase 1 acceptance achieved.

- [ ] **Step 1.10: Commit**

```bash
git add plugin/app/src/main/assets/ plugin/app/src/main/java/com/emconsentinel/data/ plugin/app/src/test/java/com/emconsentinel/data/ plugin/app/build.gradle
git commit -m "Phase 1: data model + OSINT-cited adversary library + 6 radio profiles"
```

---

## Phase 2 — Propagation engine (FSPL + CloudRF + link budget)

(SDK-independent. Math + HTTP. JUnit only.)

**Files:**
- Create: `plugin/app/src/main/java/com/emconsentinel/util/Geo.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/prop/PathLossEngine.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/prop/PropagationResult.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/prop/FreeSpaceEngine.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/prop/CloudRfEngine.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/prop/LinkBudget.java`
- Modify: `plugin/app/build.gradle` (add `implementation 'com.squareup.okhttp3:okhttp:4.12.0'`)
- Test: `plugin/app/src/test/java/com/emconsentinel/{util,prop}/`

- [ ] **Step 2.1: Write `Geo.java`** (haversine + bearing + destination — pure JVM)

```java
package com.emconsentinel.util;

public final class Geo {
    private static final double EARTH_RADIUS_KM = 6371.0088;
    private Geo() {}

    public static double distanceKm(double lat1, double lon1, double lat2, double lon2) {
        double phi1 = Math.toRadians(lat1), phi2 = Math.toRadians(lat2);
        double dPhi = Math.toRadians(lat2 - lat1);
        double dLam = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dPhi/2)*Math.sin(dPhi/2)
                 + Math.cos(phi1)*Math.cos(phi2)*Math.sin(dLam/2)*Math.sin(dLam/2);
        return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a));
    }

    public static double bearingDeg(double lat1, double lon1, double lat2, double lon2) {
        double phi1 = Math.toRadians(lat1), phi2 = Math.toRadians(lat2);
        double dLam = Math.toRadians(lon2 - lon1);
        double y = Math.sin(dLam) * Math.cos(phi2);
        double x = Math.cos(phi1)*Math.sin(phi2) - Math.sin(phi1)*Math.cos(phi2)*Math.cos(dLam);
        return (Math.toDegrees(Math.atan2(y, x)) + 360) % 360;
    }

    /** Given start lat/lon, bearing in degrees, distance in km, compute destination. */
    public static double[] destination(double lat, double lon, double bearingDeg, double distKm) {
        double phi1 = Math.toRadians(lat);
        double lam1 = Math.toRadians(lon);
        double theta = Math.toRadians(bearingDeg);
        double delta = distKm / EARTH_RADIUS_KM;
        double phi2 = Math.asin(Math.sin(phi1)*Math.cos(delta)
                              + Math.cos(phi1)*Math.sin(delta)*Math.cos(theta));
        double lam2 = lam1 + Math.atan2(
            Math.sin(theta)*Math.sin(delta)*Math.cos(phi1),
            Math.cos(delta) - Math.sin(phi1)*Math.sin(phi2));
        return new double[] { Math.toDegrees(phi2), ((Math.toDegrees(lam2) + 540) % 360) - 180 };
    }
}
```

- [ ] **Step 2.2: Write `GeoTest.java`** — known distances (e.g., NYC→LA ≈ 3935 km), antipodal point bearing, monotonic distance.

(Test code follows the pattern of Step 1.8 — assert distances within 0.5%.)

- [ ] **Step 2.3: Write `PropagationResult.java` and `PathLossEngine.java` interface**

```java
package com.emconsentinel.prop;
public final class PropagationResult {
    public enum Mode { CLOUDRF, FREE_SPACE }
    public final double pathLossDb;
    public final Mode mode;
    public PropagationResult(double pathLossDb, Mode mode) {
        this.pathLossDb = pathLossDb;
        this.mode = mode;
    }
}
```

```java
package com.emconsentinel.prop;
public interface PathLossEngine {
    PropagationResult pathLoss(double txLat, double txLon, double rxLat, double rxLon, double freqMhz);
}
```

- [ ] **Step 2.4: Write `FreeSpaceEngine.java`**

```java
package com.emconsentinel.prop;
import com.emconsentinel.util.Geo;

public final class FreeSpaceEngine implements PathLossEngine {
    @Override
    public PropagationResult pathLoss(double txLat, double txLon, double rxLat, double rxLon, double freqMhz) {
        double dKm = Math.max(0.001, Geo.distanceKm(txLat, txLon, rxLat, rxLon));
        double fspl = 20.0*Math.log10(dKm) + 20.0*Math.log10(freqMhz) + 32.44;
        return new PropagationResult(fspl, PropagationResult.Mode.FREE_SPACE);
    }
}
```

- [ ] **Step 2.5: `FreeSpaceEngineTest.java`** — known-good values:
  - 5 km @ 2400 MHz → ~114 dB
  - 1 km @ 5800 MHz → ~108 dB
  - Monotonic: doubling distance adds 6 dB

- [ ] **Step 2.6: Write `LinkBudget.java`**

```java
package com.emconsentinel.prop;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.RadioBand;

public final class LinkBudget {
    private LinkBudget() {}

    /** Logistic on margin (dB). Midpoint=0, steepness k=0.2 → 50% at 0 dB, ~88% at +10 dB. */
    public static double sigmoid(double marginDb) {
        return 1.0 / (1.0 + Math.exp(-0.2 * marginDb));
    }

    /** Per-band detection probability. Returns 0 if adversary doesn't cover the band. */
    public static double bandDetectionProb(AdversarySystem adv, RadioBand band, double pathLossDb) {
        if (!adv.coversFrequency(band.freqMhz)) return 0.0;
        double receivedDbm = band.eirpDbm - pathLossDb + adv.antennaGainDbi;
        double margin = receivedDbm - adv.sensitivityDbm;
        return sigmoid(margin) * band.dutyCycle;
    }
}
```

- [ ] **Step 2.7: `LinkBudgetTest.java`** — assert sigmoid(0)=0.5, sigmoid(10)≈0.88, frequency-out-of-range returns 0, duty-cycle scaling.

- [ ] **Step 2.8: Write `CloudRfEngine.java` (with FSPL fallback on any failure)**

```java
package com.emconsentinel.prop;

import com.emconsentinel.util.Geo;
import okhttp3.*;
import org.json.JSONObject;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

public final class CloudRfEngine implements PathLossEngine {
    private static final MediaType JSON = MediaType.parse("application/json");
    private static final int FAILURES_BEFORE_TRIP = 3;

    private final OkHttpClient client = new OkHttpClient();
    private final String apiKey;
    private final FreeSpaceEngine fallback = new FreeSpaceEngine();
    private final AtomicInteger failures = new AtomicInteger(0);

    public CloudRfEngine(String apiKey) { this.apiKey = apiKey; }

    @Override
    public PropagationResult pathLoss(double txLat, double txLon, double rxLat, double rxLon, double freqMhz) {
        if (failures.get() >= FAILURES_BEFORE_TRIP) {
            return fallback.pathLoss(txLat, txLon, rxLat, rxLon, freqMhz);
        }
        try {
            JSONObject body = new JSONObject()
                .put("transmitter", new JSONObject().put("lat", txLat).put("lon", txLon).put("frq", freqMhz))
                .put("receiver",    new JSONObject().put("lat", rxLat).put("lon", rxLon));
            Request req = new Request.Builder()
                .url("https://api.cloudrf.com/path/")
                .header("key", apiKey)
                .post(RequestBody.create(body.toString(), JSON))
                .build();
            try (Response resp = client.newCall(req).execute()) {
                if (!resp.isSuccessful() || resp.body() == null) throw new IOException("HTTP " + resp.code());
                JSONObject json = new JSONObject(resp.body().string());
                double pathLossDb = json.getJSONObject("Receiver").getDouble("path_loss_dB");
                failures.set(0);
                return new PropagationResult(pathLossDb, PropagationResult.Mode.CLOUDRF);
            }
        } catch (Exception e) {
            failures.incrementAndGet();
            return fallback.pathLoss(txLat, txLon, rxLat, rxLon, freqMhz);
        }
    }
}
```

- [ ] **Step 2.9: Smoke unit-test for the public `bandDetectionProb` integration** — given a synthetic `AdversarySystem` (Zhitel-like) and a `RadioBand` (2400 MHz @ 20 dBm), at 5 km FSPL, assert detection prob > 0.9; at 50 km, < 0.05.

- [ ] **Step 2.10: Commit + tests pass**

```bash
./gradlew :app:testCivDebugUnitTest
git add plugin/app/src/main/java/com/emconsentinel/{prop,util}/ plugin/app/src/test/java/com/emconsentinel/{prop,util}/ plugin/app/build.gradle
git commit -m "Phase 2: FSPL engine + CloudRF engine with circuit-breaker fallback + link budget"
```

---

## Phase 3 — Risk scorer

(SDK-independent. Pure JVM. JUnit only.)

**Files:**
- Create: `plugin/app/src/main/java/com/emconsentinel/risk/DwellClock.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/risk/MovingAverage.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/risk/RiskScorer.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/risk/DisplacementSearch.java`
- Test: `plugin/app/src/test/java/com/emconsentinel/risk/`

- [ ] **Step 3.1: `DwellClock.java`** — accumulates seconds while operator stays in 50 m radius and `isKeying`; resets if either fails. Unit-test: simulate 300 s with movement at t=120s, assert dwell resets.

- [ ] **Step 3.2: `MovingAverage.java`** — fixed-window mean over the last 5 samples (or last 5 seconds when `update(now,...)` is sparse).

- [ ] **Step 3.3: `RiskScorer.java`**

Composite probability across N adversary systems:
```
P_lock_i = P_detect_i * (1 - exp(-t / tau_i))
P_compromise = 1 - PROD_i (1 - P_lock_i)
displayedRisk = movingAverage(P_compromise)   // 5-s smoothing
```

Public API:
```java
public final class RiskScorer {
    public RiskScorer(AssetLibrary lib, RadioProfile profile, PathLossEngine prop, DwellClock clock, MovingAverage smoother);
    public RiskUpdate update(long nowMillis, double opLat, double opLon, boolean isKeying,
                             List<PlacedAdversary> adversariesOnMap);
}
```

`RiskUpdate` carries: `displayedScore`, `dwellSeconds`, `topThreatId`, `topThreatBearingDeg`, `topThreatRangeKm`, `propagationModeBanner` (CLOUDRF / FSPL_FALLBACK).

- [ ] **Step 3.4: `DisplacementSearch.java`** — for each of 24 candidate points (8 bearings × 3 ranges), simulate "stop keying for 30 s, then move there and stay for 30 s," score with same RiskScorer math. Return top 3 by predicted risk reduction.

- [ ] **Step 3.5–3.7: Tests**:
  - `DwellClockTest`: keying continuously, dwell rises monotonically; movement out of radius resets to 0.
  - `RiskScorerTest`: 5-min keying near a Zhitel-like system → smoothed score climbs from ~0 to ~0.9; stop keying → score drops below 0.1 within 30 s.
  - `DisplacementSearchTest`: from a high-risk position, top candidate's predicted risk < current.

- [ ] **Step 3.8: Commit**

```bash
git commit -m "Phase 3: dwell clock + composite risk scorer + 24-candidate displacement search"
```

---

## Phase 4 — ATAK UI

(Requires Phase 0 success and a working device/emulator. Code touches ATAK SDK classes — `MapView`, `MapItem`, `Marker`, `Shape`, `DropDownReceiver`, `Route`.)

**Files:**
- Modify: `plugin/app/src/main/java/com/emconsentinel/EmconSentinelDropDownReceiver.java` (build out the setup pane)
- Modify: `plugin/app/src/main/java/com/emconsentinel/EmconSentinelMapComponent.java` (register layers + tickers)
- Create: `plugin/app/src/main/java/com/emconsentinel/ui/RiskDialView.java` (custom Canvas View)
- Create: `plugin/app/src/main/java/com/emconsentinel/ui/ThreatCircleRenderer.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/ui/DisplaceBanner.java`
- Create: `plugin/app/src/main/java/com/emconsentinel/ui/KeyingButton.java`
- Create: `plugin/app/src/main/res/layout/setup_pane.xml`
- Create: `plugin/app/src/main/res/layout/risk_dial.xml`
- Create: `plugin/app/src/main/res/layout/displace_banner.xml`

- [ ] **Step 4.1: Setup pane layout (`setup_pane.xml`)** — `Spinner` for radio profile, `RecyclerView` for adversary asset overlay, `Button` "Add Asset," `Button` "Start/Stop Keying," `Button` "Load Demo Scenario," `Button` "About."

- [ ] **Step 4.2: Hook up tap-to-place adversary marker.** When user taps Add Asset and selects a system from the spinner, register a one-shot map-tap listener (`MapView.getMapEventDispatcher().addMapEventListener(MapEvent.MAP_CLICK, ...)`). On tap, create a `Marker` at that GeoPoint with a custom icon per platform (vehicle / aircraft drawable), persist it in a session list (`PlacedAdversary { adversarySystemId, lat, lon }`).

- [ ] **Step 4.3: Risk dial floating widget.** Use `MapView.getRootGroup()` overlay or `WindowManager.addView` for a floating `RiskDialView` at bottom-right. Custom `Canvas` paints the colored arc and centered text (numeric score + dwell timer).

- [ ] **Step 4.4: Threat circles on map.** For each `PlacedAdversary`, render an ATAK `Circle` (or `Shape`) with center at marker, radius `groundRangeKm` (or `airborneRangeKm` if platform is airborne). Color: `argb(int(P_lock * 153), 255, 0, 0)` — red, alpha proportional to per-asset lock probability. Update on each tick.

- [ ] **Step 4.5: Displace banner.** A `TextView` overlay at top-of-map, hidden until composite score ≥ 0.5. Shows "DISPLACE — risk 0.62." Tap → opens a dialog listing top-3 displacement candidates with predicted risk; tap candidate → call ATAK `RouteMapReceiver.broadcastRoute(...)` (or open `RoutePlannerInterface`) to drop a route from current position to chosen point.

- [ ] **Step 4.6: Tick loop.** A `Handler` posting `riskScorer.update(...)` every 1000 ms (or 100 ms in DEMO 10× mode), pushing results to the dial view.

- [ ] **Step 4.7: Phase-4 acceptance.** Manual end-to-end: configure profile → drop Zhitel marker 8 km east → Start Keying → dial climbs amber → red over ~4 minutes → banner appears → tap → pick candidate → route renders → manually drag operator marker to candidate → Start Keying → dial stays green.

- [ ] **Step 4.8: Commit**

```bash
git commit -m "Phase 4: ATAK setup pane + risk dial overlay + threat circles + displace banner with route handoff"
```

---

## Phase 5 — Demo polish

- [ ] **Step 5.1: `demo_scenarios/rubicon_pokrovsk.json`** — operator at a fictional grid in Donetsk Oblast; 3 pre-placed adversaries: Zhitel @ 8 km east, Borisoglebsk-2 @ 14 km south-east, Leer-3 (airborne) @ 12 km north-east. "Load Demo Scenario" button in setup pane reads the JSON, drops markers + sets operator location.

- [ ] **Step 5.2: 10× time scaler.** `DemoModeFlag` singleton; `RiskScorer` multiplies dwell delta by `flag.scale()`. Watermark `Toast` or persistent `TextView` "DEMO MODE 10×" when on. Long-press the dial to toggle.

- [ ] **Step 5.3: Sound cues.** Two short OGG files in `res/raw/`. `SoundPool` loads at component create. Threshold-crossing detector inside `RiskScorer.update` returns a `CueEvent` enum, dial widget plays it.

- [ ] **Step 5.4: About fragment.** A modal dialog listing OSINT sources from `adversary_df_systems.json` (`source` field), plus the propagation-model citations and a link to the GitHub repo.

- [ ] **Step 5.5: Commit**

```bash
git commit -m "Phase 5: demo scenario + 10x time scaler + sound cues + About"
```

---

## Phase 6 — README + architecture diagram + demo video + submission

- [ ] **Step 6.1: README.md.** Sections: 30-second pitch, problem (Rubicon kill chain, no existing tool), solution, how it works (architecture diagram embed), demo video link, build instructions (everything in this plan, condensed), how to run demo scenario, limitations (no real SDR, OSINT-only adversary data, FSPL fallback when CloudRF unreachable), roadmap (real SDR via HackRF, ML emitter classification, CoT federation, DELTA / Kropyva ports), citations, license.

- [ ] **Step 6.2: Architecture diagram.** Single PNG produced in Excalidraw or similar — five boxes (radio profile + GPS + keying state + adversary library → propagation engine → risk scorer → UI layer with dial/cones/displacement). Embed in README.

- [ ] **Step 6.3: 3-min demo video.** Scripted to brief.

- [ ] **Step 6.4: Submission package.** Zip with signed APK + repo link + README + video + architecture PNG + 1-pager.

- [ ] **Step 6.5: Final commit + tag + GitHub release**

```bash
git tag v1.0.0-hackathon
git push --tags
gh release create v1.0.0-hackathon \
  plugin/app/build/outputs/apk/civ/release/ATAK-Plugin-EmconSentinel-*-civ-release.apk \
  --title "EMCON Sentinel v1.0 (xTech submission)" \
  --notes-file docs/release_notes_v1.0.md
```

---

## Phase 7 — Stretch (only if 4+ hours remaining and core demo bulletproof)

Pick **one**, in priority order:

1. **CoT federation.** `EmconSentinelLifecycle` emits a custom CoT message every 5 s carrying current risk score. Other ATAK instances on the same TAK server (or local UDP multicast) render team icons color-coded by risk.

2. **Offline SPLAT! propagation.** Bundle SPLAT! binaries (Linux x86_64 + ARM64 in `assets/native/`) and one SRTM tile (Donetsk area). New `SplatEngine implements PathLossEngine`. Demo works fully offline.

3. **HackRF live feed.** Python sidecar subscribes to HackRF, publishes detection events over local socket, plugin treats them as confirmed-detected events that bypass the propagation calculation for that band.

---

## Acceptance checklist (before declaring done)

- [ ] All Phase 1–3 unit tests pass: `./gradlew :app:testCivDebugUnitTest`
- [ ] APK builds cleanly: `./gradlew :app:assembleCivDebug` and `:app:assembleCivRelease`
- [ ] APK installs on emulator + dev-ATAK and toolbar button is visible
- [ ] Full demo flow works end-to-end without manual code-poking
- [ ] OSINT-source citations visible in About screen
- [ ] FSPL fallback banner renders when CloudRF API key is missing or down
- [ ] README is judge-readable in under 2 minutes
- [ ] Demo video stays under 3:00
- [ ] LICENSE is Apache-2.0 at the repo root
- [ ] Public GitHub repo URL works for an unauthenticated browser
