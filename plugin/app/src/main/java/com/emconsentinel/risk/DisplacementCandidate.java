package com.emconsentinel.risk;

public final class DisplacementCandidate {
    public final double lat;
    public final double lon;
    public final double bearingDeg;
    public final double distanceMeters;
    public final double predictedComposite; // P_compromise after 30s stop-keying then move-and-rest
    public final double predictedDelta;     // current - predicted

    public DisplacementCandidate(double lat, double lon, double bearingDeg, double distanceMeters,
                                  double predictedComposite, double predictedDelta) {
        this.lat = lat;
        this.lon = lon;
        this.bearingDeg = bearingDeg;
        this.distanceMeters = distanceMeters;
        this.predictedComposite = predictedComposite;
        this.predictedDelta = predictedDelta;
    }
}
