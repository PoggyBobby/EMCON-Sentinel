
package com.emconsentinel;

import android.content.Context;
import android.content.Intent;

import com.atakmap.android.ipc.AtakBroadcast.DocumentedIntentFilter;
import com.atakmap.android.maps.MapView;
import com.atakmap.android.dropdown.DropDownMapComponent;
import com.atakmap.coremap.log.Log;

import com.emconsentinel.data.AssetLibrary;
import com.emconsentinel.plugin.R;

import java.io.InputStream;

public class EmconSentinelMapComponent extends DropDownMapComponent {

    private static final String TAG = "EmconSentinelMapComponent";

    private Context pluginContext;
    private EmconSentinelDropDownReceiver ddr;
    private AssetLibrary assetLibrary;

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
        }

        ddr = new EmconSentinelDropDownReceiver(view, context);

        Log.d(TAG, "registering the plugin filter");
        DocumentedIntentFilter ddFilter = new DocumentedIntentFilter();
        ddFilter.addAction(EmconSentinelDropDownReceiver.SHOW_PLUGIN);
        registerDropDownReceiver(ddr, ddFilter);
    }

    public AssetLibrary getAssetLibrary() {
        return assetLibrary;
    }

    @Override
    protected void onDestroyImpl(Context context, MapView view) {
        super.onDestroyImpl(context, view);
    }

}
