package com.emconsentinel.prop;

public final class PropagationResult {
    public enum Mode { CLOUDRF, FREE_SPACE }

    public final double pathLossDb;
    public final Mode mode;

    public PropagationResult(double pathLossDb, Mode mode) {
        this.pathLossDb = pathLossDb;
        this.mode = mode;
    }
}
