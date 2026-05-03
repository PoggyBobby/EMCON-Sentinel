package com.emconsentinel.ui;

import android.os.Handler;
import android.os.Looper;

import com.atakmap.android.maps.MapView;
import com.atakmap.android.maps.Marker;
import com.atakmap.coremap.maps.coords.GeoPoint;

import com.emconsentinel.cot.CotEmitter;
import com.emconsentinel.cot.CotEvent;
import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.RadioBand;
import com.emconsentinel.data.RadioProfile;
import com.emconsentinel.prop.LinkBudget;
import com.emconsentinel.prop.PathLossEngine;
import com.emconsentinel.prop.PropagationResult;
import com.emconsentinel.risk.HopCoach;
import com.emconsentinel.risk.HopRecommendation;
import com.emconsentinel.risk.PlacedAdversary;
import com.emconsentinel.risk.RiskScorer;
import com.emconsentinel.risk.RiskUpdate;
import com.emconsentinel.util.Geo;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 1-Hz Handler-driven loop. Each tick:
 *   1. Sources operator GPS (mapView.getSelfMarker().getPoint(); falls back to map center).
 *   2. Calls RiskScorer.update with current PluginState (profile, placed, keying).
 *   3. Pushes the resulting RiskUpdate to the dial view + threat-circle renderer.
 *
 * Period is reduced to 100 ms when demo mode is on (10x time scaler is in DwellClock,
 * but UI feels smoother with faster ticks). Otherwise 1000 ms.
 */
public final class RiskTickLoop {

