package com.emconsentinel.risk;

import com.emconsentinel.data.AdversarySystem;

public final class PlacedAdversary {
    public final AdversarySystem system;
    public final double lat;
    public final double lon;
    /**
     * When true, the adversary is on the map but invisible to the operator's risk
     * loop until a friendly scanner (e.g. an ARGUS drone) detects it. Lets us
     * model the "fog of war" demo where threats are revealed progressively
     * by sensor coverage instead of being assumed up front.
     */
    public boolean hidden;

    public PlacedAdversary(AdversarySystem system, double lat, double lon) {
        this(system, lat, lon, false);
    }

    public PlacedAdversary(AdversarySystem system, double lat, double lon, boolean hidden) {
        this.system = system;
        this.lat = lat;
        this.lon = lon;
        this.hidden = hidden;
    }
}
