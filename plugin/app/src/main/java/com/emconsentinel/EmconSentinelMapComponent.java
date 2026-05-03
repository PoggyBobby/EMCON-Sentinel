
package com.emconsentinel;

import android.content.Context;
import android.content.Intent;
import android.net.wifi.WifiManager;

import com.atakmap.android.ipc.AtakBroadcast;
import com.atakmap.android.ipc.AtakBroadcast.DocumentedIntentFilter;
import com.atakmap.android.maps.MapItem;
import com.atakmap.android.maps.MapView;
import com.atakmap.android.dropdown.DropDownMapComponent;
import com.atakmap.coremap.filesystem.FileSystemUtils;
import com.atakmap.coremap.log.Log;

import com.atakmap.coremap.maps.coords.GeoPoint;

import com.emconsentinel.argus.ArgusDrone;
import com.emconsentinel.argus.ArgusFleet;
import com.emconsentinel.argus.ArgusFleetRenderer;
import com.emconsentinel.c2.C2Bridge;
import com.emconsentinel.c2.SdrBridge;
import com.emconsentinel.cot.CotEmitter;
import com.emconsentinel.cot.CotReceiver;
import com.emconsentinel.phone.PhoneEmitterMonitor;
import com.emconsentinel.data.AORPosture;
import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.AssetLibrary;
import com.emconsentinel.data.DemoScenario;
import com.emconsentinel.plugin.R;
import com.emconsentinel.prop.FreeSpaceEngine;
import com.emconsentinel.prop.PathLossEngine;
import com.emconsentinel.risk.DisplacementSearch;
import com.emconsentinel.risk.DwellClock;
import com.emconsentinel.risk.RiskScorer;
import com.emconsentinel.ui.AORPostureManager;
import com.emconsentinel.ui.AdversaryPlacer;
import com.emconsentinel.ui.BottomSheetController;
import com.emconsentinel.ui.BuddyAlertController;
import com.emconsentinel.ui.DisplaceModalController;
import com.emconsentinel.ui.DisplacementWaypointRenderer;
import com.emconsentinel.ui.HopCoachChip;
import com.emconsentinel.ui.FirstRunTutorial;
import com.emconsentinel.ui.MathOverlayController;
import com.emconsentinel.ui.PluginState;
import com.emconsentinel.ui.RiskTickLoop;
import com.emconsentinel.ui.SoundCues;
import com.emconsentinel.ui.SurvivabilityModalController;
import com.emconsentinel.ui.TabOperate;
import com.emconsentinel.ui.TabPosture;
import com.emconsentinel.ui.TabRadio;
import com.emconsentinel.ui.ThreatCircleRenderer;
import com.emconsentinel.ui.TopHudStrip;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;

public class EmconSentinelMapComponent extends DropDownMapComponent {

    private static final String TAG = "EmconSentinelMapComponent";

    private Context pluginContext;
    private EmconSentinelDropDownReceiver ddr;
    private AssetLibrary assetLibrary;
    private PluginState state;
    private AdversaryPlacer placer;
    private RiskTickLoop tickLoop;
    private ThreatCircleRenderer threatCircles;
    private TopHudStrip hud;
    private BottomSheetController bottomSheet;
    private TabRadio tabRadio;
    private TabPosture tabPosture;
    private TabOperate tabOperate;
    private DisplaceModalController displaceModal;
    private DisplacementWaypointRenderer waypointRenderer;
    private MathOverlayController mathOverlay;
    private HopCoachChip hopChip;
    private SurvivabilityModalController survModal;
    private FirstRunTutorial firstRun;
    private AORPostureManager postureManager;
    private ArgusFleet argusFleet;
    private ArgusFleetRenderer argusRenderer;
    private PhoneEmitterMonitor phoneEmitterMonitor;
    private SoundCues sounds;
    private CotEmitter cotEmitter;
    private CotReceiver cotReceiver;
    private BuddyAlertController buddyAlerts;
    private C2Bridge c2Bridge;
    private SdrBridge sdrBridge;
    private WifiManager.MulticastLock multicastLock;

