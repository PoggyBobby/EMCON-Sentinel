package com.emconsentinel.argus;

import com.atakmap.android.drawing.mapItems.DrawingCircle;
import com.atakmap.android.maps.MapGroup;
import com.atakmap.android.maps.MapView;
import com.atakmap.android.maps.Marker;
import com.atakmap.coremap.maps.coords.GeoPoint;
import com.atakmap.coremap.maps.coords.GeoPointMetaData;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Draws each ArgusDrone as a friendly-air ATAK marker plus a faint blue circle
 * showing its scan footprint. Updates positions in place each tick instead of
 * recreating markers — keeps the map smooth.
 */
public final class ArgusFleetRenderer {

    private final MapView mapView;
    private final MapGroup group;
    private final Map<String, Marker> markers = new HashMap<>();
    private final Map<String, DrawingCircle> circles = new HashMap<>();

    public ArgusFleetRenderer(MapView mapView) {
        this.mapView = mapView;
        this.group = mapView.getRootGroup();
    }

    public void apply(List<ArgusDrone> drones) {
        java.util.Set<String> seen = new java.util.HashSet<>();
        for (ArgusDrone d : drones) {
            seen.add(d.id);
            GeoPoint pt = new GeoPoint(d.lat(), d.lon());

            Marker m = markers.get(d.id);
            if (m == null) {
                m = new Marker(pt, UUID.randomUUID().toString());
                m.setTitle(d.callsign);
                m.setType("a-f-A-M-F-Q");      // friendly air, manned, fixed-wing, recon (Q)
                m.setMetaString("emcon-argus-id", d.id);
                m.setAlwaysShowText(true);
                m.setColor(0xFF66CCFF);
                m.setMetaString("callsign", d.callsign);
                group.addItem(m);
                markers.put(d.id, m);
            } else {
                m.setPoint(pt);
            }

            DrawingCircle c = circles.get(d.id);
            if (c == null) {
                c = new DrawingCircle(mapView, UUID.randomUUID().toString());
                c.setCenterPoint(GeoPointMetaData.wrap(pt));
                c.setRadius(d.scanRadiusKm * 1000.0);
                c.setStrokeColor(0x6666CCFF);
                c.setStrokeWeight(1.5);
                c.setFillColor(0x1166CCFF);     // very faint blue
                c.setMetaString("shapeName", d.callsign + " scan");
                c.setMetaString("emcon-argus-id", d.id);
                c.setMetaBoolean("addToObjList", false);
                group.addItem(c);
                circles.put(d.id, c);
            } else {
                c.setCenterPoint(GeoPointMetaData.wrap(pt));
            }
        }
        // Remove markers/circles for drones that aren't in the fleet anymore
        java.util.Iterator<Map.Entry<String, Marker>> mit = markers.entrySet().iterator();
        while (mit.hasNext()) {
            Map.Entry<String, Marker> e = mit.next();
            if (!seen.contains(e.getKey())) {
                group.removeItem(e.getValue());
                mit.remove();
            }
        }
        java.util.Iterator<Map.Entry<String, DrawingCircle>> cit = circles.entrySet().iterator();
        while (cit.hasNext()) {
            Map.Entry<String, DrawingCircle> e = cit.next();
            if (!seen.contains(e.getKey())) {
                group.removeItem(e.getValue());
                cit.remove();
            }
        }
    }

    public void clear() {
        for (Marker m : markers.values()) group.removeItem(m);
        for (DrawingCircle c : circles.values()) group.removeItem(c);
        markers.clear();
        circles.clear();
    }
}
