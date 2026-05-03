package com.emconsentinel.phone;

import android.content.Context;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.os.Handler;
import android.os.Looper;
import android.telephony.CellSignalStrength;
import android.telephony.ServiceState;
import android.telephony.SignalStrength;
import android.telephony.TelephonyManager;

import com.atakmap.coremap.log.Log;

import com.emconsentinel.data.RadioBand;

import java.util.ArrayList;
import java.util.List;

/**
 * Reads the operator phone's own RF emitters every 5 s and publishes them as
 * a list of RadioBands the EMCON Sentinel risk model should account for.
 *
 * The phone is itself a high-EIRP emitter at the operator's location — DF
 * assets get bearings on cellular, WiFi, and BT just as readily as on the
 * drone control link. Most operators forget this. This monitor surfaces it.
 *
 * No simulated data: every band reported here is observed from Android system
 * services (TelephonyManager / WifiManager). If a radio is off, it doesn't
 * emit and isn't reported.
 *
 * Permissions required: ACCESS_WIFI_STATE (already in manifest) and
 * READ_PHONE_STATE (for cellular details — granted at runtime on Android 6+).
 * Without READ_PHONE_STATE, cellular falls back to "present, parameters unknown".
 */
public final class PhoneEmitterMonitor {

    private static final String TAG = "EmconSentinel.PhoneEmitterMonitor";
    private static final long POLL_PERIOD_MS = 5_000;

    public interface Sink {
        /** Called every poll with the operator phone's currently active emitter bands. */
        void onPhoneEmitters(List<RadioBand> bands);
    }

