package com.emconsentinel.ui;

import com.atakmap.android.maps.MapEvent;
import com.atakmap.android.maps.MapEventDispatcher;
import com.atakmap.android.maps.MapView;
import com.atakmap.android.maps.Marker;
import com.atakmap.coremap.log.Log;
import com.atakmap.coremap.maps.coords.GeoPoint;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.risk.PlacedAdversary;

import java.util.UUID;

/**
 * Subscribes to MAP_CLICK on the ATAK MapView and, when a placement is pending in
 * PluginState, drops a Marker at the tapped lat/lon and records a PlacedAdversary.
 * No-op when there's no pending placement (so user can interact with the map normally).
 */
public final class AdversaryPlacer {

    private static final String TAG = "EmconSentinel.AdversaryPlacer";

    private final MapView mapView;
    private final PluginState state;
    private final MapEventDispatcher.MapEventDispatchListener listener;

    public AdversaryPlacer(MapView mapView, PluginState state) {
        this.mapView = mapView;
        this.state = state;
        this.listener = new MapEventDispatcher.MapEventDispatchListener() {
            @Override public void onMapEvent(MapEvent event) {
                AdversarySystem pending = state.consumePendingPlacement();
                if (pending == null) return;
                GeoPoint p = event.getPoint() == null ? null : null;
                // MapEvent for MAP_CLICK doesn't carry GeoPoint directly — pull from pixel via inverse
                android.graphics.PointF pt = event.getPointF();
                if (pt == null) {
                    Log.w(TAG, "MAP_CLICK event has no PointF — cannot place");
                    return;
                }
                GeoPoint geo = mapView.inverse(pt.x, pt.y).get();
                placeAt(pending, geo);
            }
        };
    }

    public void register() {
        mapView.getMapEventDispatcher().addMapEventListener(MapEvent.MAP_CLICK, listener);
    }

    public void unregister() {
        mapView.getMapEventDispatcher().removeMapEventListener(MapEvent.MAP_CLICK, listener);
    }

    public void placeAt(AdversarySystem adv, GeoPoint geo) {
        Marker marker = new Marker(geo, UUID.randomUUID().toString());
        marker.setTitle("EMCON: " + adv.displayName);
        marker.setMetaString("emcon-adversary-id", adv.id);
        marker.setMetaString("emcon-platform", adv.platform.name());
        marker.setColor(0xFFFF1F1F);
        marker.setAlwaysShowText(true);
        marker.setType(adv.platform == AdversarySystem.Platform.AIRBORNE
                ? "a-h-A" : "a-h-G");
        mapView.getRootGroup().addItem(marker);
        state.addPlaced(new PlacedAdversary(adv, geo.getLatitude(), geo.getLongitude()));
        Log.i(TAG, "placed " + adv.id + " at " + geo.getLatitude() + ", " + geo.getLongitude());
    }
}
