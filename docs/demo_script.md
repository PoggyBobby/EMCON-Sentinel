# EMCON Sentinel — 3-minute demo script

Target: **3:00 max**. Land the problem, show the solution working end-to-end, close with the gap nobody else fills.

## 0:00 – 0:30  · The problem

> *Open with the news clip OR a card.*

**Voice-over:**
> Russian counter-drone units like Rubicon hunt Ukrainian drone operators by direction-finding their RF emissions. Sensor-to-shooter cycles are under two minutes. The single greatest predictor of an operator's death is **how long they keyed in one place** — not skill, not platform, not enemy. Pure dwell time on a band the adversary covers.
>
> Today, no tool on an operator's tablet tells them when their accumulated keying time has made them locatable. Every adjacent product — DroneShield, Anduril Pulsar, CRFS RFeye, CloudRF SOOTHSAYER — looks at **the enemy's** emissions or models **friendly** coverage. None closes the loop on the friendly operator's own behavioral risk.

## 0:30 – 1:00  · The setup

> *Cut to ATAK on the tablet. Empty map view, EMCON Sentinel toolbar button visible.*

**Voice-over:**
> EMCON Sentinel is a free, open-source ATAK plugin. Pick your radio profile — say, FPV with a TBS Crossfire 2.4 GHz controller and a 5.8 GHz video downlink.

> *Click the radio profile spinner, choose FPV+Crossfire.*

> Drop your adversary DF assets on the map. The library has Zhitel, Borisoglebsk-2, Pole-21, Shipovnik-Aero, and Leer-3 / Orlan-10 — every parameter cited to public OSINT, no classified data anywhere.

> *Click "Load Demo Scenario" — three red markers and three translucent circles bloom on the map (Pokrovsk axis).*

## 1:00 – 2:00  · The keying climb

> *Long-press the dial. "DEMO MODE 10×" yellow watermark appears.*

**Voice-over:**
> I'm running this in 10× time compression so you can see four minutes of dwell-time risk in 25 seconds. The math is real — every per-asset detection probability is a sigmoid on the link-budget margin in dB; the lock probability over time is one minus the exponential of negative dwell over time-to-fix. The composite is one minus the product of one-minus-each-lock. Five-second moving average for display so it doesn't flicker.

> *Tap START KEYING. The big green button turns red. Dial starts climbing.*

> Watch the threat circles. The Zhitel 8 km east is closest, lowest sensitivity margin — its alpha deepens first. The Leer-3 airborne goniometer has the shortest time-to-fix at 45 seconds, so it crosses 50% lock probability fastest. The dial composite climbs through amber...

> *Soft chime as it crosses 0.3.*

> ...and into red.

> *Sharper double-beep at 0.7. Banner appears: "DISPLACE — risk 0.74".*

## 2:00 – 2:30  · The save

**Voice-over:**
> The banner appears at top-of-map the moment risk crosses 0.5. One tap.

> *Tap the DISPLACE banner. AlertDialog appears: top-3 candidates with predicted risk reduction.*

> EMCON Sentinel sampled 24 candidate hides — eight bearings, three ranges of 200, 400, 800 meters — and predicts what your composite risk would be 30 seconds after a stop-keying-and-move. These are the three best.

> *Tap the top candidate. ATAK Route engine drops a route from current position to the chosen hide.*

> The ATAK route engine drops the path. I move the operator marker.

> *Manually drag operator marker to the candidate. Tap START KEYING.*

> Re-key. Dial stays green.

## 2:30 – 3:00  · Why this matters

**Voice-over:**
> This category — operator-side behavioral EMCON awareness — is currently empty. DARPA's SMART solicitation calls it out by name. There is no commercial product. No DOD program of record. No open-source tool until today.
>
> Every component is open and Apache-2.0. The plugin loads against the public DoD ATAK-CIV SDK; no TAK.gov account required. The OSINT adversary library is one JSON file — anyone can extend it. The propagation backend is CloudRF SOOTHSAYER with a free-space fallback for offline robustness.
>
> Path to operators: ATAK plugin catalog, civtak.org, Brave1. We can be in Ukrainian operator hands by the end of next week.
>
> EMCON Sentinel. The fuel gauge for emissions you didn't know you needed.

> *End card: github.com/<org>/emcon-sentinel, Apache-2.0, EAR99.*

---

## Notes for recording

- **Pre-record the dial climb** if the laptop screen recorder lags — 10× demo mode plus a 30 fps capture is fine.
- **The "I refuse" button on EULA shouldn't be on screen** — pre-accept on the device before the take.
- **Sound: keep both threshold beeps** — they're load-bearing for the climb visualization.
- **The route render** is the visual punchline. Make sure ATAK is actually showing the route polyline before cutting, not just the dialog dismissal.
- **Don't mention Argus** or any related project name. Clean room.
