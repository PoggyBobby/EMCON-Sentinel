
package com.emconsentinel;

import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import com.atak.plugins.impl.PluginLayoutInflater;
import com.atakmap.android.dropdown.DropDown.OnStateListener;
import com.atakmap.android.dropdown.DropDownReceiver;
import com.atakmap.android.maps.MapView;
import com.atakmap.coremap.log.Log;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.AssetLibrary;
import com.emconsentinel.data.RadioProfile;
import com.emconsentinel.plugin.R;
import com.emconsentinel.ui.PluginState;

import java.util.ArrayList;
import java.util.List;

public class EmconSentinelDropDownReceiver extends DropDownReceiver implements OnStateListener {

    public static final String TAG = "EmconSentinelDropDownReceiver";
    public static final String SHOW_PLUGIN = "com.emconsentinel.SHOW_PLUGIN";

    private final View paneView;
    private final Context pluginContext;
    private final PluginState state;
    private final Runnable onClearAssets;
    private final Runnable onLoadDemoScenario;

    private Button keyingButton;
    private TextView keyingStatusLabel;
    private TextView placedAssetsLabel;

    public EmconSentinelDropDownReceiver(final MapView mapView,
                                          final Context context,
                                          final PluginState state,
                                          final Runnable onClearAssets,
                                          final Runnable onLoadDemoScenario) {
        super(mapView);
        this.pluginContext = context;
        this.state = state;
        this.onClearAssets = onClearAssets;
        this.onLoadDemoScenario = onLoadDemoScenario;
        this.paneView = PluginLayoutInflater.inflate(context, R.layout.setup_pane, null);
        wireWidgets();
    }

    private void wireWidgets() {
        AssetLibrary lib = state.library();

        // 1. Radio profile spinner
        Spinner profileSpinner = paneView.findViewById(R.id.radio_profile_spinner);
        final List<RadioProfile> profiles = lib.radioProfiles();
        List<String> profileLabels = new ArrayList<>();
        for (RadioProfile p : profiles) profileLabels.add(p.displayName);
        ArrayAdapter<String> profileAdapter = new ArrayAdapter<>(pluginContext,
                android.R.layout.simple_spinner_item, profileLabels);
        profileAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        profileSpinner.setAdapter(profileAdapter);
        profileSpinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> p, View v, int position, long id) {
                state.setActiveProfile(profiles.get(position));
                Log.i(TAG, "active radio profile: " + profiles.get(position).id);
            }
            @Override public void onNothingSelected(AdapterView<?> p) {}
        });

        // 2. Adversary picker spinner
        final Spinner advSpinner = paneView.findViewById(R.id.adversary_picker_spinner);
        final List<AdversarySystem> systems = lib.adversarySystems();
        List<String> sysLabels = new ArrayList<>();
        for (AdversarySystem s : systems) sysLabels.add(s.displayName);
        ArrayAdapter<String> sysAdapter = new ArrayAdapter<>(pluginContext,
                android.R.layout.simple_spinner_item, sysLabels);
        sysAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        advSpinner.setAdapter(sysAdapter);

        placedAssetsLabel = paneView.findViewById(R.id.placed_assets_label);
        refreshPlacedLabel();

        // 3. Add asset
        Button addAssetBtn = paneView.findViewById(R.id.add_asset_button);
        addAssetBtn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                int pos = advSpinner.getSelectedItemPosition();
                if (pos < 0 || pos >= systems.size()) return;
                AdversarySystem chosen = systems.get(pos);
                state.setPendingPlacement(chosen);
                Toast.makeText(pluginContext,
                        "Tap on map to place: " + chosen.displayName, Toast.LENGTH_SHORT).show();
            }
        });

        // 4. Clear assets
        Button clearBtn = paneView.findViewById(R.id.clear_assets_button);
        clearBtn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                if (onClearAssets != null) onClearAssets.run();
                refreshPlacedLabel();
                Toast.makeText(pluginContext, "Cleared all adversary assets", Toast.LENGTH_SHORT).show();
            }
        });

        // 5. Load demo scenario
        Button demoBtn = paneView.findViewById(R.id.load_demo_button);
        demoBtn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                if (onLoadDemoScenario != null) onLoadDemoScenario.run();
                refreshPlacedLabel();
            }
        });

        // 6. Keying toggle
        keyingButton = paneView.findViewById(R.id.keying_button);
        keyingStatusLabel = paneView.findViewById(R.id.keying_status_label);
        applyKeyingButtonState();
        keyingButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                state.setKeying(!state.isKeying());
                applyKeyingButtonState();
            }
        });

        // 7. About
        Button aboutBtn = paneView.findViewById(R.id.about_button);
        aboutBtn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { showAboutDialog(); }
        });
    }

    public void refreshPlacedLabel() {
        if (placedAssetsLabel != null) {
            int n = state.placedCount();
            placedAssetsLabel.setText(n == 0 ? "(none placed)" : (n + " placed"));
        }
    }

    private void applyKeyingButtonState() {
        if (keyingButton == null) return;
        boolean keying = state.isKeying();
        keyingButton.setText(keying ? "STOP KEYING" : "START KEYING");
        keyingButton.setBackgroundColor(keying ? 0xFFCC1F1F : 0xFF2ECC40);
        keyingButton.setTextColor(0xFFFFFFFF);
        keyingStatusLabel.setText(keying
                ? "Keying — risk dial active. Stop to reset dwell."
                : "Idle. Press START KEYING to begin emitting.");
    }

    private void showAboutDialog() {
        StringBuilder sb = new StringBuilder();
        sb.append("EMCON Sentinel — adversary OSINT sources\n\n");
        for (AdversarySystem s : state.library().adversarySystems()) {
            sb.append("• ").append(s.displayName).append("\n   ").append(s.source).append("\n\n");
        }
        sb.append("\nPropagation: CloudRF SOOTHSAYER API (terrain-aware) with free-space ");
        sb.append("Friis fallback. Risk model: sigmoid detection × exponential dwell ");
        sb.append("saturation × 1-minus-product composite.\n\n");
        sb.append("Open source under Apache 2.0.");
        new AlertDialog.Builder(getMapView().getContext())
                .setTitle("About EMCON Sentinel")
                .setMessage(sb.toString())
                .setPositiveButton("Close", null)
                .show();
    }

    public void disposeImpl() {}

    @Override
    public void onReceive(Context context, Intent intent) {
        if (SHOW_PLUGIN.equals(intent.getAction())) {
            Log.d(TAG, "showing EMCON Sentinel pane");
            showDropDown(paneView, HALF_WIDTH, FULL_HEIGHT, FULL_WIDTH, HALF_HEIGHT, false, this);
        }
    }

    @Override public void onDropDownSelectionRemoved() {}
    @Override public void onDropDownVisible(boolean v) {}
    @Override public void onDropDownSizeChanged(double w, double h) {}
    @Override public void onDropDownClose() {}
}
