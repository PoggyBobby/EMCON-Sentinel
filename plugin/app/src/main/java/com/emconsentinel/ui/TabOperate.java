package com.emconsentinel.ui;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;

import com.atak.plugins.impl.PluginLayoutInflater;

import com.emconsentinel.c2.C2Status;
import com.emconsentinel.data.RadioBand;
import com.emconsentinel.data.RadioProfile;
import com.emconsentinel.plugin.R;
import com.emconsentinel.risk.HopRecommendation;

import java.util.Locale;

/**
 * Tab 3: drive the operation. Big START/STOP KEYING button. Status lines.
 * Power-user toggles behind a disclosure.
 */
public final class TabOperate {

    private final Context pluginContext;
    private final PluginState state;
    private final Runnable onShowSurvivability;
    private final View root;
    private final Button keyingBtn;
    private final TextView statusLabel;
    private final TextView c2StatusLabel;
    private final TextView demoSpeedLabel;
    private final TextView moreDisclosure;
    private final View morePanel;
    private final CheckBox useC2Toggle;
    private final LinearLayout bandsContainer;
    private RadioProfile lastRenderedProfile;
    private int highlightBandIdx = -1;
    private long highlightStartedMs = 0;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Runnable refreshTick = new Runnable() {
        @Override public void run() {
            refreshC2Status();
            refreshKeyingButton();
            refreshDemoSpeed();
            renderBands();
            ui.postDelayed(this, 1000);
        }
    };

    /**
     * Render per-band Switch rows for the active radio. No-op if profile
     * unchanged. Always re-syncs Switch state (chip-driven changes elsewhere).
     */
    private void renderBands() {
        if (bandsContainer == null) return;
        RadioProfile p = state.activeProfile();
        if (p == null) {
            bandsContainer.removeAllViews();
            lastRenderedProfile = null;
            return;
        }
        boolean profileChanged = (lastRenderedProfile == null
                || !lastRenderedProfile.id.equals(p.id)
                || lastRenderedProfile.bands.size() != p.bands.size());
        if (profileChanged) {
            bandsContainer.removeAllViews();
            for (int i = 0; i < p.bands.size(); i++) {
                final int idx = i;
                final RadioBand band = p.bands.get(i);
                View row = PluginLayoutInflater.inflate(pluginContext,
                        R.layout.band_toggle_row, null);
                bandsContainer.addView(row);
                TextView title = row.findViewById(R.id.band_row_title);
                Switch sw = row.findViewById(R.id.band_row_switch);
                title.setText(formatBandTitle(band));
                sw.setChecked(!state.isBandDisabled(p, idx));
                sw.setOnCheckedChangeListener((b, checked) ->
                        state.setBandDisabled(p, idx, !checked));
            }
            lastRenderedProfile = p;
        } else {
            // Sync Switch state from PluginState (chip-driven changes don't
            // go through these listeners)
            for (int i = 0; i < p.bands.size(); i++) {
                View row = bandsContainer.getChildAt(i);
                if (row == null) continue;
                Switch sw = row.findViewById(R.id.band_row_switch);
                boolean shouldBeChecked = !state.isBandDisabled(p, i);
                if (sw.isChecked() != shouldBeChecked) {
                    final int idx = i;
                    sw.setOnCheckedChangeListener(null);
                    sw.setChecked(shouldBeChecked);
                    sw.setOnCheckedChangeListener((b, checked) ->
                            state.setBandDisabled(p, idx, !checked));
                }
            }
        }
        applyBandHighlight();
        updateContributionLabels();
    }

    private void updateContributionLabels() {
        if (bandsContainer == null) return;
        HopRecommendation rec = state.lastHopRecommendation();
        RadioProfile p = state.activeProfile();
        if (p == null) return;
        for (int i = 0; i < p.bands.size(); i++) {
            View row = bandsContainer.getChildAt(i);
            if (row == null) continue;
            TextView contrib = row.findViewById(R.id.band_row_contribution);
            String label;
            if (state.isBandDisabled(p, i)) {
                label = "disabled";
            } else if (rec != null && rec.bandsToDisable.contains(i)) {
                label = String.format(java.util.Locale.US,
                        "dominant — disabling drops risk %d%%",
                        (int) Math.round(rec.riskDeltaFraction * 100));
            } else {
                label = "active";
            }
            contrib.setText(label);
        }
    }

    /** Caller (chip) asks us to amber-flash a specific band row to draw the eye. */
    public void highlightBand(int bandIdx) {
        this.highlightBandIdx = bandIdx;
        this.highlightStartedMs = System.currentTimeMillis();
        applyBandHighlight();
    }

    private void applyBandHighlight() {
        if (highlightBandIdx < 0 || bandsContainer == null) return;
        long elapsed = System.currentTimeMillis() - highlightStartedMs;
        if (elapsed > 2500) {
            for (int i = 0; i < bandsContainer.getChildCount(); i++) {
                bandsContainer.getChildAt(i).setBackgroundColor(0xFF1A1A1A);
            }
            highlightBandIdx = -1;
            return;
        }
        for (int i = 0; i < bandsContainer.getChildCount(); i++) {
            int color = (i == highlightBandIdx) ? 0xFF5A4A1A : 0xFF1A1A1A;
            bandsContainer.getChildAt(i).setBackgroundColor(color);
        }
    }

