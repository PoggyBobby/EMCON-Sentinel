package com.emconsentinel.risk;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.RadioBand;
import com.emconsentinel.data.RadioProfile;
import com.emconsentinel.prop.LinkBudget;
import com.emconsentinel.prop.PathLossEngine;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Per-tick advisor: computes per-band P_lock contributions for the operator's
 * currently-active radio bands and, when one band dominates, recommends a
 * sibling-disabled subset of the SAME radio that meaningfully lowers risk
 * (≥30% reduction by default).
 *
 * Pure-Java; no Android. The tick loop calls compute() and routes the result
 * to UI.
 */
public final class HopCoach {

    /** Minimum fractional risk reduction required before we surface a recommendation. */
    public static final double MIN_REDUCTION_FRACTION = 0.30;

    private final PathLossEngine prop;

    public HopCoach(PathLossEngine prop) {
        this.prop = prop;
    }

    public HopRecommendation compute(RadioProfile profile,
                                     Set<Integer> alreadyDisabled,
                                     double opLat, double opLon,
                                     List<PlacedAdversary> placed,
                                     double dwellSeconds) {
        if (profile == null || profile.bands == null || profile.bands.isEmpty()) return null;
        if (placed == null || placed.isEmpty()) return null;

        // Build the active-band index set (everything not in alreadyDisabled)
        List<Integer> activeIdx = new ArrayList<>();
        for (int i = 0; i < profile.bands.size(); i++) {
            if (alreadyDisabled == null || !alreadyDisabled.contains(i)) activeIdx.add(i);
        }
        if (activeIdx.size() < 2) return null;     // single band can't be hopped

        // Composite P_lock with current active set
        double currentComposite = composite(profile, activeIdx, opLat, opLon, placed, dwellSeconds);
        if (currentComposite < 0.05) return null;  // not contributing meaningfully

        // Per-band attribution: for each currently-active band, what's its share?
        // "Share" = drop in composite if we disable just that band.
        double bestDelta = 0;
        int bestIdx = -1;
        for (int i : activeIdx) {
            List<Integer> withoutOne = new ArrayList<>(activeIdx);
            withoutOne.remove(Integer.valueOf(i));
            if (withoutOne.isEmpty()) continue;     // never recommend disabling all bands
            double withoutOneComposite = composite(profile, withoutOne, opLat, opLon, placed, dwellSeconds);
            double delta = currentComposite - withoutOneComposite;
            if (delta > bestDelta) {
                bestDelta = delta;
                bestIdx = i;
            }
        }
        if (bestIdx < 0) return null;

        // Threshold check: must be a ≥30% fractional reduction
        double fractionReduction = bestDelta / currentComposite;
        if (fractionReduction < MIN_REDUCTION_FRACTION) return null;

        RadioBand dominant = profile.bands.get(bestIdx);
        List<Integer> toDisable = Collections.singletonList(bestIdx);
        double recommendedComposite = currentComposite - bestDelta;
        String oneLiner = formatOneLiner(profile, bestIdx, fractionReduction);
        return new HopRecommendation(dominant, toDisable,
                currentComposite, recommendedComposite, fractionReduction, oneLiner);
    }

    /** Composite P_lock across all placed adversaries using only the supplied band indices. */
    private double composite(RadioProfile profile, List<Integer> bandIndices,
                             double opLat, double opLon, List<PlacedAdversary> placed,
                             double dwellSeconds) {
        List<RadioBand> subset = new ArrayList<>(bandIndices.size());
        for (int i : bandIndices) subset.add(profile.bands.get(i));

        double oneMinus = 1.0;
        for (PlacedAdversary p : placed) {
            if (p.hidden) continue;
            if (p.system == null) continue;
            AdversarySystem adv = p.system;
            double pDetect = LinkBudget.assetDetectionProb(adv, subset,
                    opLat, opLon, p.lat, p.lon, prop);
            if (pDetect <= 0) continue;
            double tau = Math.max(1, adv.timeToFixSeconds);
            double pLock = pDetect * (1.0 - Math.exp(-dwellSeconds / tau));
            oneMinus *= (1.0 - pLock);
        }
        return 1.0 - oneMinus;
    }

    /**
     * Build the user-facing one-liner. Names the band(s) the operator can KEEP,
     * not the one to disable, because operators think in terms of "use this one":
     *   "💡 Quieter: try only 2.4 GHz control — drops risk 32%"
     */
    private static String formatOneLiner(RadioProfile profile, int disabledIdx,
                                         double fractionReduction) {
        List<RadioBand> keep = new ArrayList<>();
        for (int i = 0; i < profile.bands.size(); i++) {
            if (i != disabledIdx) keep.add(profile.bands.get(i));
        }
        StringBuilder sb = new StringBuilder("Quieter: try only ");
        for (int i = 0; i < keep.size(); i++) {
            if (i > 0) sb.append(" + ");
            sb.append(formatBandName(keep.get(i)));
        }
        sb.append(String.format(Locale.US, " — drops risk %d%%",
                (int) Math.round(fractionReduction * 100)));
        return sb.toString();
    }

    private static String formatBandName(RadioBand b) {
        String freq = b.freqMhz >= 1000
                ? String.format(Locale.US, "%.1f GHz", b.freqMhz / 1000.0)
                : String.format(Locale.US, "%.0f MHz", b.freqMhz);
        return freq + " " + (b.purpose == null ? "" : b.purpose);
    }
}
