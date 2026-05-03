package com.emconsentinel.cot;

import android.os.Bundle;

import com.atakmap.comms.CommsMapComponent;
import com.atakmap.comms.CotServiceRemote;
import com.atakmap.coremap.cot.event.CotDetail;
import com.atakmap.coremap.cot.event.CotEvent;
import com.atakmap.coremap.cot.event.CotPoint;
import com.atakmap.coremap.log.Log;

import com.emconsentinel.ui.PluginState;

import java.util.function.Consumer;

/**
 * Subscribes to ATAK's incoming CoT pipeline and filters for EMCON-Sentinel
 * reports from OTHER operators. Each qualifying inbound CoT event is parsed
 * into a {@link BuddyReport} and dispatched to the supplied consumer.
 *
 * Filter rules:
 *   1. Drop events whose UID matches our own operator UID (loopback).
 *   2. Keep only events that carry a {@code <emcon>} detail child — that's
 *      our extension, regular ATAK clients never emit it.
 *
 * Hooks into {@code CommsMapComponent.addOnCotEventListener}, the same surface
 * ATAK's own CotMapComponent uses internally.
 */
public final class CotReceiver {

    private static final String TAG = "EmconSentinel.CotReceiver";

    private final PluginState state;
    private final Consumer<BuddyReport> sink;
    private CotServiceRemote.CotEventListener listener;

    public CotReceiver(PluginState state, Consumer<BuddyReport> sink) {
        this.state = state;
        this.sink = sink;
    }

    public void start() {
        try {
            listener = (CotEvent ev, Bundle extra) -> handle(ev);
            CommsMapComponent.getInstance().addOnCotEventListener(listener);
            Log.i(TAG, "registered CoT receiver — listening for EMCON-tagged buddy reports");
        } catch (Exception e) {
            Log.w(TAG, "could not register CoT listener: " + e);
        }
    }

    public void stop() {
        if (listener != null) {
            try {
                CommsMapComponent.getInstance().removeOnCotEventListener(listener);
            } catch (Exception ignored) {}
            listener = null;
        }
    }

    private void handle(CotEvent ev) {
        if (ev == null) return;
        // Loopback: drop our own broadcasts
        String uid = ev.getUID();
        if (uid == null) return;
        if (state != null && uid.equals(state.operatorUid())) return;

        CotDetail detail = ev.getDetail();
        if (detail == null) return;
        CotDetail emcon = detail.getFirstChildByName(0, "emcon");
        if (emcon == null) return;

        // Parse the <emcon> child's attributes — same schema CotXml.format emits
        double score = parseDouble(emcon.getAttribute("score"), 0);
        double dwell = parseDouble(emcon.getAttribute("dwell_s"), 0);
        String topId = emcon.getAttribute("top_threat_id");
        double topRange = parseDouble(emcon.getAttribute("top_threat_range_km"), 0);
        double topBearing = parseDouble(emcon.getAttribute("top_threat_bearing_deg"), 0);

        // Position from the standard CoT point element
        CotPoint pt = ev.getCotPoint();
        if (pt == null) return;

        // Callsign from <detail><contact callsign="..."/>
        String callsign = uid;
        try {
            CotDetail contact = detail.getFirstChildByName(0, "contact");
            if (contact != null) {
                String cs = contact.getAttribute("callsign");
                if (cs != null && !cs.isEmpty()) callsign = cs;
            }
        } catch (Exception ignored) {}

        BuddyReport report = new BuddyReport(uid, callsign, pt.getLat(), pt.getLon(),
                score, dwell, topId, topRange, topBearing, System.currentTimeMillis());
        if (sink != null) sink.accept(report);
    }

    private static double parseDouble(String s, double def) {
        if (s == null || s.isEmpty()) return def;
        try { return Double.parseDouble(s); } catch (NumberFormatException e) { return def; }
    }
}
