package com.emconsentinel.ui;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.AnimationUtils;
import android.widget.FrameLayout;
import android.widget.TextView;

import com.atak.plugins.impl.PluginLayoutInflater;
import com.atakmap.android.maps.MapView;
import com.atakmap.coremap.log.Log;

import com.emconsentinel.plugin.R;

/**
 * Phone-native bottom sheet attached to the MapView. Owns expand/collapse
 * animation, tab switching, and inflation of tab content into a FrameLayout.
 *
 * Collapsed = drag handle only (~36 dp). Expanded = ~50% of map height with
 * tab strip + content. Tap the handle or call expand()/collapse() to toggle.
 */
public final class BottomSheetController {

    private static final String TAG = "EmconSentinel.BottomSheet";

    public enum Tab { RADIO, POSTURE, OPERATE }

    private final Context pluginContext;
    private final MapView mapView;
    private final View root;
    private final View tabStrip;
    private final FrameLayout contentFrame;
    private final TextView handleLabel;
    private final TextView handleCaret;
    private final TextView tabRadioBtn;
    private final TextView tabPostureBtn;
    private final TextView tabOperateBtn;

    // Tab content controllers
    private TabRadio tabRadio;
    private TabPosture tabPosture;
    private TabOperate tabOperate;

    private Tab currentTab = Tab.RADIO;
    private boolean expanded = false;
    private int expandedHeightPx = -1;
    private int collapsedHeightPx = -1;

    public BottomSheetController(Context pluginContext, MapView mapView,
                                 TabRadio tabRadio, TabPosture tabPosture, TabOperate tabOperate) {
        this.pluginContext = pluginContext;
        this.mapView = mapView;
        this.tabRadio = tabRadio;
        this.tabPosture = tabPosture;
        this.tabOperate = tabOperate;

        this.root = PluginLayoutInflater.inflate(pluginContext, R.layout.bottom_sheet, null);
        this.tabStrip = root.findViewById(R.id.sheet_tab_strip);
        this.contentFrame = root.findViewById(R.id.sheet_content_frame);
        this.handleLabel = root.findViewById(R.id.sheet_handle_label);
        this.handleCaret = root.findViewById(R.id.sheet_handle_caret);
        this.tabRadioBtn = root.findViewById(R.id.tab_btn_radio);
        this.tabPostureBtn = root.findViewById(R.id.tab_btn_threats);   // XML id retained
        this.tabOperateBtn = root.findViewById(R.id.tab_btn_operate);

        attach();
        wireHandlers();
        applyCollapsedVisuals();
    }

    private android.widget.FrameLayout attachParent;

    private void attach() {
        try {
            float density = mapView.getResources().getDisplayMetrics().density;
            collapsedHeightPx = (int) (32 * density);
            expandedHeightPx = -1;

            // Same fix as TopHudStrip: attach to the Activity's content
            // FrameLayout (android.R.id.content) so we composite above the map.
            android.app.Activity activity = activityFrom(mapView);
            attachParent = activity != null
                    ? activity.findViewById(android.R.id.content)
                    : null;
            if (attachParent == null) {
                Log.w(TAG, "could not resolve activity content FrameLayout — falling back to MapView");
                FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT, collapsedHeightPx);
                lp.gravity = Gravity.BOTTOM;
                mapView.addView(root, lp);
                return;
            }

            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT, collapsedHeightPx);
            lp.gravity = Gravity.BOTTOM;
            attachParent.addView(root, lp);
            attachParent.bringChildToFront(root);
            root.setElevation(30f * density);

