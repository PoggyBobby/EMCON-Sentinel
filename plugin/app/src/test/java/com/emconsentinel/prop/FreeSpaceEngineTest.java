package com.emconsentinel.prop;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public class FreeSpaceEngineTest {

    private final FreeSpaceEngine eng = new FreeSpaceEngine();

    @Test
    public void fsplKnownValueAt5kmAt2400Mhz() {
        // 20*log10(5) + 20*log10(2400) + 32.44 ≈ 14.0 + 67.6 + 32.44 ≈ 114.0 dB
        PropagationResult r = eng.pathLoss(0, 0, 0, 5.0 / 111.0, 2400);
        assertEquals(114.0, r.pathLossDb, 0.5);
        assertEquals(PropagationResult.Mode.FREE_SPACE, r.mode);
    }

    @Test
    public void fsplKnownValueAt1kmAt5800Mhz() {
        // 20*log10(1) + 20*log10(5800) + 32.44 ≈ 0 + 75.3 + 32.44 ≈ 107.7 dB
        PropagationResult r = eng.pathLoss(0, 0, 0, 1.0 / 111.0, 5800);
        assertEquals(107.7, r.pathLossDb, 0.5);
    }

    @Test
    public void doublingDistanceAdds6db() {
        PropagationResult r1 = eng.pathLoss(0, 0, 0, 1.0 / 111.0, 2400);
        PropagationResult r2 = eng.pathLoss(0, 0, 0, 2.0 / 111.0, 2400);
        assertEquals(6.0, r2.pathLossDb - r1.pathLossDb, 0.1);
    }

    @Test
    public void closerPointsHaveLessPathLoss() {
        double near = eng.pathLoss(0, 0, 0, 0.05, 2400).pathLossDb;
        double mid  = eng.pathLoss(0, 0, 0, 0.10, 2400).pathLossDb;
        double far  = eng.pathLoss(0, 0, 0, 0.30, 2400).pathLossDb;
        assertTrue(near < mid && mid < far);
    }
}
