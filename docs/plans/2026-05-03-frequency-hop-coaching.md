# Frequency-Hop Coaching Implementation Plan

> Authored 2026-05-03 by the Plan agent. Ready to execute task-by-task.

**Goal:** When the operator's currently-active radio band is the dominant detection contributor, surface a "💡 Quieter: try only 5.8 GHz video band — drops risk 32%" recommendation so they can disable the noisier band of their current multi-band radio without leaving the FOB or swapping radios.

**Architecture:** Pure-Java analytical layer (`HopCoach`) computes per-band P_lock contributions per tick using the existing LinkBudget machinery, identifies the dominant band, searches for a sibling-band-disabled subset of the *same* radio that yields ≥30% lower P_lock, and emits a `HopRecommendation`. State held in `PluginState` as `Map<String, Set<Integer>>` of disabled band indices keyed by `RadioProfile.id`. UI surfaces are (1) a small chip in `TopHudStrip` (sub-line area), (2) a one-shot `Toast` on first appearance per dominant-band identity, and (3) per-band on/off toggles inside `TabOperate` under a new "Active bands" panel.

**Tech Stack:** Java 17, AGP 4.2.2, ATAK-CIV SDK 4.6.0.5, JUnit 4. Existing `FreeSpaceEngine`. Existing `Toast`/`TextView`/`CheckBox` for UI.

---

## File structure

**New files:**
- `risk/BandContribution.java` — POJO `{int bandIndex; double pLockContribution; RadioBand band;}`.
- `risk/HopRecommendation.java` — POJO with dominant band, bandsToDisable list, currentCompositeOnly, recommendedCompositeOnly, riskDeltaFraction, oneLiner.
- `risk/HopCoach.java` — Pure-Java engine. `compute(profile, disabledIdx, op, placed, dwellSec)` → `HopRecommendation` or `null`.
- `risk/HopCoachTest.java` — Unit tests (no Android, runs under `./gradlew :app:test`).
- `ui/HopCoachChip.java` — Wraps a `TextView` chip pinned just below `TopHudStrip`.
- `res/layout/hop_coach_chip.xml` — Layout (semi-transparent dark pill, 12sp, dismiss "×").
- `res/layout/band_toggle_row.xml` — Per-band row with title, contribution %, Switch.

**Modified files:**
- `ui/PluginState.java` — Add `disabledBandsByProfileId` map plus accessors and `effectiveProfile(RadioProfile)` helper. Also `setLastHopRecommendation` / `lastHopRecommendation`.
- `ui/RiskTickLoop.java` — Build effective drone profile (active bands only), run `HopCoach.compute(...)` each tick when `riskMode == ACTIVE`.
- `ui/TabOperate.java` — New "Active bands" section with on/off Switch per band + per-band P_lock contribution %.
- `res/layout/tab_operate.xml` — Add `LinearLayout` "Active bands" panel.
- `EmconSentinelMapComponent.java` — Construct `HopCoachChip`, wire chip-tap → Operate tab + amber-flash highlight.

## Implementation-acknowledgement model

We do **not** use C2 telemetry to confirm operator disabled a band. Decision: **explicit ack via Operate tab Switch.** Chip tap → jump to Operate, amber-flash the suggested band's switch for 2s, operator flips switch = ack. Same trust model as the manual keying button.

## Phase ordering

```
Phase 1 (data + math: HopCoach + tests, JVM-only, ~5 min)
  └→ Phase 2 (state: PluginState disabled-bands)
       └→ Phase 3 (tick loop: build effective profile, run HopCoach, store result)
            ├→ Phase 4 (chip UI)
            └→ Phase 5 (tab UI: per-band toggles)
                 └→ Phase 6 (wire-up + Toast on first-show + integration)
                      └→ Phase 7 (manual emulator verification)
```

---

## Phase 1 — Math: HopCoach (Tasks 1-5)

### Task 1: BandContribution POJO

```java
package com.emconsentinel.risk;
import com.emconsentinel.data.RadioBand;
public final class BandContribution {
    public final int bandIndex;
    public final RadioBand band;
    public final double pLockContribution;
    public BandContribution(int bandIndex, RadioBand band, double pLockContribution) {
        this.bandIndex = bandIndex;
        this.band = band;
        this.pLockContribution = pLockContribution;
    }
}
```

### Task 2: HopRecommendation POJO

```java
package com.emconsentinel.risk;
import com.emconsentinel.data.RadioBand;
import java.util.Collections;
import java.util.List;
public final class HopRecommendation {
    public final RadioBand dominantBand;
    public final List<Integer> bandsToDisable;
    public final double currentCompositeOnly;
    public final double recommendedCompositeOnly;
    public final double riskDeltaFraction;
    public final String oneLiner;
    public HopRecommendation(RadioBand dominantBand, List<Integer> bandsToDisable,
                             double currentCompositeOnly, double recommendedCompositeOnly,
                             double riskDeltaFraction, String oneLiner) {
        this.dominantBand = dominantBand;
        this.bandsToDisable = Collections.unmodifiableList(bandsToDisable);
        this.currentCompositeOnly = currentCompositeOnly;
        this.recommendedCompositeOnly = recommendedCompositeOnly;
        this.riskDeltaFraction = riskDeltaFraction;
        this.oneLiner = oneLiner;
    }
}
```

### Tasks 3-4: HopCoach skeleton + dominant-band detection

Full implementation: see agent transcript for the complete `compute()` method that builds active-band index set, computes composite, attributes per-band by removing one band at a time, picks the band with maximum drop, applies the ≥30% threshold, and formats the one-liner naming the surviving (kept) band.

