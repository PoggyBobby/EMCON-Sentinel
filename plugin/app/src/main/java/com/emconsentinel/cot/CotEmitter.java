package com.emconsentinel.cot;

import com.atakmap.coremap.log.Log;

import java.net.DatagramPacket;
import java.net.InetAddress;
import java.net.MulticastSocket;
import java.nio.charset.StandardCharsets;

/**
 * Fire-and-forget UDP multicast sender for CoT events. Default group + port match
 * the ATAK SA mesh: 239.2.3.1:6969. Tolerates failure silently — a downed network
 * must not crash the plugin tick loop.
 */
public final class CotEmitter {

    private static final String TAG = "EmconSentinel.CotEmitter";
    public static final String DEFAULT_GROUP = "239.2.3.1";
    public static final int    DEFAULT_PORT  = 6969;

    private final InetAddress group;
    private final int port;
    private MulticastSocket socket;
    private boolean enabled = true;

    public CotEmitter() throws Exception {
        this(DEFAULT_GROUP, DEFAULT_PORT);
    }

    public CotEmitter(String groupAddr, int port) throws Exception {
        this.group = InetAddress.getByName(groupAddr);
        this.port = port;
        this.socket = new MulticastSocket();
        this.socket.setTimeToLive(2);  // local subnet only
    }

    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public boolean isEnabled() { return enabled; }

    public void emit(CotEvent event) {
        if (!enabled || socket == null) return;
        try {
            byte[] bytes = CotXml.format(event).getBytes(StandardCharsets.UTF_8);
            DatagramPacket pkt = new DatagramPacket(bytes, bytes.length, group, port);
            socket.send(pkt);
        } catch (Exception e) {
            Log.w(TAG, "CoT emit failed (suppressing): " + e.getMessage());
        }
    }

    public void close() {
        if (socket != null) {
            try { socket.close(); } catch (Exception ignored) {}
            socket = null;
        }
    }
}
