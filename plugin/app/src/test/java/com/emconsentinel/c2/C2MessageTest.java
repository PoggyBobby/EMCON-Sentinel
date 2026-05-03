package com.emconsentinel.c2;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class C2MessageTest {

    @Test public void parsesMicoAirHeartbeat() {
        String json = "{"
                + "\"v\":1,"
                + "\"ts\":1700000000.123,"
                + "\"connected\":true,"
                + "\"radio_model\":\"MicoAir LR900-F\","
                + "\"center_freq_mhz\":915.0,"
                + "\"tx_eirp_dbm\":27.0,"
                + "\"rssi_dbm\":-82.0,"
                + "\"rem_rssi_dbm\":-78.0,"
                + "\"tx_bytes_per_sec\":124,"
                + "\"rx_bytes_per_sec\":612,"
                + "\"is_transmitting_now\":true,"
                + "\"last_tx_ms\":1700000000123"
                + "}";
        C2Status s = C2Message.parse(json);
        assertTrue(s.connected);
        assertEquals("MicoAir LR900-F", s.radioModel);
        assertEquals(915.0, s.centerFreqMhz, 1e-9);
        assertEquals(27.0, s.txEirpDbm, 1e-9);
        assertEquals(-82.0, s.rssiDbm, 1e-9);
        assertEquals(-78.0, s.remRssiDbm, 1e-9);
        assertEquals(124L, s.txBytesPerSec);
        assertEquals(612L, s.rxBytesPerSec);
        assertTrue(s.isTransmittingNow);
        assertEquals(1700000000123L, s.lastTxMs);
        assertEquals(1700000000123L, s.lastUpdateMs);
    }

    @Test public void parsesDisconnectedFrame() {
        String json = "{\"v\":1,\"ts\":1700000000.0,\"connected\":false,"
                + "\"radio_model\":\"\",\"center_freq_mhz\":0.0,\"tx_eirp_dbm\":0.0,"
                + "\"rssi_dbm\":null,\"rem_rssi_dbm\":null,"
                + "\"tx_bytes_per_sec\":0,\"rx_bytes_per_sec\":0,"
                + "\"is_transmitting_now\":false,\"last_tx_ms\":0}";
        C2Status s = C2Message.parse(json);
        assertFalse(s.connected);
        assertTrue("rssi missing -> NaN", Double.isNaN(s.rssiDbm));
        assertTrue("rem_rssi missing -> NaN", Double.isNaN(s.remRssiDbm));
        assertFalse(s.isTransmittingNow);
    }

    @Test public void disconnectedFactoryFieldsZeroed() {
        C2Status s = C2Status.disconnected();
        assertFalse(s.connected);
        assertEquals("", s.radioModel);
        assertEquals(0.0, s.centerFreqMhz, 1e-9);
        assertTrue(Double.isNaN(s.rssiDbm));
        assertTrue(Double.isNaN(s.remRssiDbm));
        assertFalse(s.isTransmittingNow);
    }

    @Test public void parsesMinimalRequiredFields() {
        // Only ts is strictly required; everything else falls back to defaults
        C2Status s = C2Message.parse("{\"ts\":1700000000.5}");
        assertEquals(1700000000500L, s.lastUpdateMs);
        assertFalse(s.connected);
        assertEquals(0.0, s.centerFreqMhz, 1e-9);
    }
}
