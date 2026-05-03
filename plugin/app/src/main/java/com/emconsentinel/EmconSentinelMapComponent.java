
package com.emconsentinel;

import android.content.Context;
import android.content.Intent;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.FrameLayout;

import com.atakmap.android.ipc.AtakBroadcast.DocumentedIntentFilter;
import com.atakmap.android.maps.MapItem;
import com.atakmap.android.maps.MapView;
import com.atakmap.android.dropdown.DropDownMapComponent;
import com.atakmap.coremap.log.Log;

import com.atakmap.coremap.maps.coords.GeoPoint;

import com.emconsentinel.c2.C2Bridge;
import com.emconsentinel.cot.CotEmitter;
import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.AssetLibrary;
import com.emconsentinel.data.DemoScenario;
import com.emconsentinel.plugin.R;
import com.emconsentinel.prop.FreeSpaceEngine;
import com.emconsentinel.prop.PathLossEngine;
import com.emconsentinel.risk.DisplacementSearch;
import com.emconsentinel.risk.DwellClock;
import com.emconsentinel.risk.RiskScorer;
import com.emconsentinel.ui.AdversaryPlacer;
import com.emconsentinel.ui.DisplaceBanner;
import com.emconsentinel.ui.PluginState;
import com.emconsentinel.ui.RiskDialView;
import com.emconsentinel.ui.RiskTickLoop;
import com.emconsentinel.ui.SoundCues;
import com.emconsentinel.ui.ThreatCircleRenderer;

import java.io.InputStream;

public class EmconSentinelMapComponent extends DropDownMapComponent {

    private static final String TAG = "EmconSentinelMapComponent";

    private Context pluginContext;
    private EmconSentinelDropDownReceiver ddr;
    private AssetLibrary assetLibrary;
    private PluginState state;
    private AdversaryPlacer placer;
    private RiskTickLoop tickLoop;
    private ThreatCircleRenderer threatCircles;
    private RiskDialView dial;
    private DisplaceBanner banner;
    private SoundCues sounds;
    private CotEmitter cotEmitter;
    private C2Bridge c2Bridge;

