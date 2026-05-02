package com.emconsentinel.prop;

import com.emconsentinel.data.AdversarySystem;
import com.emconsentinel.data.RadioBand;
import com.emconsentinel.data.RadioProfile;

import java.util.List;

public final class LinkBudget {

    private LinkBudget() {}

    /** Logistic on margin in dB. k=0.2 gives 50% at 0 dB, ~88% at +10 dB, ~12% at -10 dB. */
    public static double sigmoid(double marginDb) {
        return 1.0 / (1.0 + Math.exp(-0.2 * marginDb));
    }

    /** Per-band detection probability. 0 if adversary's tuning range doesn't cover the band. */
    public static double bandDetectionProb(AdversarySystem adv, RadioBand band, double pathLossDb) {
        if (!adv.coversFrequency(band.freqMhz)) return 0.0;
        double receivedDbm = band.eirpDbm - pathLossDb + adv.antennaGainDbi;
        double margin = receivedDbm - adv.sensitivityDbm;
        return sigmoid(margin) * band.dutyCycle;
    }

    /**
     * Per-asset detection across all bands the operator radio is transmitting on. Returns the max
     * across overlapping bands — the strongest band is what gives the adversary the best fix.
     * The propagation engine is invoked once per band because path loss is frequency-dependent.
     */
    public static double assetDetectionProb(AdversarySystem adv, RadioProfile profile,
                                             double opLat, double opLon,
                                             double advLat, double advLon,
                                             PathLossEngine prop) {
        double max = 0.0;
        for (RadioBand band : profile.bands) {
            if (!adv.coversFrequency(band.freqMhz)) continue;
            PropagationResult r = prop.pathLoss(opLat, opLon, advLat, advLon, band.freqMhz);
            double p = bandDetectionProb(adv, band, r.pathLossDb);
            if (p > max) max = p;
        }
        return max;
    }

    /** Convenience: same signature as above but returns the best (mode, prob) pair. */
    public static Result assetDetection(AdversarySystem adv, RadioProfile profile,
                                         double opLat, double opLon,
                                         double advLat, double advLon,
                                         PathLossEngine prop) {
        double max = 0.0;
        PropagationResult.Mode mode = PropagationResult.Mode.FREE_SPACE;
        for (RadioBand band : profile.bands) {
            if (!adv.coversFrequency(band.freqMhz)) continue;
            PropagationResult r = prop.pathLoss(opLat, opLon, advLat, advLon, band.freqMhz);
            double p = bandDetectionProb(adv, band, r.pathLossDb);
            if (p > max) {
                max = p;
                mode = r.mode;
            }
        }
        return new Result(max, mode);
    }

    public static final class Result {
        public final double prob;
        public final PropagationResult.Mode mode;
        public Result(double prob, PropagationResult.Mode mode) {
            this.prob = prob;
            this.mode = mode;
        }
    }

    /** Helper for callers that already iterate band-by-band themselves. */
    public static double assetDetectionProb(AdversarySystem adv, List<RadioBand> bands,
                                             double opLat, double opLon,
                                             double advLat, double advLon,
                                             PathLossEngine prop) {
        double max = 0.0;
        for (RadioBand band : bands) {
            if (!adv.coversFrequency(band.freqMhz)) continue;
            PropagationResult r = prop.pathLoss(opLat, opLon, advLat, advLon, band.freqMhz);
            double p = bandDetectionProb(adv, band, r.pathLossDb);
            if (p > max) max = p;
        }
        return max;
    }
}
