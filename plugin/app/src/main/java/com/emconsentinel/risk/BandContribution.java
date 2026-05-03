package com.emconsentinel.risk;

import com.emconsentinel.data.RadioBand;

/** Per-band contribution to a single asset's P_lock at a given tick. */
public final class BandContribution {
    public final int bandIndex;
    public final RadioBand band;
    public final double pLockContribution;

    public BandContribution(int bandIndex, RadioBand band, double pLockContribution) {
        this.bandIndex = bandIndex;
        this.band = band;
        this.pLockContribution = pLockContribution;
    }
}
