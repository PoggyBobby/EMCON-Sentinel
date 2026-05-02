package com.emconsentinel.util;

public final class Geo {
    private static final double EARTH_RADIUS_KM = 6371.0088;

    private Geo() {}

    public static double distanceKm(double lat1, double lon1, double lat2, double lon2) {
        double phi1 = Math.toRadians(lat1);
        double phi2 = Math.toRadians(lat2);
        double dPhi = Math.toRadians(lat2 - lat1);
        double dLam = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dPhi / 2) * Math.sin(dPhi / 2)
                 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLam / 2) * Math.sin(dLam / 2);
        return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)));
    }

    public static double bearingDeg(double lat1, double lon1, double lat2, double lon2) {
        double phi1 = Math.toRadians(lat1);
        double phi2 = Math.toRadians(lat2);
        double dLam = Math.toRadians(lon2 - lon1);
        double y = Math.sin(dLam) * Math.cos(phi2);
        double x = Math.cos(phi1) * Math.sin(phi2)
                 - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLam);
        return (Math.toDegrees(Math.atan2(y, x)) + 360) % 360;
    }

    public static double[] destination(double lat, double lon, double bearingDeg, double distKm) {
        double phi1 = Math.toRadians(lat);
        double lam1 = Math.toRadians(lon);
        double theta = Math.toRadians(bearingDeg);
        double delta = distKm / EARTH_RADIUS_KM;
        double phi2 = Math.asin(Math.sin(phi1) * Math.cos(delta)
                              + Math.cos(phi1) * Math.sin(delta) * Math.cos(theta));
        double lam2 = lam1 + Math.atan2(
                Math.sin(theta) * Math.sin(delta) * Math.cos(phi1),
                Math.cos(delta) - Math.sin(phi1) * Math.sin(phi2));
        return new double[] { Math.toDegrees(phi2), ((Math.toDegrees(lam2) + 540) % 360) - 180 };
    }
}
