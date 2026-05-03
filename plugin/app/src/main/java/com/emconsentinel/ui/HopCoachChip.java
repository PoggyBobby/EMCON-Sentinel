package com.emconsentinel.ui;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

import com.atak.plugins.impl.PluginLayoutInflater;
import com.atakmap.android.maps.MapView;
import com.atakmap.coremap.log.Log;

import com.emconsentinel.plugin.R;
import com.emconsentinel.risk.HopRecommendation;

/**
 * Small "Quieter: try only X — drops risk N%" chip pinned to top-center of
 * the screen, just below TopHudStrip (40 dp + 4 dp gap = top margin 44 dp).
 *
 * Behavior:
 *   - apply(rec): show with the latest one-liner, OR hide if rec == null.
 *   - First time we see a NEW dominant band, also pop a Toast for ~2 s.
 *   - Tapping the chip body fires onTap (caller jumps to Operate tab).
 *   - Tapping × dismisses for the current dominant-band identity until the
 *     dominant band changes — operator can intentionally keep a band on
 *     without being nagged.
 */
public final class HopCoachChip {

    private static final String TAG = "EmconSentinel.HopChip";

    private final MapView mapView;
    private final View root;
    private final TextView text;
    private final Button dismissBtn;
    private FrameLayout attachParent;

    private boolean visible = false;
    private double lastDominantFreqMhz = -1;
    private double lastDismissedFreqMhz = -1;

    public HopCoachChip(Context pluginContext, MapView mapView, Runnable onTap) {
        this.mapView = mapView;
        this.root = PluginLayoutInflater.inflate(pluginContext, R.layout.hop_coach_chip, null);
        this.text = root.findViewById(R.id.hop_chip_text);
        this.dismissBtn = root.findViewById(R.id.hop_chip_dismiss);

        if (onTap != null) {
            text.setOnClickListener(v -> onTap.run());
            root.setOnClickListener(v -> onTap.run());
        }
        dismissBtn.setOnClickListener(v -> {
            lastDismissedFreqMhz = lastDominantFreqMhz;
            hide();
        });

        attach();
    }

    private void attach() {
        try {
            float density = mapView.getResources().getDisplayMetrics().density;
            android.app.Activity activity = activityFrom(mapView);
            attachParent = activity != null
                    ? activity.findViewById(android.R.id.content)
                    : null;
            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.WRAP_CONTENT,
                    FrameLayout.LayoutParams.WRAP_CONTENT);
            lp.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
            // 40 dp HUD strip + 4 dp gap = 44 dp top margin
            lp.topMargin = (int) (44 * density);
            if (attachParent != null) {
                attachParent.addView(root, lp);
                attachParent.bringChildToFront(root);
                root.setElevation(28f * density);
            } else {
                Log.w(TAG, "no activity content — falling back to MapView attach");
                mapView.addView(root, lp);
            }
            root.setVisibility(View.GONE);
            Log.i(TAG, "hop chip attached");
        } catch (Exception e) {
            Log.e(TAG, "attach failed", e);
        }
    }

    /** Called from the tick loop with the latest recommendation (or null). */
    public void apply(HopRecommendation rec) {
        if (rec == null) {
            hide();
            lastDominantFreqMhz = -1;
            return;
        }
        if (rec.dominantBand.freqMhz == lastDismissedFreqMhz) {
            return;
        }
        text.setText(rec.oneLiner);
        boolean isNewDominant = (rec.dominantBand.freqMhz != lastDominantFreqMhz);
        lastDominantFreqMhz = rec.dominantBand.freqMhz;
        if (!visible) {
            root.setVisibility(View.VISIBLE);
            visible = true;
            if (isNewDominant) {
                try {
                    Toast.makeText(mapView.getContext(),
                            rec.oneLiner + "  ·  tap chip → Operate",
                            Toast.LENGTH_LONG).show();
                } catch (Exception ignored) {}
            }
        }
    }

    private void hide() {
        if (!visible) return;
        root.setVisibility(View.GONE);
        visible = false;
    }

    public boolean isVisible() { return visible; }

    public void detach(MapView mv) {
        try {
            if (attachParent != null) attachParent.removeView(root);
            else mv.removeView(root);
        } catch (Exception ignored) {}
    }

    private static android.app.Activity activityFrom(android.view.View v) {
        Context c = v.getContext();
        while (c instanceof android.content.ContextWrapper) {
            if (c instanceof android.app.Activity) return (android.app.Activity) c;
            c = ((android.content.ContextWrapper) c).getBaseContext();
        }
        return null;
    }
}