    private static String formatBandTitle(RadioBand b) {
        String freq = b.freqMhz >= 1000
                ? String.format(java.util.Locale.US, "%.1f GHz", b.freqMhz / 1000.0)
                : String.format(java.util.Locale.US, "%.0f MHz", b.freqMhz);
        return freq + " " + (b.purpose == null ? "" : b.purpose)
                + "  ·  " + (int) b.eirpDbm + " dBm";
    }

    public TabOperate(Context pluginContext, PluginState state, Runnable onShowSurvivability) {
        this.pluginContext = pluginContext;
        this.state = state;
        this.onShowSurvivability = onShowSurvivability;

        this.root = PluginLayoutInflater.inflate(pluginContext, R.layout.tab_operate, null);
        this.keyingBtn = root.findViewById(R.id.operate_keying_btn);
        this.statusLabel = root.findViewById(R.id.operate_status_label);
        this.c2StatusLabel = root.findViewById(R.id.operate_c2_status);
        this.demoSpeedLabel = root.findViewById(R.id.operate_demo_speed_toggle);
        this.moreDisclosure = root.findViewById(R.id.operate_more_disclosure);
        this.morePanel = root.findViewById(R.id.operate_more_panel);
        this.useC2Toggle = root.findViewById(R.id.operate_use_c2_for_keying);
        this.bandsContainer = root.findViewById(R.id.operate_bands_container);

        wire();
        refreshKeyingButton();
        refreshC2Status();
        refreshDemoSpeed();
        ui.postDelayed(refreshTick, 1000);
    }

    public View view() { return root; }

    private void wire() {
        keyingBtn.setOnClickListener(v -> {
            state.setKeying(!state.isKeying());
            refreshKeyingButton();
        });
        Button survBtn = root.findViewById(R.id.operate_surv_btn);
        if (survBtn != null && onShowSurvivability != null) {
            survBtn.setOnClickListener(v -> onShowSurvivability.run());
        }

        moreDisclosure.setOnClickListener(v -> {
            boolean visible = morePanel.getVisibility() == View.VISIBLE;
            morePanel.setVisibility(visible ? View.GONE : View.VISIBLE);
            moreDisclosure.setText(visible ? "▾ More options" : "▴ Hide options");
        });

        useC2Toggle.setChecked(state.useC2ForKeying());
        useC2Toggle.setOnCheckedChangeListener((b, checked) -> {
            state.setUseC2ForKeying(checked);
            refreshKeyingButton();
        });
    }

    private void refreshKeyingButton() {
        if (state.activeProfile() == null) {
            keyingBtn.setEnabled(false);
            keyingBtn.setText("PICK A RADIO FIRST");
            keyingBtn.setBackgroundColor(0xFF555555);
            statusLabel.setText("Tab 1 — pick your operator radio profile.");
            return;
        }
        boolean usingC2 = state.useC2ForKeying() && state.c2Status() != null && state.c2Status().connected;
        boolean keying = state.isKeying();
        if (usingC2) {
            keyingBtn.setEnabled(false);
            keyingBtn.setText("KEYING DRIVEN BY C2 LINK");
            keyingBtn.setBackgroundColor(keying ? 0xFFCC1F1F : 0xFF454545);
            statusLabel.setText("Manual button overridden — using observed RF activity from C2 bridge.");
        } else {
            keyingBtn.setEnabled(true);
            keyingBtn.setText(keying ? "STOP KEYING" : "START KEYING");
            keyingBtn.setBackgroundColor(keying ? 0xFFCC1F1F : 0xFF2ECC40);
            statusLabel.setText(keying
                    ? "Keying — risk dial active. Stop to reset dwell."
                    : "Idle. Press START KEYING to begin emitting.");
        }
    }

    private void refreshC2Status() {
        C2Status s = state.c2Status();
        if (s == null || !s.connected) {
            c2StatusLabel.setText("C2 bridge offline. Run tools/c2_bridge.py to observe real RF.");
            c2StatusLabel.setTextColor(0xFF888888);
            return;
        }
        StringBuilder sb = new StringBuilder();
        sb.append(String.format(Locale.US, "C2 LINK UP — %s @ %.1f MHz",
                s.radioModel.isEmpty() ? "unknown radio" : s.radioModel, s.centerFreqMhz));
        if (!Double.isNaN(s.rssiDbm)) {
            sb.append(String.format(Locale.US, "  ·  %.0f dBm", s.rssiDbm));
        }
        if (s.isTransmittingNow) sb.append("  ·  TX active");
        c2StatusLabel.setText(sb.toString());
        c2StatusLabel.setTextColor(s.isTransmittingNow ? 0xFFFF6F1F : 0xFF2ECC40);
    }

    private void refreshDemoSpeed() {
        demoSpeedLabel.setText(state.isDemoMode10x()
                ? "Demo speed: 10× — dwell saturates 10× faster (long-press HUD dial to disable)"
                : "Demo speed: 1× (long-press dial in HUD to toggle 10×)");
    }

    public void detach() {
        ui.removeCallbacks(refreshTick);
    }
}