    @Override
    public void onCreate(final Context context, Intent intent, final MapView view) {
        context.setTheme(R.style.ATAKPluginTheme);
        super.onCreate(context, intent, view);
        pluginContext = context;

        try (InputStream adv = context.getAssets().open("adversary_df_systems.json");
             InputStream prof = context.getAssets().open("radio_profiles.json")) {
            assetLibrary = AssetLibrary.load(adv, prof);
            Log.i(TAG, String.format("Loaded %d adversary systems, %d radio profiles",
                    assetLibrary.adversarySystems().size(),
                    assetLibrary.radioProfiles().size()));
        } catch (Exception e) {
            Log.e(TAG, "Failed to load asset library", e);
            return;
        }

        state = new PluginState(assetLibrary);

        // Pieces
        PathLossEngine prop = new FreeSpaceEngine();   // CloudRF wired in once user supplies a key
        RiskScorer scorer = new RiskScorer(prop, new DwellClock());
        threatCircles = new ThreatCircleRenderer(view);
        placer = new AdversaryPlacer(view, state);
        placer.register();

        dial = new RiskDialView(context);
        addDialOverlay(view, dial);
        // Long-press the dial to flip 10x demo mode (per brief)
        dial.wireDemoModeLongPress(() -> {
            state.setDemoMode10x(!state.isDemoMode10x());
            Log.i(TAG, "demo mode 10x: " + state.isDemoMode10x());
        });

        DisplacementSearch search = new DisplacementSearch(prop);
        banner = new DisplaceBanner(view, context, state, search);
        sounds = new SoundCues();

        // Phase 7 — CoT federation. Best effort; if multicast init fails (no network)
        // we just don't broadcast — the rest of the plugin keeps working.
        try {
            cotEmitter = new CotEmitter();
            Log.i(TAG, "CoT federation enabled — emitting on " + CotEmitter.DEFAULT_GROUP + ":" + CotEmitter.DEFAULT_PORT);
        } catch (Exception e) {
            Log.w(TAG, "CoT emitter unavailable: " + e.getMessage());
            cotEmitter = null;
        }

        // C2 telemetry-link bridge (real, no-sim). Listens for the Python sidecar
        // at tools/c2_bridge.py — when running, ATAK gets real RF activity and
        // can replace the manual keying toggle with observed transmissions.
        c2Bridge = new C2Bridge(state);
        c2Bridge.start();

        tickLoop = new RiskTickLoop(view, state, scorer, prop, dial, threatCircles, banner, sounds, cotEmitter);
        tickLoop.start();

        Runnable onClear = () -> {
            // Remove EMCON-tagged map items + clear placed list + clear circles
            for (MapItem mi : view.getRootGroup().getItems()) {
                String aid = mi.getMetaString("emcon-adversary-id", null);
                if (aid != null) view.getRootGroup().removeItem(mi);
            }
            state.clearPlaced();
            threatCircles.clear();
        };
        final AdversaryPlacer placerRef = placer;
        Runnable onLoadDemo = () -> {
            try (InputStream sis = context.getAssets().open("demo_scenarios/rubicon_pokrovsk.json")) {
                DemoScenario sc = DemoScenario.load(sis);
                Log.i(TAG, "loading demo scenario: " + sc.name);
                // Clear existing
                onClear.run();
                // Pan map to operator location
                view.getMapController().panTo(new GeoPoint(sc.operatorLat, sc.operatorLon), true);
                // Drop each adversary
                for (DemoScenario.PlacedEntry e : sc.adversaries) {
                    AdversarySystem adv = findSystemById(e.systemId);
                    if (adv == null) {
                        Log.w(TAG, "demo scenario references unknown system_id: " + e.systemId);
                        continue;
                    }
                    placerRef.placeAt(adv, new GeoPoint(e.lat, e.lon));
                }
                Log.i(TAG, "demo scenario loaded: " + sc.adversaries.size() + " adversaries");
            } catch (Exception ex) {
                Log.e(TAG, "failed to load demo scenario", ex);
            }
        };

        ddr = new EmconSentinelDropDownReceiver(view, context, state, onClear, onLoadDemo);
        Log.d(TAG, "registering the EMCON Sentinel DropDownReceiver filter");
        DocumentedIntentFilter ddFilter = new DocumentedIntentFilter();
        ddFilter.addAction(EmconSentinelDropDownReceiver.SHOW_PLUGIN);
        registerDropDownReceiver(ddr, ddFilter);
    }

    private void addDialOverlay(MapView mapView, RiskDialView dial) {
        try {
            float density = pluginContext.getResources().getDisplayMetrics().density;
            int w = (int) (180 * density);
            int h = (int) (220 * density);
            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(w, h);
            lp.gravity = Gravity.BOTTOM | Gravity.END;
            lp.bottomMargin = (int) (16 * density);
            lp.rightMargin = (int) (16 * density);
            mapView.addView(dial, lp);
            Log.i(TAG, "risk dial overlay attached to MapView");
        } catch (Exception e) {
            Log.e(TAG, "failed to attach dial overlay", e);
        }
    }

    public AssetLibrary getAssetLibrary() { return assetLibrary; }
    public PluginState getState() { return state; }

    private AdversarySystem findSystemById(String id) {
        for (AdversarySystem s : assetLibrary.adversarySystems()) {
            if (s.id.equals(id)) return s;
        }
        return null;
    }

    @Override
    protected void onDestroyImpl(Context context, MapView view) {
        if (tickLoop != null) tickLoop.stop();
        if (placer != null) placer.unregister();
        if (threatCircles != null) threatCircles.clear();
        if (banner != null) banner.detach();
        if (sounds != null) sounds.release();
        if (cotEmitter != null) cotEmitter.close();
        if (c2Bridge != null) c2Bridge.stop();
        super.onDestroyImpl(context, view);
    }
}
