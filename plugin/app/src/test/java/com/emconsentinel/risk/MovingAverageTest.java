package com.emconsentinel.risk;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class MovingAverageTest {

    @Test public void singlePushReturnsThatValue() {
        MovingAverage ma = new MovingAverage(5_000);
        assertEquals(0.7, ma.push(0, 0.7), 1e-9);
    }

    @Test public void averagesAcrossSamplesInWindow() {
        MovingAverage ma = new MovingAverage(5_000);
        ma.push(0, 0.4);
        ma.push(1_000, 0.6);
        ma.push(2_000, 0.8);
        assertEquals(0.6, ma.push(3_000, 0.6), 1e-9);
    }

    @Test public void evictsSamplesOlderThanWindow() {
        MovingAverage ma = new MovingAverage(5_000);
        ma.push(0, 1.0);
        ma.push(1_000, 1.0);
        // jump past the window — only the new sample remains
        double v = ma.push(10_000, 0.0);
        assertEquals(0.0, v, 1e-9);
        assertEquals(1, ma.size());
    }
}
