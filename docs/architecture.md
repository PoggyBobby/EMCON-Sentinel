# EMCON Sentinel — architecture

Three views: a polished mermaid diagram (renders on GitHub), an ASCII text view (works in any viewer), and a per-tick data-flow trace.

## System view (mermaid)

```mermaid
flowchart LR
    subgraph TABLET["Operator's Android tablet (ATAK 4.6 CIV)"]
        direction TB
        subgraph PLUGIN["EMCON Sentinel — com.emconsentinel.plugin"]
            direction TB
            subgraph DATA["Data layer"]
                AdvJson["adversary_df_systems.json<br/>9 OSINT-cited DF systems"]
                ProfJson["radio_profiles.json<br/>9 operator radio presets"]
                DemoJson["demo_scenarios/*.json<br/>Pokrovsk axis preset"]
            end
            subgraph PROP["Propagation engine"]
                CloudRF["CloudRfEngine<br/>(terrain-aware HTTP)"]
                FSPL["FreeSpaceEngine<br/>(Friis, no terrain)"]
                LB["LinkBudget<br/>sigmoid(margin, k=0.2)<br/>per-band detection"]
                CloudRF -->|fail-3x circuit breaker| FSPL
                FSPL --> LB
                CloudRF --> LB
            end
            subgraph RISK["Risk scorer"]
                Dwell["DwellClock<br/>50 m radius gate<br/>10x demo scaler"]
                Scorer["RiskScorer<br/>P_lock_i = P_detect × (1 − e^(−t/τ))<br/>composite = 1 − Π(1 − P_lock_i)"]
                Smooth["MovingAverage<br/>5-second window"]
                Disp["DisplacementSearch<br/>8 bearings × 3 ranges"]
                Dwell --> Scorer
                Scorer --> Smooth
            end
            subgraph UI["UI layer"]
                DropDown["DropDownReceiver<br/>setup pane"]
                Dial["RiskDialView<br/>(Canvas overlay)"]
                Circles["ThreatCircleRenderer<br/>(per-asset, alpha=P_lock×0.6)"]
                Banner["DisplaceBanner<br/>(top of map, ≥0.5)"]
                Sound["SoundCues<br/>(amber/red beeps)"]
            end
            DATA --> RISK
            DATA --> PROP
            PROP --> RISK
            RISK --> UI
            Disp --> Banner
        end
        ATAK["ATAK MapView + Route engine + GPS"]
        UI <--> ATAK
    end

    CloudRFAPI["api.cloudrf.com/path/<br/>(terrain SRTM-backed)"]
    CloudRF -.HTTPS POST.- CloudRFAPI

    style PLUGIN fill:#1a1a2e,stroke:#ffce3a,color:#fff
    style ATAK fill:#15161b,stroke:#888,color:#fff
    style CloudRFAPI fill:#15161b,stroke:#666,color:#bbb
```

## Single-page ASCII (works in any viewer)

