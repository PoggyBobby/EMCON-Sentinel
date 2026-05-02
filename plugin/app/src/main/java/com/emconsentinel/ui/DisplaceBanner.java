package com.emconsentinel.ui;

import android.app.AlertDialog;
import android.content.Context;
import android.graphics.Color;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.widget.FrameLayout;
import android.widget.TextView;

import com.atakmap.android.maps.MapGroup;
import com.atakmap.android.maps.MapView;
import com.atakmap.android.maps.Marker;
import com.atakmap.android.routes.Route;
import com.atakmap.coremap.log.Log;
import com.atakmap.coremap.maps.coords.GeoPoint;
import com.atakmap.coremap.maps.coords.GeoPointMetaData;

import com.emconsentinel.risk.DisplacementCandidate;
import com.emconsentinel.risk.DisplacementSearch;
import com.emconsentinel.risk.PlacedAdversary;

import java.util.List;
import java.util.Locale;
import java.util.UUID;

/**
 * Top-of-map "DISPLACE" prompt that appears when composite risk ≥ threshold.
 * Tap → AlertDialog of top-3 displacement candidates → tap candidate → drops
 * an ATAK Route from current operator position to chosen hide.
 */
public final class DisplaceBanner {

    private static final String TAG = "EmconSentinel.DisplaceBanner";
    private static final double SHOW_THRESHOLD = 0.5;
    private static final double HIDE_THRESHOLD = 0.4;   // hysteresis band

    private final MapView mapView;
    private final Context pluginContext;
    private final PluginState state;
    private final DisplacementSearch search;
    private final TextView banner;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private boolean visible = false;

    public DisplaceBanner(MapView mapView, Context pluginContext,
                          PluginState state, DisplacementSearch search) {
        this.mapView = mapView;
        this.pluginContext = pluginContext;
        this.state = state;
        this.search = search;

        this.banner = new TextView(pluginContext);
        banner.setText("DISPLACE");
        banner.setTextColor(Color.WHITE);
        banner.setBackgroundColor(0xCC900000);
        banner.setGravity(Gravity.CENTER);
        banner.setTextSize(16);
        banner.setPadding(48, 16, 48, 16);
        banner.setOnClickListener(v -> showCandidatePicker());

        float density = pluginContext.getResources().getDisplayMetrics().density;
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT);
        lp.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
        lp.topMargin = (int) (16 * density);

        ui.post(() -> {
            try {
                mapView.addView(banner, lp);
                banner.setVisibility(android.view.View.GONE);
            } catch (Exception e) {
                Log.e(TAG, "failed to attach banner", e);
            }
        });
    }

    public void apply(double currentScore, double opLat, double opLon) {
        if (!visible && currentScore >= SHOW_THRESHOLD) {
            visible = true;
            ui.post(() -> {
                banner.setText(String.format(Locale.US, "DISPLACE — risk %.2f", currentScore));
                banner.setVisibility(android.view.View.VISIBLE);
            });
        } else if (visible && currentScore < HIDE_THRESHOLD) {
            visible = false;
            ui.post(() -> banner.setVisibility(android.view.View.GONE));
        } else if (visible) {
            ui.post(() -> banner.setText(String.format(Locale.US, "DISPLACE — risk %.2f", currentScore)));
        }
    }

    private void showCandidatePicker() {
        if (state.activeProfile() == null) return;
        // Use last known operator position; if dial isn't running yet just bail
        if (state.lastRisk() == null) return;

        // Re-source operator point from map (state has it implicitly via tickLoop)
        Marker self = mapView.getSelfMarker();
        GeoPoint op = (self != null && self.getPoint() != null
                && (self.getPoint().getLatitude() != 0 || self.getPoint().getLongitude() != 0))
                ? self.getPoint()
                : mapView.getCenterPoint().get();

        List<PlacedAdversary> placed = state.placedAdversariesSnapshot();
        List<DisplacementCandidate> top = search.top3(state.lastRisk().displayedScore,
                op.getLatitude(), op.getLongitude(),
                state.activeProfile(), placed);

        if (top.isEmpty()) return;

        String[] labels = new String[top.size()];
        for (int i = 0; i < top.size(); i++) {
            DisplacementCandidate c = top.get(i);
            labels[i] = String.format(Locale.US,
                    "%s %4.0f m → predicted risk %.2f (Δ −%.2f)",
                    compass(c.bearingDeg), c.distanceMeters,
                    c.predictedComposite, c.predictedDelta);
        }

        new AlertDialog.Builder(mapView.getContext())
                .setTitle("Top displacement candidates")
                .setItems(labels, (dialog, which) -> dropRoute(op, top.get(which)))
                .setNegativeButton("Cancel", null)
                .show();
    }

    private void dropRoute(GeoPoint from, DisplacementCandidate to) {
        try {
            Route r = new Route(mapView,
                    "EMCON Displace",
                    Color.WHITE,
                    "DP",
                    UUID.randomUUID().toString());
            Marker[] m = new Marker[2];
            m[0] = Route.createWayPoint(GeoPointMetaData.wrap(from), UUID.randomUUID().toString());
            m[1] = Route.createWayPoint(GeoPointMetaData.wrap(new GeoPoint(to.lat, to.lon)),
                    UUID.randomUUID().toString());
            r.addMarkers(0, m);
            MapGroup routeGroup = mapView.getRootGroup().findMapGroup("Route");
            if (routeGroup == null) routeGroup = mapView.getRootGroup();
            routeGroup.addItem(r);
            r.persist(mapView.getMapEventDispatcher(), null, this.getClass());
            Log.i(TAG, "dropped EMCON Displace route to " + to.lat + "," + to.lon);
        } catch (Exception e) {
            Log.e(TAG, "failed to drop route", e);
        }
    }

    private static String compass(double bearingDeg) {
        String[] c = { "N","NE","E","SE","S","SW","W","NW" };
        int idx = (int) Math.floor(((bearingDeg + 22.5) % 360) / 45.0);
        return c[idx];
    }

    public void detach() {
        ui.post(() -> {
            try {
                mapView.removeView(banner);
            } catch (Exception ignored) {}
        });
    }
}
