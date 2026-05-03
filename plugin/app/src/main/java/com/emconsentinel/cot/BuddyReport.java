package com.emconsentinel.cot;

/**
 * Inbound symmetric of {@link CotEvent}: a parsed EMCON-Sentinel CoT report
 * received from another operator on the ATAK CoT mesh. Used by
 * {@code BuddyAlertController} to decide whether to alert the operator.
 */
public final class BuddyReport {
    public final String uid;
    public final String callsign;
    public final double lat;
    public final double lon;
    public final double score;
    public final double dwellSeconds;
    public final String topThreatId;
    public final double topThreatRangeKm;
    public final double topThreatBearingDeg;
    public final long receivedMs;

    public BuddyReport(String uid, String callsign, double lat, double lon,
                       double score, double dwellSeconds, String topThreatId,
                       double topThreatRangeKm, double topThreatBearingDeg,
                       long receivedMs) {
        this.uid = uid;
        this.callsign = callsign;
        this.lat = lat;
        this.lon = lon;
        this.score = score;
        this.dwellSeconds = dwellSeconds;
        this.topThreatId = topThreatId;
        this.topThreatRangeKm = topThreatRangeKm;
        this.topThreatBearingDeg = topThreatBearingDeg;
        this.receivedMs = receivedMs;
    }
}
