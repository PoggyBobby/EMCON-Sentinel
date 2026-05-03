package com.emconsentinel.ui;

import android.widget.Toast;

import com.atakmap.android.maps.MapView;
import com.atakmap.coremap.log.Log;

import com.emconsentinel.cot.BuddyReport;
import com.emconsentinel.risk.PlacedAdversary;
import com.emconsentinel.util.Geo;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.function.Consumer;

/**
 * When another operator on the CoT mesh goes red against a threat we also have
 * placed within 10 km of THAT operator AND that operator is within 25 km of US,
 * surface a toast: "BUDDY {callsign} RED at {threat} — you are {Xkm} from same".
 *
 * Debounces per (buddyUid, threatId) for 60 s so a buddy stuck red doesn't
 * flood the operator with toasts every 5 s.
 *
 * Minimal version: toast only. Marker flashing + sound chirp are roadmap polish.
 */
public final class BuddyAlertController implements Consumer<BuddyReport> {

    private static final String TAG = "EmconSentinel.BuddyAlert";
    private static final double RED_THRESHOLD = 0.7;
    private static final double BUDDY_LOCALITY_KM = 25.0;
    private static final double SAME_THREAT_RADIUS_KM = 10.0;
    private static final long DEBOUNCE_MS = 60_000;

    private final MapView mapView;
    private final PluginState state;
    /** Last alert timestamp keyed by (buddyUid + "|" + threatId). */
    private final Map<String, Long> lastAlertMs = new HashMap<>();

    public BuddyAlertController(MapView mapView, PluginState state) {
        this.mapView = mapView;
        this.state = state;
    }

    @Override
    public void accept(BuddyReport report) {
        if (report.score < RED_THRESHOLD) return;
        if (report.topThreatId == null || report.topThreatId.isEmpty()) return;

        // Locality gate: buddy must be near us
        double[] op = currentOpPoint();
        double buddyDistKm = Geo.distanceKm(op[0], op[1], report.lat, report.lon);
        if (buddyDistKm > BUDDY_LOCALITY_KM) return;

        // Same-threat correlation: do we have an adversary with this id within
        // SAME_THREAT_RADIUS_KM of buddy AND within reasonable range of us?
        PlacedAdversary matchingThreat = null;
        double matchingDistFromOp = Double.MAX_VALUE;
        for (PlacedAdversary p : state.placedAdversariesSnapshot()) {
            if (p.hidden) continue;
            if (!report.topThreatId.equals(p.system.id)) continue;
            double distFromBuddy = Geo.distanceKm(report.lat, report.lon, p.lat, p.lon);
            if (distFromBuddy > SAME_THREAT_RADIUS_KM) continue;
            double distFromOp = Geo.distanceKm(op[0], op[1], p.lat, p.lon);
            if (distFromOp < matchingDistFromOp) {
                matchingThreat = p;
                matchingDistFromOp = distFromOp;
            }
        }
        if (matchingThreat == null) return;

        // Debounce
        String key = report.uid + "|" + report.topThreatId;
        long now = System.currentTimeMillis();
        Long last = lastAlertMs.get(key);
        if (last != null && (now - last) < DEBOUNCE_MS) return;
        lastAlertMs.put(key, now);

        String msg = String.format(Locale.US,
                "⚠ BUDDY %s RED at %s — you are %.1f km from same threat",
                report.callsign, matchingThreat.system.displayName, matchingDistFromOp);
        Log.i(TAG, "buddy alert: " + msg);
        try {
            Toast.makeText(mapView.getContext(), msg, Toast.LENGTH_LONG).show();
        } catch (Exception ignored) {}
    }

    private double[] currentOpPoint() {
        if (state.hasDemoOperatorOverride()) {
            return new double[] { state.demoOperatorLat(), state.demoOperatorLon() };
        }
        if (mapView.getSelfMarker() != null && mapView.getSelfMarker().getPoint() != null) {
            com.atakmap.coremap.maps.coords.GeoPoint sp = mapView.getSelfMarker().getPoint();
            if (sp.getLatitude() != 0 || sp.getLongitude() != 0) {
                return new double[] { sp.getLatitude(), sp.getLongitude() };
            }
        }
        com.atakmap.coremap.maps.coords.GeoPoint c = mapView.getCenterPoint().get();
        return new double[] { c.getLatitude(), c.getLongitude() };
    }
}
