package com.emconsentinel.data;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class DemoScenario {

    public static final class PlacedEntry {
        public final String systemId;
        public final double lat;
        public final double lon;
        public final String note;
        /** When true, this adversary is on the map but invisible to the operator
         * until a friendly scanner detects it. Used by ARGUS-driven scenarios. */
        public final boolean hidden;
        public PlacedEntry(String systemId, double lat, double lon, String note, boolean hidden) {
            this.systemId = systemId;
            this.lat = lat;
            this.lon = lon;
            this.note = note;
            this.hidden = hidden;
        }
    }

    public static final class ArgusEntry {
        public final String id;
        public final String callsign;
        public final double altitudeMeters;
        public final double scanRadiusKm;
        public final double speedKmh;
        public final List<double[]> waypoints;   // each = {lat, lon}
        public ArgusEntry(String id, String callsign, double altitudeMeters,
                          double scanRadiusKm, double speedKmh, List<double[]> waypoints) {
            this.id = id;
            this.callsign = callsign;
            this.altitudeMeters = altitudeMeters;
            this.scanRadiusKm = scanRadiusKm;
            this.speedKmh = speedKmh;
            this.waypoints = waypoints;
        }
    }

    public final String name;
    public final String description;
    public final double operatorLat;
    public final double operatorLon;
    public final String operatorLabel;
    public final List<PlacedEntry> adversaries;
    public final List<ArgusEntry> argusDrones;

    private DemoScenario(String name, String description,
                          double operatorLat, double operatorLon, String operatorLabel,
                          List<PlacedEntry> adversaries, List<ArgusEntry> argusDrones) {
        this.name = name;
        this.description = description;
        this.operatorLat = operatorLat;
        this.operatorLon = operatorLon;
        this.operatorLabel = operatorLabel;
        this.adversaries = Collections.unmodifiableList(adversaries);
        this.argusDrones = Collections.unmodifiableList(argusDrones);
    }

    public static DemoScenario load(InputStream is) {
        JsonObject root = JsonParser.parseReader(new InputStreamReader(is, StandardCharsets.UTF_8)).getAsJsonObject();
        JsonObject op = root.getAsJsonObject("operator");

        // Support both legacy "adversaries" (visible) and new "hidden_adversaries"
        // (invisible until ARGUS reveals them). Both can coexist in one scenario.
        List<PlacedEntry> entries = new ArrayList<>();
        if (root.has("adversaries")) {
            for (JsonElement el : root.getAsJsonArray("adversaries")) {
                entries.add(parseEntry(el.getAsJsonObject(), false));
            }
        }
        if (root.has("hidden_adversaries")) {
            for (JsonElement el : root.getAsJsonArray("hidden_adversaries")) {
                entries.add(parseEntry(el.getAsJsonObject(), true));
            }
        }

        List<ArgusEntry> drones = new ArrayList<>();
        if (root.has("argus_drones")) {
            for (JsonElement el : root.getAsJsonArray("argus_drones")) {
                JsonObject d = el.getAsJsonObject();
                List<double[]> wp = new ArrayList<>();
                for (JsonElement w : d.getAsJsonArray("waypoints")) {
                    JsonObject p = w.getAsJsonObject();
                    wp.add(new double[] { p.get("lat").getAsDouble(), p.get("lon").getAsDouble() });
                }
                drones.add(new ArgusEntry(
                        d.get("id").getAsString(),
                        d.get("callsign").getAsString(),
                        d.has("altitude_m") ? d.get("altitude_m").getAsDouble() : 5000,
                        d.has("scan_radius_km") ? d.get("scan_radius_km").getAsDouble() : 15,
                        d.has("speed_kmh") ? d.get("speed_kmh").getAsDouble() : 200,
                        wp));
            }
        }

        return new DemoScenario(
                root.has("name") ? root.get("name").getAsString() : "Demo",
                root.has("description") ? root.get("description").getAsString() : "",
                op.get("lat").getAsDouble(),
                op.get("lon").getAsDouble(),
                op.has("label") ? op.get("label").getAsString() : "Operator",
                entries, drones);
    }

    private static PlacedEntry parseEntry(JsonObject o, boolean hidden) {
        return new PlacedEntry(
                o.get("system_id").getAsString(),
                o.get("lat").getAsDouble(),
                o.get("lon").getAsDouble(),
                o.has("note") ? o.get("note").getAsString() : "",
                hidden);
    }
}
