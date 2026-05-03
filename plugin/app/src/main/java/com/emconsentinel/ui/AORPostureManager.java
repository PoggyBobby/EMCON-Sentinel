package com.emconsentinel.ui;

import com.atakmap.android.maps.MapView;
import com.atakmap.coremap.log.Log;
import com.atakmap.coremap.maps.coords.GeoPoint;

import com.emconsentinel.data.AORPosture;
import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.AssetLibrary;
import com.emconsentinel.util.Geo;

/**
 * Drops a curated worst-case AOR threat envelope around the operator's current
 * position. Each posture's threats are stored bearing+range relative to the
 * operator (not at fixed lat/lon), so the same posture works wherever the
 * operator is physically standing.
 *
 * Lifecycle: apply(posture) clears existing adversaries via the supplied clear
 * callback, then projects each threat from the operator's GPS using Geo.destination.
 * Sets PluginState.demoOperatorOverride if the operator has no real GPS fix
 * (so the risk loop computes against the correct anchor).
 */
public final class AORPostureManager {

    private static final String TAG = "EmconSentinel.AORPostureManager";

    public interface ClearAndPlace {
        void clear();
        void placeAt(AdversarySystem adv, GeoPoint p);
    }

    private final AssetLibrary library;
    private final PluginState state;
    private final MapView mapView;
    private final ClearAndPlace ops;

    private String currentPostureId = null;

    public AORPostureManager(AssetLibrary library, PluginState state,
                             MapView mapView, ClearAndPlace ops) {
        this.library = library;
        this.state = state;
        this.mapView = mapView;
        this.ops = ops;
    }

    public String currentPostureId() { return currentPostureId; }

    public AORPosture currentPosture() {
        return currentPostureId == null ? null : library.findPostureById(currentPostureId);
    }

    /** Apply a posture by ID. Clears existing adversaries + drops the posture's
     * threat set around the operator's current location. */
    public void apply(String postureId) {
        AORPosture p = library.findPostureById(postureId);
        if (p == null) {
            Log.w(TAG, "unknown posture id: " + postureId);
            return;
        }
        applyPosture(p);
    }

    public void applyPosture(AORPosture p) {
        Log.i(TAG, "applying posture: " + p.name + " (" + p.threats.size() + " threats)");
        ops.clear();

        // Pick anchor: real GPS if we have one, else map center
        double[] anchor = anchorPoint();
        // If no real GPS, also set demo operator override so risk loop uses this point
        if (!hasRealGps()) {
            state.setDemoOperator(anchor[0], anchor[1]);
        }

        int placed = 0;
        for (AORPosture.RelativeThreat t : p.threats) {
            AdversarySystem adv = findSystemById(t.systemId);
            if (adv == null) {
                Log.w(TAG, "posture references unknown system_id: " + t.systemId);
                continue;
            }
            double[] dest = Geo.destination(anchor[0], anchor[1], t.bearingDeg, t.rangeKm);
            ops.placeAt(adv, new GeoPoint(dest[0], dest[1]));
            placed++;
        }
        currentPostureId = p.id;
        Log.i(TAG, "posture applied: " + placed + " threats placed around (" + anchor[0] + ", " + anchor[1] + ")");
    }

    private boolean hasRealGps() {
        if (mapView.getSelfMarker() == null) return false;
        GeoPoint sp = mapView.getSelfMarker().getPoint();
        if (sp == null) return false;
        return sp.getLatitude() != 0.0 || sp.getLongitude() != 0.0;
    }

    private double[] anchorPoint() {
        if (hasRealGps()) {
            GeoPoint sp = mapView.getSelfMarker().getPoint();
            return new double[] { sp.getLatitude(), sp.getLongitude() };
        }
        GeoPoint c = mapView.getCenterPoint().get();
        return new double[] { c.getLatitude(), c.getLongitude() };
    }

    private AdversarySystem findSystemById(String id) {
        for (AdversarySystem s : library.adversarySystems()) {
            if (s.id.equals(id)) return s;
        }
        return null;
    }
}