Key constants:
```java
public static final double MIN_REDUCTION_FRACTION = 0.30;
```

Tests cover:
- Empty placement → null recommendation
- Video band dominance → recommendation disabling video
- Single-band radio → no recommendation
- Balanced bands (twins) → no recommendation
- Already-disabled band excluded from attribution
- One-liner names surviving band correctly

## Phase 2 — State: per-band disabled tracking (Task 6)

In `PluginState.java`:

```java
private final Map<String, Set<Integer>> disabledBandsByProfileId = new HashMap<>();

public synchronized Set<Integer> disabledBandIndices(RadioProfile profile) {
    if (profile == null) return Collections.emptySet();
    Set<Integer> s = disabledBandsByProfileId.get(profile.id);
    return s == null ? Collections.<Integer>emptySet() : new LinkedHashSet<>(s);
}

public synchronized boolean isBandDisabled(RadioProfile profile, int idx) { ... }
public synchronized void setBandDisabled(RadioProfile profile, int idx, boolean disabled) { ... }

public synchronized RadioProfile effectiveProfile(RadioProfile profile) {
    // Returns subset profile with disabled bands removed, or null if all disabled.
}

private HopRecommendation lastHopRecommendation;
public synchronized HopRecommendation lastHopRecommendation() { return lastHopRecommendation; }
public synchronized void setLastHopRecommendation(HopRecommendation r) { this.lastHopRecommendation = r; }
```

## Phase 3 — Tick loop integration (Task 7)

Modify `RiskTickLoop.java`:
- Add `HopCoach hopCoach` field + constructor parameter
- Add `setHopChip(HopCoachChip)` setter
- In `doTick()`:
  - Compute `droneEffective = state.effectiveProfile(state.activeProfile())` (band-filtered)
  - Use `droneEffective` everywhere we previously used `state.activeProfile()`
  - After `RiskScorer.update`, run `hopCoach.compute(state.activeProfile(), state.disabledBandIndices(...), ...)` — uses the AS-CONFIGURED profile, not effective, so the recommendation reflects the radio not the post-disable state
  - Push to `state.setLastHopRecommendation` and `hopChip.apply`

In `EmconSentinelMapComponent.java`:
```java
HopCoach hopCoach = new HopCoach(prop);
tickLoop = new RiskTickLoop(view, state, scorer, prop, hud, threatCircles, displaceModal, sounds, cotEmitter, hopCoach);
```

## Phase 4 — Chip UI (Tasks 8-9)

`hop_coach_chip.xml`: horizontal LinearLayout, semi-transparent dark, 12sp text + dismiss "×" button.

`HopCoachChip.java`: attaches to activity content frame at top|center_horizontal with topMargin=44dp (40dp HUD + 4dp gap). `apply(rec)` shows/hides + toasts on new dominant band. `lastDismissedFreqMhz` tracks dismiss-per-dominant-band so the chip stays gone until the dominant band changes.

## Phase 5 — Tab UI: per-band toggles (Tasks 10-12)

`band_toggle_row.xml`: horizontal LinearLayout, title + contribution % + Switch.

In `tab_operate.xml`, add "Active bands" section after status label, before C2 telemetry section.

In `TabOperate.java`:
- New `LinearLayout bandsContainer` field
- `renderBands()` method called from `refreshTick`. Re-renders only on profile-id change. Always re-syncs Switch states. Updates contribution labels from `state.lastHopRecommendation()`.
- `highlightBand(int)` public method — chip taps call this to amber-flash a row for 2s.

## Phase 6 — Wire up chip → tab (Tasks 13-14)

In `EmconSentinelMapComponent.onCreate`:
```java
hopChip = new HopCoachChip(context, view, () -> {
    HopRecommendation rec = state.lastHopRecommendation();
    if (bottomSheet != null) {
        bottomSheet.expand();
        bottomSheet.selectTab(BottomSheetController.Tab.OPERATE);
    }
    if (rec != null && tabOperate != null && !rec.bandsToDisable.isEmpty()) {
        tabOperate.highlightBand(rec.bandsToDisable.get(0));
    }
});
tickLoop.setHopChip(hopChip);
```

Update `refreshHudContext()` to append `· N bands off` when bands are disabled.

In `onDestroyImpl`: `if (hopChip != null) hopChip.detach(view);`

## Phase 7 — Manual verification (Task 15)

Verify on demo scenario `centcom_drone.json` with DJI Mavic 3 (2.4 + 5.8 GHz):
- Chip appears within ~30s with ≥30% reduction one-liner
- Tap chip → bottom sheet expands → OPERATE tab → amber-flash dominant band row
- Toggle off → HUD shows `· 1 band off`, dial drops, chip disappears
- × dismiss persists until dominant band identity changes
- Single-band radio (Silvus mesh) → chip never appears

## Self-review checklist

- [ ] HopCoach.MIN_REDUCTION_FRACTION = 0.30
- [ ] Disabled bands keyed by RadioProfile.id (persists within session)
- [ ] Phone bands NOT user-toggleable (out of scope)
- [ ] PASSIVE risk mode does NOT trigger HopCoach (only when droneKeying)
- [ ] HopCoach uses AS-CONFIGURED profile (not post-disable effective)
- [ ] RiskScorer untouched — tick loop builds effective profile externally
- [ ] Chip suppresses Toast re-pop for same dominant band; reappears on new dominant
- [ ] HopRecommendation.bandsToDisable is a List (supports multi-band suggestions later — single-band now per YAGNI)
