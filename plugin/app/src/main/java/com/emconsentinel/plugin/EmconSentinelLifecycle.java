
package com.emconsentinel.plugin;


import com.atak.plugins.impl.AbstractPluginLifecycle;
import com.emconsentinel.EmconSentinelMapComponent;
import android.content.Context;


/**
 * Please note:
 *     Support for versions prior to 4.5.1 can make use of a copy of AbstractPluginLifeCycle shipped with
 *     the plugin.
 */
public class EmconSentinelLifecycle extends AbstractPluginLifecycle {

    private final static String TAG = "EmconSentinelLifecycle";

    public EmconSentinelLifecycle(Context ctx) {
        super(ctx, new EmconSentinelMapComponent());
        PluginNativeLoader.init(ctx);
    }

}
