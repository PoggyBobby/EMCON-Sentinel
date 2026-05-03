package com.emconsentinel.ui;

import android.content.Context;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;

import com.atak.plugins.impl.PluginLayoutInflater;
import com.atakmap.android.maps.MapView;
import com.atakmap.coremap.log.Log;
import com.atakmap.coremap.maps.coords.GeoPoint;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.RadioBand;
import com.emconsentinel.data.RadioProfile;
import com.emconsentinel.plugin.R;
import com.emconsentinel.prop.LinkBudget;
import com.emconsentinel.prop.PathLossEngine;
import com.emconsentinel.risk.PlacedAdversary;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

/**
 * Pre-mission survivability check. Operator inputs a planned keying dwell time;
 * tool computes composite "you don't get killed" probability for the current
 * loadout, then ranks alternative radios by predicted improvement.
 *
 * Math (per radio profile):
 *   For each visible adversary i:
 *     P_lock_i = P_detect_i * (1 - exp(-dwell / tau_i))
 *   Composite kill = 1 - product(1 - P_lock_i)
 *   Survival       = 1 - composite
 *
 * Highest-leverage life-saving feature: lets the operator change their loadout
 * BEFORE leaving the FOB based on quantified threat exposure.
 */
public final class SurvivabilityModalController {

    private static final String TAG = "EmconSentinel.SurvModal";

    private final Context pluginContext;
    private final MapView mapView;
    private final PluginState state;
    private final PathLossEngine prop;

    private View modalRoot;
    private boolean visible = false;
    private android.widget.FrameLayout attachParent;
    private int dwellMinutes = 5;

    public SurvivabilityModalController(Context pluginContext, MapView mapView,
                                        PluginState state, PathLossEngine prop) {
        this.pluginContext = pluginContext;
        this.mapView = mapView;
        this.state = state;
        this.prop = prop;
    }

