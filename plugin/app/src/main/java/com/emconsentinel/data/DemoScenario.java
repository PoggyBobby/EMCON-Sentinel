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
        public PlacedEntry(String systemId, double lat, double lon, String note) {
            this.systemId = systemId;
            this.lat = lat;
            this.lon = lon;
            this.note = note;
        }
    }

    public final String name;
    public final String description;
    public final double operatorLat;
    public final double operatorLon;
    public final String operatorLabel;
    public final List<PlacedEntry> adversaries;

    private DemoScenario(String name, String description,
                          double operatorLat, double operatorLon, String operatorLabel,
                          List<PlacedEntry> adversaries) {
        this.name = name;
        this.description = description;
        this.operatorLat = operatorLat;
        this.operatorLon = operatorLon;
        this.operatorLabel = operatorLabel;
        this.adversaries = Collections.unmodifiableList(adversaries);
    }

    public static DemoScenario load(InputStream is) {
        JsonObject root = JsonParser.parseReader(new InputStreamReader(is, StandardCharsets.UTF_8)).getAsJsonObject();
        JsonObject op = root.getAsJsonObject("operator");
        JsonArray arr = root.getAsJsonArray("adversaries");
        List<PlacedEntry> entries = new ArrayList<>(arr.size());
        for (JsonElement el : arr) {
            JsonObject o = el.getAsJsonObject();
            entries.add(new PlacedEntry(
                    o.get("system_id").getAsString(),
                    o.get("lat").getAsDouble(),
                    o.get("lon").getAsDouble(),
                    o.has("note") ? o.get("note").getAsString() : ""));
        }
        return new DemoScenario(
                root.has("name") ? root.get("name").getAsString() : "Demo",
                root.has("description") ? root.get("description").getAsString() : "",
                op.get("lat").getAsDouble(),
                op.get("lon").getAsDouble(),
                op.has("label") ? op.get("label").getAsString() : "Operator",
                entries);
    }
}
