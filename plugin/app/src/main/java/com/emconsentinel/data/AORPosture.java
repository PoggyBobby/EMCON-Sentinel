package com.emconsentinel.data;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * AOR threat posture: a curated worst-case threat envelope for a region. Each
 * threat is positioned by bearing + range FROM the operator (not at fixed lat/lon)
 * so the same posture works wherever the operator physically is.
 *
 * Loaded from assets/aor_postures/*.json. The intent is that an operator who
 * doesn't have specific S2 intel can still pick a posture and get useful EMCON
 * guidance based on the worst-case threat mix typical for that AOR.
 */
public final class AORPosture {

    public final String id;
    public final String name;
    public final String subtitle;
    public final String density;
    public final String description;
    public final List<RelativeThreat> threats;

    public AORPosture(String id, String name, String subtitle, String density,
                      String description, List<RelativeThreat> threats) {
        this.id = id;
        this.name = name;
        this.subtitle = subtitle;
        this.density = density;
        this.description = description;
        this.threats = Collections.unmodifiableList(threats);
    }

    /** A threat positioned by bearing/range FROM the operator. */
    public static final class RelativeThreat {
        public final String systemId;
        public final double bearingDeg;
        public final double rangeKm;
        public final String note;
        public RelativeThreat(String systemId, double bearingDeg, double rangeKm, String note) {
            this.systemId = systemId;
            this.bearingDeg = bearingDeg;
            this.rangeKm = rangeKm;
            this.note = note;
        }
    }

    public static AORPosture load(InputStream is) {
        JsonObject root = JsonParser.parseReader(
                new InputStreamReader(is, StandardCharsets.UTF_8)).getAsJsonObject();
        String id = root.get("id").getAsString();
        String name = root.get("name").getAsString();
        String subtitle = root.has("subtitle") ? root.get("subtitle").getAsString() : "";
        String density = root.has("density") ? root.get("density").getAsString() : "unknown";
        String description = root.has("description") ? root.get("description").getAsString() : "";
        JsonArray arr = root.getAsJsonArray("threats");
        List<RelativeThreat> threats = new ArrayList<>(arr.size());
        for (int i = 0; i < arr.size(); i++) {
            JsonObject t = arr.get(i).getAsJsonObject();
            threats.add(new RelativeThreat(
                    t.get("system_id").getAsString(),
                    t.get("bearing_deg").getAsDouble(),
                    t.get("range_km").getAsDouble(),
                    t.has("note") ? t.get("note").getAsString() : ""));
        }
        return new AORPosture(id, name, subtitle, density, description, threats);
    }
}
