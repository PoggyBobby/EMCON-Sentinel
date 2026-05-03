package com.emconsentinel.cot;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

/**
 * Formats a CotEvent as a CoT (Cursor-on-Target) v2.0 XML string. Keeps the
 * standard {@code <event>}/{@code <point>}/{@code <detail>} tree intact so
 * non-EMCON-aware ATAK clients still see the operator as a friendly ground unit;
 * adds an {@code <emcon>} child carrying the risk extension.
 */
public final class CotXml {

    private static final ThreadLocal<SimpleDateFormat> ISO = new ThreadLocal<SimpleDateFormat>() {
        @Override protected SimpleDateFormat initialValue() {
            SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
            f.setTimeZone(TimeZone.getTimeZone("UTC"));
            return f;
        }
    };

    private CotXml() {}

    public static String format(CotEvent e) {
        String now   = ISO.get().format(new Date(e.nowMillis));
        String stale = ISO.get().format(new Date(e.nowMillis + e.staleSeconds * 1000L));
        StringBuilder sb = new StringBuilder(512);
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>");
        sb.append("<event version=\"2.0\" uid=\"").append(escape(e.operatorUid))
          .append("\" type=\"a-f-G-U-C-I\" time=\"").append(now)
          .append("\" start=\"").append(now)
          .append("\" stale=\"").append(stale)
          .append("\" how=\"m-g\">");
        sb.append("<point lat=\"").append(fmt(e.lat))
          .append("\" lon=\"").append(fmt(e.lon))
          .append("\" hae=\"9999999.0\" ce=\"9999999.0\" le=\"9999999.0\"/>");
        sb.append("<detail>");
        sb.append("<contact callsign=\"").append(escape(e.callsign)).append("\"/>");
        sb.append("<__group name=\"Cyan\" role=\"Team Member\"/>");
        sb.append("<emcon")
          .append(" score=\"").append(fmt(clamp01(e.riskScore))).append("\"")
          .append(" dwell_seconds=\"").append(Math.round(e.dwellSeconds)).append("\"");
        if (e.topThreatId != null) {
            sb.append(" top_threat_id=\"").append(escape(e.topThreatId)).append("\"")
              .append(" top_threat_range_km=\"").append(fmt(e.topThreatRangeKm)).append("\"")
              .append(" top_threat_bearing_deg=\"").append(fmt(e.topThreatBearingDeg)).append("\"");
        }
        sb.append("/>");
        sb.append("<remarks>EMCON Sentinel risk update</remarks>");
        sb.append("</detail>");
        sb.append("</event>");
        return sb.toString();
    }

    private static double clamp01(double v) {
        if (v < 0) return 0;
        if (v > 1) return 1;
        return v;
    }

    private static String fmt(double v) {
        return String.format(Locale.US, "%.6f", v);
    }

    private static String escape(String s) {
        if (s == null) return "";
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\"", "&quot;").replace("'", "&apos;");
    }
}
