package com.emconsentinel.ui;

import android.media.AudioManager;
import android.media.ToneGenerator;

import com.atakmap.coremap.log.Log;

/**
 * Simple synthetic tone cues at risk-band threshold crossings. No bundled audio assets —
 * uses Android's built-in DTMF/Tone generator. A short beep on amber, a sharper double
 * beep on red.
 */
public final class SoundCues {

    private static final String TAG = "EmconSentinel.SoundCues";
    private static final double AMBER_THRESHOLD = 0.3;
    private static final double RED_THRESHOLD = 0.7;

    private final ToneGenerator toneGen;
    private double lastScore = 0;

    public SoundCues() {
        ToneGenerator g = null;
        try {
            g = new ToneGenerator(AudioManager.STREAM_NOTIFICATION, 80);
        } catch (Throwable t) {
            Log.w(TAG, "ToneGenerator unavailable — sound cues disabled", t);
        }
        this.toneGen = g;
    }

    public void onScore(double score) {
        if (toneGen == null) return;
        try {
            // Crossed into amber band
            if (lastScore < AMBER_THRESHOLD && score >= AMBER_THRESHOLD && score < RED_THRESHOLD) {
                toneGen.startTone(ToneGenerator.TONE_PROP_BEEP, 220);
            }
            // Crossed into red band
            if (lastScore < RED_THRESHOLD && score >= RED_THRESHOLD) {
                toneGen.startTone(ToneGenerator.TONE_PROP_BEEP2, 380);
            }
        } catch (Throwable t) {
            Log.w(TAG, "tone generator failure", t);
        }
        lastScore = score;
    }

    public void release() {
        if (toneGen != null) {
            try { toneGen.release(); } catch (Throwable ignored) {}
        }
    }
}
