package com.emconsentinel.ui;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.AttributeSet;
import android.view.View;

/**
 * 56dp circular risk ring used in the top HUD strip. Just the ring + a single
 * numeric in the center — no dwell/threat/prop text (those live in the HUD's
 * sibling TextViews). Color: green/amber/red by composite score thresholds.
 */
public final class MiniRiskRing extends View {

    private static final int RING_THICKNESS_DP = 4;

    private final Paint ringBgPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ringFgPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint scoreTextPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF ringRect = new RectF();

    private double score = 0;

    public MiniRiskRing(Context c) { super(c); init(); }
    public MiniRiskRing(Context c, AttributeSet a) { super(c, a); init(); }

    private void init() {
        float density = getResources().getDisplayMetrics().density;
        ringBgPaint.setColor(0xFF333333);
        ringBgPaint.setStyle(Paint.Style.STROKE);
        ringBgPaint.setStrokeWidth(RING_THICKNESS_DP * density);

        ringFgPaint.setStyle(Paint.Style.STROKE);
        ringFgPaint.setStrokeWidth(RING_THICKNESS_DP * density);
        ringFgPaint.setStrokeCap(Paint.Cap.ROUND);

        scoreTextPaint.setColor(Color.WHITE);
        scoreTextPaint.setTextSize(9f * density);
        scoreTextPaint.setTextAlign(Paint.Align.CENTER);
        scoreTextPaint.setFakeBoldText(true);
    }

    public void setScore(double s) {
        if (s < 0) s = 0; else if (s > 1) s = 1;
        if (s != score) {
            score = s;
            postInvalidate();
        }
    }

    private int colorForScore() {
        if (score < 0.3) return 0xFF2ECC40;       // green
        if (score < 0.7) return 0xFFFFA500;       // amber
        return 0xFFFF1F1F;                         // red
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float density = getResources().getDisplayMetrics().density;
        float pad = RING_THICKNESS_DP * density;
        int w = getWidth();
        int h = getHeight();
        float size = Math.min(w, h) - 2 * pad;
        float cx = w / 2f;
        float cy = h / 2f;
        ringRect.set(cx - size / 2f, cy - size / 2f, cx + size / 2f, cy + size / 2f);

        canvas.drawArc(ringRect, 0, 360, false, ringBgPaint);
        ringFgPaint.setColor(colorForScore());
        canvas.drawArc(ringRect, -90, (float) (score * 360), false, ringFgPaint);

        Paint.FontMetrics fm = scoreTextPaint.getFontMetrics();
        float textY = cy - (fm.ascent + fm.descent) / 2f;
        canvas.drawText(String.format("%d%%", (int) Math.round(score * 100)), cx, textY, scoreTextPaint);
    }
}