    public void show() {
        if (visible) return;
        try {
            modalRoot = PluginLayoutInflater.inflate(pluginContext, R.layout.survivability_modal, null);
            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    FrameLayout.LayoutParams.MATCH_PARENT);
            android.app.Activity activity = activityFrom(mapView);
            attachParent = activity != null
                    ? activity.findViewById(android.R.id.content)
                    : null;
            if (attachParent != null) {
                attachParent.addView(modalRoot, lp);
                attachParent.bringChildToFront(modalRoot);
                float density = mapView.getResources().getDisplayMetrics().density;
                modalRoot.setElevation(50f * density);
            } else {
                mapView.addView(modalRoot, lp);
            }
            visible = true;
            wire();
            recompute();
            Log.i(TAG, "survivability modal shown");
        } catch (Exception e) {
            Log.e(TAG, "failed to show survivability modal", e);
        }
    }

    public void hide() {
        if (!visible) return;
        try {
            if (modalRoot != null) {
                if (attachParent != null) attachParent.removeView(modalRoot);
                else mapView.removeView(modalRoot);
            }
        } catch (Exception ignored) {}
        modalRoot = null;
        visible = false;
    }

    private void wire() {
        SeekBar seek = modalRoot.findViewById(R.id.surv_dwell_seek);
        seek.setProgress(dwellMinutes - 1);  // SeekBar 0..14 = 1..15 min
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s, int progress, boolean fromUser) {
                dwellMinutes = progress + 1;
                recompute();
            }
            @Override public void onStartTrackingTouch(SeekBar s) {}
            @Override public void onStopTrackingTouch(SeekBar s) {}
        });
        Button close = modalRoot.findViewById(R.id.surv_close_btn);
        close.setOnClickListener(v -> hide());
    }

    private void recompute() {
        if (modalRoot == null) return;
        TextView dwellLabel = modalRoot.findViewById(R.id.surv_dwell_label);
        TextView currentLabel = modalRoot.findViewById(R.id.surv_current_label);
        LinearLayout recoContainer = modalRoot.findViewById(R.id.surv_recommendations);
        recoContainer.removeAllViews();

        dwellLabel.setText(dwellMinutes + " min keying dwell");

        RadioProfile current = state.activeProfile();
        List<PlacedAdversary> placed = visiblePlaced();

        if (current == null || placed.isEmpty()) {
            currentLabel.setText(current == null ? "Pick a radio" : "No threats placed");
            currentLabel.setTextColor(0xFFAAAAAA);
            return;
        }

        double[] op = currentOperatorPoint();
        double currentSurvival = computeSurvival(current, op[0], op[1], placed, dwellMinutes * 60.0);

        currentLabel.setText(String.format(Locale.US, "%d%% survival",
                (int) Math.round(currentSurvival * 100)));
        currentLabel.setTextColor(colorForSurvival(currentSurvival));

        // Try every other radio profile, sort by predicted improvement
        List<RadioProfile> profiles = state.library().radioProfiles();
        List<double[]> scored = new ArrayList<>();    // [profile-index, survival, delta]
        for (int i = 0; i < profiles.size(); i++) {
            RadioProfile p = profiles.get(i);
            if (p.id.equals(current.id)) continue;
            double s = computeSurvival(p, op[0], op[1], placed, dwellMinutes * 60.0);
            scored.add(new double[] { i, s, s - currentSurvival });
        }
        Collections.sort(scored, new Comparator<double[]>() {
            @Override public int compare(double[] a, double[] b) {
                return Double.compare(b[1], a[1]);  // higher survival first
            }
        });

        int rendered = 0;
        for (double[] row : scored) {
            if (rendered >= 3) break;
            RadioProfile p = profiles.get((int) row[0]);
            double s = row[1];
            double delta = row[2];
            renderRecommendation(recoContainer, p, s, delta);
            rendered++;
        }
        if (rendered == 0) {
            TextView none = new TextView(mapView.getContext());
            none.setText("No alternative radios in library.");
            none.setTextColor(0xFFAAAAAA);
            none.setPadding(8, 8, 8, 8);
            recoContainer.addView(none);
        }
    }

    private void renderRecommendation(LinearLayout container, RadioProfile p,
                                       double survival, double delta) {
        LinearLayout row = new LinearLayout(mapView.getContext());
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(12, 10, 12, 10);
        row.setBackgroundColor(0xFF1A1A1A);

        LinearLayout.LayoutParams rowLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        rowLp.bottomMargin = 6;
        row.setLayoutParams(rowLp);

        TextView name = new TextView(mapView.getContext());
        name.setText(p.displayName);
        name.setTextColor(0xFFFFFFFF);
        name.setTextSize(13);
        name.setLayoutParams(new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1));

        TextView pct = new TextView(mapView.getContext());
        pct.setText(String.format(Locale.US, "%d%%  (%+d%%)",
                (int) Math.round(survival * 100),
                (int) Math.round(delta * 100)));
        pct.setTextColor(delta > 0 ? 0xFF2ECC40 : (delta < 0 ? 0xFFFF6F1F : 0xFFCCCCCC));
        pct.setTextSize(13);
        pct.setTypeface(null, android.graphics.Typeface.BOLD);

        row.addView(name);
        row.addView(pct);
        container.addView(row);
    }

    private double computeSurvival(RadioProfile profile, double opLat, double opLon,
                                    List<PlacedAdversary> placed, double dwellSeconds) {
        double composite_one_minus = 1.0;
        for (PlacedAdversary p : placed) {
            AdversarySystem adv = p.system;
            // Iterate per-band — same logic as RiskScorer but standalone
            double pDetect = 0.0;
            for (RadioBand b : profile.bands) {
                if (!adv.coversFrequency(b.freqMhz)) continue;
                double pl = prop.pathLoss(opLat, opLon, p.lat, p.lon, b.freqMhz).pathLossDb;
                double rx = b.eirpDbm - pl + adv.antennaGainDbi;
                double margin = rx - adv.sensitivityDbm;
                double pBand = LinkBudget.sigmoid(margin) * b.dutyCycle;
                if (pBand > pDetect) pDetect = pBand;
            }
            if (pDetect <= 0) continue;
            double tau = Math.max(1, adv.timeToFixSeconds);
            double pLock = pDetect * (1.0 - Math.exp(-dwellSeconds / tau));
            composite_one_minus *= (1.0 - pLock);
        }
        return composite_one_minus;     // = 1 - composite kill
    }

    private List<PlacedAdversary> visiblePlaced() {
        List<PlacedAdversary> out = new ArrayList<>();
        for (PlacedAdversary p : state.placedAdversariesSnapshot()) {
            if (!p.hidden) out.add(p);
        }
        return out;
    }

    private double[] currentOperatorPoint() {
        if (state.hasDemoOperatorOverride()) {
            return new double[] { state.demoOperatorLat(), state.demoOperatorLon() };
        }
        if (mapView.getSelfMarker() != null && mapView.getSelfMarker().getPoint() != null) {
            GeoPoint sp = mapView.getSelfMarker().getPoint();
            if (sp.getLatitude() != 0 || sp.getLongitude() != 0) {
                return new double[] { sp.getLatitude(), sp.getLongitude() };
            }
        }
        GeoPoint c = mapView.getCenterPoint().get();
        return new double[] { c.getLatitude(), c.getLongitude() };
    }

    private static int colorForSurvival(double s) {
        if (s >= 0.7) return 0xFF2ECC40;       // green
        if (s >= 0.3) return 0xFFFFA500;       // amber
        return 0xFFFF1F1F;                      // red
    }

    private static android.app.Activity activityFrom(android.view.View v) {
        Context c = v.getContext();
        while (c instanceof android.content.ContextWrapper) {
            if (c instanceof android.app.Activity) return (android.app.Activity) c;
            c = ((android.content.ContextWrapper) c).getBaseContext();
        }
        return null;
    }

    public void detach() { hide(); }
}