    @Override
    public void onCreate(final Context context, Intent intent, final MapView view) {
        context.setTheme(R.style.ATAKPluginTheme);
        super.onCreate(context, intent, view);
        pluginContext = context;

        // Install bundled MOBAC tile sources (ESRI World Imagery, OSM) into ATAK's
        // mapsources scan dir on first run. ATAK ships with no imagery; without
        // this, users see a blurry vector world map. We drop XMLs the user can
        // then select from Layers Manager.
        installBasemaps(context);

        try (InputStream adv = context.getAssets().open("adversary_df_systems.json");
             InputStream prof = context.getAssets().open("radio_profiles.json")) {
            // Load AOR postures from assets/aor_postures/*.json before constructing
            // the AssetLibrary so they live alongside adversaries + radios.
            List<AORPosture> postures = loadAORPostures(context);
            assetLibrary = AssetLibrary.load(adv, prof, postures);
            Log.i(TAG, String.format("Loaded %d adversary systems, %d radio profiles, %d AOR postures",
                    assetLibrary.adversarySystems().size(),
                    assetLibrary.radioProfiles().size(),
                    assetLibrary.postures().size()));
        } catch (Exception e) {
            Log.e(TAG, "Failed to load asset library", e);
            return;
        }

        state = new PluginState(assetLibrary);

        // Core risk pipeline
        final PathLossEngine prop = new FreeSpaceEngine();   // CloudRF wired in once user supplies a key
        RiskScorer scorer = new RiskScorer(prop, new DwellClock());
        threatCircles = new ThreatCircleRenderer(view);
        placer = new AdversaryPlacer(view, state);
        placer.register();
        sounds = new SoundCues();
        DisplacementSearch search = new DisplacementSearch(prop);

        // New phone-first UI shell:
        //   TopHudStrip pinned to top   — risk ring + plain-English status + math button
        //   BottomSheetController       — collapsible 3-tab bottom sheet (Radio/Threats/Operate)
        //   DisplaceModalController     — full-screen MOVE NOW alert with vibrate + sound
        //   MathOverlayController       — judge-bait link-budget calc overlay

        mathOverlay = new MathOverlayController(context, view, state, prop);
        hud = new TopHudStrip(context, view,
                () -> mathOverlay.toggle(),
                () -> {
                    state.setDemoMode10x(!state.isDemoMode10x());
                    Log.i(TAG, "demo mode 10x: " + state.isDemoMode10x());
                    android.widget.Toast.makeText(view.getContext(),
                            state.isDemoMode10x() ? "Demo speed: 10×" : "Demo speed: 1×",
                            android.widget.Toast.LENGTH_SHORT).show();
                });
        displaceModal = new DisplaceModalController(context, view, state, search, sounds);

        // Bottom-sheet tab callbacks. Both implementations live here in MapComponent
        // because they own placer + threatCircles + map state.
        final TabPosture.ClearAllCallback clearAll = () -> clearAllAdversaries(view);
        final TabPosture.ScenarioLoader scenarioLoader =
                assetPath -> loadScenarioByPath(context, view, assetPath);

        survModal = new SurvivabilityModalController(context, view, state, prop);

        tabRadio = new TabRadio(context, state);
        tabOperate = new TabOperate(context, state, () -> survModal.show());
        // Posture manager constructed below uses placer+clearAllAdversaries that
        // are already set up. We construct the manager first, then the tab.
        // The deferred-post() block at the end of onCreate will auto-apply default.

        // Acquire a WifiManager MulticastLock so the wifi chipset doesn't filter
        // our outbound CoT and inbound C2 multicast packets. Without this on a
        // production phone, multicast send appears to "succeed" but nothing
        // leaves the device — which is exactly the silent-fail we were seeing.
        try {
            WifiManager wm = (WifiManager) view.getContext()
                    .getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if (wm != null) {
                multicastLock = wm.createMulticastLock("emcon-sentinel");
                multicastLock.setReferenceCounted(false);
                multicastLock.acquire();
                Log.i(TAG, "multicast lock acquired");
            }
        } catch (Exception e) {
            Log.w(TAG, "could not acquire multicast lock: " + e);
        }

        // Phase 7 — CoT federation. Best effort; if multicast init fails (no network)
        // we just don't broadcast — the rest of the plugin keeps working.
        try {
            cotEmitter = new CotEmitter();
            Log.i(TAG, "CoT federation enabled — emitting on " + CotEmitter.DEFAULT_GROUP + ":" + CotEmitter.DEFAULT_PORT);
        } catch (Exception e) {
            Log.w(TAG, "CoT emitter unavailable: " + e);
            cotEmitter = null;
        }

        // C2 telemetry-link bridge (real, no-sim). Listens for the Python sidecar
        // at tools/c2_bridge.py — when running, ATAK gets real RF activity and
        // can replace the manual keying toggle with observed transmissions.
        c2Bridge = new C2Bridge(state);
        c2Bridge.start();

        // Buddy alerts via the CoT mesh. When another EMCON Sentinel operator
        // goes red against a threat we also have placed (within 10 km of them
        // and within 25 km of us), surface a toast warning. Real shipping
        // feature, doesn't require a real second device — works the moment
        // any ATAK client running EMCON Sentinel joins the mesh.
        buddyAlerts = new BuddyAlertController(view, state);
        cotReceiver = new CotReceiver(state, buddyAlerts);
        cotReceiver.start();

        // SDR sidecar receiver — real ambient-RF observations from tools/sdr_bridge.py.
        // When the sidecar reports own-TX detection, isKeying() returns true (overrides
        // the manual button). When it reports adversary EW activity, that's surfaced as
        // a real "jammer detected" signal (state.sdrAdversaryEwActive()).
        sdrBridge = new SdrBridge(state);
        sdrBridge.start();

        // Phone-side RF emitter monitor — polls Android system services for
        // cellular/WiFi/BT state every 5 s and pushes the active emitter bands
        // into PluginState. The risk loop merges these with the operator's
        // chosen drone radio, so the dial reflects the FULL operator signature
        // (the phone is itself a high-EIRP emitter at the operator's location).
        // 100% real signal — no simulation; a radio that's off doesn't emit.
        phoneEmitterMonitor = new PhoneEmitterMonitor(view.getContext().getApplicationContext(),
                bands -> state.setPhoneEmitters(bands));
        phoneEmitterMonitor.start();

        // Hop-coach chip — surfaces "Quieter: try only X — drops risk N%" when
        // one band of the active drone radio is the dominant detection contributor.
        // Tap → expand bottom sheet → OPERATE tab (per-band toggles ship in next phase).
        hopChip = new HopCoachChip(context, view, () -> {
            com.emconsentinel.risk.HopRecommendation rec = state.lastHopRecommendation();
            if (bottomSheet != null) {
                bottomSheet.expand();
                bottomSheet.selectTab(BottomSheetController.Tab.OPERATE);
            }
            if (rec != null && tabOperate != null && !rec.bandsToDisable.isEmpty()) {
                tabOperate.highlightBand(rec.bandsToDisable.get(0));
            }
        });

        tickLoop = new RiskTickLoop(view, state, scorer, prop, hud, threatCircles, displaceModal, sounds, cotEmitter);
        tickLoop.setHopChip(hopChip);
        // Proactive "go here" green markers when risk crosses CAUTION (≥0.3) —
        // operator gets continuous displacement guidance, not just at MOVE NOW.
        waypointRenderer = new DisplacementWaypointRenderer(view, search);
        tickLoop.setWaypointRenderer(waypointRenderer);
        tickLoop.start();

        // AOR posture manager — drops curated worst-case threats around operator.
        // Auto-applies "generic worst case" so the tool is useful from minute zero
        // even if the operator never touches the Posture tab.
        postureManager = new AORPostureManager(assetLibrary, state, view, new AORPostureManager.ClearAndPlace() {
            @Override public void clear() { clearAllAdversaries(view); }
            @Override public void placeAt(AdversarySystem adv, GeoPoint p) { placer.placeAt(adv, p); }
        });

        // ARGUS fleet — simulated friendly UAS that scan for hidden adversaries.
        // When a drone's footprint covers a hidden threat, we drop a marker for it
        // and the next risk tick starts counting it. Lets the demo tell a "build
        // the picture before you commit to keying" story.
        argusRenderer = new ArgusFleetRenderer(view);
        argusFleet = new ArgusFleet(state,
                drones -> argusRenderer.apply(drones),
                (revealed, byWhom) -> {
                    // Drop a visible marker for the now-revealed adversary
                    com.atakmap.android.maps.Marker m = new com.atakmap.android.maps.Marker(
                            new GeoPoint(revealed.lat, revealed.lon),
                            java.util.UUID.randomUUID().toString());
                    m.setTitle("EMCON: " + revealed.system.displayName + " (by " + byWhom.callsign + ")");
                    m.setMetaString("emcon-adversary-id", revealed.system.id);
                    m.setColor(0xFFFF1F1F);
                    m.setAlwaysShowText(true);
                    m.setType(revealed.system.platform == AdversarySystem.Platform.AIRBORNE
                            ? "a-h-A" : "a-h-G");
                    view.getRootGroup().addItem(m);
                    android.widget.Toast.makeText(view.getContext(),
                            byWhom.callsign + " detected " + revealed.system.displayName,
                            android.widget.Toast.LENGTH_SHORT).show();
                });

        // Posture tab needs the manager built above
        tabPosture = new TabPosture(context, view, state, postureManager, scenarioLoader, clearAll);
        bottomSheet = new BottomSheetController(context, view, tabRadio, tabPosture, tabOperate);
        bottomSheet.selectTab(BottomSheetController.Tab.RADIO);

        // Defer to post() so MapView has a real center point by then
        view.post(() -> {
            if (state.placedCount() == 0) {
                postureManager.apply("generic-worst-case");
                if (tabPosture != null) tabPosture.refreshSelection();
            }
            refreshHudContext();
        });

        // First-run guided demo: orchestrates "load scenario, switch to 10×, start
        // keying" — uses the same scenario loader + state setters the tabs do.
        firstRun = new FirstRunTutorial(context, view, state, new FirstRunTutorial.DemoActions() {
            @Override public void loadScenario(String assetPath) {
                loadScenarioByPath(context, view, assetPath);
            }
            @Override public void startKeying() {
                state.setKeying(true);
            }
        });

        // DropDownReceiver becomes a thin wrapper: SHOW_PLUGIN intent just expands
        // the bottom sheet (and triggers the first-run prompt on first open).
        ddr = new EmconSentinelDropDownReceiver(view, context, state, bottomSheet, firstRun);
        Log.d(TAG, "registering the EMCON Sentinel DropDownReceiver filter");
        DocumentedIntentFilter ddFilter = new DocumentedIntentFilter();
        ddFilter.addAction(EmconSentinelDropDownReceiver.SHOW_PLUGIN);
        registerDropDownReceiver(ddr, ddFilter);
    }

