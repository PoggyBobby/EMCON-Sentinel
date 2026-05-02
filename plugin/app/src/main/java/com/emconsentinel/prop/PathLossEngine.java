package com.emconsentinel.prop;

public interface PathLossEngine {
    PropagationResult pathLoss(double txLat, double txLon, double rxLat, double rxLon, double freqMhz);
}
