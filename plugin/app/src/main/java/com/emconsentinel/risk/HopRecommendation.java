package com.emconsentinel.risk;

import com.emconsentinel.data.RadioBand;

import java.util.Collections;
import java.util.List;

/**
 * "If you disable bands {bandsToDisable} of your current radio, your composite
 * risk drops from currentCompositeOnly to recommendedCompositeOnly (a
 * riskDeltaFraction fractional reduction, in [0,1])."
 *
 * "OnlY" suffix because these numbers are computed from the operator radio
 * bands alone — phone bands are excluded so the comparison is apples-to-apples
 * (phone bands aren't toggleable from this tool).
 */
public final class HopRecommendation {
    public final RadioBand dominantBand;
    public final List<Integer> bandsToDisable;
    public final double currentCompositeOnly;
    public final double recommendedCompositeOnly;
    public final double riskDeltaFraction;
    public final String oneLiner;

    public HopRecommendation(RadioBand dominantBand,
                             List<Integer> bandsToDisable,
                             double currentCompositeOnly,
                             double recommendedCompositeOnly,
                             double riskDeltaFraction,
                             String oneLiner) {
        this.dominantBand = dominantBand;
        this.bandsToDisable = Collections.unmodifiableList(bandsToDisable);
        this.currentCompositeOnly = currentCompositeOnly;
        this.recommendedCompositeOnly = recommendedCompositeOnly;
        this.riskDeltaFraction = riskDeltaFraction;
        this.oneLiner = oneLiner;
    }
}
