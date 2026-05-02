package com.emconsentinel.data;

public final class RadioBand {
    public final double freqMhz;
    public final double eirpDbm;
    public final double dutyCycle;
    public final String purpose;

    public RadioBand(double freqMhz, double eirpDbm, double dutyCycle, String purpose) {
        this.freqMhz = freqMhz;
        this.eirpDbm = eirpDbm;
        this.dutyCycle = dutyCycle;
        this.purpose = purpose;
    }
}
