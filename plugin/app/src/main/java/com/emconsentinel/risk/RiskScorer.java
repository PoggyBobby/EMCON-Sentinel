package com.emconsentinel.risk;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.RadioProfile;
import com.emconsentinel.prop.LinkBudget;
import com.emconsentinel.prop.PathLossEngine;
import com.emconsentinel.prop.PropagationResult;
import com.emconsentinel.util.Geo;

import java.util.List;

/**
 * Computes composite risk in [0, 1] from a stream of (now, position, isKeying) events.
 *
 * Per-asset lock prob over time:    P_lock_i(t) = P_detect_i * (1 - exp(-t / tau_i))
 * Across assets:                    P_compromise = 1 - PROD_i (1 - P_lock_i)
 * Display:                          5-second moving average of P_compromise
 *
 * The DwellClock owns time accumulation and 50 m radius gating. RiskScorer is otherwise
 * stateless except for the smoothing buffer.
 */
public final class RiskScorer {

    private static final long SMOOTHING_WINDOW_MILLIS = 5_000;

    private final PathLossEngine prop;
    private final DwellClock clock;
    private final MovingAverage smoother;

    public RiskScorer(PathLossEngine prop, DwellClock clock) {
        this.prop = prop;
        this.clock = clock;
        this.smoother = new MovingAverage(SMOOTHING_WINDOW_MILLIS);
    }

    public DwellClock dwellClock() {
        return clock;
    }

    public RiskUpdate update(long nowMillis, double opLat, double opLon, boolean isKeying,
                              RadioProfile profile, List<PlacedAdversary> placed) {
        clock.update(nowMillis, opLat, opLon, isKeying);
        double t = clock.getDwellSeconds();

        if (!isKeying || placed.isEmpty() || profile == null) {
            double smoothed = smoother.push(nowMillis, 0.0);
            return new RiskUpdate(smoothed, 0.0, t, null, null, 0, 0, 0,
                    PropagationResult.Mode.FREE_SPACE);
        }

        double composite_one_minus = 1.0;
        String topId = null;
        String topName = null;
        double topProb = 0.0;
        double topBearing = 0.0;
        double topRange = 0.0;
        PropagationResult.Mode mode = PropagationResult.Mode.FREE_SPACE;

        for (PlacedAdversary p : placed) {
            AdversarySystem adv = p.system;
            double rangeKm = Geo.distanceKm(opLat, opLon, p.lat, p.lon);
            double maxRangeKm = adv.platform == AdversarySystem.Platform.AIRBORNE
                    ? adv.airborneRangeKm : adv.groundRangeKm;
            // Don't bother computing for assets way outside their own published reach
            if (rangeKm > maxRangeKm * 4) continue;

            LinkBudget.Result detect = LinkBudget.assetDetection(adv, profile,
                    opLat, opLon, p.lat, p.lon, prop);
            double pDetect = detect.prob;
            if (pDetect <= 0) continue;
            if (detect.mode == PropagationResult.Mode.FREE_SPACE) mode = detect.mode;

            double tau = Math.max(1, adv.timeToFixSeconds);
            double pLock = pDetect * (1.0 - Math.exp(-t / tau));
            composite_one_minus *= (1.0 - pLock);

            if (pLock > topProb) {
                topProb = pLock;
                topId = adv.id;
                topName = adv.displayName;
                topBearing = Geo.bearingDeg(opLat, opLon, p.lat, p.lon);
                topRange = rangeKm;
            }
        }

        double composite = 1.0 - composite_one_minus;
        double smoothed = smoother.push(nowMillis, composite);
        return new RiskUpdate(smoothed, composite, t, topId, topName, topBearing, topRange, topProb, mode);
    }

    public void reset() {
        clock.reset();
        smoother.reset();
    }
}