```
                       ┌────────────────────────────────────────┐
                       │            Operator's tablet            │
                       │              (Android, ATAK)            │
                       └────────────────────────────────────────┘
                                          │
        ┌─────────────────────────────────┼─────────────────────────────────┐
        │                                 │                                 │
        ▼                                 ▼                                 ▼
┌───────────────┐               ┌───────────────────┐              ┌────────────────┐
│  Inputs       │               │  EMCON Sentinel   │              │  Outputs        │
│  (ATAK gives) │               │      Plugin        │              │  (UI overlays)  │
├───────────────┤               ├───────────────────┤              ├────────────────┤
│ Operator GPS  │  ───────────► │  Data Layer       │              │ Risk Dial      │
│ (selfMarker)  │               │  • adversary lib  │              │ (bottom right) │
│               │               │  • radio profiles │              │                │
│ Map taps      │  ───────────► │  • demo scenarios │              │ Threat Circles │
│ (MAP_CLICK)   │               │                   │              │ (per-asset,    │
│               │               │  Risk Layer       │              │  alpha=P_lock) │
│ Map view      │  ───────────► │  • DwellClock     │ ──────────►  │                │
│ + items       │               │    (50m radius)   │              │ Displace       │
│               │               │  • RiskScorer     │              │ Banner         │
│               │               │    (composite)    │              │ (top, ≥0.5)    │
│               │               │  • 5s smoothing   │              │                │
│               │               │  • Displacement   │              │ Route to       │
│               │               │    Search         │              │ chosen hide    │
│               │               │    (8×3 sample)   │              │ (ATAK Route    │
│               │               │                   │              │  engine)       │
│               │               │  Propagation      │              │                │
│               │               │  • CloudRF API    │ ── HTTPS ──► │ Sound cues     │
│               │               │  • FSPL fallback  │              │ (amber, red)   │
│               │               │  • sigmoid LB     │              │                │
└───────────────┘               └───────────────────┘              └────────────────┘
                                          │
                                          ▼
                              ┌─────────────────────┐
                              │  Optional external  │
                              │   CloudRF API       │
                              │  (terrain-aware     │
                              │   path loss)        │
                              │                     │
                              │  Falls back to FSPL │
                              │  on any failure or  │
                              │  empty API key.     │
                              └─────────────────────┘
```

## Per-tick data flow (1 Hz, 10 Hz under DEMO 10×)

```
         RiskTickLoop.doTick()
                │
                ▼
        Source operator GPS
        (selfMarker → mapView center fallback)
                │
                ▼
        DwellClock.update(now, lat, lon, isKeying)
        ─ accumulates dwell while in-radius + keying
        ─ resets on movement-out or stop-keying
                │
                ▼
        For each PlacedAdversary:
        ┌────────────────────────────────────────────────┐
        │ For each band the radio profile transmits on   │
        │ ─ if adversary covers that band:               │
        │     PathLossEngine.pathLoss(op, adv, freq)     │
        │     → CloudRF (terrain) or FSPL (free-space)   │
        │     LinkBudget.bandDetectionProb               │
        │     → sigmoid(margin_dB) × dutyCycle           │
        │ ─ take max P_detect across overlapping bands   │
        │ ─ P_lock_i = P_detect × (1 − exp(−t/τ_i))      │
        └────────────────────────────────────────────────┘
                │
                ▼
        composite = 1 − Π(1 − P_lock_i)
        smoothed  = MovingAverage(5s).push(composite)
                │
                ▼
        Pushes update to:
        ─ RiskDialView          (numeric + ring color + dwell)
        ─ ThreatCircleRenderer  (per-asset alpha = P_lock × 0.6)
        ─ DisplaceBanner        (visible when smoothed ≥ 0.5)
        ─ SoundCues             (chime on amber/red crossings)
```

## Key invariants

- **All math is pure Java with zero ATAK dependencies.** `data/`, `prop/`, `risk/`, `util/` packages are unit-testable on the laptop without an emulator. 45 JUnit tests, 100% green.
- **The propagation backend is swappable.** `PathLossEngine` is a one-method interface. `FreeSpaceEngine` is the offline-safe default. `CloudRfEngine` is a thin OkHttp/Gson wrapper with a circuit breaker that drops back to FSPL after 3 consecutive failures.
- **State is single-source-of-truth.** `PluginState` (in `ui/`) owns the live mutable state — active radio profile, placed adversaries, keying flag, demo flag, last RiskUpdate. Both the DropDownReceiver (UI thread) and the RiskTickLoop (main Handler) read/write through synchronized accessors.
- **The dial is a custom Canvas View.** No external view dependencies. Attached to the ATAK MapView via `mapView.addView(dial, FrameLayout.LayoutParams)` with bottom-right gravity.
- **Routes go through ATAK's native engine.** `Route.persist(mapEventDispatcher, null, this.getClass())` — no custom route renderer; the operator gets the same UX they get for any ATAK route.
