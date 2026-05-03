package com.emconsentinel.ui;

import com.emconsentinel.c2.C2Status;
import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.AssetLibrary;
import com.emconsentinel.data.RadioBand;
import com.emconsentinel.data.RadioProfile;
import com.emconsentinel.risk.HopRecommendation;
import com.emconsentinel.risk.PlacedAdversary;
import com.emconsentinel.risk.RiskUpdate;

import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

/**
 * Mutable, single-source-of-truth state container for the live plugin session.
 * Held by EmconSentinelMapComponent. Both the DropDownReceiver (UI) and the tick loop
 * read/write through this instance.
 *
 * No threading model enforced here — callers (UI thread for setters, tick loop on the
 * UI Handler) hand off via Handler.post when they need to invalidate views.
 */
public final class PluginState {

    /** Which emitter set produced the dial number — for the HUD context line. */
    public enum RiskMode { IDLE, PASSIVE, ACTIVE }

    private final AssetLibrary library;
    private final List<PlacedAdversary> placed = new ArrayList<>();
    private RiskMode riskMode = RiskMode.IDLE;
    public synchronized RiskMode riskMode() { return riskMode; }
    public synchronized void setRiskMode(RiskMode m) { this.riskMode = m; }

    private RadioProfile activeProfile;
    private AdversarySystem pendingAdversaryToPlace; // when set, next map-tap places this
    private boolean isKeying = false;
    private boolean demoMode10x = false;
    private RiskUpdate lastRisk;

    // Demo operator override: when a scenario is loaded, the operator should be
    // positioned at the scenario's operator coords (not the device's real GPS,
    // which is wherever the demo is being run). Cleared on clearPlaced().
    private double demoOperatorLat = Double.NaN;
    private double demoOperatorLon = Double.NaN;

    // Phase 7 — operator identity for CoT broadcasts
    private final String operatorUid;
    private String operatorCallsign = "EMCON-1";

    // C2 telemetry-link integration
    private C2Status c2Status = C2Status.disconnected();
    private boolean useC2ForKeying = false;     // when true, isKeying is driven by C2

    public PluginState(AssetLibrary library) {
        this.library = library;
        if (!library.radioProfiles().isEmpty()) {
            this.activeProfile = library.radioProfiles().get(0);
        }
        this.operatorUid = "EMCON-Operator-" + UUID.randomUUID().toString().substring(0, 8);
    }

    public AssetLibrary library() { return library; }

    public synchronized RadioProfile activeProfile() { return activeProfile; }
    public synchronized void setActiveProfile(RadioProfile p) { this.activeProfile = p; }

    public synchronized List<PlacedAdversary> placedAdversariesSnapshot() {
        return new ArrayList<>(placed);
    }
    public synchronized void addPlaced(PlacedAdversary p) { placed.add(p); }
    public synchronized void clearPlaced() {
        placed.clear();
        demoOperatorLat = Double.NaN;
        demoOperatorLon = Double.NaN;
    }

    public synchronized boolean hasDemoOperatorOverride() {
        return !Double.isNaN(demoOperatorLat) && !Double.isNaN(demoOperatorLon);
    }
    public synchronized double demoOperatorLat() { return demoOperatorLat; }
    public synchronized double demoOperatorLon() { return demoOperatorLon; }
    public synchronized void setDemoOperator(double lat, double lon) {
        this.demoOperatorLat = lat;
        this.demoOperatorLon = lon;
    }
    public synchronized int placedCount() { return placed.size(); }

    public synchronized AdversarySystem pendingPlacement() { return pendingAdversaryToPlace; }
    public synchronized void setPendingPlacement(AdversarySystem a) { this.pendingAdversaryToPlace = a; }
    public synchronized AdversarySystem consumePendingPlacement() {
        AdversarySystem a = pendingAdversaryToPlace;
        pendingAdversaryToPlace = null;
        return a;
    }

    public synchronized boolean isKeying() {
        // SDR override beats everything — if the RTL-SDR sidecar saw real RF
        // energy at the operator's drone band, that's ground truth, not a guess.
        if (sdrConfirmedKeying) return true;
        // C2 link is next-best — when MAVLink RADIO_STATUS shows TX, that's real
        // for the operator's chosen radio.
        if (useC2ForKeying && c2Status != null && c2Status.connected) {
            return c2Status.isTransmittingNow;
        }
        return isKeying;
    }
    public synchronized void setKeying(boolean keying) { this.isKeying = keying; }

    public synchronized boolean isDemoMode10x() { return demoMode10x; }
    public synchronized void setDemoMode10x(boolean v) { this.demoMode10x = v; }

    public synchronized RiskUpdate lastRisk() { return lastRisk; }
    public synchronized void setLastRisk(RiskUpdate u) { this.lastRisk = u; }

    public String operatorUid() { return operatorUid; }
    public synchronized String operatorCallsign() { return operatorCallsign; }
    public synchronized void setOperatorCallsign(String c) { this.operatorCallsign = c; }

