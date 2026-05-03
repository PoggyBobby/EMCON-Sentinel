package com.emconsentinel;

import android.content.Context;
import android.content.Intent;
import android.view.View;

import com.atakmap.android.dropdown.DropDown.OnStateListener;
import com.atakmap.android.dropdown.DropDownReceiver;
import com.atakmap.android.maps.MapView;
import com.atakmap.coremap.log.Log;

import com.emconsentinel.ui.BottomSheetController;
import com.emconsentinel.ui.FirstRunTutorial;
import com.emconsentinel.ui.PluginState;

/**
 * Thin wrapper around the new bottom-sheet UX. The EMCON Sentinel tile in the
 * ATAK Tools menu fires the SHOW_PLUGIN intent — we respond by expanding the
 * bottom sheet and (on first run) showing the welcome/auto-demo prompt.
 *
 * No more right-side DropDown pane: all the controls now live in the bottom
 * sheet attached directly to the MapView, which works whether the plugin is
 * "selected" by ATAK's DropDownManager or not.
 */
public class EmconSentinelDropDownReceiver extends DropDownReceiver implements OnStateListener {

    public static final String TAG = "EmconSentinelDropDownReceiver";
    public static final String SHOW_PLUGIN = "com.emconsentinel.SHOW_PLUGIN";

    private final BottomSheetController bottomSheet;
    private final FirstRunTutorial firstRun;

    /** Hidden 1×1 view we hand to ATAK's DropDownManager since it requires a non-null view. */
    private final View dummyView;

    public EmconSentinelDropDownReceiver(MapView mapView, Context pluginContext,
                                          PluginState state,
                                          BottomSheetController bottomSheet,
                                          FirstRunTutorial firstRun) {
        super(mapView);
        this.bottomSheet = bottomSheet;
        this.firstRun = firstRun;
        this.dummyView = new View(mapView.getContext());
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        if (!SHOW_PLUGIN.equals(intent.getAction())) return;
        Log.d(TAG, "SHOW_PLUGIN received — expanding bottom sheet");
        if (bottomSheet != null) {
            bottomSheet.expand();
            // Show first-run prompt the very first time the user opens us
            if (firstRun != null && firstRun.shouldPrompt()) {
                firstRun.promptIfFirstRun();
            }
        }
        // We don't actually open a DropDown pane any more, but ATAK's
        // DropDownManager expects something. Hand it our dummy view at 0×0
        // so it considers the request "handled" and doesn't re-fire.
    }

    @Override public void disposeImpl() {}
    @Override public void onDropDownSelectionRemoved() {}
    @Override public void onDropDownVisible(boolean v) {}
    @Override public void onDropDownSizeChanged(double w, double h) {}
    @Override public void onDropDownClose() {}
}
