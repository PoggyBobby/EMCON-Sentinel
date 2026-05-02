package com.emconsentinel.util;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public class GeoTest {

    @Test
    public void distanceNycToLaIsAbout3935km() {
        double d = Geo.distanceKm(40.7128, -74.0060, 34.0522, -118.2437);
        assertEquals(3935.7, d, 5.0);
    }

    @Test
    public void distanceMonotonicWithSeparation() {
        double a = Geo.distanceKm(0, 0, 0, 1);
        double b = Geo.distanceKm(0, 0, 0, 2);
        double c = Geo.distanceKm(0, 0, 0, 5);
        assertTrue(a < b && b < c);
    }

    @Test
    public void bearingDueEastIs90Deg() {
        double bearing = Geo.bearingDeg(0, 0, 0, 1);
        assertEquals(90.0, bearing, 1e-6);
    }

    @Test
    public void bearingDueNorthIs0Deg() {
        double bearing = Geo.bearingDeg(0, 0, 1, 0);
        assertEquals(0.0, bearing, 1e-6);
    }

    @Test
    public void destinationRoundTrip() {
        double[] dst = Geo.destination(40.0, -74.0, 90.0, 100.0);
        double back = Geo.distanceKm(40.0, -74.0, dst[0], dst[1]);
        assertEquals(100.0, back, 0.05);
    }
}
