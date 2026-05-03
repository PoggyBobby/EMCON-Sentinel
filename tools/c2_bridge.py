#!/usr/bin/env python3
"""EMCON Sentinel C2 telemetry bridge — real-RF observer for MAVLink links.

Connects to a real MAVLink-capable C2 telemetry radio (default target: the
MicoAir LR900-F at 915 MHz LoRa, but works with any SiK / mRo / Holybro /
mavlink2-compatible radio) and observes the link in real time.

For each MAVLink frame seen, it tracks:
  * link state (HEARTBEAT freshness)
  * RX/TX byte rates over a 1-second sliding window
  * local + remote RSSI / SNR (from RADIO_STATUS, when the radio emits it)
  * transmit-now flag (set when a frame originating at the ground station
    is observed within the last second)

Once per second it broadcasts a JSON state frame over UDP multicast (default
group 239.2.3.2 port 14660) which the EMCON Sentinel ATAK plugin's C2Bridge
listens for and uses to drive the risk computation off REAL emissions instead
of the manual START KEYING toggle.

NO simulated data. NO hard-coded RF activity. If you don't have the radio
plugged in, the bridge sits idle and broadcasts disconnected status.

Two ingestion modes (auto-detected, or pick with --source):

  serial  — Read directly from the radio's USB serial port. The MicoAir
            LR900-F enumerates as /dev/tty.usbserial-* on macOS,
            /dev/ttyUSB* on Linux, COMx on Windows. Default baud 57600
            (MicoAir factory; bump to 115200 if you reconfigured).

  udp     — Read from a UDP port. Configure QGroundControl or Mission
            Planner to forward MAVLink to localhost:14550 (Application
            Settings → MAVLink → Comm Links → add UDP forward) so both
            QGC and this bridge can see the stream.

Dependencies:
  pip install pymavlink pyserial         # required
  pip install pymavlink[wheels]          # alternative
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import socket
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    from pymavlink import mavutil
except ImportError:
    print("ERROR: pymavlink not installed.\n"
          "  Install with: pip3 install pymavlink pyserial\n"
          "  (Optional: pip3 install pymavlink[wheels] for prebuilt wheels.)",
          file=sys.stderr)
    sys.exit(2)


# --- Constants ----------------------------------------------------------------
DEFAULT_MULTICAST_GROUP = "239.2.3.2"
DEFAULT_MULTICAST_PORT  = 14660
DEFAULT_BAUD            = 57600
DEFAULT_QGC_UDP_PORT    = 14550
HEARTBEAT_TIMEOUT_S     = 3.0
TX_FRESH_WINDOW_S       = 1.0
PUBLISH_PERIOD_S        = 1.0

# MicoAir LR900-F default RF parameters (per Micoair datasheet rev 2.1).
# 902-928 MHz US ISM band, configurable up to 27 dBm (500 mW).
DEFAULT_RADIO_MODEL     = "MicoAir LR900-F"
DEFAULT_CENTER_FREQ_MHZ = 915.0
DEFAULT_TX_EIRP_DBM     = 27.0


# --- State accumulator --------------------------------------------------------
@dataclass
class LinkStats:
    """Rolling 1-second window of observed MAVLink traffic."""
    radio_model: str = DEFAULT_RADIO_MODEL
    center_freq_mhz: float = DEFAULT_CENTER_FREQ_MHZ
    tx_eirp_dbm: float = DEFAULT_TX_EIRP_DBM
    last_heartbeat_ms: int = 0
    last_tx_ms: int = 0
    rssi_dbm: Optional[float] = None
    rem_rssi_dbm: Optional[float] = None
    # Per-second byte counters reset on each publish
    tx_bytes_window: int = 0
    rx_bytes_window: int = 0
    # MAVLink system IDs we've seen — anything not == ground station is "drone"
    seen_systems: set[int] = field(default_factory=set)
    # ID we believe is the ground station; first system_id we observe coming FROM mavlink_connection.target_system
    gcs_system_id: Optional[int] = None
    # Set when the radio identifies itself in a PARAM_VALUE
    detected_radio_param: Optional[str] = None

    def now_ms(self) -> int:
        return int(time.time() * 1000)

    def is_connected(self) -> bool:
        return (self.now_ms() - self.last_heartbeat_ms) < HEARTBEAT_TIMEOUT_S * 1000

    def is_transmitting_now(self) -> bool:
        return (self.now_ms() - self.last_tx_ms) < TX_FRESH_WINDOW_S * 1000


# --- MAVLink message handling -------------------------------------------------
def update_from_message(stats: LinkStats, msg, frame_size_estimate: int = 0):
    """Mutates stats based on one received MAVLink message."""
    now_ms = stats.now_ms()
    msg_type = msg.get_type()

    # System ID tracking — first non-zero src system seen from a HEARTBEAT
    # tagged with autopilot=8 (INVALID, used by GCS) is the GCS itself.
    src_sys = getattr(msg, "_header", None)
    if src_sys is not None:
        sid = msg.get_srcSystem()
        stats.seen_systems.add(sid)

    if msg_type == "HEARTBEAT":
        stats.last_heartbeat_ms = now_ms
        # MAV_AUTOPILOT_INVALID (8) means the heartbeat is from a GCS, not a vehicle.
        # We use that to identify "us" so we can flag GCS->vehicle frames as TX.
        if msg.autopilot == 8 and stats.gcs_system_id is None:
            stats.gcs_system_id = msg.get_srcSystem()

    if msg_type == "RADIO_STATUS":
        # SiK/mavlink-radio frames carry per-link RSSI in 0..255, where dBm = (rssi/1.9) - 127
        rssi_raw = getattr(msg, "rssi", 0)
        rem_raw  = getattr(msg, "remrssi", 0)
        if rssi_raw:
            stats.rssi_dbm = (rssi_raw / 1.9) - 127.0
        if rem_raw:
            stats.rem_rssi_dbm = (rem_raw / 1.9) - 127.0

    if msg_type == "PARAM_VALUE":
        # If the radio firmware reports a NAME parameter we can detect the model.
        pid = getattr(msg, "param_id", "")
        if "RADIO" in pid.upper() or "MODEL" in pid.upper():
            stats.detected_radio_param = pid

    # TX vs RX classification:
    # - if we have identified the GCS system_id, frames ORIGINATING from GCS = TX
    # - if not yet identified, fall back to: any COMMAND_*, MISSION_*, RC_CHANNELS_OVERRIDE,
    #   MANUAL_CONTROL, SET_*, REQUEST_* — these are always GCS->vehicle
    is_tx = False
    if stats.gcs_system_id is not None:
        if msg.get_srcSystem() == stats.gcs_system_id:
            is_tx = True
    if not is_tx and msg_type.startswith(("COMMAND_", "MISSION_", "MANUAL_CONTROL",
                                          "SET_", "REQUEST_", "RC_CHANNELS_OVERRIDE",
                                          "PARAM_REQUEST_", "PARAM_SET")):
        is_tx = True

    bytes_estimate = frame_size_estimate or _approx_frame_size(msg)
    if is_tx:
        stats.tx_bytes_window += bytes_estimate
        stats.last_tx_ms = now_ms
    else:
        stats.rx_bytes_window += bytes_estimate


def _approx_frame_size(msg) -> int:
    """Estimate the on-wire size of a MAVLink frame. mavlink2 baseline header is 12 bytes
    plus payload plus 2-byte checksum + optional signature."""
    try:
        return len(msg.get_msgbuf())
    except Exception:
        # Fallback: rough average for typical telemetry frame
        return 24


# --- Multicast publisher ------------------------------------------------------
class StatePublisher:
    """Sends each frame over multicast (cross-host production) AND localhost
    unicast (same-host testing). macOS multicast loopback is unreliable; the
    second unicast send guarantees an Android emulator or local test listener
    on the same machine sees the frame."""

    def __init__(self, group: str, port: int, ttl: int = 2,
                 unicast_targets: Optional[list[tuple[str, int]]] = None):
        self.group = group
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        self.unicast_targets = unicast_targets or [("127.0.0.1", port)]

    def publish(self, stats: LinkStats):
        msg = {
            "v": 1,
            "ts": time.time(),
            "connected": stats.is_connected(),
            "radio_model": stats.detected_radio_param or stats.radio_model,
            "center_freq_mhz": stats.center_freq_mhz,
            "tx_eirp_dbm": stats.tx_eirp_dbm,
            "rssi_dbm": stats.rssi_dbm,
            "rem_rssi_dbm": stats.rem_rssi_dbm,
            "tx_bytes_per_sec": stats.tx_bytes_window,
            "rx_bytes_per_sec": stats.rx_bytes_window,
            "is_transmitting_now": stats.is_transmitting_now(),
            "last_tx_ms": stats.last_tx_ms,
        }
        payload = json.dumps(msg).encode("utf-8")
        # 1. Multicast (cross-host)
        try:
            self.sock.sendto(payload, (self.group, self.port))
        except OSError as e:
            print(f"[publish] multicast send failed: {e}", file=sys.stderr)
        # 2. Unicast loopback + any additional unicast targets
        for host, port in self.unicast_targets:
            try:
                self.sock.sendto(payload, (host, port))
            except OSError as e:
                print(f"[publish] unicast {host}:{port} failed: {e}", file=sys.stderr)
        return msg


# --- Source autodetection -----------------------------------------------------
def autodetect_source() -> Optional[str]:
    """Find a likely MicoAir / SiK USB serial port."""
    sys_name = platform.system()
    if sys_name == "Darwin":
        candidates = sorted(glob.glob("/dev/tty.usbserial-*") + glob.glob("/dev/tty.SLAB_USBtoUART*")
                            + glob.glob("/dev/tty.usbmodem*"))
    elif sys_name == "Linux":
        candidates = sorted(glob.glob("/dev/serial/by-id/*") + glob.glob("/dev/ttyUSB*")
                            + glob.glob("/dev/ttyACM*"))
    elif sys_name == "Windows":
        # Windows enumeration through pyserial would be better; keep it simple here.
        return None
    else:
        return None
    return candidates[0] if candidates else None


# --- Main loop ----------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", help="MAVLink source. Examples:\n"
                   "  /dev/tty.usbserial-A906FUKK    (USB serial, default 57600 baud)\n"
                   "  serial:/dev/ttyUSB0:115200     (explicit baud)\n"
                   "  udp:0.0.0.0:14550              (listen for QGC forward)\n"
                   "  udpin:0.0.0.0:14550            (alias)\n"
                   "  tcp:127.0.0.1:5760             (SITL or mavproxy)\n"
                   "If omitted, autodetects the first /dev/tty.usbserial-* (macOS) or "
                   "/dev/ttyUSB* (Linux). Falls back to udpin:0.0.0.0:14550 if none.")
    p.add_argument("--baud", type=int, default=DEFAULT_BAUD,
                   help=f"Serial baud rate when --source is a tty (default: {DEFAULT_BAUD})")
    p.add_argument("--multicast-group", default=DEFAULT_MULTICAST_GROUP,
                   help=f"Multicast group for state broadcasts (default: {DEFAULT_MULTICAST_GROUP})")
    p.add_argument("--multicast-port", type=int, default=DEFAULT_MULTICAST_PORT,
                   help=f"Multicast UDP port (default: {DEFAULT_MULTICAST_PORT})")
    p.add_argument("--unicast-target", action="append", default=[],
                   help="Additional unicast target as host:port. Loopback "
                        "(127.0.0.1:multicast-port) is always added implicitly.")
    p.add_argument("--radio-model", default=DEFAULT_RADIO_MODEL,
                   help="Radio model string included in published frames")
    p.add_argument("--center-freq-mhz", type=float, default=DEFAULT_CENTER_FREQ_MHZ,
                   help=f"RF center frequency in MHz (default: {DEFAULT_CENTER_FREQ_MHZ})")
    p.add_argument("--tx-eirp-dbm", type=float, default=DEFAULT_TX_EIRP_DBM,
                   help=f"Configured TX EIRP in dBm (default: {DEFAULT_TX_EIRP_DBM})")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Print every published frame to stderr")
    args = p.parse_args()

    source = args.source
    if not source:
        autodetected = autodetect_source()
        if autodetected:
            source = autodetected
            print(f"# Auto-detected serial source: {source}", file=sys.stderr)
        else:
            source = f"udpin:0.0.0.0:{DEFAULT_QGC_UDP_PORT}"
            print(f"# No serial radio found — listening on {source} for QGC forward",
                  file=sys.stderr)

    # Normalize for pymavlink
    if source.startswith("/dev/") or (len(source) > 3 and source[1] == ":" and platform.system() == "Windows"):
        connect_str = source
        baud = args.baud
    elif source.startswith("serial:"):
        parts = source.split(":")
        connect_str = parts[1]
        baud = int(parts[2]) if len(parts) > 2 else args.baud
    else:
        connect_str = source
        baud = args.baud

    print(f"# Connecting to MAVLink source: {connect_str} (baud {baud})", file=sys.stderr)
    print(f"# Publishing C2 state to multicast {args.multicast_group}:{args.multicast_port}",
          file=sys.stderr)

    try:
        conn = mavutil.mavlink_connection(connect_str, baud=baud, autoreconnect=True)
    except Exception as e:
        print(f"# Could not open MAVLink source ({e}). Bridge will broadcast disconnected status.",
              file=sys.stderr)
        conn = None

    stats = LinkStats(radio_model=args.radio_model,
                      center_freq_mhz=args.center_freq_mhz,
                      tx_eirp_dbm=args.tx_eirp_dbm)
    extra_unicast = []
    for t in args.unicast_target:
        host, port = t.rsplit(":", 1)
        extra_unicast.append((host.strip("[]"), int(port)))
    unicast_targets = [("127.0.0.1", args.multicast_port)] + extra_unicast
    pub = StatePublisher(args.multicast_group, args.multicast_port,
                         unicast_targets=unicast_targets)
    next_publish = time.time() + PUBLISH_PERIOD_S

    try:
        while True:
            if conn is not None:
                # Drain available frames quickly so we have fresh stats by publish time
                deadline = time.time() + 0.2
                while time.time() < deadline:
                    msg = conn.recv_match(blocking=False)
                    if msg is None:
                        break
                    if msg.get_type() == "BAD_DATA":
                        continue
                    update_from_message(stats, msg)

            if time.time() >= next_publish:
                published = pub.publish(stats)
                if args.verbose:
                    print(f"[pub] {json.dumps(published)}", file=sys.stderr)
                # Reset per-second window counters
                stats.tx_bytes_window = 0
                stats.rx_bytes_window = 0
                next_publish += PUBLISH_PERIOD_S

            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n# c2_bridge stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
