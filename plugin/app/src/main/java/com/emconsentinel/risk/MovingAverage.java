package com.emconsentinel.risk;

import java.util.ArrayDeque;
import java.util.Deque;

/**
 * Time-windowed mean. Samples older than windowSeconds are evicted on each push.
 * Used to smooth the displayed risk score so the dial doesn't flicker.
 */
public final class MovingAverage {

    private static final class Sample {
        final long t;
        final double v;
        Sample(long t, double v) { this.t = t; this.v = v; }
    }

    private final long windowMillis;
    private final Deque<Sample> samples = new ArrayDeque<>();
    private double sum = 0;

    public MovingAverage(long windowMillis) {
        this.windowMillis = windowMillis;
    }

    public double push(long nowMillis, double value) {
        samples.addLast(new Sample(nowMillis, value));
        sum += value;
        long cutoff = nowMillis - windowMillis;
        while (!samples.isEmpty() && samples.peekFirst().t < cutoff) {
            sum -= samples.removeFirst().v;
        }
        return sum / samples.size();
    }

    public void reset() {
        samples.clear();
        sum = 0;
    }

    public int size() {
        return samples.size();
    }
}