    /** Push the current posture/scenario + radio name into the HUD's context sub-line. */
    private void refreshHudContext() {
        if (hud == null) return;
        StringBuilder sb = new StringBuilder();
        // Lead with risk mode so operator immediately knows what's contributing
        if (state != null) {
            switch (state.riskMode()) {
                case ACTIVE:  sb.append("ACTIVE"); break;
                case PASSIVE: sb.append("PASSIVE — phone only"); break;
                case IDLE:    sb.append("IDLE"); break;
            }
            sb.append("  ·  ");
        }
        if (currentScenarioName != null && !currentScenarioName.isEmpty()) {
            sb.append(currentScenarioName);
        } else {
            AORPosture p = postureManager == null ? null : postureManager.currentPosture();
            if (p != null) sb.append(p.name);
        }
        if (state != null && state.activeProfile() != null) {
            if (sb.length() > 0) sb.append("  ·  ");
            sb.append(state.activeProfile().displayName);
            int disabledCount = state.disabledBandIndices(state.activeProfile()).size();
            if (disabledCount > 0) {
                sb.append("  ·  ").append(disabledCount).append(" band")
                  .append(disabledCount > 1 ? "s" : "").append(" off");
            }
        }
        hud.setContext(sb.toString());
    }

    private String currentScenarioName;