    private final MapView mapView;
    private final PluginState state;
    private final RiskScorer scorer;
    private final PathLossEngine prop;
    private final TopHudStrip hud;
    private final ThreatCircleRenderer circles;
    private final DisplaceModalController displaceModal;
    private com.emconsentinel.ui.DisplacementWaypointRenderer waypoints;
    public void setWaypointRenderer(com.emconsentinel.ui.DisplacementWaypointRenderer w) { this.waypoints = w; }
    private final SoundCues sounds;
    private final CotEmitter cotEmitter;            // null if CoT init failed (no network)
    private final HopCoach hopCoach;                // pure-Java; never null
    private HopCoachChip hopChip;                   // optional, set via setter
    public void setHopChip(HopCoachChip chip) { this.hopChip = chip; }
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final AtomicBoolean running = new AtomicBoolean(false);
    private long lastCotEmitMs = 0;
    private static final long COT_PERIOD_MS = 5000;

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (!running.get()) return;
            doTick();
            long period = state.isDemoMode10x() ? 100L : 1000L;
            handler.postDelayed(this, period);
        }
    };

    public RiskTickLoop(MapView mapView, PluginState state, RiskScorer scorer,
                        PathLossEngine prop, TopHudStrip hud,
                        ThreatCircleRenderer circles, DisplaceModalController displaceModal,
                        SoundCues sounds, CotEmitter cotEmitter) {
        this.mapView = mapView;
        this.state = state;
        this.scorer = scorer;
        this.prop = prop;
        this.hud = hud;
        this.circles = circles;
        this.displaceModal = displaceModal;
        this.sounds = sounds;
        this.cotEmitter = cotEmitter;
        this.hopCoach = new HopCoach(prop);
        scorer.dwellClock().setTimeScale(state.isDemoMode10x() ? 10.0 : 1.0);
    }

    public void start() {
        if (running.compareAndSet(false, true)) {
            handler.post(tick);
        }
    }

    public void stop() {
        running.set(false);
        handler.removeCallbacks(tick);
    }

    private void doTick() {
        scorer.dwellClock().setTimeScale(state.isDemoMode10x() ? 10.0 : 1.0);

        GeoPoint op = currentOperatorPoint();
        if (op == null) {
            hud.setRisk(0, 0, "No GPS fix yet", "", state.isDemoMode10x());
            return;
        }

        List<PlacedAdversary> placed = state.placedAdversariesSnapshot();
        long now = System.currentTimeMillis();

        // Three modes:
        //   ACTIVE  — operator is keying their drone radio. Risk = phone bands
        //             + drone bands. Highest signature.
        //   PASSIVE — not keying, but phone radios always emit. Risk = phone bands
        //             only. Lower but non-zero — your phone alone CAN get you DF'd.
        //   IDLE    — no phone bands either (airplane mode). Risk = 0.
        //
        // The dial used to read 0% whenever isKeying was false, which was
        // misleading: the phone is itself a high-EIRP emitter at the operator
        // location and never stops. That's exactly the risk operators ignore
        // until it kills them. Always-on now.
        boolean droneKeying = state.isKeying();
        List<RadioBand> phoneBands = state.phoneEmittersSnapshot();
        boolean phoneEmitting = !phoneBands.isEmpty();

        // Apply per-band disable toggles. effectiveProfile() returns null if
        // every band of the active radio is disabled.
        RadioProfile droneEffective = state.effectiveProfile(state.activeProfile());

        RadioProfile effectiveProfile;
        boolean effectiveKeying;
        if (droneKeying && droneEffective != null) {
            // ACTIVE: drone radio (band-filtered) + phone bands
            effectiveProfile = mergePhoneBands(droneEffective, phoneBands);
            effectiveKeying = true;
        } else if (phoneEmitting) {
            // PASSIVE: phone bands only, but force isKeying=true so RiskScorer
            // computes (the underlying check just gates whether emissions are
            // contributing — phones always do)
            effectiveProfile = new RadioProfile("phone-only-passive",
                    "Phone radios (passive)", phoneBands);
            effectiveKeying = true;
        } else {
            // IDLE: nothing emitting
            effectiveProfile = state.activeProfile();
            effectiveKeying = false;
        }

        RiskUpdate update = scorer.update(now, op.getLatitude(), op.getLongitude(),
                effectiveKeying, effectiveProfile, placed);
        state.setLastRisk(update);
        // Track which mode produced the displayed score so the HUD can label it.
        state.setRiskMode(droneKeying ? PluginState.RiskMode.ACTIVE
                : phoneEmitting ? PluginState.RiskMode.PASSIVE
                : PluginState.RiskMode.IDLE);

        // Hop coaching — only meaningful in ACTIVE mode (operator can't toggle
        // phone radios). Compute against the AS-CONFIGURED profile, not the
        // post-disable effectiveProfile, so the recommendation reflects the
        // radio's full band list — the dominant-band identity is stable across
        // disable/enable toggles.
        HopRecommendation hop = null;
        if (droneKeying && state.activeProfile() != null) {
            hop = hopCoach.compute(state.activeProfile(),
                    state.disabledBandIndices(state.activeProfile()),
                    op.getLatitude(), op.getLongitude(),
                    placed, update.dwellSeconds);
        }
        state.setLastHopRecommendation(hop);
        if (hopChip != null) hopChip.apply(hop);

        // Per-asset lock probs for circle renderer. Use effectiveProfile (which
        // includes phone bands) so circles fill in PASSIVE mode too — otherwise
        // the dial reads 30% but the circles look empty, which makes the visual
        // story inconsistent.
        Map<String, Double> perAssetLockProb = new HashMap<>();
        if (effectiveKeying && effectiveProfile != null) {
            double t = update.dwellSeconds;
            for (PlacedAdversary p : placed) {
                if (p.hidden) continue;
                if (p.system == null) continue;
                AdversarySystem adv = p.system;
                LinkBudget.Result detect = LinkBudget.assetDetection(adv, effectiveProfile,
                        op.getLatitude(), op.getLongitude(), p.lat, p.lon, prop);
                double tau = Math.max(1, adv.timeToFixSeconds);
                double pLock = detect.prob * (1.0 - Math.exp(-t / tau));
                perAssetLockProb.put(p.system.id + "@" + p.lat + "," + p.lon, pLock);
            }
        }
        circles.apply(placed, perAssetLockProb);

        String topThreatLine = "";
        if (update.topThreatId != null) {
            topThreatLine = String.format("Top: %s (%.1f km %s)", update.topThreatDisplayName,
                    update.topThreatRangeKm, compass(update.topThreatBearingDeg));
        }
        String propModeLine = update.propagationMode == PropagationResult.Mode.FREE_SPACE
                ? "FREE-SPACE FALLBACK — TERRAIN NOT MODELED"
                : "";

        // Mode-aware context line — operator must immediately see whether the
        // dial number reflects active drone keying or just passive phone leakage.
        String modePrefix;
        switch (state.riskMode()) {
            case ACTIVE:  modePrefix = "ACTIVE"; break;
            case PASSIVE: modePrefix = "PASSIVE — phone only"; break;
            default:      modePrefix = "IDLE"; break;
        }
        hud.setContext(modePrefix + (state.activeProfile() != null
                ? "  ·  " + state.activeProfile().displayName : ""));

        hud.setRisk(update.displayedScore, update.dwellSeconds, topThreatLine, propModeLine,
                state.isDemoMode10x());

        if (displaceModal != null) {
            displaceModal.apply(update.displayedScore, op.getLatitude(), op.getLongitude());
        }
        if (waypoints != null) {
            waypoints.apply(update.displayedScore, op.getLatitude(), op.getLongitude(),
                    new com.emconsentinel.ui.DisplacementWaypointRenderer.RiskTickLoopState(
                            state.activeProfile()),
                    placed);
        }
        if (sounds != null) {
            sounds.onScore(update.displayedScore);
        }
        // Phase 7 — federate composite risk over CoT every 5 s. Other ATAK clients
        // on the same SA mesh (multicast 239.2.3.1:6969) see this operator as a
        // friendly ground unit AND can color-code by the <emcon score> child.
        if (cotEmitter != null && (now - lastCotEmitMs) >= COT_PERIOD_MS) {
            String topId = update.topThreatId;
            CotEvent ev = new CotEvent(
                    state.operatorUid(), state.operatorCallsign(),
                    now, /*staleSeconds=*/30,
                    op.getLatitude(), op.getLongitude(),
                    update.displayedScore, update.dwellSeconds,
                    topId, update.topThreatRangeKm, update.topThreatBearingDeg);
            cotEmitter.emit(ev);
            lastCotEmitMs = now;
        }
    }

    /** Combine the operator's chosen radio bands with the phone-emitter bands. */
    private static RadioProfile mergePhoneBands(RadioProfile base, List<RadioBand> phoneBands) {
        if (base == null) {
            return phoneBands == null || phoneBands.isEmpty() ? null
                    : new RadioProfile("merged-phone-only", "Phone radios", phoneBands);
        }
        if (phoneBands == null || phoneBands.isEmpty()) return base;
        List<RadioBand> merged = new ArrayList<>(base.bands.size() + phoneBands.size());
        merged.addAll(base.bands);
        merged.addAll(phoneBands);
        return new RadioProfile(base.id + "+phone", base.displayName + " + phone radios", merged);
    }

    private GeoPoint currentOperatorPoint() {
        // Demo override beats real GPS — when a scenario is loaded the operator
        // is supposed to be standing at the scenario's named position, not at
        // wherever the demo physically takes place.
        if (state.hasDemoOperatorOverride()) {
            return new GeoPoint(state.demoOperatorLat(), state.demoOperatorLon());
        }
        Marker self = mapView.getSelfMarker();
        if (self != null && self.getPoint() != null) {
            GeoPoint p = self.getPoint();
            // self marker can sit at (0,0) when there's no GPS fix; treat that as missing
            if (p.getLatitude() != 0.0 || p.getLongitude() != 0.0) return p;
        }
        // Fallback: map center (lets operator demo without a real GPS fix)
        return mapView.getCenterPoint().get();
    }

    private static String compass(double bearingDeg) {
        String[] c = { "N","NE","E","SE","S","SW","W","NW" };
        int idx = (int) Math.floor(((bearingDeg + 22.5) % 360) / 45.0);
        return c[idx];
    }
}
