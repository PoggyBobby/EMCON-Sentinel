package com.emconsentinel.ui;

import android.os.Handler;
import android.os.Looper;

import com.atakmap.android.maps.MapView;
import com.atakmap.android.maps.Marker;
import com.atakmap.coremap.maps.coords.GeoPoint;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.prop.LinkBudget;
import com.emconsentinel.prop.PathLossEngine;
import com.emconsentinel.prop.PropagationResult;
import com.emconsentinel.risk.PlacedAdversary;
import com.emconsentinel.risk.RiskScorer;
import com.emconsentinel.risk.RiskUpdate;
import com.emconsentinel.util.Geo;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 1-Hz Handler-driven loop. Each tick:
 *   1. Sources operator GPS (mapView.getSelfMarker().getPoint(); falls back to map center).
 *   2. Calls RiskScorer.update with current PluginState (profile, placed, keying).
 *   3. Pushes the resulting RiskUpdate to the dial view + threat-circle renderer.
 *
 * Period is reduced to 100 ms when demo mode is on (10x time scaler is in DwellClock,
 * but UI feels smoother with faster ticks). Otherwise 1000 ms.
 */
public final class RiskTickLoop {

    private final MapView mapView;
    private final PluginState state;
    private final RiskScorer scorer;
    private final PathLossEngine prop;
    private final RiskDialView dial;
    private final ThreatCircleRenderer circles;
    private final DisplaceBanner banner;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final AtomicBoolean running = new AtomicBoolean(false);

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (!running.get()) return;
            doTick();
            long period = state.isDemoMode10x() ? 100L : 1000L;
            handler.postDelayed(this, period);
        }
    };

    public RiskTickLoop(MapView mapView, PluginState state, RiskScorer scorer,
                        PathLossEngine prop, RiskDialView dial,
                        ThreatCircleRenderer circles, DisplaceBanner banner) {
        this.mapView = mapView;
        this.state = state;
        this.scorer = scorer;
        this.prop = prop;
        this.dial = dial;
        this.circles = circles;
        this.banner = banner;
        scorer.dwellClock().setTimeScale(state.isDemoMode10x() ? 10.0 : 1.0);
    }

    public void start() {
        if (running.compareAndSet(false, true)) {
            handler.post(tick);
        }
    }

    public void stop() {
        running.set(false);
        handler.removeCallbacks(tick);
    }

    private void doTick() {
        scorer.dwellClock().setTimeScale(state.isDemoMode10x() ? 10.0 : 1.0);

        GeoPoint op = currentOperatorPoint();
        if (op == null) {
            dial.setRisk(0, 0, "No GPS fix yet", "", state.isDemoMode10x());
            return;
        }

        List<PlacedAdversary> placed = state.placedAdversariesSnapshot();
        long now = System.currentTimeMillis();
        RiskUpdate update = scorer.update(now, op.getLatitude(), op.getLongitude(),
                state.isKeying(), state.activeProfile(), placed);
        state.setLastRisk(update);

        // Per-asset lock probs for circle renderer
        Map<String, Double> perAssetLockProb = new HashMap<>();
        if (state.isKeying() && state.activeProfile() != null) {
            double t = update.dwellSeconds;
            for (PlacedAdversary p : placed) {
                AdversarySystem adv = p.system;
                LinkBudget.Result detect = LinkBudget.assetDetection(adv, state.activeProfile(),
                        op.getLatitude(), op.getLongitude(), p.lat, p.lon, prop);
                double tau = Math.max(1, adv.timeToFixSeconds);
                double pLock = detect.prob * (1.0 - Math.exp(-t / tau));
                perAssetLockProb.put(p.system.id + "@" + p.lat + "," + p.lon, pLock);
            }
        }
        circles.apply(placed, perAssetLockProb);

        String topThreatLine = "";
        if (update.topThreatId != null) {
            topThreatLine = String.format("Top: %s (%.1f km %s)", update.topThreatDisplayName,
                    update.topThreatRangeKm, compass(update.topThreatBearingDeg));
        }
        String propModeLine = update.propagationMode == PropagationResult.Mode.FREE_SPACE
                ? "FREE-SPACE FALLBACK — TERRAIN NOT MODELED"
                : "";

        dial.setRisk(update.displayedScore, update.dwellSeconds, topThreatLine, propModeLine,
                state.isDemoMode10x());

        if (banner != null) {
            banner.apply(update.displayedScore, op.getLatitude(), op.getLongitude());
        }
    }

    private GeoPoint currentOperatorPoint() {
        Marker self = mapView.getSelfMarker();
        if (self != null && self.getPoint() != null) {
            GeoPoint p = self.getPoint();
            // self marker can sit at (0,0) when there's no GPS fix; treat that as missing
            if (p.getLatitude() != 0.0 || p.getLongitude() != 0.0) return p;
        }
        // Fallback: map center (lets operator demo without a real GPS fix)
        return mapView.getCenterPoint().get();
    }

    private static String compass(double bearingDeg) {
        String[] c = { "N","NE","E","SE","S","SW","W","NW" };
        int idx = (int) Math.floor(((bearingDeg + 22.5) % 360) / 45.0);
        return c[idx];
    }
}
