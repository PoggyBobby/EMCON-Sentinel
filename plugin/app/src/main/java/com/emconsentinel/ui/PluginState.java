package com.emconsentinel.ui;

import com.emconsentinel.c2.C2Status;
import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.AssetLibrary;
import com.emconsentinel.data.RadioProfile;
import com.emconsentinel.risk.PlacedAdversary;
import com.emconsentinel.risk.RiskUpdate;

import java.util.ArrayList;
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

    private final AssetLibrary library;
    private final List<PlacedAdversary> placed = new ArrayList<>();

    private RadioProfile activeProfile;
    private AdversarySystem pendingAdversaryToPlace; // when set, next map-tap places this
    private boolean isKeying = false;
    private boolean demoMode10x = false;
    private RiskUpdate lastRisk;

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
    public synchronized void clearPlaced() { placed.clear(); }
    public synchronized int placedCount() { return placed.size(); }

    public synchronized AdversarySystem pendingPlacement() { return pendingAdversaryToPlace; }
    public synchronized void setPendingPlacement(AdversarySystem a) { this.pendingAdversaryToPlace = a; }
    public synchronized AdversarySystem consumePendingPlacement() {
        AdversarySystem a = pendingAdversaryToPlace;
        pendingAdversaryToPlace = null;
        return a;
    }

    public synchronized boolean isKeying() {
        // If C2 link is being used as the truth source, override the manual toggle.
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
}
