package com.emconsentinel.ui;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.TextView;

import com.atak.plugins.impl.PluginLayoutInflater;
import com.atakmap.android.maps.MapView;
import com.atakmap.coremap.log.Log;

import com.emconsentinel.plugin.R;

/**
 * Always-visible top status strip attached to the MapView. Drop-in replacement
 * for the old corner RiskDialView — same setRisk() signature so RiskTickLoop
 * doesn't need to change. Renders:
 *   - Mini risk ring (color-coded)
 *   - Plain-English status line ("SAFE" / "CAUTION — fix in 45s" / "MOVE NOW")
 *   - Top-threat name + range/bearing on a second line
 *   - Math button (∑) → opens MathOverlayController
 */
public final class TopHudStrip {

    private static final String TAG = "EmconSentinel.TopHudStrip";

    private final View root;
    private final MiniRiskRing ring;
    private final TextView statusLine;
    private final TextView threatLine;
    private final Button mathBtn;

    private double lastScore = -1;

    public TopHudStrip(Context pluginContext, MapView mapView, Runnable onMathButtonTap,
                       Runnable onRingLongPress) {
        this.root = PluginLayoutInflater.inflate(pluginContext, R.layout.top_hud_strip, null);
        this.ring = root.findViewById(R.id.hud_mini_ring);
        this.statusLine = root.findViewById(R.id.hud_status_line);
        this.threatLine = root.findViewById(R.id.hud_threat_line);
        this.mathBtn = root.findViewById(R.id.hud_math_button);

        if (onMathButtonTap != null) {
            mathBtn.setOnClickListener(v -> onMathButtonTap.run());
            ring.setOnClickListener(v -> onMathButtonTap.run());
        }
        if (onRingLongPress != null) {
            ring.setOnLongClickListener(v -> { onRingLongPress.run(); return true; });
            statusLine.setOnLongClickListener(v -> { onRingLongPress.run(); return true; });
        }

        attach(mapView);
    }

    private android.widget.FrameLayout attachParent;

    private void attach(MapView mapView) {
        try {
            float density = mapView.getResources().getDisplayMetrics().density;
            // 40 dp tall, anchored to the very top of the screen. With 40dp height
            // the bar ends at ~112 px on 3x density, well above ATAK's toolbar
            // icons (centered at y≈135 px) so they remain tappable below us.
            final int hudHeightPx = (int) (40 * density);

            android.app.Activity activity = activityFrom(mapView);
            attachParent = activity != null
                    ? activity.findViewById(android.R.id.content)
                    : null;
            if (attachParent == null) {
                Log.w(TAG, "could not resolve activity content FrameLayout — falling back to MapView");
                FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT, hudHeightPx);
                lp.gravity = Gravity.TOP;
                mapView.addView(root, lp);
                return;
            }

            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT, hudHeightPx);
            lp.gravity = Gravity.TOP;
            lp.topMargin = 0;
            attachParent.addView(root, lp);
            attachParent.bringChildToFront(root);
            root.setElevation(30f * density);
            Log.i(TAG, "top HUD strip attached at y=0 (height=" + hudHeightPx + " px)");
        } catch (Exception e) {
            Log.e(TAG, "failed to attach top HUD strip", e);
        }
    }

    private static android.app.Activity activityFrom(android.view.View v) {
        Context c = v.getContext();
        while (c instanceof android.content.ContextWrapper) {
            if (c instanceof android.app.Activity) return (android.app.Activity) c;
            c = ((android.content.ContextWrapper) c).getBaseContext();
        }
        return null;
    }

    /**
     * Drop-in replacement for RiskDialView.setRisk. Called every tick by RiskTickLoop.
     * @param score 0..1 composite risk
     * @param dwellSeconds seconds of accumulated dwell at current position
     * @param topThreatLine "Top: R-330Zh (12.4 km NE)" or "" if none
     * @param propModeLine "FREE-SPACE FALLBACK — TERRAIN NOT MODELED" or ""
     * @param demoMode10x ignored here (HUD is the same regardless)
     */
    /** Optional context line — e.g., "Generic worst-case posture · TBS Crossfire". Set by MapComponent on posture change. */
    private String contextLine = "";

    public void setContext(String contextLine) {
        this.contextLine = contextLine == null ? "" : contextLine;
    }

    public void setRisk(double score, double dwellSeconds, String topThreatLine,
                        String propModeLine, boolean demoMode10x) {
        if (score < 0) score = 0; else if (score > 1) score = 1;
        ring.setScore(score);

        // Operator-actionable status: SAFE shows safe-keying budget (estimated
        // seconds until you cross into CAUTION). CAUTION shows time-to-MOVE-NOW.
        // MOVE NOW is the only thing that matters when you're red.
        String statusText;
        int statusColor;
        if (score < 0.3) {
            int budgetSecs = estimateSafeBudget(score, dwellSeconds);
            statusText = budgetSecs > 0
                    ? String.format("SAFE  —  ~%ds budget", budgetSecs)
                    : "SAFE";
            statusColor = 0xFF2ECC40;
        } else if (score < 0.7) {
            int secsToRed = estimateTimeToRed(score, dwellSeconds);
            statusText = secsToRed > 0
                    ? String.format("CAUTION  —  fix in ~%ds", secsToRed)
                    : String.format("CAUTION  —  %d%%", (int) Math.round(score * 100));
            statusColor = 0xFFFFA500;
        } else {
            statusText = "MOVE NOW";
            statusColor = 0xFFFF1F1F;
        }
        statusLine.setText(statusText);
        statusLine.setTextColor(statusColor);

        // Sub-line. Priority: top threat (if any) > posture/context line > dwell time.
        StringBuilder sb = new StringBuilder();
        if (topThreatLine != null && !topThreatLine.isEmpty()) {
            sb.append(topThreatLine);
        } else if (!contextLine.isEmpty()) {
            sb.append(contextLine);
        } else {
            sb.append("Dwell ").append((int) (dwellSeconds / 60)).append("m ")
              .append((int) (dwellSeconds % 60)).append("s — no active threats");
        }
        if (propModeLine != null && !propModeLine.isEmpty()) {
            sb.append("  ·  free-space");
        }
        threatLine.setText(sb.toString());

        lastScore = score;
    }

    /** "If I keep keying at this position, when will I cross 0.3?" */
    private static int estimateSafeBudget(double currentScore, double dwellSeconds) {
        if (dwellSeconds < 1) return -1;
        if (currentScore <= 0) return -1;
        double rate = currentScore / dwellSeconds;
        if (rate < 1e-4) return -1;
        double remaining = (0.3 - currentScore) / rate;
        if (remaining < 0 || remaining > 600) return -1;
        return (int) Math.round(remaining);
    }

    /** "If I keep keying at this position, when will I cross 0.7?" */
    private static int estimateTimeToRed(double currentScore, double dwellSeconds) {
        if (dwellSeconds < 1 || currentScore <= 0) return -1;
        double rate = currentScore / dwellSeconds;
        if (rate < 1e-4) return -1;
        double remaining = (0.7 - currentScore) / rate;
        if (remaining < 0 || remaining > 600) return -1;
        return (int) Math.round(remaining);
    }

    public View view() { return root; }

    public void detach(MapView mapView) {
        try {
            if (attachParent != null) attachParent.removeView(root);
            else mapView.removeView(root);
        } catch (Exception ignored) {}
    }
}
