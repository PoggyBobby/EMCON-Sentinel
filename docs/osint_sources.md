# OSINT sources for EMCON Sentinel adversary library

Every numeric parameter in `plugin/app/src/main/assets/adversary_df_systems.json` traces to one or more public sources. Nothing classified, nothing FOUO, nothing ITAR-restricted. EAR99 throughout.

| System | Frequency range | Sensitivity | Antenna gain | Range | τ (time-to-fix) | Sources |
|---|---|---|---|---|---|---|
| **R-330Zh Zhitel** | 100–2000 MHz | −110 dBm | 12 dBi | 25 km ground / 50 km air | 90 s | Sprotyv G7 *Russian EW Systems Analytic Insight Report* (Nov 2023); CSIS Russia EW capability briefs |
| **Borisoglebsk-2 (RB-301B)** | 30–3000 MHz | −107 dBm | 10 dBi | 30 km ground / 60 km air | 120 s | Sprotyv G7 (Nov 2023); RUSI Russian EW assessments |
| **Pole-21** | 1000–2500 MHz | −100 dBm | 8 dBi | 15 km ground / 30 km air | 60 s | Sprotyv G7 (Nov 2023); open Russian milblogger reporting (Telegram, 2024) |
| **Shipovnik-Aero** | 100–6000 MHz | −115 dBm | 14 dBi | 10 km ground / 20 km air | 75 s | Sprotyv G7 (Nov 2023); Russian EW capability open-source reporting |
| **Leer-3 (Orlan-10 RB-341V)** | 800–2500 MHz | −95 dBm | 6 dBi | 6 km ground / 25 km air | 45 s | Sprotyv G7 (Nov 2023); Conflict Armament Research Orlan-10 teardown (2022) |
| **Krasukha-4 (1RL257)** | 8–18 GHz | −118 dBm | 18 dBi | 50 km ground / 250 km air | 60 s | Sprotyv G7 (Nov 2023); CSIS Russian EW capability briefs |
| **Murmansk-BN** | 3–30 MHz (HF) | −120 dBm | 16 dBi | 100 km ground / 300 km air | 180 s | Sprotyv G7 (Nov 2023); RUSI assessments — strategic HF DF |
| **Torn-MDM** | 1.5–3000 MHz | −108 dBm | 9 dBi | 30 km ground / 60 km air | 70 s | Sprotyv G7 (Nov 2023); manpack tactical SIGINT/DF, widely deployed in Donbas 2022–2024 |
| **RB-636 Svet-KU** | 100–8000 MHz | −110 dBm | 11 dBi | 20 km ground / 40 km air | 80 s | Sprotyv G7 (Nov 2023); open Russian MoD trade-show photos and brochures |

### People's Republic of China (INDOPACOM)

| System | Frequency range | Sensitivity | Antenna gain | Range | τ | Sources |
|---|---|---|---|---|---|---|
| **DWL-002 Passive Surveillance** | 100–3000 MHz | −120 dBm | 16 dBi | 60 km ground / 400 km air | 90 s | CSIS China Military Watch (2022–2024); Janes Land Warfare; CETC (NRIET) brochures. Multi-static passive coherent location, claimed ~400 km against airborne emitters. |
| **CHL-906 Tactical DF** | 100–3000 MHz | −107 dBm | 10 dBi | 25 km ground / 50 km air | 75 s | Janes Land Warfare Platforms; PLA Strategic Support Force open-source order-of-battle assessments. Vehicle-mounted tactical DF analogous to Borisoglebsk. |

### Islamic Republic of Iran (CENTCOM)

| System | Frequency range | Sensitivity | Antenna gain | Range | τ | Sources |
|---|---|---|---|---|---|---|
| **Iranian COMINT vehicle** (templated) | 30–3000 MHz | −105 dBm | 9 dBi | 20 km ground / 40 km air | 100 s | RUSI 2023 IRGC EW assessments; specific identifications limited; templated to peer-vehicular profile. |

### Generic peer threat templates

For when you suspect a class of threat in the AO but lack a specific identification. Conservative middle-of-the-pack values. Use these to model what you don't know.

| System | Frequency range | Sensitivity | Antenna gain | Range | τ | Use case |
|---|---|---|---|---|---|---|
| **Generic peer vehicular wide-band DF** | 30–6000 MHz | −108 dBm | 11 dBi | 25 km ground / 50 km air | 90 s | Templated Borisoglebsk-class vehicular SIGINT/DF. |
| **Generic man-portable HF/VHF DF** | 1.5–500 MHz | −100 dBm | 6 dBi | 15 km ground / 30 km air | 150 s | 4-person SIGINT team with backpack DF receiver. Modest sensitivity, slow time-to-fix; can position in unconventional locations (rooftops, observation posts). |
| **Generic airborne SIGINT pod** | 30–18000 MHz | −118 dBm | 12 dBi | 10 km ground / 200 km air | 30 s | Pod on an ISR platform (Tu-214R, Y-9JB, Saegheh-derived UAS). Long airborne LoS reach; fast time-to-fix on a single airborne pass. |

All values are **conservative first-order estimates** suitable for an EMCON awareness aid. They are deliberately not ground-truth performance specifications. If you have access to better-cited public numbers (a specific Sprotyv update, a CSIS report number, a RUSI dataset version), open a PR and replace the entry.

## Primary references

- **Sprotyv G7** — *Russian EW Systems Analytic Insight Report*, November 2023. The single best public catalog of Russian ground-based and tactical EW assets.
- **CSIS** (Center for Strategic and International Studies) — multiple briefs on Russian electronic-warfare capability and posture.
- **RUSI** (Royal United Services Institute) — periodic Russian EW assessments, especially their Eastern-Front operational reporting.
- **Conflict Armament Research** — Orlan-10 teardown (2022) gave us concrete RB-341V Leer-3 sensitivity bounds.
- **Telegram milblogger channels** (open) — reporting on Russian EW deployment patterns, particularly for Pole-21 and Shipovnik-Aero in the Kursk and Donetsk axes through 2024.

## Radio profile sources

`radio_profiles.json` EIRP and duty-cycle estimates come from public datasheets:

- **DJI Mavic 3** — DJI public OcuSync 3+ specs
- **Skydio X10** — Skydio public datasheet
- **TBS Crossfire** — TBS public product specs (LongRange RC)
- **Silvus SC4240** — Silvus public mesh radio datasheet
- **HIMERA G1 Pro** — Himera public product specs (Ukrainian-developed encrypted comms)
- **Generic Wi-Fi GCS** — IEEE 802.11 specs (laptop-class PA)
- **Autel EVO Max 4T** — Autel public datasheet (OcuSync-class link)
- **Parrot Anafi USA** — Parrot public datasheet
- **Rajant Breadcrumb** — Rajant public mesh radio datasheet (sub-GHz + 2.4 GHz dual-band)

## What we DO NOT use

- No classified data (any level)
- No FOUO / CUI material
- No ITAR-restricted technical data
- No proprietary vendor information that wasn't part of a public datasheet or marketing release
- No data from any government program

If a contributor wants to add an entry sourced from anything in the above list, **don't**. Open an issue first describing the public source and we can decide whether it qualifies.
