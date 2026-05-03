package com.emconsentinel.ui;

import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.preference.PreferenceManager;
import android.widget.Toast;

import com.atakmap.android.maps.MapView;
import com.atakmap.coremap.log.Log;

import com.emconsentinel.data.RadioProfile;

/**
 * First-run UX. On the first time the user opens EMCON Sentinel after enabling
 * the plugin, prompt: "Run the 60-second guided demo?". If yes, load INDOPACOM
 * + 10× speed + auto-start keying + narrate at 5/15/30/45 s via Toast popups.
 *
 * Gated by SharedPref "emcon-first-run-completed" so the prompt only shows once
 * per device. User can also re-trigger from settings (tab not yet built).
 */
public final class FirstRunTutorial {

    private static final String TAG = "EmconSentinel.FirstRun";
    private static final String PREF_KEY = "emcon-first-run-completed";

    public interface DemoActions {
        void loadScenario(String assetPath);
        void startKeying();
    }

    private final Context pluginContext;
    private final MapView mapView;
    private final PluginState state;
    private final DemoActions actions;
    private final SharedPreferences prefs;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final java.util.List<Runnable> pendingRunnables = new java.util.ArrayList<>();

    /** Cancel all pending postDelayed narration callbacks. Called from
     *  EmconSentinelMapComponent.onDestroyImpl so toasts don't fire after
     *  the plugin tears down (which would crash on a dead Activity context). */
    public void cancel() {
        synchronized (pendingRunnables) {
            for (Runnable r : pendingRunnables) ui.removeCallbacks(r);
            pendingRunnables.clear();
        }
    }

    private void scheduleNarration(Runnable r, long delayMs) {
        synchronized (pendingRunnables) { pendingRunnables.add(r); }
        ui.postDelayed(r, delayMs);
    }

    public FirstRunTutorial(Context pluginContext, MapView mapView, PluginState state,
                            DemoActions actions) {
        this.pluginContext = pluginContext;
        this.mapView = mapView;
        this.state = state;
        this.actions = actions;
        this.prefs = PreferenceManager.getDefaultSharedPreferences(mapView.getContext());
    }

    public boolean shouldPrompt() {
        return !prefs.getBoolean(PREF_KEY, false);
    }

    public void markCompleted() {
        prefs.edit().putBoolean(PREF_KEY, true).apply();
    }

    /** Call this from the bottom-sheet expand handler the first time the user opens it. */
    public void promptIfFirstRun() {
        if (!shouldPrompt()) return;
        try {
            new AlertDialog.Builder(mapView.getContext())
                    .setTitle("Welcome to EMCON Sentinel")
                    .setMessage("This plugin warns you when adversary RF direction-finding "
                            + "assets are about to fix your position.\n\n"
                            + "Run the 60-second guided demo? You'll see a sample threat "
                            + "scenario, watch the risk dial climb, and get a DISPLACE alert.")
                    .setPositiveButton("Run demo", (d, w) -> { markCompleted(); runDemo(); })
                    .setNegativeButton("Skip", (d, w) -> markCompleted())
                    .setCancelable(false)
                    .show();
        } catch (Exception e) {
            Log.e(TAG, "first-run prompt failed", e);
        }
    }

    /** The actual 60-second demo flow. Public so a "Run demo again" button can call it. */
    public void runDemo() {
        Log.i(TAG, "starting 60-second guided demo");

        // 1. Pick MicoAir LR900-F profile if it exists, else first profile
        RadioProfile picked = null;
        for (RadioProfile p : state.library().radioProfiles()) {
            if (p.id != null && p.id.toLowerCase().contains("micoair")) { picked = p; break; }
        }
        if (picked == null && !state.library().radioProfiles().isEmpty()) {
            picked = state.library().radioProfiles().get(0);
        }
        if (picked != null) state.setActiveProfile(picked);

        // 2. Switch to 10× demo speed so dwell saturates fast
        state.setDemoMode10x(true);

        // 3. Load INDOPACOM scenario (PRC adversaries pre-placed)
        actions.loadScenario("demo_scenarios/indopacom_island.json");

        // 4. Start keying after a short beat so user sees the scenario load first
        scheduleNarration(() -> {
            actions.startKeying();
            toast("Demo started — 10× speed, INDOPACOM PRC adversaries placed.");
        }, 1500);

        // 5. Narration toasts at key beats (timings reflect 10× scaling). All
        // tracked so cancel() can stop them if plugin destroys mid-tutorial.
        scheduleNarration(() -> toast(
                "Watch the dial — composite risk is climbing as adversaries dwell on you."), 6000);
        scheduleNarration(() -> toast(
                "CAUTION threshold passed — top threat name + range now in HUD."), 16000);
        scheduleNarration(() -> toast(
                "Crossing 50% — DISPLACE modal will pop up. Pick a candidate to drop a route."), 26000);
        scheduleNarration(() -> toast(
                "Tap the dial in the HUD to see the live link-budget math."), 46000);
    }

    private void toast(String msg) {
        try {
            Toast.makeText(mapView.getContext(), msg, Toast.LENGTH_LONG).show();
        } catch (Exception ignored) {}
    }
}
