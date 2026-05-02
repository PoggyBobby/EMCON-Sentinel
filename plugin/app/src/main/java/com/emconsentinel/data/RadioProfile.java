package com.emconsentinel.data;

import java.util.Collections;
import java.util.List;

public final class RadioProfile {
    public final String id;
    public final String displayName;
    public final List<RadioBand> bands;

    public RadioProfile(String id, String displayName, List<RadioBand> bands) {
        this.id = id;
        this.displayName = displayName;
        this.bands = Collections.unmodifiableList(bands);
    }
}
