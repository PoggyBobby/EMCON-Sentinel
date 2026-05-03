package com.emconsentinel.argus;

import android.os.Handler;
import android.os.Looper;

import com.atakmap.coremap.log.Log;

import com.emconsentinel.risk.PlacedAdversary;
import com.emconsentinel.ui.PluginState;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Owns a list of ArgusDrones and ticks them on a 1-Hz Handler. Each tick:
 *   1. Each drone advances 1 second along its route
 *   2. For every hidden adversary in PluginState, check if any drone's scan
 *      footprint covers it. If yes, reveal it.
 *   3. Notify the renderer to update markers.
 *
 * Stateless re-entry-safe.
 */
public final class ArgusFleet {

    private static final String TAG = "EmconSentinel.ArgusFleet";

    public interface OnTick {
        void onTick(List<ArgusDrone> drones);
    }

    public interface OnDetect {
        void onDetect(PlacedAdversary revealed, ArgusDrone byWhom);
    }

    private final PluginState state;
    private final List<ArgusDrone> drones = new ArrayList<>();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final OnTick onTick;
    private final OnDetect onDetect;

    private final Runnable tickRunnable = new Runnable() {
        @Override public void run() {
            if (!running.get()) return;
            doTick();
            handler.postDelayed(this, 1000L);
        }
    };

    public ArgusFleet(PluginState state, OnTick onTick, OnDetect onDetect) {
        this.state = state;
        this.onTick = onTick;
        this.onDetect = onDetect;
    }

    public List<ArgusDrone> drones() { return drones; }

    public void setDrones(List<ArgusDrone> ds) {
        drones.clear();
        drones.addAll(ds);
        Log.i(TAG, "fleet now has " + drones.size() + " drones");
    }

    public void start() {
        if (running.compareAndSet(false, true)) {
            handler.post(tickRunnable);
        }
    }

    public void stop() {
        running.set(false);
        handler.removeCallbacks(tickRunnable);
        drones.clear();
    }

    public boolean isRunning() { return running.get(); }

    private void doTick() {
        // 1. Advance every drone by 1 second
        for (ArgusDrone d : drones) d.tick(1.0);

        // 2. Reveal any hidden adversaries that fall inside any drone's footprint
        for (PlacedAdversary p : state.placedAdversariesSnapshot()) {
            if (!p.hidden) continue;
            for (ArgusDrone d : drones) {
                if (d.canDetect(p.lat, p.lon)) {
                    p.hidden = false;
                    Log.i(TAG, d.callsign + " detected " + p.system.id + " at "
                            + p.lat + "," + p.lon);
                    if (onDetect != null) onDetect.onDetect(p, d);
                    break;
                }
            }
        }

        // 3. Tell the renderer to redraw
        if (onTick != null) onTick.onTick(drones);
    }
}
