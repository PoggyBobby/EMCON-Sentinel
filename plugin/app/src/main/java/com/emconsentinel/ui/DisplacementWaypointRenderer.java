package com.emconsentinel.ui;

import com.atakmap.android.maps.MapGroup;
import com.atakmap.android.maps.MapView;
import com.atakmap.android.maps.Marker;
import com.atakmap.coremap.log.Log;
import com.atakmap.coremap.maps.coords.GeoPoint;

import com.emconsentinel.risk.DisplacementCandidate;
import com.emconsentinel.risk.DisplacementSearch;
import com.emconsentinel.risk.PlacedAdversary;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Drops up to 3 GREEN "go here" markers on the map showing the operator's
 * top displacement candidates whenever risk crosses CAUTION (≥ 0.3). Updates
 * each tick so the waypoints follow risk geometry as it changes. Removes them
 * when risk drops back to safe.
 *
 * Reuses the same DisplacementSearch.top3 math as the MOVE NOW modal — these
 * markers are just the proactive "where to go" version of the same recommendation.
 */
public final class DisplacementWaypointRenderer {

    private static final String TAG = "EmconSentinel.DispWaypoint";
    private static final double SHOW_THRESHOLD = 0.2;     // show early — 20% lock prob is meaningful
    private static final double HIDE_THRESHOLD = 0.15;    // hysteresis

    private final MapView mapView;
    private final MapGroup group;
    private final DisplacementSearch search;
    /** Markers keyed by index so we can update in place rather than re-create. */
    private final Map<Integer, Marker> markers = new HashMap<>();
    private boolean visible = false;

    public DisplacementWaypointRenderer(MapView mapView, DisplacementSearch search) {
        this.mapView = mapView;
        this.group = mapView.getRootGroup();
        this.search = search;
    }

    /** Called every tick from RiskTickLoop. */
    public void apply(double currentScore, double opLat, double opLon,
                      RiskTickLoopState st, List<PlacedAdversary> placed) {
        // Hysteresis: hide below 0.25, show at 0.3+
        if (visible && currentScore < HIDE_THRESHOLD) {
            clear();
            visible = false;
            return;
        }
        if (currentScore < SHOW_THRESHOLD) return;
        if (st.activeProfile == null) return;

        List<DisplacementCandidate> top = search.top3(currentScore, opLat, opLon,
                st.activeProfile, placed);
        if (top == null || top.isEmpty()) {
            clear();
            visible = false;
            return;
        }

        visible = true;
        java.util.Set<Integer> seen = new java.util.HashSet<>();
        for (int i = 0; i < top.size(); i++) {
            DisplacementCandidate c = top.get(i);
            seen.add(i);
            Marker m = markers.get(i);
            GeoPoint p = new GeoPoint(c.lat, c.lon);
            String label = String.format(java.util.Locale.US,
                    "→ Safer: risk %.2f (%s %.0fm)",
                    c.predictedComposite, compass(c.bearingDeg), c.distanceMeters);
            if (m == null) {
                m = new Marker(p, UUID.randomUUID().toString());
                m.setTitle(label);
                m.setMetaString("emcon-displace-waypoint", "true");
                m.setMetaInteger("emcon-displace-rank", i);
                m.setColor(0xFF2ECC40);                  // green
                m.setAlwaysShowText(true);
                m.setType("a-f-G");                      // friendly ground
                group.addItem(m);
                markers.put(i, m);
            } else {
                m.setPoint(p);
                m.setTitle(label);
            }
        }
        // Remove any stale markers (fewer candidates than last tick)
        java.util.Iterator<Map.Entry<Integer, Marker>> it = markers.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<Integer, Marker> e = it.next();
            if (!seen.contains(e.getKey())) {
                group.removeItem(e.getValue());
                it.remove();
            }
        }
    }

    public void clear() {
        for (Marker m : markers.values()) {
            try { group.removeItem(m); } catch (Exception ignored) {}
        }
        markers.clear();
    }

    private static String compass(double bearingDeg) {
        String[] c = { "N","NE","E","SE","S","SW","W","NW" };
        int idx = (int) Math.floor(((bearingDeg + 22.5) % 360) / 45.0);
        return c[idx];
    }

    /** Tiny adapter so we can pass just what the renderer needs without leaking PluginState. */
    public static final class RiskTickLoopState {
        public final com.emconsentinel.data.RadioProfile activeProfile;
        public RiskTickLoopState(com.emconsentinel.data.RadioProfile activeProfile) {
            this.activeProfile = activeProfile;
        }
    }
}
