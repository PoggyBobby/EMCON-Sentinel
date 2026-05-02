package com.emconsentinel.data;

import org.junit.Test;

import java.io.FileInputStream;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public class DemoScenarioTest {

    @Test public void loadsRubiconPokrovskScenario() throws Exception {
        DemoScenario s = DemoScenario.load(
                new FileInputStream("src/main/assets/demo_scenarios/rubicon_pokrovsk.json"));
        assertEquals("Rubicon — Pokrovsk axis", s.name);
        assertTrue("description must be cited and non-trivial", s.description.length() > 50);
        assertEquals("expected 3 adversaries in scenario", 3, s.adversaries.size());

        // operator near Pokrovsk lat ~48.28, lon ~37.17
        assertTrue("operator lat must be in eastern-Ukraine band 47-49N", s.operatorLat > 47 && s.operatorLat < 49);
        assertTrue("operator lon must be in 36-39E band", s.operatorLon > 36 && s.operatorLon < 39);

        // first entry must reference a system id in our adversary library
        assertEquals("r-330zh-zhitel", s.adversaries.get(0).systemId);
    }
}
