package com.emconsentinel.c2;

import com.atakmap.coremap.log.Log;
import com.emconsentinel.ui.PluginState;

import java.net.DatagramPacket;
import java.net.InetAddress;
import java.net.MulticastSocket;
import java.net.NetworkInterface;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Background thread that listens on UDP multicast for C2Message JSON frames
 * published by {@code tools/c2_bridge.py}, parses them, and pushes the
 * resulting {@link C2Status} into {@link PluginState}.
 *
 * Stale handling: if no message arrives for STALE_MS (default 4 s), we
 * automatically downgrade the state to disconnected so the dial stops
 * trusting last-seen RF activity.
 *
 * No fake data anywhere — if the bridge isn't running, this listener simply
 * never gets a packet and {@code PluginState.c2Status()} stays disconnected.
 * The plugin keeps working with the manual keying toggle in that case.
 */
public final class C2Bridge {

    private static final String TAG = "EmconSentinel.C2Bridge";
    public static final String DEFAULT_GROUP = "239.2.3.2";
    public static final int    DEFAULT_PORT  = 14660;
    private static final long  STALE_MS      = 4000;
    private static final int   READ_TIMEOUT_MS = 1500;

    private final PluginState state;
    private final String groupAddr;
    private final int port;
    private MulticastSocket socket;
    private Thread thread;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public C2Bridge(PluginState state) {
        this(state, DEFAULT_GROUP, DEFAULT_PORT);
    }

    public C2Bridge(PluginState state, String groupAddr, int port) {
        this.state = state;
        this.groupAddr = groupAddr;
        this.port = port;
    }

    public void start() {
        if (!running.compareAndSet(false, true)) return;
        thread = new Thread(this::runLoop, "EmconSentinel-C2Bridge");
        thread.setDaemon(true);
        thread.start();
    }

    public void stop() {
        running.set(false);
        if (socket != null) {
            try { socket.close(); } catch (Exception ignored) {}
            socket = null;
        }
        if (thread != null) {
            thread.interrupt();
            thread = null;
        }
    }

    private void runLoop() {
        try {
            socket = new MulticastSocket(port);
            socket.setSoTimeout(READ_TIMEOUT_MS);
            InetAddress group = InetAddress.getByName(groupAddr);
            try {
                NetworkInterface ni = NetworkInterface.getByInetAddress(InetAddress.getLocalHost());
                if (ni != null) socket.joinGroup(new java.net.InetSocketAddress(group, port), ni);
                else socket.joinGroup(group);
            } catch (Exception e) {
                socket.joinGroup(group);
            }
            Log.i(TAG, "listening on " + groupAddr + ":" + port);
        } catch (Exception e) {
            Log.e(TAG, "failed to bind multicast socket", e);
            running.set(false);
            return;
        }

        byte[] buf = new byte[8192];
        while (running.get()) {
            try {
                DatagramPacket pkt = new DatagramPacket(buf, buf.length);
                socket.receive(pkt);
                String json = new String(pkt.getData(), 0, pkt.getLength(), StandardCharsets.UTF_8);
                try {
                    C2Status s = C2Message.parse(json);
                    state.setC2Status(s);
                } catch (Exception e) {
                    Log.w(TAG, "malformed C2 frame from " + pkt.getAddress() + ": " + e.getMessage());
                }
            } catch (java.net.SocketTimeoutException e) {
                // Normal: no traffic in READ_TIMEOUT_MS. Check staleness and continue.
                C2Status cur = state.c2Status();
                if (cur != null && cur.connected
                        && (System.currentTimeMillis() - cur.lastUpdateMs) > STALE_MS) {
                    Log.i(TAG, "C2 link gone stale — marking disconnected");
                    state.setC2Status(C2Status.disconnected());
                }
            } catch (Exception e) {
                if (running.get()) Log.w(TAG, "receive error: " + e.getMessage());
            }
        }
        Log.i(TAG, "stopped");
    }
}
