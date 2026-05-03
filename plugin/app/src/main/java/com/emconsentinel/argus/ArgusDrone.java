package com.emconsentinel.argus;

import com.emconsentinel.util.Geo;

import java.util.List;

/**
 * Simulated friendly UAS for the ARGUS scan demo. Carries a SIGINT receiver with
 * a published scan radius. Flies a sequence of waypoints (looping). On each tick
 * it advances along the current leg by speed * dt.
 *
 * Pure data + math; no Android types. ArgusFleet drives the tick loop and
 * ArgusFleetRenderer projects positions onto the MapView.
 */
public final class ArgusDrone {

    public final String id;
    public final String callsign;
    public final double altitudeMeters;
    public final double scanRadiusKm;
    public final double speedKmh;
    public final List<double[]> waypoints;   // each = {lat, lon}

    private double lat;
    private double lon;
    private int currentLeg = 0;              // index of waypoint we're flying TOWARD

    public ArgusDrone(String id, String callsign, double altitudeMeters, double scanRadiusKm,
                      double speedKmh, List<double[]> waypoints) {
        this(id, callsign, altitudeMeters, scanRadiusKm, speedKmh, waypoints,
                Double.NaN, Double.NaN);
    }

    /**
     * @param launchLat,launchLon  starting position (e.g. operator GPS). The drone
     *   spawns here and flies to waypoint 0 first, giving the demo a "drones
     *   take off from your location" visual instead of teleporting to the
     *   scenario's far-away first waypoint. Pass NaN/NaN to disable (start at
     *   waypoint 0 like before).
     */
    public ArgusDrone(String id, String callsign, double altitudeMeters, double scanRadiusKm,
                      double speedKmh, List<double[]> waypoints,
                      double launchLat, double launchLon) {
        if (waypoints == null || waypoints.isEmpty()) {
            throw new IllegalArgumentException("ArgusDrone needs at least 1 waypoint");
        }
        this.id = id;
        this.callsign = callsign;
        this.altitudeMeters = altitudeMeters;
        this.scanRadiusKm = scanRadiusKm;
        this.speedKmh = speedKmh;
        this.waypoints = waypoints;
        boolean hasLaunch = !Double.isNaN(launchLat) && !Double.isNaN(launchLon);
        if (hasLaunch) {
            this.lat = launchLat;
            this.lon = launchLon;
            this.currentLeg = 0;     // first leg = launch → waypoint 0
        } else {
            this.lat = waypoints.get(0)[0];
            this.lon = waypoints.get(0)[1];
            this.currentLeg = waypoints.size() > 1 ? 1 : 0;
        }
    }

    public double lat() { return lat; }
    public double lon() { return lon; }

    /** Advance the drone along its route by dtSeconds. Loops back to start at end. */
    public void tick(double dtSeconds) {
        if (waypoints.size() < 2) return;
        double[] target = waypoints.get(currentLeg);
        double remainingKm = Geo.distanceKm(lat, lon, target[0], target[1]);
        double stepKm = (speedKmh / 3600.0) * dtSeconds;
        if (stepKm >= remainingKm) {
            // Reached this waypoint — snap to it and advance leg
            lat = target[0];
            lon = target[1];
            currentLeg = (currentLeg + 1) % waypoints.size();
        } else {
            double bearing = Geo.bearingDeg(lat, lon, target[0], target[1]);
            double[] next = Geo.destination(lat, lon, bearing, stepKm);
            lat = next[0];
            lon = next[1];
        }
    }

    /** True if the given lat/lon falls inside this drone's scan footprint. */
    public boolean canDetect(double targetLat, double targetLon) {
        return Geo.distanceKm(lat, lon, targetLat, targetLon) <= scanRadiusKm;
    }
}
