package com.emconsentinel.risk;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.RadioProfile;
import com.emconsentinel.prop.LinkBudget;
import com.emconsentinel.prop.PathLossEngine;
import com.emconsentinel.util.Geo;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Samples 8 bearings × 3 ranges (200 m, 400 m, 800 m) from current position. For each
 * candidate, predicts the composite P_compromise assuming the operator stops keying for
 * 30 s and then resumes from the candidate (resetting dwell). Returns the top 3 by
 * largest reduction from current risk.
 */
public final class DisplacementSearch {

    private static final int    BEARING_STEPS = 8;
    private static final double BEARING_STEP_DEG = 360.0 / BEARING_STEPS;
    private static final double[] RANGES_M = { 200.0, 400.0, 800.0 };
    private static final double POST_MOVE_DWELL_SECONDS = 30.0;

    private final PathLossEngine prop;

    public DisplacementSearch(PathLossEngine prop) {
        this.prop = prop;
    }

    public List<DisplacementCandidate> top3(double currentComposite,
                                             double opLat, double opLon,
                                             RadioProfile profile,
                                             List<PlacedAdversary> placed) {
        List<DisplacementCandidate> all = new ArrayList<>(BEARING_STEPS * RANGES_M.length);
        for (int b = 0; b < BEARING_STEPS; b++) {
            double bearing = b * BEARING_STEP_DEG;
            for (double rangeM : RANGES_M) {
                double[] dst = Geo.destination(opLat, opLon, bearing, rangeM / 1000.0);
                double pComp = predictedComposite(dst[0], dst[1], profile, placed);
                double delta = currentComposite - pComp;
                all.add(new DisplacementCandidate(dst[0], dst[1], bearing, rangeM, pComp, delta));
            }
        }
        all.sort(Comparator.comparingDouble((DisplacementCandidate c) -> c.predictedComposite));
        return all.subList(0, Math.min(3, all.size()));
    }

    private double predictedComposite(double newLat, double newLon,
                                       RadioProfile profile,
                                       List<PlacedAdversary> placed) {
        double oneMinus = 1.0;
        for (PlacedAdversary p : placed) {
            AdversarySystem adv = p.system;
            LinkBudget.Result detect = LinkBudget.assetDetection(adv, profile,
                    newLat, newLon, p.lat, p.lon, prop);
            double pDetect = detect.prob;
            if (pDetect <= 0) continue;
            double tau = Math.max(1, adv.timeToFixSeconds);
            double pLock = pDetect * (1.0 - Math.exp(-POST_MOVE_DWELL_SECONDS / tau));
            oneMinus *= (1.0 - pLock);
        }
        return 1.0 - oneMinus;
    }
}