    /** Recursively collect EMCON-tagged items from a MapGroup. */
    private static void collectEmconItems(com.atakmap.android.maps.MapGroup g, List<MapItem> out) {
        if (g == null) return;
        for (MapItem mi : g.getItems()) {
            if (mi.getMetaString("emcon-adversary-id", null) != null
                    || mi.getMetaString("emcon-argus-id", null) != null
                    || mi.getMetaString("emcon-displace-route", null) != null
                    || mi.getMetaString("emcon-displace-waypoint", null) != null) {
                out.add(mi);
            }
        }
        for (com.atakmap.android.maps.MapGroup child : g.getChildGroups()) {
            collectEmconItems(child, out);
        }
    }

    /** Enumerate assets/aor_postures/*.json and load each into AORPosture objects. */
    private List<AORPosture> loadAORPostures(Context context) {
        List<AORPosture> out = new ArrayList<>();
        try {
            String[] files = context.getAssets().list("aor_postures");
            if (files == null) return out;
            for (String f : files) {
                if (!f.endsWith(".json")) continue;
                try (InputStream is = context.getAssets().open("aor_postures/" + f)) {
                    out.add(AORPosture.load(is));
                } catch (Exception e) {
                    Log.w(TAG, "could not load posture " + f + ": " + e);
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "could not enumerate aor_postures dir: " + e);
        }
        return out;
    }

    /** Clear all EMCON-tagged adversaries, ARGUS drones, and Displace routes
     * (with their waypoint markers) from the map. */
    private void clearAllAdversaries(MapView view) {
        // Snapshot before removing — removeItem mutates getItems()'s backing
        // collection, which throws ConcurrentModification. Walk both the root
        // group AND the Route group, since waypoints get persisted into Route.
        List<MapItem> toRemove = new ArrayList<>();
        collectEmconItems(view.getRootGroup(), toRemove);
        com.atakmap.android.maps.MapGroup routeGroup = view.getRootGroup().findMapGroup("Route");
        if (routeGroup != null) collectEmconItems(routeGroup, toRemove);
        for (MapItem mi : toRemove) {
            com.atakmap.android.maps.MapGroup g = mi.getGroup();
            if (g != null) g.removeItem(mi);
            else view.getRootGroup().removeItem(mi);
        }
        state.clearPlaced();
        if (threatCircles != null) threatCircles.clear();
        if (argusFleet != null) argusFleet.stop();
        if (argusRenderer != null) argusRenderer.clear();
        if (tabPosture != null) tabPosture.refreshSelection();
        // Reset scenario name so HUD reverts to posture name on next refresh
        currentScenarioName = null;
    }

    /**
     * Load a demo scenario JSON from assets/, clear current state, pan to operator,
     * and drop each adversary. Used by Threats tab buttons and first-run tutorial.
     */
    private void loadScenarioByPath(Context context, MapView view, String assetPath) {
        try (InputStream sis = context.getAssets().open(assetPath)) {
            DemoScenario sc = DemoScenario.load(sis);
            Log.i(TAG, "loading demo scenario: " + sc.name);
            clearAllAdversaries(view);
            view.getMapController().panTo(new GeoPoint(sc.operatorLat, sc.operatorLon), true);
            state.setDemoOperator(sc.operatorLat, sc.operatorLon);
            currentScenarioName = sc.name;
            refreshHudContext();
            // Switch the bottom sheet to OPERATE so the user lands on the keying
            // button — they just confirmed they want to start the scenario.
            if (bottomSheet != null) {
                bottomSheet.selectTab(BottomSheetController.Tab.OPERATE);
            }

            // Spin up ARGUS fleet if the scenario defines drones. Drones launch
            // from the operator's actual location and fly out to their first
            // waypoint (visible takeoff). Honest "(sim)" tag on callsigns.
            if (!sc.argusDrones.isEmpty()) {
                java.util.List<ArgusDrone> drones = new java.util.ArrayList<>();
                double launchLat = sc.operatorLat;
                double launchLon = sc.operatorLon;
                for (DemoScenario.ArgusEntry a : sc.argusDrones) {
                    drones.add(new ArgusDrone(a.id, a.callsign + " (sim)",
                            a.altitudeMeters, a.scanRadiusKm, a.speedKmh, a.waypoints,
                            launchLat, launchLon));
                }
                argusFleet.setDrones(drones);
                argusFleet.start();
                Log.i(TAG, "ARGUS fleet started with " + drones.size() + " drones (launching from "
                        + launchLat + "," + launchLon + ")");
            }

            for (DemoScenario.PlacedEntry e : sc.adversaries) {
                AdversarySystem adv = findSystemById(e.systemId);
                if (adv == null) {
                    Log.w(TAG, "demo scenario references unknown system_id: " + e.systemId);
                    continue;
                }
                placer.placeAt(adv, new GeoPoint(e.lat, e.lon), e.hidden);
            }
            if (tabPosture != null) tabPosture.refreshSelection();
            Log.i(TAG, "demo scenario loaded: " + sc.adversaries.size() + " adversaries");
        } catch (Exception ex) {
            Log.e(TAG, "failed to load demo scenario " + assetPath, ex);
        }
    }

    /**
     * Drop bundled MOBAC tile-source XMLs into ATAK's mapsources scan dir
     * (atak_root/mobac/mapsources/) so the user gets selectable basemaps in the
     * Layers Manager without manual setup. ATAK auto-scans on the SCAN broadcast;
     * we fire one to make the new sources visible without an app restart.
     */
    private void installBasemaps(Context context) {
        // ESRI World Imagery only. We previously also shipped OSM as a fallback,
        // but OpenStreetMap's tile usage policy blocks ATAK's User-Agent —
        // tiles return HTTP 403 "Access blocked" images that look like a broken
        // map. Better to drop one good source than two with one broken.
        String[] sources = { "esri_world_imagery.xml" };
        boolean newAny = false;
        for (String s : sources) {
            File dst = FileSystemUtils.getItem("mobac/mapsources/" + s);
            if (dst.exists()) continue;
            try {
                File parent = dst.getParentFile();
                if (parent != null && !parent.exists()) {
                    boolean made = parent.mkdirs();
                    if (!made) {
                        Log.w(TAG, "could not create basemap parent dir " + parent.getAbsolutePath()
                                + " — basemap install likely to fail. Permissions?");
                    }
                }
                try (InputStream in = context.getAssets().open("mobac/" + s);
                     OutputStream out = new FileOutputStream(dst)) {
                    byte[] buf = new byte[8192];
                    int n;
                    while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                }
                Log.i(TAG, "installed basemap: " + dst.getAbsolutePath());
                newAny = true;
            } catch (Exception e) {
                Log.w(TAG, "could not install basemap " + s + ": " + e);
            }
        }
        if (newAny) {
            try {
                AtakBroadcast.getInstance().sendBroadcast(
                        new Intent("com.atakmap.android.maps.layers.SCAN"));
                Log.i(TAG, "broadcast SCAN to refresh ATAK Layers Manager");
            } catch (Exception e) {
                Log.w(TAG, "SCAN broadcast failed: " + e);
            }
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
        if (displaceModal != null) displaceModal.detach();
        if (waypointRenderer != null) waypointRenderer.clear();
        if (mathOverlay != null) mathOverlay.detach();
        if (hopChip != null) hopChip.detach(view);
        if (firstRun != null) firstRun.cancel();
        if (survModal != null) survModal.detach();
        if (hud != null) hud.detach(view);
        if (bottomSheet != null) bottomSheet.detach();
        if (tabOperate != null) tabOperate.detach();
        if (sounds != null) sounds.release();
        if (cotEmitter != null) cotEmitter.close();
        if (cotReceiver != null) cotReceiver.stop();
        if (c2Bridge != null) c2Bridge.stop();
        if (sdrBridge != null) sdrBridge.stop();
        if (phoneEmitterMonitor != null) phoneEmitterMonitor.stop();
        if (argusFleet != null) argusFleet.stop();
        if (argusRenderer != null) argusRenderer.clear();
        if (multicastLock != null && multicastLock.isHeld()) {
            try { multicastLock.release(); } catch (Exception ignored) {}
        }
        super.onDestroyImpl(context, view);
    }
}
