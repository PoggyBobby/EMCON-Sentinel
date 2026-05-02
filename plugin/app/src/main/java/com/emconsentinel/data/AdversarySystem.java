package com.emconsentinel.data;

public final class AdversarySystem {
    public enum Platform { GROUND_VEHICLE, AIRBORNE }

    public final String id;
    public final String displayName;
    public final Platform platform;
    public final double frequencyMinMhz;
    public final double frequencyMaxMhz;
    public final double antennaGainDbi;
    public final double sensitivityDbm;
    public final double groundRangeKm;
    public final double airborneRangeKm;
    public final double timeToFixSeconds;
    public final String source;

    public AdversarySystem(
            String id,
            String displayName,
            Platform platform,
            double frequencyMinMhz,
            double frequencyMaxMhz,
            double antennaGainDbi,
            double sensitivityDbm,
            double groundRangeKm,
            double airborneRangeKm,
            double timeToFixSeconds,
            String source) {
        this.id = id;
        this.displayName = displayName;
        this.platform = platform;
        this.frequencyMinMhz = frequencyMinMhz;
        this.frequencyMaxMhz = frequencyMaxMhz;
        this.antennaGainDbi = antennaGainDbi;
        this.sensitivityDbm = sensitivityDbm;
        this.groundRangeKm = groundRangeKm;
        this.airborneRangeKm = airborneRangeKm;
        this.timeToFixSeconds = timeToFixSeconds;
        this.source = source;
    }

    public boolean coversFrequency(double freqMhz) {
        return freqMhz >= frequencyMinMhz && freqMhz <= frequencyMaxMhz;
    }
}
