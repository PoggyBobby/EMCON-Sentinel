package com.emconsentinel.cot;

import com.atakmap.coremap.log.Log;

import java.net.DatagramPacket;
import java.net.InetAddress;
import java.net.MulticastSocket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

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
    private String lastErrorClass = null;
    private long suppressedErrorCount = 0;
    // Network I/O on Android's main thread throws NetworkOnMainThreadException.
    // Send packets on a single-thread executor so the UI tick stays responsive.
    private final ExecutorService sender = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "EmconCotEmitter");
        t.setDaemon(true);
        return t;
    });

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
        // Format on the caller's thread (cheap, no I/O) so we capture event state
        // synchronously, then hand the bytes to the sender thread.
        final byte[] bytes = CotXml.format(event).getBytes(StandardCharsets.UTF_8);
        sender.execute(() -> {
            try {
                DatagramPacket pkt = new DatagramPacket(bytes, bytes.length, group, port);
                socket.send(pkt);
                if (lastErrorClass != null) {
                    Log.i(TAG, "CoT emit recovered after " + suppressedErrorCount + " suppressed errors");
                    lastErrorClass = null;
                    suppressedErrorCount = 0;
                }
            } catch (Exception e) {
                // Log first occurrence of each distinct error type; suppress repeats.
                String cls = e.getClass().getName();
                if (!cls.equals(lastErrorClass)) {
                    Log.w(TAG, "CoT emit failed (will suppress repeats): " + e);
                    lastErrorClass = cls;
                    suppressedErrorCount = 0;
                } else {
                    suppressedErrorCount++;
                }
            }
        });
    }

    public void close() {
        sender.shutdownNow();
        if (socket != null) {
            try { socket.close(); } catch (Exception ignored) {}
            socket = null;
        }
    }
}
