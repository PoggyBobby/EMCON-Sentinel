package com.emconsentinel.ui;

import android.graphics.Color;

import com.atakmap.android.maps.MapGroup;
import com.atakmap.android.maps.MapView;
import com.atakmap.coremap.maps.coords.GeoPoint;
import com.atakmap.coremap.maps.coords.GeoPointMetaData;
import com.atakmap.android.drawing.mapItems.DrawingCircle;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.risk.PlacedAdversary;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Per-adversary translucent red circle on the ATAK map. Radius = ground_range_km (or
 * airborne_range_km for airborne platforms). Fill alpha is proportional to the asset's
 * current per-asset lock probability (0..1) so the visual saturation matches risk.
 *
 * Maintains a map keyed by adversary id; updates radii/colors in place rather than
 * recreating circles each tick.
 */
public final class ThreatCircleRenderer {

    private final MapView mapView;
    private final MapGroup group;
    private final Map<String, DrawingCircle> circles = new HashMap<>();

    public ThreatCircleRenderer(MapView mapView) {
        this.mapView = mapView;
        this.group = mapView.getRootGroup();
    }

    public void apply(List<PlacedAdversary> placed, Map<String, Double> perAssetLockProb) {
        // Add or update circles for placed adversaries (skip hidden ones — those
        // are ARGUS-undetected threats that the operator shouldn't see yet)
        java.util.Set<String> seen = new java.util.HashSet<>();
        for (PlacedAdversary p : placed) {
            if (p.hidden) continue;
            if (p.system == null) continue;       // P0: corrupt scenario JSON
            String key = circleKey(p);
            seen.add(key);
            DrawingCircle c = circles.get(key);
            double radiusKm = p.system.platform == AdversarySystem.Platform.AIRBORNE
                    ? p.system.airborneRangeKm : p.system.groundRangeKm;
            double radiusMeters = radiusKm * 1000.0;
            double prob = perAssetLockProb == null ? 0 : perAssetLockProb.getOrDefault(key, 0.0);
            int alpha = (int) Math.min(160, prob * 0.6 * 255);
            int fill = Color.argb(alpha, 255, 30, 30);

            if (c == null) {
                GeoPointMetaData center = GeoPointMetaData.wrap(new GeoPoint(p.lat, p.lon));
                c = new DrawingCircle(mapView, java.util.UUID.randomUUID().toString());
                c.setCenterPoint(center);
                c.setRadius(radiusMeters);
                c.setStrokeColor(0xCCFF1F1F);
                c.setStrokeWeight(2.5);
                c.setFillColor(fill);
                c.setMetaString("shapeName", "EMCON: " + p.system.displayName + " range");
                c.setMetaString("emcon-asset-key", key);
                c.setMetaBoolean("addToObjList", false);
                group.addItem(c);
                circles.put(key, c);
            } else {
                c.setCenterPoint(GeoPointMetaData.wrap(new GeoPoint(p.lat, p.lon)));
                c.setRadius(radiusMeters);
                c.setFillColor(fill);
            }
        }
        // Remove circles for adversaries no longer on the map
        java.util.Iterator<Map.Entry<String, DrawingCircle>> it = circles.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<String, DrawingCircle> e = it.next();
            if (!seen.contains(e.getKey())) {
                group.removeItem(e.getValue());
                it.remove();
            }
        }
    }

    public void clear() {
        for (DrawingCircle c : circles.values()) {
            group.removeItem(c);
        }
        circles.clear();
    }

    private static String circleKey(PlacedAdversary p) {
        return p.system.id + "@" + p.lat + "," + p.lon;
    }
}
