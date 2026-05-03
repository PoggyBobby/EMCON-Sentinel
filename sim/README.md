# EMCON Sentinel — browser simulator

A self-contained HTML+JS port of the EMCON Sentinel ATAK plugin. Runs in any modern browser. No build step, no install.

## Open it

```bash
open ~/Desktop/EmconSentinel/sim/index.html      # macOS
xdg-open sim/index.html                          # Linux
start sim/index.html                             # Windows
```

Or double-click the file in Finder/Explorer.

Or serve it: `cd sim && python3 -m http.server 8000` → http://localhost:8000

## What it does

Identical math, identical OSINT adversary library, identical UI behavior to the ATAK plugin — just in a browser instead of on a tablet:

- **Real OpenStreetMap** background (Leaflet)
- **Risk dial** (color-coded ring, numeric score, dwell timer, top-threat indicator)
- **Threat circles** (per-adversary, alpha = per-asset lock probability × 0.6)
- **Displace banner** (top-of-map at risk ≥ 0.5)
- **Top-3 candidate picker** with route line drop on selection
- **Sound cues** (Web Audio oscillator) at amber/red threshold crossings
- **DEMO MODE 10×** (long-press the dial)

## Demo flow

1. Tap **Load demo scenario** — Pokrovsk-axis fictional grid loads with three adversaries
2. **Long-press the dial** in bottom-right — yellow `DEMO MODE 10×` watermark appears
3. Tap **START KEYING**
4. Watch dial: green → amber (chime) → red (double beep) over ~25 s
5. **DISPLACE — risk 0.7x** banner appears at top → tap → pick a candidate → route line drops to chosen hide
6. Drag the operator marker (yellow dot) onto the candidate, tap **START KEYING** again — dial stays green

## Differences vs. the ATAK plugin

| Aspect | Browser sim | ATAK plugin |
|---|---|---|
| Math | Identical | Identical |
| OSINT data | Identical | Identical |
| Map | Leaflet + OSM tiles | ATAK MapView |
| Path loss | Free-space only | CloudRF (terrain) + FSPL fallback |
| Route handoff | Simple polyline overlay | ATAK Route engine (real navigation) |
| Sound | Web Audio sine waves | Android ToneGenerator beeps |
| Operator GPS | Drag the yellow marker | Real device GPS |

## Why a browser sim?

- **No device required** — judges, teammates, you can all run the sim in any browser today.
- **Recording is trivial** — screen capture → MP4 → submission video.
- **Math validation in the wild** — anyone can verify the dial behavior without setting up Android tooling.
- **Zero deployment** — drop `index.html` on any web server (or open via `file://`) and it works.

The sim is intentionally faithful to the plugin so the demo flow translates 1:1 when running on a real Android tablet.