            attachParent.addOnLayoutChangeListener(new View.OnLayoutChangeListener() {
                @Override public void onLayoutChange(View v,
                        int l, int t, int r, int b, int ol, int ot, int or, int ob) {
                    int parentH = b - t;
                    expandedHeightPx = (int) (parentH * 0.60);
                    pinToBottom(parentH);
                    root.bringToFront();
                }
            });
            root.post(() -> {
                pinToBottom(attachParent.getHeight());
                root.bringToFront();
            });
            Log.i(TAG, "bottom sheet attached to activity content frame");
        } catch (Exception e) {
            Log.e(TAG, "failed to attach bottom sheet", e);
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

    private void pinToBottom(int parentH) {
        int desired = expanded ? expandedHeightPx : collapsedHeightPx;
        if (desired <= 0) desired = collapsedHeightPx;
        ViewGroup.LayoutParams lp = root.getLayoutParams();
        if (lp.height != desired) {
            lp.height = desired;
            root.setLayoutParams(lp);
        }
        // FrameLayout positions us via gravity=BOTTOM; setY would override that.
        // We just resize and the layout snaps to the bottom of the parent.
    }

    private void wireHandlers() {
        // Tap the handle to toggle expanded/collapsed
        root.findViewById(R.id.sheet_handle_row).setOnClickListener(v -> toggle());

        tabRadioBtn.setOnClickListener(v -> selectTab(Tab.RADIO));
        tabPostureBtn.setOnClickListener(v -> selectTab(Tab.POSTURE));
        tabOperateBtn.setOnClickListener(v -> selectTab(Tab.OPERATE));
    }

    public void toggle() {
        if (expanded) collapse(); else expand();
    }

    public void expand() {
        if (expanded) return;
        expanded = true;
        if (expandedHeightPx <= 0) expandedHeightPx = (int) (mapView.getHeight() * 0.60);
        applyExpandedVisuals();
        animateHeight(collapsedHeightPx, expandedHeightPx);
        // Reload the current tab so its data is fresh
        showTabContent(currentTab);
    }

    public void collapse() {
        if (!expanded) return;
        expanded = false;
        applyCollapsedVisuals();
        animateHeight(expandedHeightPx, collapsedHeightPx);
    }

    public boolean isExpanded() { return expanded; }

    private void animateHeight(int from, int to) {
        ViewGroup.LayoutParams lp = root.getLayoutParams();
        // Simple instant resize — phone-friendly, no jank from ValueAnimator
        // contention with MapView's GL thread. If we want cinematic later, swap
        // to a ValueAnimator that interpolates over 200 ms.
        lp.height = to;
        root.setLayoutParams(lp);
        pinToBottom(mapView.getHeight());
    }

    private void applyExpandedVisuals() {
        handleLabel.setText("EMCON SENTINEL  ·  tap to collapse");
        handleCaret.setText("▼");
        tabStrip.setVisibility(View.VISIBLE);
        contentFrame.setVisibility(View.VISIBLE);
    }

    private void applyCollapsedVisuals() {
        handleLabel.setText("EMCON SENTINEL  ·  tap to set up");
        handleCaret.setText("▲");
        tabStrip.setVisibility(View.GONE);
        contentFrame.setVisibility(View.GONE);
    }

    public void selectTab(Tab t) {
        currentTab = t;
        tabRadioBtn.setBackgroundColor(t == Tab.RADIO ? 0xFF2A2A2A : 0x00000000);
        tabRadioBtn.setTextColor(t == Tab.RADIO ? 0xFFFFFFFF : 0xFFCCCCCC);
        tabPostureBtn.setBackgroundColor(t == Tab.POSTURE ? 0xFF2A2A2A : 0x00000000);
        tabPostureBtn.setTextColor(t == Tab.POSTURE ? 0xFFFFFFFF : 0xFFCCCCCC);
        tabOperateBtn.setBackgroundColor(t == Tab.OPERATE ? 0xFF2A2A2A : 0x00000000);
        tabOperateBtn.setTextColor(t == Tab.OPERATE ? 0xFFFFFFFF : 0xFFCCCCCC);
        showTabContent(t);
    }

    private void showTabContent(Tab t) {
        contentFrame.removeAllViews();
        View child;
        switch (t) {
            case RADIO:   child = tabRadio.view(); break;
            case POSTURE: child = tabPosture.view(); break;
            case OPERATE: child = tabOperate.view(); break;
            default: return;
        }
        if (child.getParent() instanceof ViewGroup) {
            ((ViewGroup) child.getParent()).removeView(child);
        }
        contentFrame.addView(child, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
    }

    public void detach() {
        try {
            if (attachParent != null) attachParent.removeView(root);
            else mapView.removeView(root);
        } catch (Exception ignored) {}
    }
}
