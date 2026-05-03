package com.emconsentinel.risk;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.RadioBand;
import com.emconsentinel.data.RadioProfile;
import com.emconsentinel.prop.FreeSpaceEngine;

import org.junit.Test;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

public class HopCoachTest {

    /** Adversary covering 100 MHz – 6 GHz (catches 2.4 + 5.8 + 900 MHz). */
    private static final AdversarySystem WIDEBAND = new AdversarySystem(
            "wb", "Wideband-DF", AdversarySystem.Platform.GROUND_VEHICLE,
            100, 6000, 12.0, -110.0, 25, 50, 90, "test");

    /** Single-band adversary tuned only at 2.4 GHz. */
    private static final AdversarySystem NARROW_24 = new AdversarySystem(
            "n24", "Narrowband-2.4", AdversarySystem.Platform.GROUND_VEHICLE,
            2300, 2500, 12.0, -110.0, 25, 50, 90, "test");

    /** FPV-style two-band radio: 2.4 GHz control + 5.8 GHz video. */
    private static final RadioProfile FPV = new RadioProfile("fpv", "FPV", Arrays.asList(
            new RadioBand(2400, 20, 0.8, "control"),
            new RadioBand(5800, 23, 1.0, "video")));

    private HopCoach build() {
        return new HopCoach(new FreeSpaceEngine());
    }

    @Test public void noPlacedAdversariesGivesNullRecommendation() {
        HopCoach c = build();
        HopRecommendation r = c.compute(FPV, Collections.<Integer>emptySet(),
                0, 0,
                Collections.<PlacedAdversary>emptyList(),
                300.0);
        assertNull(r);
    }

    @Test public void singleBandRadioGivesNoRecommendation() {
        RadioProfile mesh = new RadioProfile("mesh", "Mesh", Collections.singletonList(
                new RadioBand(2200, 33, 1.0, "mesh_data")));
        HopCoach c = build();
        List<PlacedAdversary> placed = Collections.singletonList(
                new PlacedAdversary(WIDEBAND, 0, 5.0 / 111.0));
        HopRecommendation r = c.compute(mesh, Collections.<Integer>emptySet(),
                0, 0, placed, 300.0);
        assertNull("Single-band radio should never produce a recommendation", r);
    }

    @Test public void disabledBandsAreExcludedFromAttribution() {
        HopCoach c = build();
        List<PlacedAdversary> placed = Collections.singletonList(
                new PlacedAdversary(WIDEBAND, 0, 5.0 / 111.0));
        Set<Integer> disabled = new HashSet<>();
        disabled.add(1);    // disable 5.8 GHz video
        HopRecommendation r = c.compute(FPV, disabled, 0, 0, placed, 300.0);
        assertNull("Single-active-band situation should give no recommendation", r);
    }

    @Test public void narrowbandThreatLetsHopCoachRecommendDisablingMatchingBand() {
        // NARROW_24 only sees 2.4 GHz, so disabling 2.4 (band index 0) drops
        // composite to 0. The survivor is 5.8 GHz video.
        HopCoach c = build();
        List<PlacedAdversary> placed = Collections.singletonList(
                new PlacedAdversary(NARROW_24, 0, 5.0 / 111.0));
        HopRecommendation r = c.compute(FPV, Collections.<Integer>emptySet(),
                0, 0, placed, 300.0);
        assertNotNull("Expected a recommendation when one band dominates", r);
        assertEquals("Should recommend disabling exactly one band", 1, r.bandsToDisable.size());
        assertTrue("oneLiner should mention 5.8 GHz survivor: " + r.oneLiner,
                r.oneLiner.contains("5.8 GHz"));
        // Note: dominant band's display might also contain "2.4 GHz" but the
        // surviving-band naming should put 5.8 in the message
        assertTrue("riskDeltaFraction should meet threshold: " + r.riskDeltaFraction,
                r.riskDeltaFraction >= HopCoach.MIN_REDUCTION_FRACTION);
    }

    @Test public void identicalBandsGiveNoRecommendation() {
        // Two identical bands → removing one leaves the other still saturating.
        // Reduction won't meet the 30% threshold.
        RadioProfile twins = new RadioProfile("twins", "Twins", Arrays.asList(
                new RadioBand(2400, 20, 0.5, "a"),
                new RadioBand(2400, 20, 0.5, "b")));
        HopCoach c = build();
        List<PlacedAdversary> placed = Collections.singletonList(
                new PlacedAdversary(WIDEBAND, 0, 5.0 / 111.0));
        HopRecommendation r = c.compute(twins, Collections.<Integer>emptySet(),
                0, 0, placed, 300.0);
        assertNull("Two identical bands should not trigger a recommendation: " + r, r);
    }
}
