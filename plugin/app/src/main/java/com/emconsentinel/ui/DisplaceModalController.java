package com.emconsentinel.ui;

import android.content.Context;
import android.graphics.Color;
import android.os.Handler;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.atak.plugins.impl.PluginLayoutInflater;
import com.atakmap.android.maps.MapGroup;
import com.atakmap.android.maps.MapView;
import com.atakmap.android.maps.Marker;
import com.atakmap.android.routes.Route;
import com.atakmap.coremap.log.Log;
import com.atakmap.coremap.maps.coords.GeoPoint;
import com.atakmap.coremap.maps.coords.GeoPointMetaData;

import com.emconsentinel.plugin.R;
import com.emconsentinel.risk.DisplacementCandidate;
import com.emconsentinel.risk.DisplacementSearch;
import com.emconsentinel.risk.PlacedAdversary;

import java.util.List;
import java.util.Locale;
import java.util.UUID;

/**
 * Phone-native replacement for DisplaceBanner. Instead of a small "DISPLACE"
 * text band at the top of the map, this slides up a full-screen modal with
 * the current threat level, top-3 candidates, and a tap-to-route action.
 *
 * Uses vibrate + sound on first appearance for unmissable alerting.
 */
public final class DisplaceModalController {

    private static final String TAG = "EmconSentinel.DisplaceModal";
    private static final double SHOW_THRESHOLD = 0.5;
    private static final double HIDE_THRESHOLD = 0.4;   // hysteresis

    private final Context pluginContext;
    private final MapView mapView;
    private final PluginState state;
    private final DisplacementSearch search;
    private final SoundCues sounds;
    private final Vibrator vibrator;
    private final Handler ui = new Handler(Looper.getMainLooper());

    private View modalRoot;
    private boolean visible = false;
    private android.widget.FrameLayout attachParent;

    // Hysteresis-aware dismissal: once the user accepts risk / cancels, do NOT
    // re-show until risk drops below HIDE_THRESHOLD AND climbs back above
    // SHOW_THRESHOLD. Otherwise the modal would re-pop on every tick because
    // currentScore stays ≥0.5 right after dismiss.
    private boolean userDismissedThisCycle = false;

    public DisplaceModalController(Context pluginContext, MapView mapView,
                                   PluginState state, DisplacementSearch search,
                                   SoundCues sounds) {
        this.pluginContext = pluginContext;
        this.mapView = mapView;
        this.state = state;
        this.search = search;
        this.sounds = sounds;
        this.vibrator = (Vibrator) mapView.getContext().getSystemService(Context.VIBRATOR_SERVICE);
    }

    /** Called every tick by RiskTickLoop with the smoothed composite score. */
    public void apply(double currentScore, double opLat, double opLon) {
        // Once user accepts risk, stay quiet until they're back to safe territory.
        // Reset suppression once score crosses below the lower hysteresis band.
        if (userDismissedThisCycle && currentScore < HIDE_THRESHOLD) {
            userDismissedThisCycle = false;
        }

        if (!visible && currentScore >= SHOW_THRESHOLD && !userDismissedThisCycle) {
            ui.post(() -> showModal(currentScore, opLat, opLon));
        } else if (visible && currentScore < HIDE_THRESHOLD) {
            ui.post(this::hideModal);
        }
        if (visible && modalRoot != null) {
            ui.post(() -> updateTitle(currentScore));
        }
    }

