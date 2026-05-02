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
import static org.junit.Assert.assertTrue;

public class DisplacementSearchTest {

    private static final AdversarySystem ZHITEL = new AdversarySystem(
            "zhitel", "R-330Zh Zhitel", AdversarySystem.Platform.GROUND_VEHICLE,
            100, 2000, 12.0, -110.0, 25, 50, 90, "test");

    private static final RadioProfile FPV = new RadioProfile("fpv", "FPV", Arrays.asList(
            new RadioBand(900, 20, 1.0, "ctrl")));

    @Test public void returnsExactly3CandidatesWhenAdversaryPresent() {
        DisplacementSearch search = new DisplacementSearch(new FreeSpaceEngine());
        List<PlacedAdversary> placed = Collections.singletonList(
                new PlacedAdversary(ZHITEL, 0, 0.001));   // very close (~111 m east)
        List<DisplacementCandidate> top = search.top3(0.9, 0, 0, FPV, placed);
        assertEquals(3, top.size());
    }

    @Test public void candidatesAreSortedByPredictedComposite() {
        DisplacementSearch search = new DisplacementSearch(new FreeSpaceEngine());
        List<PlacedAdversary> placed = Collections.singletonList(
                new PlacedAdversary(ZHITEL, 0, 0.001));
        List<DisplacementCandidate> top = search.top3(0.9, 0, 0, FPV, placed);
        for (int i = 1; i < top.size(); i++) {
            assertTrue("candidates must be sorted by predictedComposite ascending",
                    top.get(i - 1).predictedComposite <= top.get(i).predictedComposite);
        }
    }

    @Test public void bestCandidateMovesAwayFromAdversary() {
        DisplacementSearch search = new DisplacementSearch(new FreeSpaceEngine());
        // Adversary 1 km east of operator
        List<PlacedAdversary> placed = Collections.singletonList(
                new PlacedAdversary(ZHITEL, 0, 0.009));
        List<DisplacementCandidate> top = search.top3(0.9, 0, 0, FPV, placed);
        DisplacementCandidate best = top.get(0);
        // best candidate's bearing should NOT be roughly east (where the adversary is) — i.e. 270° ± 90° is fine
        // Adversary is at bearing ~90° (east). Best escape is bearing ~270° (west).
        double diffFromWest = Math.abs(((best.bearingDeg - 270 + 540) % 360) - 180);
        assertTrue("best escape should be roughly opposite the adversary direction; got bearing=" + best.bearingDeg,
                diffFromWest < 90);
    }

    @Test public void deltaIsPositiveWhenCandidateImprovesRisk() {
        DisplacementSearch search = new DisplacementSearch(new FreeSpaceEngine());
        List<PlacedAdversary> placed = Collections.singletonList(
                new PlacedAdversary(ZHITEL, 0, 0.001));
        List<DisplacementCandidate> top = search.top3(0.9, 0, 0, FPV, placed);
        // Best should have the largest delta improvement
        for (DisplacementCandidate c : top) {
            assertTrue("each top candidate should improve risk; predicted=" + c.predictedComposite,
                    c.predictedComposite < 0.9);
        }
    }
}
