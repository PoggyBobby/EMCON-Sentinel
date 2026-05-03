package com.emconsentinel.c2;

/**
 * Snapshot of the C2 (command-and-control) telemetry-link state, as reported by
 * the Python sidecar bridge (tools/c2_bridge.py) over UDP multicast.
 *
 * The sidecar parses real MAVLink frames coming off the operator's telemetry
 * radio (e.g., MicoAir LR900-F at 915 MHz) and emits a heartbeat every second
 * describing whether the link is up, who the radio is, recent RSSI/SNR, and
 * whether we're transmitting RIGHT NOW (within the last second).
 *
 * No fake data, no simulation: every field here originates in observed RF
 * activity on the actual telemetry radio.
 */
public final class C2Status {
    public final boolean connected;
    public final long    lastUpdateMs;          // wall clock on the host that last published
    public final String  radioModel;            // e.g., "MicoAir LR900-F" or "" if unknown
    public final double  centerFreqMhz;         // 915.0 for the LR900-F
    public final double  txEirpDbm;             // current EIRP estimate from RADIO_STATUS
    public final double  rssiDbm;               // local RSSI, NaN if unknown
    public final double  remRssiDbm;            // remote RSSI, NaN if unknown
    public final long    txBytesPerSec;
    public final long    rxBytesPerSec;
    public final boolean isTransmittingNow;     // true if a TX MAVLink frame seen in last 1 s
    public final long    lastTxMs;              // epoch ms of last observed TX frame; 0 if none

    public C2Status(boolean connected, long lastUpdateMs, String radioModel,
                    double centerFreqMhz, double txEirpDbm,
                    double rssiDbm, double remRssiDbm,
                    long txBytesPerSec, long rxBytesPerSec,
                    boolean isTransmittingNow, long lastTxMs) {
        this.connected = connected;
        this.lastUpdateMs = lastUpdateMs;
        this.radioModel = radioModel == null ? "" : radioModel;
        this.centerFreqMhz = centerFreqMhz;
        this.txEirpDbm = txEirpDbm;
        this.rssiDbm = rssiDbm;
        this.remRssiDbm = remRssiDbm;
        this.txBytesPerSec = txBytesPerSec;
        this.rxBytesPerSec = rxBytesPerSec;
        this.isTransmittingNow = isTransmittingNow;
        this.lastTxMs = lastTxMs;
    }

    public static C2Status disconnected() {
        return new C2Status(false, 0, "", 0, 0,
                Double.NaN, Double.NaN, 0, 0, false, 0);
    }
}
