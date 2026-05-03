#!/usr/bin/env python3
"""EMCON Sentinel CoT listener — team-side decoder.

Subscribes to the ATAK CoT multicast group (239.2.3.1:6969 by default) and
prints a colored team status line whenever an EMCON-extension CoT message
arrives. Drop this on a teammate's laptop on the same LAN as the operators'
tablets and you get a real-time formation view of who's locatable right now.

Usage:
    python3 cot_listener.py                           # default group + port
    python3 cot_listener.py --group 239.2.3.1 --port 6969
    python3 cot_listener.py --json                    # machine-readable output

No dependencies beyond the Python 3 standard library.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import struct
import sys
import time
import xml.etree.ElementTree as ET

# ANSI color codes; degrade to no-color if stdout isn't a TTY
ANSI_GREEN  = "\033[32m"
ANSI_AMBER  = "\033[33m"
ANSI_RED    = "\033[31m"
ANSI_DIM    = "\033[2m"
ANSI_RESET  = "\033[0m"
ANSI_BOLD   = "\033[1m"


def color_for(score: float) -> str:
    if score < 0.3:
        return ANSI_GREEN
    if score < 0.7:
        return ANSI_AMBER
    return ANSI_RED


def parse_cot(xml_bytes: bytes) -> dict | None:
    """Return a flattened dict of fields if this is an EMCON Sentinel event,
    else None."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    if root.tag != "event":
        return None
    detail = root.find("detail")
    if detail is None:
        return None
    emcon = detail.find("emcon")
    if emcon is None:
        # Not an EMCON-extended CoT (could be a regular ATAK position update).
        return None
    contact = detail.find("contact")
    point = root.find("point")
    return {
        "uid": root.attrib.get("uid", ""),
        "callsign": (contact.attrib.get("callsign", "") if contact is not None else ""),
        "time": root.attrib.get("time", ""),
        "lat": float(point.attrib.get("lat", "0")) if point is not None else 0.0,
        "lon": float(point.attrib.get("lon", "0")) if point is not None else 0.0,
        "score": float(emcon.attrib.get("score", "0")),
        "dwell_seconds": int(emcon.attrib.get("dwell_seconds", "0")),
        "top_threat_id": emcon.attrib.get("top_threat_id"),
        "top_threat_range_km": float(emcon.attrib.get("top_threat_range_km", "0") or 0),
        "top_threat_bearing_deg": float(emcon.attrib.get("top_threat_bearing_deg", "0") or 0),
    }


def compass(deg: float) -> str:
    points = ["N","NE","E","SE","S","SW","W","NW"]
    return points[int(((deg + 22.5) % 360) // 45)]


def render_line(d: dict, use_color: bool) -> str:
    color = color_for(d["score"]) if use_color else ""
    reset = ANSI_RESET if use_color else ""
    bold = ANSI_BOLD if use_color else ""
    dim = ANSI_DIM if use_color else ""
    score = d["score"]
    bar_len = 20
    filled = int(round(score * bar_len))
    bar = "█" * filled + "·" * (bar_len - filled)
    threat = ""
    if d.get("top_threat_id"):
        threat = (f"  {dim}top:{reset} {d['top_threat_id']}"
                  f" ({d['top_threat_range_km']:.1f} km {compass(d['top_threat_bearing_deg'])})")
    callsign = d["callsign"] or d["uid"]
    return (f"{color}{bold}{score:>4.2f}{reset} "
            f"{color}{bar}{reset} "
            f"{bold}{callsign:<14}{reset}"
            f"  dwell {d['dwell_seconds']:>3}s"
            f"  ({d['lat']:.4f}, {d['lon']:.4f}){threat}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--group", default="239.2.3.1", help="Multicast group (default: ATAK SA mesh)")
    p.add_argument("--port", type=int, default=6969, help="UDP port (default: 6969)")
    p.add_argument("--json", action="store_true", help="Emit JSON lines instead of pretty status")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI color")
    args = p.parse_args()

    use_color = (not args.no_color) and sys.stdout.isatty() and (not args.json)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass
    sock.bind(("", args.port))
    mreq = struct.pack("4sl", socket.inet_aton(args.group), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print(f"# Listening for EMCON CoT on {args.group}:{args.port} — Ctrl-C to quit",
          file=sys.stderr)

    last_seen: dict[str, float] = {}
    try:
        while True:
            data, addr = sock.recvfrom(65535)
            d = parse_cot(data)
            if d is None:
                continue
            d["_received_from"] = addr[0]
            d["_received_at"] = time.time()
            last_seen[d["uid"]] = d["_received_at"]
            if args.json:
                print(json.dumps(d), flush=True)
            else:
                print(render_line(d, use_color), flush=True)
    except KeyboardInterrupt:
        print("\n# Listener stopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
