package com.emconsentinel.risk;

import com.emconsentinel.util.Geo;

/**
 * Accumulates dwell time (in seconds) while the operator stays within a fixed radius
 * AND continues keying. Movement outside the radius OR stop-keying resets the clock.
 *
 * Wall-clock-driven: caller passes nowMillis on each update. The clock anchors to the
 * first (lat, lon) seen after a reset.
 */
public final class DwellClock {

    private static final double DWELL_RADIUS_METERS = 50.0;

    private boolean active = false;
    private long lastUpdateMillis = 0;
    private double anchorLat = 0;
    private double anchorLon = 0;
    private double accumulatedSeconds = 0;
    private double scale = 1.0;

    public void setTimeScale(double scale) {
        this.scale = scale;
    }

    public double getTimeScale() {
        return scale;
    }

    public double getDwellSeconds() {
        return accumulatedSeconds;
    }

    public boolean isActive() {
        return active;
    }

    public void reset() {
        active = false;
        accumulatedSeconds = 0;
        lastUpdateMillis = 0;
    }

    public void update(long nowMillis, double opLat, double opLon, boolean isKeying) {
        if (!isKeying) {
            reset();
            return;
        }
        if (!active) {
            active = true;
            anchorLat = opLat;
            anchorLon = opLon;
            lastUpdateMillis = nowMillis;
            accumulatedSeconds = 0;
            return;
        }
        double distMeters = Geo.distanceKm(anchorLat, anchorLon, opLat, opLon) * 1000.0;
        if (distMeters > DWELL_RADIUS_METERS) {
            // Operator displaced outside dwell radius — reset timer to new anchor
            anchorLat = opLat;
            anchorLon = opLon;
            accumulatedSeconds = 0;
            lastUpdateMillis = nowMillis;
            return;
        }
        double deltaSeconds = (nowMillis - lastUpdateMillis) / 1000.0;
        accumulatedSeconds += deltaSeconds * scale;
        lastUpdateMillis = nowMillis;
    }
}
