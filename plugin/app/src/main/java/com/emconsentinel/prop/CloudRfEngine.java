package com.emconsentinel.prop;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Calls CloudRF /path/ for terrain-aware path loss. Falls back to FreeSpaceEngine on any
 * failure or after FAILURES_BEFORE_TRIP consecutive errors (circuit-breaker).
 *
 * The fallback path is deliberately exposed via PropagationResult.mode so the UI can render
 * a "FREE-SPACE FALLBACK — TERRAIN NOT MODELED" banner whenever CloudRF is degraded.
 */
public final class CloudRfEngine implements PathLossEngine {

    private static final String ENDPOINT = "https://api.cloudrf.com/path/";
    private static final int CONNECT_TIMEOUT_MS = 4_000;
    private static final int READ_TIMEOUT_MS = 8_000;
    private static final int FAILURES_BEFORE_TRIP = 3;

    private final String apiKey;
    private final FreeSpaceEngine fallback;
    private final AtomicInteger failures = new AtomicInteger(0);

    public CloudRfEngine(String apiKey) {
        this.apiKey = apiKey;
        this.fallback = new FreeSpaceEngine();
    }

    public boolean isCircuitTripped() {
        return failures.get() >= FAILURES_BEFORE_TRIP;
    }

    public void resetCircuit() {
        failures.set(0);
    }

    @Override
    public PropagationResult pathLoss(double txLat, double txLon, double rxLat, double rxLon, double freqMhz) {
        if (apiKey == null || apiKey.isEmpty() || isCircuitTripped()) {
            return fallback.pathLoss(txLat, txLon, rxLat, rxLon, freqMhz);
        }
        try {
            JsonObject tx = new JsonObject();
            tx.addProperty("lat", txLat);
            tx.addProperty("lon", txLon);
            tx.addProperty("frq", freqMhz);

            JsonObject rx = new JsonObject();
            rx.addProperty("lat", rxLat);
            rx.addProperty("lon", rxLon);

            JsonObject body = new JsonObject();
            body.add("transmitter", tx);
            body.add("receiver", rx);

            HttpURLConnection conn = (HttpURLConnection) new URL(ENDPOINT).openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("key", apiKey);
            conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(READ_TIMEOUT_MS);
            conn.setDoOutput(true);

            try (OutputStream os = conn.getOutputStream()) {
                os.write(body.toString().getBytes(StandardCharsets.UTF_8));
            }
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) {
                failures.incrementAndGet();
                return fallback.pathLoss(txLat, txLon, rxLat, rxLon, freqMhz);
            }
            StringBuilder sb = new StringBuilder();
            try (BufferedReader r = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = r.readLine()) != null) sb.append(line);
            }
            JsonObject root = JsonParser.parseString(sb.toString()).getAsJsonObject();
            double pathLossDb = root.getAsJsonObject("Receiver").get("path_loss_dB").getAsDouble();
            failures.set(0);
            return new PropagationResult(pathLossDb, PropagationResult.Mode.CLOUDRF);
        } catch (Exception e) {
            failures.incrementAndGet();
            return fallback.pathLoss(txLat, txLon, rxLat, rxLon, freqMhz);
        }
    }
}
