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

public final class AssetLibrary {

    private final List<AdversarySystem> adversarySystems;
    private final List<RadioProfile> radioProfiles;
    private final List<AORPosture> postures;

    private AssetLibrary(List<AdversarySystem> adversarySystems,
                         List<RadioProfile> radioProfiles,
                         List<AORPosture> postures) {
        this.adversarySystems = Collections.unmodifiableList(adversarySystems);
        this.radioProfiles = Collections.unmodifiableList(radioProfiles);
        this.postures = Collections.unmodifiableList(postures);
    }

    public List<AdversarySystem> adversarySystems() {
        return adversarySystems;
    }

    public List<RadioProfile> radioProfiles() {
        return radioProfiles;
    }

    public List<AORPosture> postures() {
        return postures;
    }

    public AORPosture findPostureById(String id) {
        for (AORPosture p : postures) if (p.id.equals(id)) return p;
        return null;
    }

    /** Backwards-compat: 2-arg load (no postures). Used by existing tests. */
    public static AssetLibrary load(InputStream adversariesJson, InputStream profilesJson) {
        return new AssetLibrary(parseAdversaries(adversariesJson),
                parseProfiles(profilesJson),
                Collections.<AORPosture>emptyList());
    }

    /** Production load: includes pre-loaded AOR postures. */
    public static AssetLibrary load(InputStream adversariesJson, InputStream profilesJson,
                                    List<AORPosture> postures) {
        return new AssetLibrary(parseAdversaries(adversariesJson),
                parseProfiles(profilesJson),
                postures);
    }

    private static List<AdversarySystem> parseAdversaries(InputStream is) {
        JsonObject root = JsonParser.parseReader(new InputStreamReader(is, StandardCharsets.UTF_8)).getAsJsonObject();
        JsonArray arr = root.getAsJsonArray("systems");
        List<AdversarySystem> out = new ArrayList<>(arr.size());
        for (JsonElement el : arr) {
            JsonObject o = el.getAsJsonObject();
            out.add(new AdversarySystem(
                    o.get("id").getAsString(),
                    o.get("display_name").getAsString(),
                    AdversarySystem.Platform.valueOf(o.get("platform").getAsString().toUpperCase()),
                    o.get("frequency_min_mhz").getAsDouble(),
                    o.get("frequency_max_mhz").getAsDouble(),
                    o.get("antenna_gain_dbi").getAsDouble(),
                    o.get("sensitivity_dbm").getAsDouble(),
                    o.get("ground_range_km").getAsDouble(),
                    o.get("airborne_range_km").getAsDouble(),
                    o.get("time_to_fix_seconds").getAsDouble(),
                    o.get("source").getAsString()));
        }
        return out;
    }

    private static List<RadioProfile> parseProfiles(InputStream is) {
        JsonObject root = JsonParser.parseReader(new InputStreamReader(is, StandardCharsets.UTF_8)).getAsJsonObject();
        JsonArray arr = root.getAsJsonArray("profiles");
        List<RadioProfile> out = new ArrayList<>(arr.size());
        for (JsonElement el : arr) {
            JsonObject p = el.getAsJsonObject();
            JsonArray bands = p.getAsJsonArray("bands");
            List<RadioBand> bandList = new ArrayList<>(bands.size());
            for (JsonElement b : bands) {
                JsonObject bo = b.getAsJsonObject();
                bandList.add(new RadioBand(
                        bo.get("freq_mhz").getAsDouble(),
                        bo.get("eirp_dbm").getAsDouble(),
                        bo.get("duty_cycle").getAsDouble(),
                        bo.get("purpose").getAsString()));
            }
            out.add(new RadioProfile(
                    p.get("id").getAsString(),
                    p.get("display_name").getAsString(),
                    bandList));
        }
        return out;
    }
}
