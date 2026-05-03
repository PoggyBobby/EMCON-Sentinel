package com.emconsentinel.c2;

import com.atakmap.coremap.log.Log;
import com.emconsentinel.ui.PluginState;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.net.DatagramPacket;
import java.net.InetAddress;
import java.net.MulticastSocket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Receives RF detection events from {@code tools/sdr_bridge.py} (RTL-SDR
 * sidecar). Mirror of {@link C2Bridge} but on multicast group 239.2.3.3:14661.
 *
 * Two event classes drive different state:
 *
 *   "own-tx"        — energy at the operator's drone control band. Confirms
 *                     the operator is transmitting with REAL RF, not the
 *                     manual START KEYING toggle. Forces
 *                     {@code PluginState.setSdrConfirmedKeying(true)}.
 *
 *   "adversary-ew"  — energy at a published adversary EW band center.
 *                     Surfaces a "real adversary EW activity detected" flag
 *                     in PluginState that the HUD can show.
 *
 * If the SDR sidecar isn't running, no packets arrive and the SDR state
 * stays "not present" — plugin works fine without it.
 */
public final class SdrBridge {

    private static final String TAG = "EmconSentinel.SdrBridge";
    public static final String DEFAULT_GROUP = "239.2.3.3";
    public static final int    DEFAULT_PORT  = 14661;
    private static final long  STALE_MS      = 30000;     // 30 s — sidecar scan period is ~10s
    private static final int   READ_TIMEOUT_MS = 1500;
    private static final long  OWN_TX_FRESH_MS = 5000;    // Don't forget own-TX for 5 s after detection

    private final PluginState state;
    private final String groupAddr;
    private final int port;
    private MulticastSocket socket;
    private Thread thread;
    private final AtomicBoolean running = new AtomicBoolean(false);

    private long lastEventMs = 0;
    private long lastOwnTxMs = 0;
    private long lastAdversaryEwMs = 0;

    public SdrBridge(PluginState state) {
        this(state, DEFAULT_GROUP, DEFAULT_PORT);
    }

    public SdrBridge(PluginState state, String group, int port) {
        this.state = state;
        this.groupAddr = group;
        this.port = port;
    }

    public void start() {
        if (!running.compareAndSet(false, true)) return;
        thread = new Thread(this::loop, "EmconSdrBridge");
        thread.setDaemon(true);
        thread.start();
        Log.i(TAG, "started; listening on " + groupAddr + ":" + port);
    }

    public void stop() {
        running.set(false);
        if (socket != null) {
            try { socket.close(); } catch (Exception ignored) {}
            socket = null;
        }
        Log.i(TAG, "stopped");
    }

    private void loop() {
        byte[] buf = new byte[4096];
        try {
            socket = new MulticastSocket(port);
            socket.setSoTimeout(READ_TIMEOUT_MS);
            socket.joinGroup(InetAddress.getByName(groupAddr));
            Log.i(TAG, "joined multicast group " + groupAddr + ":" + port);
        } catch (Exception e) {
            Log.w(TAG, "could not join multicast group: " + e);
            running.set(false);
            return;
        }

        while (running.get()) {
            DatagramPacket pkt = new DatagramPacket(buf, buf.length);
            try {
                socket.receive(pkt);
                String json = new String(pkt.getData(), 0, pkt.getLength(), StandardCharsets.UTF_8);
                handle(json);
            } catch (java.net.SocketTimeoutException ignore) {
                // periodic — used to expire stale state
                expireStale();
            } catch (Exception e) {
                if (running.get()) Log.w(TAG, "recv error: " + e);
            }
        }
    }

    private void handle(String json) {
        try {
            JsonObject o = JsonParser.parseString(json).getAsJsonObject();
            long now = System.currentTimeMillis();
            lastEventMs = now;
            String type = o.has("type") ? o.get("type").getAsString() : "";
            if ("hello".equals(type) || "heartbeat".equals(type)) {
                state.setSdrPresent(true);
                return;
            }
            if (!"detection".equals(type)) return;

            String klass = o.has("class") ? o.get("class").getAsString() : "";
            double freqMhz = o.has("freq_mhz") ? o.get("freq_mhz").getAsDouble() : 0;
            double powerDbm = o.has("power_dbm") ? o.get("power_dbm").getAsDouble() : 0;
            String label = o.has("label") ? o.get("label").getAsString() : "";

            if ("own-tx".equals(klass)) {
                lastOwnTxMs = now;
                state.setSdrConfirmedKeying(true);
                Log.i(TAG, "own-TX confirmed by SDR: " + label + " @ " + freqMhz + " MHz");
            } else if ("adversary-ew".equals(klass)) {
                lastAdversaryEwMs = now;
                state.setSdrAdversaryEwActive(true, label, freqMhz, powerDbm);
                Log.i(TAG, "adversary EW active: " + label + " @ " + freqMhz + " MHz");
            }
        } catch (Exception e) {
            Log.w(TAG, "parse failed: " + e);
        }
    }

    private void expireStale() {
        long now = System.currentTimeMillis();
        if (lastOwnTxMs > 0 && now - lastOwnTxMs > OWN_TX_FRESH_MS) {
            state.setSdrConfirmedKeying(false);
            lastOwnTxMs = 0;
        }
        if (lastEventMs > 0 && now - lastEventMs > STALE_MS) {
            state.setSdrPresent(false);
            state.setSdrAdversaryEwActive(false, "", 0, 0);
            lastEventMs = 0;
            lastAdversaryEwMs = 0;
        }
    }
}
