package com.emconsentinel.data;

import org.junit.Test;

import java.io.ByteArrayInputStream;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

public class AssetLibraryTest {

    private static final String ADV_JSON = "{\"systems\":[{"
            + "\"id\":\"x\",\"display_name\":\"X\",\"platform\":\"ground_vehicle\","
            + "\"frequency_min_mhz\":100,\"frequency_max_mhz\":2000,"
            + "\"antenna_gain_dbi\":12.0,\"sensitivity_dbm\":-110,"
            + "\"ground_range_km\":25,\"airborne_range_km\":50,"
            + "\"time_to_fix_seconds\":90,\"source\":\"test\"}]}";

    private static final String PROF_JSON = "{\"profiles\":[{"
            + "\"id\":\"p\",\"display_name\":\"P\","
            + "\"bands\":[{\"freq_mhz\":2400,\"eirp_dbm\":20,\"duty_cycle\":0.8,\"purpose\":\"ctrl\"}]"
            + "}]}";

    @Test
    public void parsesInlineAdversariesAndProfiles() {
        AssetLibrary lib = AssetLibrary.load(
                new ByteArrayInputStream(ADV_JSON.getBytes(StandardCharsets.UTF_8)),
                new ByteArrayInputStream(PROF_JSON.getBytes(StandardCharsets.UTF_8)));
        assertEquals(1, lib.adversarySystems().size());
        AdversarySystem a = lib.adversarySystems().get(0);
        assertEquals("x", a.id);
        assertEquals(AdversarySystem.Platform.GROUND_VEHICLE, a.platform);
        assertEquals(-110.0, a.sensitivityDbm, 1e-9);
        assertTrue(a.coversFrequency(900));
        assertFalse(a.coversFrequency(3000));

        assertEquals(1, lib.radioProfiles().size());
        RadioProfile p = lib.radioProfiles().get(0);
        assertEquals(1, p.bands.size());
        assertEquals(2400.0, p.bands.get(0).freqMhz, 1e-9);
        assertEquals(0.8, p.bands.get(0).dutyCycle, 1e-9);
    }

    @Test
    public void parsesShippedAssetFiles() throws Exception {
        AssetLibrary lib = AssetLibrary.load(
                new FileInputStream("src/main/assets/adversary_df_systems.json"),
                new FileInputStream("src/main/assets/radio_profiles.json"));
        assertEquals("expected 5 OSINT-cited adversary systems", 5, lib.adversarySystems().size());
        assertEquals("expected 6 radio profiles", 6, lib.radioProfiles().size());

        AdversarySystem zhitel = lib.adversarySystems().stream()
                .filter(s -> s.id.equals("r-330zh-zhitel"))
                .findFirst()
                .orElse(null);
        assertNotNull("Zhitel must be present", zhitel);
        assertEquals(AdversarySystem.Platform.GROUND_VEHICLE, zhitel.platform);
        assertEquals(25.0, zhitel.groundRangeKm, 1e-9);
        assertEquals(90.0, zhitel.timeToFixSeconds, 1e-9);
        assertTrue("Zhitel covers HF/VHF/UHF up to 2 GHz", zhitel.coversFrequency(900));
        assertFalse("Zhitel does not cover 2.4 GHz (cap is 2000 MHz per OSINT)", zhitel.coversFrequency(2400));
        assertFalse("Zhitel does not cover 5.8 GHz video band", zhitel.coversFrequency(5800));
        assertTrue("source must be cited and non-empty", zhitel.source.length() > 10);

        AdversarySystem leer = lib.adversarySystems().stream()
                .filter(s -> s.id.equals("leer-3"))
                .findFirst()
                .orElse(null);
        assertNotNull("Leer-3 (airborne) must be present", leer);
        assertEquals(AdversarySystem.Platform.AIRBORNE, leer.platform);

        RadioProfile mavic = lib.radioProfiles().stream()
                .filter(p -> p.id.equals("dji-mavic-3"))
                .findFirst()
                .orElse(null);
        assertNotNull("Mavic 3 profile must be present", mavic);
        assertEquals(2, mavic.bands.size());
    }

    @Test
    public void everyAdversaryEntryHasNonEmptyOsintSource() throws Exception {
        AssetLibrary lib = AssetLibrary.load(
                new FileInputStream("src/main/assets/adversary_df_systems.json"),
                new FileInputStream("src/main/assets/radio_profiles.json"));
        for (AdversarySystem s : lib.adversarySystems()) {
            assertNotNull("source missing on " + s.id, s.source);
            assertTrue("source on " + s.id + " is too short to be a real citation",
                    s.source.length() > 10);
        }
    }
}