    private final Context context;
    private final Sink sink;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final WifiManager wifi;
    private final TelephonyManager tel;
    private boolean running = false;

    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if (!running) return;
            try {
                List<RadioBand> bands = sample();
                if (sink != null) sink.onPhoneEmitters(bands);
            } catch (Exception e) {
                Log.w(TAG, "phone emitter sample failed: " + e);
            }
            handler.postDelayed(this, POLL_PERIOD_MS);
        }
    };

    public PhoneEmitterMonitor(Context context, Sink sink) {
        this.context = context.getApplicationContext();
        this.sink = sink;
        this.wifi = (WifiManager) this.context.getSystemService(Context.WIFI_SERVICE);
        this.tel = (TelephonyManager) this.context.getSystemService(Context.TELEPHONY_SERVICE);
    }

    public void start() {
        if (running) return;
        running = true;
        handler.post(poll);
        Log.i(TAG, "PhoneEmitterMonitor started — polling every " + POLL_PERIOD_MS + " ms");
    }

    public void stop() {
        running = false;
        handler.removeCallbacks(poll);
    }

    /** Poll the phone's radios and return active emitter bands. */
    private List<RadioBand> sample() {
        List<RadioBand> out = new ArrayList<>();

        // --- WiFi -------------------------------------------------------------
        // Active 2.4 GHz / 5 GHz / 6 GHz emission when WiFi radio is on AND we
        // have an association (probe traffic + keepalives + data). EIRP cap on
        // most phones is ~20 dBm (FCC Part 15). Frequency: per current channel.
        try {
            if (wifi != null && wifi.isWifiEnabled()) {
                WifiInfo info = wifi.getConnectionInfo();
                int freqMhz = info != null ? info.getFrequency() : 0;
                int rssi = info != null ? info.getRssi() : Integer.MIN_VALUE;
                // Even unassociated WiFi emits probe requests every few seconds.
                // Treat enabled-but-not-associated as 2440 MHz, low duty.
                if (freqMhz <= 0) freqMhz = 2440;
                double duty = (info != null && rssi != Integer.MIN_VALUE) ? 0.30 : 0.05;
                out.add(new RadioBand(freqMhz, /*eirpDbm*/ 20.0, duty, "phone-wifi"));
            }
        } catch (Exception e) {
            Log.w(TAG, "wifi sample failed: " + e);
        }

        // --- Cellular ---------------------------------------------------------
        // Phones beacon to the cell tower continuously when on. TX power is
        // adaptive (closed-loop) but worst case ~23 dBm class-3. Frequency is
        // band-dependent; pick representative center per network type.
        //
        // Gate on ServiceState — a SIM being inserted and unlocked
        // (SIM_STATE_READY) tells us nothing about whether the radio is on.
        // ServiceState.STATE_POWER_OFF is the OS's authoritative answer for
        // "the cellular radio is hardware-off" (airplane mode, manual radio
        // toggle, modem reset — anything that actually stops emissions). We
        // mirror the principle WiFi/BT already use: ask the radio's own state,
        // not a proxy.
        try {
            if (tel != null) {
                ServiceState ss = tel.getServiceState();
                boolean radioOn = ss != null && ss.getState() != ServiceState.STATE_POWER_OFF;
                if (radioOn) {
                    int netType = tel.getNetworkType();
                    double centerMhz = cellularCenterFreqMhz(netType);
                    // UL duty: low when idle, higher in active call/data. 0.10 = conservative.
                    double duty = 0.10;
                    out.add(new RadioBand(centerMhz, /*eirpDbm*/ 23.0, duty,
                            "phone-cellular-" + cellularLabel(netType)));
                }
            }
        } catch (SecurityException se) {
            // READ_PHONE_STATE not granted. Without it we can't read the radio
            // state at all — refuse to fabricate a band. Operator sees IDLE
            // for cellular until the permission is granted, which is the honest
            // answer (we can't observe so we don't claim).
        } catch (Exception e) {
            Log.w(TAG, "cellular sample failed: " + e);
        }

        // --- Bluetooth --------------------------------------------------------
        // BT class-2 emits ~4 dBm; class-1 up to 20 dBm. 2.4 GHz ISM. Low duty
        // when nothing is paired/streaming; high during audio. We can't easily
        // tell if it's actively transmitting without BluetoothAdapter inspection,
        // so be conservative: report it as a low-duty 2.4 GHz emitter when on.
        try {
            android.bluetooth.BluetoothAdapter ba =
                    android.bluetooth.BluetoothAdapter.getDefaultAdapter();
            if (ba != null && ba.isEnabled()) {
                out.add(new RadioBand(2440, 4.0, 0.05, "phone-bluetooth"));
            }
        } catch (Exception e) {
            Log.w(TAG, "bt sample failed: " + e);
        }

        return out;
    }

    /** Map TelephonyManager network type → representative center frequency. */
    private static double cellularCenterFreqMhz(int netType) {
        switch (netType) {
            case TelephonyManager.NETWORK_TYPE_GSM:
            case TelephonyManager.NETWORK_TYPE_GPRS:
            case TelephonyManager.NETWORK_TYPE_EDGE:
                return 900;        // GSM-900 worldwide common
            case TelephonyManager.NETWORK_TYPE_UMTS:
            case TelephonyManager.NETWORK_TYPE_HSPA:
            case TelephonyManager.NETWORK_TYPE_HSPAP:
                return 2100;       // UMTS Band 1
            case TelephonyManager.NETWORK_TYPE_LTE:
                return 1900;       // LTE Band 2 (PCS) — most common in US
            case TelephonyManager.NETWORK_TYPE_NR:
                return 3500;       // NR n78 (mid-band 5G)
            default:
                return 1900;
        }
    }

    private static String cellularLabel(int netType) {
        switch (netType) {
            case TelephonyManager.NETWORK_TYPE_GSM:
            case TelephonyManager.NETWORK_TYPE_GPRS:
            case TelephonyManager.NETWORK_TYPE_EDGE: return "gsm";
            case TelephonyManager.NETWORK_TYPE_UMTS:
            case TelephonyManager.NETWORK_TYPE_HSPA:
            case TelephonyManager.NETWORK_TYPE_HSPAP: return "umts";
            case TelephonyManager.NETWORK_TYPE_LTE: return "lte";
            case TelephonyManager.NETWORK_TYPE_NR: return "5g";
            default: return "unknown";
        }
    }
}
