package com.emconsentinel.prop;

import com.emconsentinel.util.Geo;

public final class FreeSpaceEngine implements PathLossEngine {

    @Override
    public PropagationResult pathLoss(double txLat, double txLon, double rxLat, double rxLon, double freqMhz) {
        double dKm = Math.max(0.001, Geo.distanceKm(txLat, txLon, rxLat, rxLon));
        double fspl = 20.0 * Math.log10(dKm) + 20.0 * Math.log10(freqMhz) + 32.44;
        return new PropagationResult(fspl, PropagationResult.Mode.FREE_SPACE);
    }
}
