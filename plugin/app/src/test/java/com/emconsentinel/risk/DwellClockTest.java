package com.emconsentinel.risk;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class DwellClockTest {

    @Test public void dwellAccumulatesWhileKeyingInPlace() {
        DwellClock c = new DwellClock();
        c.update(0,     40.0, -74.0, true);
        c.update(1000,  40.0, -74.0, true);
        c.update(5000,  40.0, -74.0, true);
        assertEquals(5.0, c.getDwellSeconds(), 0.01);
        assertTrue(c.isActive());
    }

    @Test public void stopKeyingResetsClock() {
        DwellClock c = new DwellClock();
        c.update(0, 40.0, -74.0, true);
        c.update(5000, 40.0, -74.0, true);
        assertEquals(5.0, c.getDwellSeconds(), 0.01);
        c.update(6000, 40.0, -74.0, false);
        assertEquals(0.0, c.getDwellSeconds(), 0.01);
        assertFalse(c.isActive());
    }

    @Test public void movementOutsideRadiusResetsAndReanchors() {
        DwellClock c = new DwellClock();
        c.update(0, 40.0, -74.0, true);
        c.update(60_000, 40.0, -74.0, true);
        assertEquals(60.0, c.getDwellSeconds(), 0.01);
        // jump 100m east — way outside the 50m radius
        // 100m east of (40, -74) is approx (40, -74 + 0.001175)
        c.update(61_000, 40.0, -74.0 + 0.0012, true);
        assertEquals(0.0, c.getDwellSeconds(), 0.01);
        // continue from new anchor
        c.update(63_000, 40.0, -74.0 + 0.0012, true);
        assertEquals(2.0, c.getDwellSeconds(), 0.01);
    }

    @Test public void microMovementWithinRadiusKeepsClockRunning() {
        DwellClock c = new DwellClock();
        c.update(0, 40.0, -74.0, true);
        c.update(10_000, 40.0, -74.0, true);
        // move ~10m — within the 50m radius
        c.update(10_500, 40.0, -74.0 + 0.00012, true);
        assertTrue("dwell must not reset on micro-move", c.getDwellSeconds() > 10.0);
    }

    @Test public void timeScaleAcceleratesAccumulation() {
        DwellClock c = new DwellClock();
        c.setTimeScale(10.0);
        c.update(0, 40.0, -74.0, true);
        c.update(5000, 40.0, -74.0, true);
        // 5 wall seconds × 10 = 50 simulated seconds
        assertEquals(50.0, c.getDwellSeconds(), 0.05);
    }
}
