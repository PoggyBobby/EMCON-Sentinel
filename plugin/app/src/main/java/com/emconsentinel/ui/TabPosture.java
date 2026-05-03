package com.emconsentinel.ui;

import android.content.Context;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import com.atak.plugins.impl.PluginLayoutInflater;
import com.atakmap.android.maps.MapView;
import com.atakmap.coremap.log.Log;

import com.emconsentinel.data.AORPosture;
import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.plugin.R;

import java.util.ArrayList;
import java.util.List;

/**
 * Tab 2: AOR Posture picker. Replaces the old "Threats" tab. Top: vertical list
 * of posture cards (one-tap to drop a worst-case threat envelope around the
 * operator's current position). Below: collapsed "I have specific intel"
 * disclosure with named-scenario buttons + place-by-hand controls.
 *
 * The new flow makes the tool useful from minute zero with no S2 brief — the
 * default "generic worst case" posture is already applied when the plugin loads.
 */
public final class TabPosture {

    private static final String TAG = "EmconSentinel.TabPosture";

    public interface ScenarioLoader {
        void load(String assetPath);
    }

    public interface ClearAllCallback {
        void clearAll();
    }

    private final Context pluginContext;
    private final MapView mapView;
    private final PluginState state;
    private final AORPostureManager postureManager;
    private final ScenarioLoader scenarioLoader;
    private final ClearAllCallback clearAllCallback;

    private final View root;
    private final LinearLayout cardContainer;
    private final List<View> cardViews = new ArrayList<>();
    private final List<AORPosture> postures;

    public TabPosture(Context pluginContext, MapView mapView, PluginState state,
                     AORPostureManager postureManager,
                     ScenarioLoader scenarioLoader, ClearAllCallback clearAllCallback) {
        this.pluginContext = pluginContext;
        this.mapView = mapView;
        this.state = state;
        this.postureManager = postureManager;
        this.scenarioLoader = scenarioLoader;
        this.clearAllCallback = clearAllCallback;
        this.postures = state.library().postures();

        this.root = PluginLayoutInflater.inflate(pluginContext, R.layout.tab_posture, null);
        this.cardContainer = root.findViewById(R.id.posture_card_container);

        buildCards();
        wireAdvanced();
        refreshSelection();
    }

    public View view() { return root; }

    /** Refresh the active-card highlight (e.g., after posture changes externally). */
    public void refreshSelection() {
        String activeId = postureManager == null ? null : postureManager.currentPostureId();
        for (int i = 0; i < cardViews.size(); i++) {
            View card = cardViews.get(i);
            boolean selected = activeId != null && activeId.equals(postures.get(i).id);
            TextView check = card.findViewById(R.id.posture_card_check);
            check.setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
            card.setBackgroundColor(selected ? 0xFF2A4A2A : 0xFF1A1A1A);
        }
    }

    private void buildCards() {
        for (final AORPosture p : postures) {
            PluginLayoutInflater.inflate(pluginContext, R.layout.posture_card, cardContainer);
            View cardView = cardContainer.getChildAt(cardContainer.getChildCount() - 1);
            TextView title = cardView.findViewById(R.id.posture_card_title);
            TextView subtitle = cardView.findViewById(R.id.posture_card_subtitle);
            View densityStrip = cardView.findViewById(R.id.posture_card_density_strip);
            title.setText(p.name);
            subtitle.setText(p.subtitle == null || p.subtitle.isEmpty()
                    ? p.density + " density · " + p.threats.size() + " threats"
                    : p.subtitle + "  ·  " + p.threats.size() + " threats");
            densityStrip.setBackgroundColor(densityColor(p.density));
            cardView.setOnClickListener(v -> {
                postureManager.applyPosture(p);
                refreshSelection();
                Toast.makeText(mapView.getContext(),
                        "Applied " + p.name + " (" + p.threats.size() + " threats around you)",
                        Toast.LENGTH_SHORT).show();
            });
            cardViews.add(cardView);
        }
    }

    private static int densityColor(String density) {
        if (density == null) return 0xFF666666;
        switch (density.toLowerCase()) {
            case "high":     return 0xFFFF1F1F;
            case "medium":   return 0xFFFFA500;
            case "moderate": return 0xFFFFA500;
            case "low":      return 0xFF2ECC40;
            default:         return 0xFF888888;
        }
    }

    private void wireAdvanced() {
        TextView disclosure = root.findViewById(R.id.posture_advanced_disclosure);
        View panel = root.findViewById(R.id.posture_advanced_panel);
        disclosure.setOnClickListener(v -> {
            boolean visible = panel.getVisibility() == View.VISIBLE;
            panel.setVisibility(visible ? View.GONE : View.VISIBLE);
            disclosure.setText(visible ? "▾ I have specific intel" : "▴ Hide intel options");
        });

        Button indo = root.findViewById(R.id.posture_btn_indo_scenario);
        Button eu   = root.findViewById(R.id.posture_btn_eu_scenario);
        Button cc   = root.findViewById(R.id.posture_btn_cc_scenario);
        Button argus = root.findViewById(R.id.posture_btn_argus_demo);
        indo.setOnClickListener(v -> scenarioLoader.load("demo_scenarios/indopacom_island.json"));
        eu.setOnClickListener(v -> scenarioLoader.load("demo_scenarios/rubicon_pokrovsk.json"));
        cc.setOnClickListener(v -> scenarioLoader.load("demo_scenarios/centcom_iran.json"));
        argus.setOnClickListener(v -> scenarioLoader.load("demo_scenarios/centcom_drone.json"));

        // Place-by-hand spinner + button
        final Spinner spinner = root.findViewById(R.id.posture_system_spinner);
        final List<AdversarySystem> systems = state.library().adversarySystems();
        List<String> labels = new ArrayList<>();
        for (AdversarySystem s : systems) labels.add(s.displayName);
        ArrayAdapter<String> adapter = new ArrayAdapter<>(pluginContext,
                R.layout.spinner_item, labels);
        adapter.setDropDownViewResource(R.layout.spinner_dropdown_item);
        spinner.setAdapter(adapter);

        Button addBtn = root.findViewById(R.id.posture_add_btn);
        addBtn.setOnClickListener(v -> {
            int pos = spinner.getSelectedItemPosition();
            if (pos < 0 || pos >= systems.size()) return;
            AdversarySystem chosen = systems.get(pos);
            state.setPendingPlacement(chosen);
            Toast.makeText(mapView.getContext(),
                    "Tap on map to place: " + chosen.displayName, Toast.LENGTH_SHORT).show();
        });

        Button clearBtn = root.findViewById(R.id.posture_clear_btn);
        clearBtn.setOnClickListener(v -> {
            if (clearAllCallback != null) clearAllCallback.clearAll();
            refreshSelection();
            Toast.makeText(mapView.getContext(), "Cleared all threats", Toast.LENGTH_SHORT).show();
        });
    }
}
