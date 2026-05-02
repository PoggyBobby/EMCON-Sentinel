package com.emconsentinel.prop;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.RadioBand;
import com.emconsentinel.data.RadioProfile;

import org.junit.Test;

import java.util.Arrays;
import java.util.Collections;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public class LinkBudgetTest {

    private static final AdversarySystem ZHITEL_LIKE = new AdversarySystem(
            "test-zhitel", "Zhitel-like", AdversarySystem.Platform.GROUND_VEHICLE,
            100, 2000, 12.0, -110.0, 25, 50, 90, "test");

    private static final AdversarySystem AIRBORNE_24 = new AdversarySystem(
            "test-airborne", "Airborne RG drone", AdversarySystem.Platform.AIRBORNE,
            800, 2500, 6.0, -95.0, 6, 25, 45, "test");

    @Test public void sigmoidAtZeroIs50Percent() {
        assertEquals(0.5, LinkBudget.sigmoid(0), 1e-9);
    }

    @Test public void sigmoidAt10dbIsAbout88Percent() {
        assertEquals(0.881, LinkBudget.sigmoid(10), 0.01);
    }

    @Test public void sigmoidAtMinus10dbIsAbout12Percent() {
        assertEquals(0.119, LinkBudget.sigmoid(-10), 0.01);
    }

    @Test public void bandOutOfRangeReturnsZero() {
        RadioBand band58 = new RadioBand(5800, 23, 1.0, "video");
        // Zhitel cap is 2 GHz, 5.8 GHz video band is out of its tuning range
        double p = LinkBudget.bandDetectionProb(ZHITEL_LIKE, band58, 100);
        assertEquals(0.0, p, 1e-9);
    }

    @Test public void dutyCycleScalesDetection() {
        RadioBand b100 = new RadioBand(900, 20, 1.0, "ctrl");
        RadioBand b50  = new RadioBand(900, 20, 0.5, "ctrl");
        double pathLoss = 100;  // gives positive margin
        double p100 = LinkBudget.bandDetectionProb(ZHITEL_LIKE, b100, pathLoss);
        double p50  = LinkBudget.bandDetectionProb(ZHITEL_LIKE, b50, pathLoss);
        assertEquals(p100 * 0.5, p50, 1e-6);
    }

    @Test public void closeKeyingNearZhitelGivesHighDetection() {
        RadioProfile fpv = new RadioProfile("fpv", "FPV", Arrays.asList(
                new RadioBand(900, 20, 0.8, "ctrl")));
        FreeSpaceEngine prop = new FreeSpaceEngine();
        // ~1 km away
        double p = LinkBudget.assetDetectionProb(ZHITEL_LIKE, fpv,
                0, 0, 0, 0.009, prop);
        assertTrue("Expected high detection at 1 km, got " + p, p > 0.6);
    }

    @Test public void detectionMonotonicallyDropsWithDistance() {
        // FSPL alone is the optimistic case for the adversary (no terrain blockage).
        // What we can guarantee is monotonic decrease: closer = higher detection.
        RadioProfile fpv = new RadioProfile("fpv", "FPV", Arrays.asList(
                new RadioBand(900, 20, 0.8, "ctrl")));
        FreeSpaceEngine prop = new FreeSpaceEngine();
        double pNear = LinkBudget.assetDetectionProb(ZHITEL_LIKE, fpv, 0, 0, 0, 0.001, prop);
        double pMid  = LinkBudget.assetDetectionProb(ZHITEL_LIKE, fpv, 0, 0, 0, 0.05, prop);
        double pFar  = LinkBudget.assetDetectionProb(ZHITEL_LIKE, fpv, 0, 0, 0, 5.0, prop);
        assertTrue("near=" + pNear + " should >= mid=" + pMid, pNear >= pMid);
        assertTrue("mid=" + pMid + " should >= far=" + pFar, pMid >= pFar);
    }

    @Test public void weakTransmitterFarOutOfRangeGivesNearZero() {
        // -30 dBm EIRP at 50 km — well below sensitivity even with antenna gain
        RadioProfile weak = new RadioProfile("weak", "weak", Arrays.asList(
                new RadioBand(900, -30, 1.0, "ctrl")));
        FreeSpaceEngine prop = new FreeSpaceEngine();
        double p = LinkBudget.assetDetectionProb(ZHITEL_LIKE, weak,
                0, 0, 0, 50.0 / 111.0, prop);
        assertTrue("Expected near-zero detection for weak emitter at 50 km, got " + p, p < 0.05);
    }

    @Test public void airborneAdversaryUsesMaxAcrossBandsInRange() {
        RadioProfile fpv = new RadioProfile("fpv", "FPV", Arrays.asList(
                new RadioBand(900, 10, 1.0, "ctrl"),       // out of Airborne 800-2500 range? 900 is in range
                new RadioBand(2400, 20, 1.0, "control"),    // also in range
                new RadioBand(5800, 23, 1.0, "video")));    // out of range
        FreeSpaceEngine prop = new FreeSpaceEngine();
        LinkBudget.Result r = LinkBudget.assetDetection(AIRBORNE_24, fpv,
                0, 0, 0, 0.05, prop);
        assertTrue("Expected detection > 0 since some bands are in range", r.prob > 0);
        assertEquals(PropagationResult.Mode.FREE_SPACE, r.mode);
    }

    @Test public void emptyOverlapReturnsZero() {
        RadioProfile videoOnly = new RadioProfile("v", "video-only", Collections.singletonList(
                new RadioBand(5800, 23, 1.0, "video")));
        FreeSpaceEngine prop = new FreeSpaceEngine();
        // Zhitel is 100-2000 MHz, video-only profile is 5800 MHz - no overlap
        double p = LinkBudget.assetDetectionProb(ZHITEL_LIKE, videoOnly,
                0, 0, 0, 0.001, prop);
        assertEquals(0.0, p, 1e-9);
    }
}