    private void showModal(double score, double opLat, double opLon) {
        if (visible) return;
        if (state.activeProfile() == null) return;

        try {
            modalRoot = PluginLayoutInflater.inflate(pluginContext, R.layout.displace_modal, null);
            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    FrameLayout.LayoutParams.MATCH_PARENT);
            // Attach to the activity content frame so we composite above the GL map.
            android.app.Activity activity = activityFrom(mapView);
            attachParent = activity != null
                    ? activity.findViewById(android.R.id.content)
                    : null;
            if (attachParent != null) {
                attachParent.addView(modalRoot, lp);
                attachParent.bringChildToFront(modalRoot);
                float density = mapView.getResources().getDisplayMetrics().density;
                modalRoot.setElevation(50f * density);
            } else {
                mapView.addView(modalRoot, lp);
            }
            visible = true;
            updateTitle(score);
            populateCandidates(opLat, opLon);
            wireCancel();
            triggerAlertCues();
            Log.i(TAG, "displace modal shown at score " + score);
        } catch (Exception e) {
            Log.e(TAG, "failed to show displace modal", e);
        }
    }

    private void hideModal() {
        if (!visible) return;
        try {
            if (modalRoot != null) {
                if (attachParent != null) attachParent.removeView(modalRoot);
                else mapView.removeView(modalRoot);
            }
        } catch (Exception ignored) {}
        modalRoot = null;
        visible = false;
        Log.i(TAG, "displace modal hidden");
    }

    private static android.app.Activity activityFrom(android.view.View v) {
        Context c = v.getContext();
        while (c instanceof android.content.ContextWrapper) {
            if (c instanceof android.app.Activity) return (android.app.Activity) c;
            c = ((android.content.ContextWrapper) c).getBaseContext();
        }
        return null;
    }

    private void updateTitle(double score) {
        if (modalRoot == null) return;
        TextView subtitle = modalRoot.findViewById(R.id.displace_subtitle);
        subtitle.setText(String.format(Locale.US,
                "Composite risk %.2f — adversary fix imminent", score));
    }

    private void populateCandidates(double opLat, double opLon) {
        if (modalRoot == null) return;
        LinearLayout container = modalRoot.findViewById(R.id.displace_candidates_container);
        container.removeAllViews();

        List<PlacedAdversary> placed = state.placedAdversariesSnapshot();
        List<DisplacementCandidate> top = search.top3(
                state.lastRisk() != null ? state.lastRisk().displayedScore : 0.5,
                opLat, opLon, state.activeProfile(), placed);

        if (top.isEmpty()) {
            TextView empty = new TextView(mapView.getContext());
            empty.setText("No safer position found within search radius. Stop keying or move opportunistically.");
            empty.setTextColor(0xFFAAAAAA);
            empty.setPadding(20, 20, 20, 20);
            container.addView(empty);
            return;
        }

        for (DisplacementCandidate c : top) {
            // P0: capture the inflated view directly. PluginLayoutInflater with
            // root=container may or may not auto-attach; relying on
            // container.getChildAt(getChildCount()-1) was racy when consecutive
            // inflates happened to attach in different orders.
            View card = PluginLayoutInflater.inflate(pluginContext,
                    R.layout.displace_candidate_card, null);
            container.addView(card);
            TextView dir = card.findViewById(R.id.displace_card_dir);
            TextView det = card.findViewById(R.id.displace_card_detail);
            dir.setText(String.format(Locale.US, "%s  ·  %.0f m",
                    compass(c.bearingDeg), c.distanceMeters));
            det.setText(String.format(Locale.US,
                    "Predicted risk %.2f  (Δ −%.2f from current)",
                    c.predictedComposite, c.predictedDelta));
            card.setOnClickListener(v -> {
                dropRoute(opLat, opLon, c);
                hideModal();
            });
        }
    }

    private void wireCancel() {
        Button cancel = modalRoot.findViewById(R.id.displace_cancel_btn);
        cancel.setOnClickListener(v -> {
            userDismissedThisCycle = true;
            hideModal();
        });
    }

    private void triggerAlertCues() {
        try {
            if (vibrator != null && vibrator.hasVibrator()) {
                if (android.os.Build.VERSION.SDK_INT >= 26) {
                    vibrator.vibrate(VibrationEffect.createOneShot(400, VibrationEffect.DEFAULT_AMPLITUDE));
                } else {
                    vibrator.vibrate(400);
                }
            }
        } catch (Exception ignored) {}
        if (sounds != null) {
            sounds.onScore(0.9);   // forces the red cue
        }
    }

    private void dropRoute(double opLat, double opLon, DisplacementCandidate c) {
        try {
            Route r = new Route(mapView, "EMCON Displace", Color.WHITE, "DP",
                    UUID.randomUUID().toString());
            // Tag for clearAllAdversaries() so the route gets removed when posture
            // or scenario changes. Both the Route and its waypoint markers carry
            // the tag — ATAK persists waypoints separately.
            r.setMetaString("emcon-displace-route", "true");
            Marker[] m = new Marker[2];
            m[0] = Route.createWayPoint(GeoPointMetaData.wrap(new GeoPoint(opLat, opLon)),
                    UUID.randomUUID().toString());
            m[0].setMetaString("emcon-displace-route", "true");
            m[1] = Route.createWayPoint(GeoPointMetaData.wrap(new GeoPoint(c.lat, c.lon)),
                    UUID.randomUUID().toString());
            m[1].setMetaString("emcon-displace-route", "true");
            r.addMarkers(0, m);
            MapGroup routeGroup = mapView.getRootGroup().findMapGroup("Route");
            if (routeGroup == null) routeGroup = mapView.getRootGroup();
            routeGroup.addItem(r);
            r.persist(mapView.getMapEventDispatcher(), null, this.getClass());
            Log.i(TAG, "dropped displace route to " + c.lat + "," + c.lon);
        } catch (Exception e) {
            Log.e(TAG, "failed to drop displace route", e);
        }
    }

    private static String compass(double bearingDeg) {
        String[] c = { "N","NE","E","SE","S","SW","W","NW" };
        int idx = (int) Math.floor(((bearingDeg + 22.5) % 360) / 45.0);
        return c[idx];
    }

    public void detach() {
        hideModal();
    }
}
