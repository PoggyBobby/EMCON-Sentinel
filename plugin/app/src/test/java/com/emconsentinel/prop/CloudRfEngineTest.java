package com.emconsentinel.prop;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public class CloudRfEngineTest {

    @Test
    public void emptyApiKeyForcesFallback() {
        CloudRfEngine eng = new CloudRfEngine("");
        PropagationResult r = eng.pathLoss(0, 0, 0, 0.05, 2400);
        assertEquals(PropagationResult.Mode.FREE_SPACE, r.mode);
        assertTrue(r.pathLossDb > 0);
    }

    @Test
    public void nullApiKeyForcesFallback() {
        CloudRfEngine eng = new CloudRfEngine(null);
        PropagationResult r = eng.pathLoss(0, 0, 0, 0.05, 2400);
        assertEquals(PropagationResult.Mode.FREE_SPACE, r.mode);
    }

    @Test
    public void invalidKeyTripsCircuitAfterFailures() {
        // Use a bogus key; the request will fail (auth or network). We expect FSPL fallback
        // and the circuit to remain tripped after FAILURES_BEFORE_TRIP errors.
        CloudRfEngine eng = new CloudRfEngine("DEFINITELY_NOT_A_REAL_KEY");
        for (int i = 0; i < 5; i++) {
            PropagationResult r = eng.pathLoss(0, 0, 0, 0.05, 2400);
            assertEquals("fallback should be FREE_SPACE", PropagationResult.Mode.FREE_SPACE, r.mode);
        }
        assertTrue("circuit should be tripped after repeated failures", eng.isCircuitTripped());
    }
}
