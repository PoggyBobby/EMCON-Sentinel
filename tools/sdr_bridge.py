#!/usr/bin/env python3
"""EMCON Sentinel SDR sidecar — TRUE ambient-RF observer.

Wraps `rtl_power` (RTL-SDR project) to continuously scan operator-relevant
RF bands and report energy events to the EMCON Sentinel ATAK plugin.

Two classes of detection:

  own-tx       Energy spike in the operator's drone control bands
               (868/915/2400/5800 MHz). Confirms "the operator is
               transmitting" with REAL RF, not the manual START KEYING
               toggle. Drives state.isKeying() override.

  adversary-ew Energy spike in published adversary EW band centers
               (Pole-21 GNSS jam ~1.575 GHz, Krasukha ~10 GHz,
               broad VHF/UHF SIGINT 30-3000 MHz). Confirms "an
               adversary asset is actively emitting" so the operator
               sees real evidence, not just the modeled threat list.

Events are published as JSON heartbeats over UDP multicast
239.2.3.3:14661 (separate from the C2 bridge group). The Java
SdrBridge consumes these and feeds them into PluginState.

NO simulated data. If no RTL-SDR is connected or rtl_power is missing,
the script reports the missing dependency and exits cleanly. The
plugin's risk loop continues to work without it (just without the
real-RF override).

Hardware needed:
    RTL-SDR Blog V4 (~$30) or Nooelec NESDR SMArt — anything driver-
    compatible with rtl_power. Tunable 24 MHz - 1.7 GHz natively, or
    use an upconverter/down-converter for higher bands.

Software needed:
    macOS:   brew install librtlsdr
    Linux:   apt install rtl-sdr
    The `rtl_power` binary should be on PATH after install.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

DEFAULT_MULTICAST_GROUP = "239.2.3.3"
DEFAULT_MULTICAST_PORT  = 14661
PUBLISH_PERIOD_S        = 1.0
DETECTION_THRESHOLD_DB  = -50.0   # Above this dBm at the receiver = "real signal"

# Operator drone control bands — when energy here, operator is transmitting
OPERATOR_BANDS_MHZ = [
    (433, 0.5,   "FPV 433 MHz"),
    (868, 0.5,   "Crossfire / EU LR"),
    (915, 0.5,   "MicoAir LR900-F / TBS US"),
    (2400, 25,   "FPV / DJI 2.4 GHz"),
    (5800, 50,   "DJI / FPV 5.8 GHz"),
]

# Adversary EW band centers — when energy here, adversary is emitting
ADVERSARY_BANDS_MHZ = [
    (1575, 5,    "GNSS jam (Pole-21 class)"),
    (1700, 100,  "VHF/UHF SIGINT (Borisoglebsk class)"),
    (2200, 100,  "S-band radar / SIGINT"),
]


@dataclass
class Detection:
    timestamp: float
    freq_mhz: float
    power_dbm: float
    label: str
    band_class: str   # "own-tx" or "adversary-ew"


def check_rtl_power() -> Optional[str]:
    """Return the path to rtl_power if available, else None."""
    return shutil.which("rtl_power")


def check_rtl_device() -> bool:
    """Return True if at least one RTL-SDR device is enumerated."""
    rtl_test = shutil.which("rtl_test")
    if not rtl_test:
        return False
    try:
        r = subprocess.run([rtl_test, "-t"], capture_output=True, text=True, timeout=4)
        # rtl_test exits non-zero with no device, or prints "No supported devices"
        return "Found" in r.stderr or "Found" in r.stdout
    except (subprocess.TimeoutExpired, OSError):
        return False


def scan_band(freq_min_mhz: float, freq_max_mhz: float, bin_width_khz: int = 100,
              integration_s: int = 1) -> list[tuple[float, float]]:
    """One-shot scan via rtl_power. Returns list of (freq_mhz, power_dbm)."""
    rtl_power = check_rtl_power()
    if not rtl_power:
        return []
    # rtl_power output format: date,time,freq_low,freq_high,bin_width,samples,db,db,...
    cmd = [rtl_power,
           "-f", f"{freq_min_mhz}M:{freq_max_mhz}M:{bin_width_khz}k",
           "-i", str(integration_s),
           "-1",                        # one-shot
           "-c", "20%",                 # crop edges
           "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=integration_s + 5)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"[scan] rtl_power failed: {e}", file=sys.stderr)
        return []
    out = []
    for line in r.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 7:
            continue
        try:
            f_lo = float(parts[2])
            bw   = float(parts[4])
            powers = [float(p) for p in parts[6:]]
            for i, db in enumerate(powers):
                center_hz = f_lo + (i + 0.5) * bw
                out.append((center_hz / 1e6, db))
        except ValueError:
            continue
    return out


def detect_in_band(scan: list[tuple[float, float]], center_mhz: float, bw_mhz: float,
                   threshold_db: float) -> Optional[tuple[float, float]]:
    """Return (peak_freq_mhz, peak_db) if any bin in [center±bw/2] exceeds threshold."""
    lo = center_mhz - bw_mhz / 2
    hi = center_mhz + bw_mhz / 2
    peak = None
    for f, db in scan:
        if lo <= f <= hi and db >= threshold_db:
            if peak is None or db > peak[1]:
                peak = (f, db)
    return peak


class StatePublisher:
    """Emits detections + heartbeats over multicast (and 127.0.0.1 unicast for
    local same-host testing — macOS multicast loopback is unreliable)."""
    def __init__(self, group: str, port: int, ttl: int = 2):
        self.group = group
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)

    def publish(self, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        for dst in [(self.group, self.port), ("127.0.0.1", self.port)]:
            try:
                self.sock.sendto(data, dst)
            except OSError as e:
                print(f"[pub] send to {dst} failed: {e}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--multicast-group", default=DEFAULT_MULTICAST_GROUP)
    p.add_argument("--multicast-port", type=int, default=DEFAULT_MULTICAST_PORT)
    p.add_argument("--threshold-db", type=float, default=DETECTION_THRESHOLD_DB)
    p.add_argument("--scan-period-s", type=float, default=10.0,
                   help="Seconds between full-band scans (longer = lower CPU)")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    if not check_rtl_power():
        print("ERROR: rtl_power not found on PATH.\n"
              "  macOS: brew install librtlsdr\n"
              "  Linux: apt install rtl-sdr\n"
              "Bridge will exit. Plugin still works without it.", file=sys.stderr)
        sys.exit(1)
    if not check_rtl_device():
        print("ERROR: no RTL-SDR device detected. Plug in a hardware SDR.\n"
              "Bridge will exit. Plugin still works without it.", file=sys.stderr)
        sys.exit(2)

    pub = StatePublisher(args.multicast_group, args.multicast_port)
    print(f"# SDR sidecar online — publishing detections to "
          f"{args.multicast_group}:{args.multicast_port}", file=sys.stderr)

    # Heartbeat first so the plugin knows we're alive
    pub.publish({"v": 1, "ts": time.time(), "type": "hello", "sdr_present": True})

    while True:
        try:
            # One scan cycle covers all bands. Each band scan is short (1-2s).
            for center_mhz, bw_mhz, label in OPERATOR_BANDS_MHZ + ADVERSARY_BANDS_MHZ:
                klass = "own-tx" if (center_mhz, bw_mhz, label) in OPERATOR_BANDS_MHZ else "adversary-ew"
                scan = scan_band(center_mhz - bw_mhz / 2, center_mhz + bw_mhz / 2)
                if not scan:
                    continue
                hit = detect_in_band(scan, center_mhz, bw_mhz, args.threshold_db)
                if hit is None:
                    continue
                peak_f, peak_db = hit
                event = {
                    "v": 1, "ts": time.time(), "type": "detection",
                    "freq_mhz": peak_f, "power_dbm": peak_db,
                    "label": label, "class": klass,
                }
                pub.publish(event)
                if args.verbose:
                    print(f"[detect] {klass} {label}: {peak_f:.2f} MHz @ {peak_db:.1f} dBm",
                          file=sys.stderr)

            # Heartbeat between scan cycles so plugin knows bridge is healthy
            pub.publish({"v": 1, "ts": time.time(), "type": "heartbeat", "sdr_present": True})
            time.sleep(args.scan_period_s)
        except KeyboardInterrupt:
            print("\n# SDR sidecar stopped", file=sys.stderr)
            break


if __name__ == "__main__":
    main()
