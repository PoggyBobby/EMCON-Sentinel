package com.emconsentinel.ui;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.AttributeSet;
import android.view.View;

/**
 * A small floating dial that paints a colored ring (green / amber / red) for the composite
 * risk score, plus a numeric score, dwell timer, and top-threat string. Pure Canvas — no
 * external view dependencies — so it can be added to any ATAK overlay.
 */
public final class RiskDialView extends View {

    private static final int RING_THICKNESS_DP = 14;
    private static final int CONTAINER_BG = 0xCC000000;

    private final Paint ringBgPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ringFgPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint scoreTextPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint subTextPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint smallTextPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint bgPaint = new Paint();
    private final RectF ringRect = new RectF();

    private double score = 0;       // 0..1
    private double dwellSeconds = 0;
    private String topThreatLine = "";
    private String propModeLine = "";
    private boolean demoMode10x = false;

    public RiskDialView(Context context) { super(context); init(); }
    public RiskDialView(Context context, AttributeSet attrs) { super(context, attrs); init(); }

    public void wireDemoModeLongPress(final Runnable onLongPress) {
        setOnLongClickListener(v -> {
            if (onLongPress != null) onLongPress.run();
            return true;
        });
    }

    private void init() {
        float density = getResources().getDisplayMetrics().density;
        ringBgPaint.setColor(0xFF333333);
        ringBgPaint.setStyle(Paint.Style.STROKE);
        ringBgPaint.setStrokeWidth(RING_THICKNESS_DP * density);

        ringFgPaint.setStyle(Paint.Style.STROKE);
        ringFgPaint.setStrokeWidth(RING_THICKNESS_DP * density);
        ringFgPaint.setStrokeCap(Paint.Cap.ROUND);

        scoreTextPaint.setColor(Color.WHITE);
        scoreTextPaint.setTextSize(34f * density);
        scoreTextPaint.setTextAlign(Paint.Align.CENTER);
        scoreTextPaint.setFakeBoldText(true);

        subTextPaint.setColor(0xFFCCCCCC);
        subTextPaint.setTextSize(11f * density);
        subTextPaint.setTextAlign(Paint.Align.CENTER);

        smallTextPaint.setColor(0xFF888888);
        smallTextPaint.setTextSize(9f * density);
        smallTextPaint.setTextAlign(Paint.Align.CENTER);

        bgPaint.setColor(CONTAINER_BG);
    }

    public void setRisk(double score, double dwellSeconds, String topThreatLine,
                        String propModeLine, boolean demoMode10x) {
        this.score = clamp01(score);
        this.dwellSeconds = dwellSeconds;
        this.topThreatLine = topThreatLine == null ? "" : topThreatLine;
        this.propModeLine = propModeLine == null ? "" : propModeLine;
        this.demoMode10x = demoMode10x;
        postInvalidate();
    }

    private static double clamp01(double v) {
        if (v < 0) return 0;
        if (v > 1) return 1;
        return v;
    }

    private int colorForScore() {
        if (score < 0.3) return 0xFF2ECC40;       // green
        if (score < 0.7) return 0xFFFFA500;       // amber
        return 0xFFFF1F1F;                         // red
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        int w = getWidth();
        int h = getHeight();
        canvas.drawRect(0, 0, w, h, bgPaint);

        float density = getResources().getDisplayMetrics().density;
        float pad = RING_THICKNESS_DP * density;
        float ringSize = Math.min(w, h * 0.7f) - 2 * pad;
        float cx = w / 2f;
        float ringTop = pad;
        ringRect.set(cx - ringSize / 2f, ringTop, cx + ringSize / 2f, ringTop + ringSize);

        canvas.drawArc(ringRect, 0, 360, false, ringBgPaint);
        ringFgPaint.setColor(colorForScore());
        canvas.drawArc(ringRect, -90, (float) (score * 360), false, ringFgPaint);

        String numeric = String.format("%.2f", score);
        Paint.FontMetrics fm = scoreTextPaint.getFontMetrics();
        float scoreCy = ringRect.centerY() - (fm.ascent + fm.descent) / 2f;
        canvas.drawText(numeric, cx, scoreCy, scoreTextPaint);

        long dwellInt = (long) dwellSeconds;
        long mins = dwellInt / 60;
        long secs = dwellInt % 60;
        canvas.drawText(String.format("dwell %dm %02ds", mins, secs),
                cx, ringRect.bottom + 14 * density, subTextPaint);

        if (!topThreatLine.isEmpty()) {
            canvas.drawText(topThreatLine, cx, ringRect.bottom + 30 * density, smallTextPaint);
        }

        if (!propModeLine.isEmpty()) {
            canvas.drawText(propModeLine, cx, ringRect.bottom + 46 * density, smallTextPaint);
        }

        if (demoMode10x) {
            Paint demoPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
            demoPaint.setColor(0xFFFFFF66);
            demoPaint.setTextSize(11f * density);
            demoPaint.setTextAlign(Paint.Align.CENTER);
            canvas.drawText("DEMO MODE 10x", cx, 14 * density, demoPaint);
        }
    }
}
