package com.emconsentinel.cot;

/**
 * Value class for one EMCON Sentinel CoT broadcast.
 *
 * The CoT spec carries operator position via {@code <point>}; we extend it with a
 * custom {@code <emcon>} child carrying composite risk + dwell + top-threat metadata.
 * Standard ATAK clients still see the operator as a friendly ground marker; clients
 * that know about EMCON Sentinel can parse the extension and color-code.
 */
public final class CotEvent {
    public final String operatorUid;       // stable id, e.g. "EMCON-Operator-<deviceUid>"
    public final String callsign;          // e.g. "EMCON-1"
    public final long   nowMillis;         // wall clock for time/start/stale
    public final long   staleSeconds;      // how long this event remains "fresh"
    public final double lat;
    public final double lon;
    public final double riskScore;         // composite, [0,1]
    public final double dwellSeconds;
    public final String topThreatId;       // null if none
    public final double topThreatRangeKm;
    public final double topThreatBearingDeg;

    public CotEvent(String operatorUid, String callsign, long nowMillis, long staleSeconds,
                    double lat, double lon,
                    double riskScore, double dwellSeconds,
                    String topThreatId, double topThreatRangeKm, double topThreatBearingDeg) {
        this.operatorUid = operatorUid;
        this.callsign = callsign;
        this.nowMillis = nowMillis;
        this.staleSeconds = staleSeconds;
        this.lat = lat;
        this.lon = lon;
        this.riskScore = riskScore;
        this.dwellSeconds = dwellSeconds;
        this.topThreatId = topThreatId;
        this.topThreatRangeKm = topThreatRangeKm;
        this.topThreatBearingDeg = topThreatBearingDeg;
    }
}
