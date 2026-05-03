package com.emconsentinel.c2;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

/**
 * Wire-format parser for the JSON payload that {@code tools/c2_bridge.py} broadcasts
 * over UDP multicast (group 239.2.3.2 port 14660 by default).
 *
 * Schema (versioned):
 * <pre>
 * {
 *   "v": 1,
 *   "ts": 1700000000.123,            // epoch seconds
 *   "connected": true,
 *   "radio_model": "MicoAir LR900-F",
 *   "center_freq_mhz": 915.0,
 *   "tx_eirp_dbm": 27.0,
 *   "rssi_dbm": -82.0,                // local RSSI; null if unknown
 *   "rem_rssi_dbm": -78.0,            // remote (drone) RSSI; null if unknown
 *   "tx_bytes_per_sec": 124,
 *   "rx_bytes_per_sec": 612,
 *   "is_transmitting_now": true,
 *   "last_tx_ms": 1700000000123       // epoch ms of last observed TX frame
 * }
 * </pre>
 */
public final class C2Message {

    private C2Message() {}

    public static C2Status parse(String json) {
        JsonObject o = JsonParser.parseString(json).getAsJsonObject();
        long lastUpdateMs = (long) (o.get("ts").getAsDouble() * 1000);
        return new C2Status(
                getBool(o, "connected", false),
                lastUpdateMs,
                getStr(o, "radio_model", ""),
                getDouble(o, "center_freq_mhz", 0.0),
                getDouble(o, "tx_eirp_dbm", 0.0),
                getNullableDouble(o, "rssi_dbm"),
                getNullableDouble(o, "rem_rssi_dbm"),
                getLong(o, "tx_bytes_per_sec", 0),
                getLong(o, "rx_bytes_per_sec", 0),
                getBool(o, "is_transmitting_now", false),
                getLong(o, "last_tx_ms", 0));
    }

    private static String getStr(JsonObject o, String k, String d) {
        return o.has(k) && !o.get(k).isJsonNull() ? o.get(k).getAsString() : d;
    }
    private static boolean getBool(JsonObject o, String k, boolean d) {
        return o.has(k) && !o.get(k).isJsonNull() ? o.get(k).getAsBoolean() : d;
    }
    private static double getDouble(JsonObject o, String k, double d) {
        return o.has(k) && !o.get(k).isJsonNull() ? o.get(k).getAsDouble() : d;
    }
    private static double getNullableDouble(JsonObject o, String k) {
        return o.has(k) && !o.get(k).isJsonNull() ? o.get(k).getAsDouble() : Double.NaN;
    }
    private static long getLong(JsonObject o, String k, long d) {
        return o.has(k) && !o.get(k).isJsonNull() ? o.get(k).getAsLong() : d;
    }
}
