# EMCON Sentinel — sidecar tools

Two Python sidecars. Both work on macOS, Linux, and Windows. Both speak only standard protocols on standard ports — no proprietary glue.

## `c2_bridge.py` — real C2 telemetry observer

The plugin's manual **START KEYING** button is fine for demos. In production it should be driven by **observed RF activity on the actual telemetry radio**, not a button. `c2_bridge.py` is the sidecar that does that.

It connects to the operator's MAVLink-capable telemetry radio (designed against the **MicoAir LR900-F** at 915 MHz LoRa, but works with any SiK / mRo / Holybro radio that speaks MAVLink), parses real frames, and broadcasts a JSON state update every second over UDP. The plugin's `C2Bridge` listens for these updates and uses them to drive the dial — no synthetic data anywhere.

### Hardware: MicoAir LR900-F

- Frequency: 902–928 MHz US ISM (LoRa CSS, frequency-hopping)
- TX power: configurable up to **27 dBm (500 mW)**
- Range: ~30 km LoS claimed
- Interface: USB ↔ UART (CP2102 USB-serial)
- MAVLink-compatible (works with QGroundControl, Mission Planner, MAVProxy)

The LR900-F at 915 MHz triggers detection from **6 of the 9 adversary systems** in our OSINT library (Borisoglebsk-2, Torn-MDM, Zhitel, Shipovnik-Aero, Leer-3, RB-636 Svet-KU all cover the 915 MHz band).

### Install

```bash
pip3 install pymavlink pyserial
```

### Run modes

**1. Direct serial (recommended for production)** — radio plugged into the laptop running this bridge:

```bash
python3 tools/c2_bridge.py --source /dev/tty.usbserial-A906FUKK --baud 57600
```

If you don't pass `--source`, the bridge auto-detects:
- macOS: first `/dev/tty.usbserial-*` or `/dev/tty.SLAB_USBtoUART*`
- Linux: first `/dev/serial/by-id/*` or `/dev/ttyUSB*`
- Falls back to `udpin:0.0.0.0:14550` if none found

**2. UDP (when you want QGroundControl to share the radio)** — configure QGC to forward MAVLink to UDP:
- QGC → Application Settings → MAVLink → Comm Links → add a UDP Server on port 14550
- Then run the bridge as a UDP listener:

```bash
python3 tools/c2_bridge.py --source udpin:0.0.0.0:14550
```

Both QGC and the bridge see the same stream.

**3. SITL (no real hardware, for testing the bridge code itself)**:

```bash
# Start ArduPilot SITL emitting MAVLink to UDP 14550
sim_vehicle.py -v ArduCopter --map --console
# Bridge listens to it
python3 tools/c2_bridge.py --source udpin:0.0.0.0:14550 --verbose
```

This is the ONLY synthetic path; it's for testing the bridge itself, not for fake demo data.

### What the bridge publishes

Every 1 s, JSON like:

```json
{
  "v": 1,
  "ts": 1700000000.123,
  "connected": true,
  "radio_model": "MicoAir LR900-F",
  "center_freq_mhz": 915.0,
  "tx_eirp_dbm": 27.0,
  "rssi_dbm": -82.0,
  "rem_rssi_dbm": -78.0,
  "tx_bytes_per_sec": 124,
  "rx_bytes_per_sec": 612,
  "is_transmitting_now": true,
  "last_tx_ms": 1700000000123
}
```

Sent over UDP **multicast group 239.2.3.2 port 14660** (cross-host, works on any LAN with multicast routing) AND **unicast 127.0.0.1:14660** (same-host fallback for testing).

### Verify it's running

A one-liner Python listener:

```bash
python3 -c "
import socket, json
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('127.0.0.1', 14660))
while True:
    data, _ = s.recvfrom(8192)
    print(json.dumps(json.loads(data), indent=2))
"
```

You should see one frame per second.

### How the plugin consumes it

`com.emconsentinel.c2.C2Bridge` (Java thread inside the plugin) joins the same multicast group, parses the JSON, updates `PluginState.c2Status`. When the operator ticks the **"Use C2 link for keying detection"** checkbox in the setup pane, the plugin treats `is_transmitting_now=true` as the keying signal and ignores the manual button. RF emissions, dwell time, and risk are all driven by **observed reality**.

If the bridge stops broadcasting for >4 s, the plugin marks the link stale and falls back to the manual toggle. No silent failures.

---

## `cot_listener.py` — team-side CoT decoder

Each operator's plugin emits a custom CoT XML message every 5 s carrying their composite risk + dwell + top threat. This sidecar listens on the standard ATAK SA mesh (multicast 239.2.3.1:6969), decodes EMCON-extension events, and prints a colored team status line per operator.

```bash
python3 tools/cot_listener.py
# 0.74 ███████████████····· EMCON-1   dwell 124s  (48.2814, 37.1762)  top: r-330zh-zhitel (4.2 km W)
# 0.31 ██████·············· EMCON-2   dwell  47s  (48.3001, 37.1900)  top: leer-3 (8.1 km NE)
```

Drop on any laptop on the same LAN. Format `--json` for machine-readable output (one JSON object per line, suitable for piping into `jq` or a dashboard).

---

## Putting it all together (production wiring)

```
                                         [drone w/ Pixhawk + LR900-F]
                                                 ↕ 915 MHz LoRa
[operator's tablet w/ ATAK + EMCON Sentinel]   [operator's laptop]
        ↑                                              ↑
        │  C2 multicast 239.2.3.2:14660                │  USB-serial
        │  ←──────────────────────────────────         │
        │                                       [c2_bridge.py]
        │                                              ↑
        │  CoT multicast 239.2.3.1:6969                │  parses MAVLink
        │  ──────────────────────────────────→         │  HEARTBEAT,
        ↓                                              │  RADIO_STATUS,
[team-lead's laptop w/ cot_listener.py]                │  RC_CHANNELS, ...
```

All on the same LAN. No cloud. No fake data. The operator's actual emissions drive the risk; the operator's actual risk drives the team-lead's view.