    public synchronized C2Status c2Status() { return c2Status; }
    public synchronized void setC2Status(C2Status s) { this.c2Status = s; }

    public synchronized boolean useC2ForKeying() { return useC2ForKeying; }
    public synchronized void setUseC2ForKeying(boolean v) { this.useC2ForKeying = v; }

    // SDR (RTL-SDR sidecar) state — true real-RF observations from tools/sdr_bridge.py.
    private boolean sdrPresent = false;
    private boolean sdrConfirmedKeying = false;
    private boolean sdrAdversaryEwActive = false;
    private String  sdrAdversaryEwLabel = "";
    private double  sdrAdversaryEwFreqMhz = 0;
    private double  sdrAdversaryEwPowerDbm = 0;

    public synchronized boolean sdrPresent() { return sdrPresent; }
    public synchronized void setSdrPresent(boolean v) {
        this.sdrPresent = v;
        // P1 audit fix: when SDR drops, also clear any cached own-TX confirmation
        // so isKeying() doesn't report ACTIVE forever from a stale detection.
        if (!v) {
            this.sdrConfirmedKeying = false;
            this.sdrAdversaryEwActive = false;
        }
    }
    public synchronized boolean sdrConfirmedKeying() { return sdrConfirmedKeying; }
    public synchronized void setSdrConfirmedKeying(boolean v) { this.sdrConfirmedKeying = v; }
    public synchronized boolean sdrAdversaryEwActive() { return sdrAdversaryEwActive; }
    public synchronized String  sdrAdversaryEwLabel() { return sdrAdversaryEwLabel; }
    public synchronized double  sdrAdversaryEwFreqMhz() { return sdrAdversaryEwFreqMhz; }
    public synchronized double  sdrAdversaryEwPowerDbm() { return sdrAdversaryEwPowerDbm; }
    public synchronized void setSdrAdversaryEwActive(boolean active, String label,
                                                      double freqMhz, double powerDbm) {
        this.sdrAdversaryEwActive = active;
        this.sdrAdversaryEwLabel = label == null ? "" : label;
        this.sdrAdversaryEwFreqMhz = freqMhz;
        this.sdrAdversaryEwPowerDbm = powerDbm;
    }

    // Per-radio-profile set of band indices the operator has manually disabled
    // (e.g. "video downlink off"). effectiveProfile() excludes them from the
    // risk computation. Keyed by RadioProfile.id so toggles persist across
    // active-radio swaps within a session.
    private final Map<String, Set<Integer>> disabledBandsByProfileId = new HashMap<>();

    public synchronized Set<Integer> disabledBandIndices(RadioProfile profile) {
        if (profile == null) return Collections.emptySet();
        Set<Integer> s = disabledBandsByProfileId.get(profile.id);
        return s == null ? Collections.<Integer>emptySet() : new LinkedHashSet<>(s);
    }

    public synchronized boolean isBandDisabled(RadioProfile profile, int idx) {
        if (profile == null) return false;
        Set<Integer> s = disabledBandsByProfileId.get(profile.id);
        return s != null && s.contains(idx);
    }

    public synchronized void setBandDisabled(RadioProfile profile, int idx, boolean disabled) {
        if (profile == null) return;
        Set<Integer> s = disabledBandsByProfileId.get(profile.id);
        if (s == null) {
            s = new LinkedHashSet<>();
            disabledBandsByProfileId.put(profile.id, s);
        }
        if (disabled) s.add(idx);
        else          s.remove(Integer.valueOf(idx));
    }

    /** Returns subset profile with disabled bands removed; null if all disabled. */
    public synchronized RadioProfile effectiveProfile(RadioProfile profile) {
        if (profile == null) return null;
        Set<Integer> disabled = disabledBandsByProfileId.get(profile.id);
        if (disabled == null || disabled.isEmpty()) return profile;
        java.util.List<RadioBand> kept = new ArrayList<>();
        for (int i = 0; i < profile.bands.size(); i++) {
            if (!disabled.contains(i)) kept.add(profile.bands.get(i));
        }
        if (kept.isEmpty()) return null;
        return new RadioProfile(profile.id + "+filtered", profile.displayName, kept);
    }

    private HopRecommendation lastHopRecommendation;
    public synchronized HopRecommendation lastHopRecommendation() { return lastHopRecommendation; }
    public synchronized void setLastHopRecommendation(HopRecommendation r) { this.lastHopRecommendation = r; }

    // Phone-side emitters (cellular, WiFi, BT) observed from Android system services.
    // Always added to the operator's effective emitter set in the risk computation,
    // because these radios emit from the operator's location whether they intend
    // it or not — DF assets get bearings on them.
    private List<RadioBand> phoneEmitters = Collections.emptyList();
    public synchronized List<RadioBand> phoneEmittersSnapshot() {
        return new ArrayList<>(phoneEmitters);
    }
    public synchronized void setPhoneEmitters(List<RadioBand> bands) {
        this.phoneEmitters = bands == null ? Collections.<RadioBand>emptyList() : new ArrayList<>(bands);
    }
}
