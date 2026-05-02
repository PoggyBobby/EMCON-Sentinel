package com.emconsentinel.risk;

import com.emconsentinel.data.AdversarySystem;

public final class PlacedAdversary {
    public final AdversarySystem system;
    public final double lat;
    public final double lon;

    public PlacedAdversary(AdversarySystem system, double lat, double lon) {
        this.system = system;
        this.lat = lat;
        this.lon = lon;
    }
}
