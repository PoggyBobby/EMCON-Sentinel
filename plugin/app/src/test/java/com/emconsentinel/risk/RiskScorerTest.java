package com.emconsentinel.risk;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.RadioBand;
import com.emconsentinel.data.RadioProfile;
import com.emconsentinel.prop.FreeSpaceEngine;

import org.junit.Test;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

public class RiskScorerTest {

    private static final AdversarySystem ZHITEL = new AdversarySystem(
            "zhitel", "R-330Zh Zhitel", AdversarySystem.Platform.GROUND_VEHICLE,
            100, 2000, 12.0, -110.0, 25, 50, 90, "test");

    private static final RadioProfile FPV = new RadioProfile("fpv", "FPV", Arrays.asList(
            new RadioBand(900, 20, 1.0, "ctrl")));

    private RiskScorer build() {
        return new RiskScorer(new FreeSpaceEngine(), new DwellClock());
    }

    private static List<PlacedAdversary> withZhitelAt(double lat, double lon) {
        return Collections.singletonList(new PlacedAdversary(ZHITEL, lat, lon));
    }

    @Test public void noAdversariesGivesZeroRisk() {
        RiskScorer s = build();
        RiskUpdate r = s.update(0, 0, 0, true, FPV,
                Collections.<PlacedAdversary>emptyList());
        assertEquals(0.0, r.displayedScore, 1e-9);
        assertEquals(0.0, r.rawCompositeScore, 1e-9);
        assertNull(r.topThreatId);
    }

    @Test public void notKeyingGivesZeroRisk() {
        RiskScorer s = build();
        // Zhitel 5 km east
        RiskUpdate r = s.update(0, 0, 0, false, FPV, withZhitelAt(0, 5.0 / 111.0));
        assertEquals(0.0, r.displayedScore, 1e-9);
        assertNull(r.topThreatId);
    }

    @Test public void riskRisesOverFiveMinutesNearZhitel() {
        RiskScorer s = build();
        // Zhitel 5 km east, operator at origin
        List<PlacedAdversary> placed = withZhitelAt(0, 5.0 / 111.0);
        RiskUpdate r0 = s.update(0, 0, 0, true, FPV, placed);
        // After 5 minutes (300 s), well past tau=90 s
        RiskUpdate r5 = null;
        for (long t = 1000; t <= 300_000; t += 1000) {
            r5 = s.update(t, 0, 0, true, FPV, placed);
        }
        assertTrue("Initial raw composite should start near 0, was " + r0.rawCompositeScore,
                r0.rawCompositeScore < 0.05);
        assertTrue("After 5 min, raw composite should be very high, was " + r5.rawCompositeScore,
                r5.rawCompositeScore > 0.85);
        assertNotNull(r5.topThreatId);
        assertEquals("zhitel", r5.topThreatId);
    }

    @Test public void riskDropsToNearZeroAfterStopKeyingPlus30s() {
        RiskScorer s = build();
        List<PlacedAdversary> placed = withZhitelAt(0, 5.0 / 111.0);
        // Build up risk over 5 min
        for (long t = 0; t <= 300_000; t += 1000) {
            s.update(t, 0, 0, true, FPV, placed);
        }
        // Stop keying — composite goes to 0 immediately. Smoothing window is 5s,
        // so smoothed should be near 0 within 30s.
        long base = 300_000;
        RiskUpdate stopped = null;
        for (long t = base + 1000; t <= base + 30_000; t += 1000) {
            stopped = s.update(t, 0, 0, false, FPV, placed);
        }
        assertTrue("After stop+30s, displayed should be < 0.1, was " + stopped.displayedScore,
                stopped.displayedScore < 0.1);
    }

    @Test public void compositeAcrossTwoAssetsIsHigherThanEither() {
        RiskScorer s = build();
        AdversarySystem zhitelB = new AdversarySystem(
                "zhitel-b", "Zhitel B", AdversarySystem.Platform.GROUND_VEHICLE,
                100, 2000, 12.0, -110.0, 25, 50, 90, "test");
        // Two assets equidistant
        List<PlacedAdversary> placed = Arrays.asList(
                new PlacedAdversary(ZHITEL,  0,  5.0 / 111.0),
                new PlacedAdversary(zhitelB, 0, -5.0 / 111.0));
        // Run both single-asset and dual-asset for ~minute
        RiskScorer single = build();
        List<PlacedAdversary> singleList = Collections.singletonList(placed.get(0));
        RiskUpdate rSingle = null;
        RiskUpdate rDual = null;
        for (long t = 0; t <= 60_000; t += 1000) {
            rSingle = single.update(t, 0, 0, true, FPV, singleList);
            rDual   = s.update(t, 0, 0, true, FPV, placed);
        }
        assertTrue("dual=" + rDual.rawCompositeScore + " should exceed single=" + rSingle.rawCompositeScore,
                rDual.rawCompositeScore > rSingle.rawCompositeScore);
    }

    @Test public void timeScaleSpeedsUpRiskClimb() {
        RiskScorer fast = build();
        fast.dwellClock().setTimeScale(10.0);  // 10x demo mode
        List<PlacedAdversary> placed = withZhitelAt(0, 5.0 / 111.0);
        // 25 wall-seconds × 10 = 250 simulated seconds (well past tau=90s)
        RiskUpdate r = null;
        for (long t = 0; t <= 25_000; t += 1000) {
            r = fast.update(t, 0, 0, true, FPV, placed);
        }
        assertTrue("With 10x scaler, 25s wall-clock should produce high risk: " + r.rawCompositeScore,
                r.rawCompositeScore > 0.85);
    }
}
