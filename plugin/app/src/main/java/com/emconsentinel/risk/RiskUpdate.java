package com.emconsentinel.risk;

import com.emconsentinel.prop.PropagationResult;

public final class RiskUpdate {
    public final double displayedScore;       // 5-s smoothed composite, [0,1]
    public final double rawCompositeScore;    // unsmoothed, [0,1]
    public final double dwellSeconds;
    public final String topThreatId;          // null if no adversaries in range
    public final String topThreatDisplayName;
    public final double topThreatBearingDeg;
    public final double topThreatRangeKm;
    public final double topThreatLockProb;
    public final PropagationResult.Mode propagationMode;

    public RiskUpdate(double displayedScore, double rawCompositeScore, double dwellSeconds,
                      String topThreatId, String topThreatDisplayName,
                      double topThreatBearingDeg, double topThreatRangeKm,
                      double topThreatLockProb, PropagationResult.Mode propagationMode) {
        this.displayedScore = displayedScore;
        this.rawCompositeScore = rawCompositeScore;
        this.dwellSeconds = dwellSeconds;
        this.topThreatId = topThreatId;
        this.topThreatDisplayName = topThreatDisplayName;
        this.topThreatBearingDeg = topThreatBearingDeg;
        this.topThreatRangeKm = topThreatRangeKm;
        this.topThreatLockProb = topThreatLockProb;
        this.propagationMode = propagationMode;
    }
}
