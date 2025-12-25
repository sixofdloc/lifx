# LIFX LAN Controller

A Python library and command-line tools for controlling LIFX smart lights over the local network using the LIFX LAN Protocol.

## Features

- **Device Discovery** - Scan your network to find all LIFX devices
- **Power Control** - Turn lights on/off with optional fade transitions
- **Color Control** - Set colors using names, hex, RGB, HSB, or HSBK values
- **Waveform Effects** - Run animated effects (pulse, breathe, etc.)
- **Device Info** - Query detailed device information (firmware, WiFi, uptime, etc.)
- **MultiZone Support** - Query zone colors on LIFX Z strips, Beam, and String lights
- **No Cloud Required** - Direct LAN communication, works offline

## Requirements

- Python 3.10+
- LIFX devices on the same local network
- UDP port 56700 accessible (not blocked by firewall)

No external dependencies required - uses only Python standard library.

## Files

| File | Description |
|------|-------------|
| `lifx_protocol.py` | Shared library with protocol implementation |
| `lifx_scanner.py` | Simple device discovery tool |
| `lifx_control.py` | Full-featured device controller |

## Quick Start

```bash
# Discover devices on your network
python3 lifx_scanner.py

# Scan with the controller (shows more details)
python3 lifx_control.py scan

# Turn all lights on
python3 lifx_control.py on all

# Set a light to red
python3 lifx_control.py color "Living Room" red

# Run a breathing effect
python3 lifx_control.py waveform all blue --waveform sine --cycles 10
```

---

## Command-Line Tools

### lifx_scanner.py

Simple device discovery tool. Broadcasts GetService packets and collects responses.

```bash
# Basic scan (default subnet 192.168.64.0/24)
python3 lifx_scanner.py

# Scan a different subnet
python3 lifx_scanner.py -s 192.168.1.0/24

# Scan with longer timeout
python3 lifx_scanner.py -t 5 -r 3

# JSON output
python3 lifx_scanner.py --json

# Verbose mode (shows protocol details)
python3 lifx_scanner.py -v
```

**Options:**
| Option | Description | Default |
|--------|-------------|---------|
| `-s, --subnet` | Network subnet in CIDR notation | 192.168.64.0/24 |
| `-t, --timeout` | Response timeout (seconds) | 2.0 |
| `-r, --retries` | Number of broadcast attempts | 3 |
| `-p, --port` | LIFX UDP port | 56700 |
| `-v, --verbose` | Show detailed output | False |
| `--json` | Output in JSON format | False |

---

### lifx_control.py

Full-featured controller with multiple commands.

#### Global Options

```bash
python3 lifx_control.py [options] <command> [command-options]
```

| Option | Description | Default |
|--------|-------------|---------|
| `-s, --subnet` | Network subnet | 192.168.64.0/24 |
| `-t, --timeout` | Response timeout (seconds) | 1.0 |
| `-r, --retries` | Discovery retries | 2 |
| `-v, --verbose` | Verbose output | False |
| `--json` | JSON output (for scan/info) | False |

#### Commands

##### `scan` - Discover Devices

```bash
python3 lifx_control.py scan
python3 lifx_control.py scan --json
```

##### `on` / `off` - Power Control

```bash
# Turn on a specific device (by label, serial, or IP)
python3 lifx_control.py on "Living Room"
python3 lifx_control.py on d0:73:d5:87:ad:40
python3 lifx_control.py on 192.168.64.175

# Turn off all devices
python3 lifx_control.py off all

# Fade on over 2 seconds
python3 lifx_control.py on all -d 2
```

| Option | Description | Default |
|--------|-------------|---------|
| `-d, --duration` | Transition time (seconds) | 0 |

##### `color` - Set Color

```bash
# Named colors
python3 lifx_control.py color all red
python3 lifx_control.py color all warm_white

# Hex colors
python3 lifx_control.py color "Office" "#FF6600"
python3 lifx_control.py color "Office" FF6600

# RGB
python3 lifx_control.py color all "rgb(255, 100, 0)"

# HSB (hue degrees, saturation %, brightness %)
python3 lifx_control.py color all "hsb(120, 100, 50)"

# HSBK (includes kelvin)
python3 lifx_control.py color all "hsbk(0, 0, 100, 2700)"

# With transition and kelvin override
python3 lifx_control.py color all white -k 4000 -d 1

# Override brightness
python3 lifx_control.py color all blue -b 50
```

**Named Colors:** `red`, `orange`, `yellow`, `lime`, `green`, `teal`, `cyan`, `sky`, `blue`, `purple`, `magenta`, `pink`, `white`, `warm_white`, `cool_white`

| Option | Description | Default |
|--------|-------------|---------|
| `-d, --duration` | Transition time (seconds) | 0 |
| `-k, --kelvin` | Color temperature (1500-9000) | 3500 |
| `-b, --brightness` | Brightness override (0-100) | - |

##### `waveform` - Animated Effects

```bash
# Sine wave breathing effect
python3 lifx_control.py waveform all red --waveform sine

# Fast pulse
python3 lifx_control.py waveform "Bedroom" blue -w pulse -p 0.5 -c 20

# Slow triangle wave, stay at target color
python3 lifx_control.py waveform all green -w triangle -p 3 --no-transient
```

**Waveform Types:**
- `saw` - Sawtooth wave
- `sine` - Smooth sine wave (default)
- `half_sine` - Half sine wave
- `triangle` - Triangle wave
- `pulse` - Square pulse (use `--duty-cycle` to control)

| Option | Description | Default |
|--------|-------------|---------|
| `-w, --waveform` | Waveform type | sine |
| `-p, --period` | Cycle period (seconds) | 1.0 |
| `-c, --cycles` | Number of cycles | 5.0 |
| `--transient` | Return to original color | True |
| `--no-transient` | Stay at target color | - |
| `--duty-cycle` | For PULSE waveform (0-1) | 0.5 |
| `-k, --kelvin` | Color temperature | 3500 |
| `-b, --brightness` | Brightness override (0-100) | - |

##### `info` - Device Information

```bash
# Get info for one device
python3 lifx_control.py info "Office"

# Get info for all devices
python3 lifx_control.py info all

# JSON output
python3 lifx_control.py info all --json
```

Shows: product name, firmware version, WiFi signal strength, location, group, uptime, and capability-specific info (infrared level, zone colors, etc.)

---

## Library API (lifx_protocol.py)

The library can be imported for use in your own Python scripts.

### Constants

```python
from lifx_protocol import (
    LIFX_PORT,              # 56700
    PROTOCOL_NUMBER,        # 1024
    
    # Message Types
    GETSERVICE_TYPE,        # 2
    STATESERVICE_TYPE,      # 3
    SETPOWER_TYPE,          # 21
    SETCOLOR_TYPE,          # 102
    # ... and many more
    
    # Service Types
    SERVICE_UDP,            # 1
)
```

### Data Classes

```python
from lifx_protocol import LIFXDevice, HSBK

# LIFXDevice - represents a discovered device
device = LIFXDevice(
    ip_address="192.168.64.175",
    port=56700,
    serial="d0:73:d5:87:ad:40",
    service=1,
    label="Living Room",
    power=65535,
    hue=0,
    saturation=0,
    brightness=65535,
    kelvin=3500
)

# HSBK - color representation
color = HSBK(hue=0, saturation=65535, brightness=65535, kelvin=3500)

# Create from human-readable values
color = HSBK.from_degrees(hue=120, saturation=1.0, brightness=0.5, kelvin=3500)

# Create from RGB
color = HSBK.from_rgb(255, 0, 0)

# Create from hex
color = HSBK.from_hex("#FF6600")
```

### Waveform Enum

```python
from lifx_protocol import Waveform

Waveform.SAW        # 0
Waveform.SINE       # 1
Waveform.HALF_SINE  # 2
Waveform.TRIANGLE   # 3
Waveform.PULSE      # 4
```

### Product Registry

```python
from lifx_protocol import LIFX_PRODUCTS

# Look up product info by ID
product = LIFX_PRODUCTS.get(29)
# {'name': 'LIFX A19 Night Vision', 'features': {'color': True, 'infrared': True, ...}}
```

### Utility Functions

```python
from lifx_protocol import get_broadcast_address, generate_source_id

broadcast = get_broadcast_address("192.168.1.0/24")  # "192.168.1.255"
source = generate_source_id()  # Random uint32 (2 to 0xFFFFFFFF)
```

### Packet Creation Functions

```python
from lifx_protocol import (
    create_lifx_header,
    create_getservice_packet,
    create_getlabel_packet,
    create_getcolor_packet,
    create_setpower_packet,
    create_setlightpower_packet,
    create_setcolor_packet,
    create_setwaveform_packet,
    create_getversion_packet,
    create_gethostfirmware_packet,
    create_getwifiinfo_packet,
    create_getinfo_packet,
    create_getlocation_packet,
    create_getgroup_packet,
    create_getinfrared_packet,
    create_getcolorzones_packet,
    create_getextendedcolorzones_packet,
    create_getmultizoneeffect_packet,
)

# Example: Create a SetColor packet
source = generate_source_id()
target = device.target_bytes  # 8-byte target address
color = HSBK.from_degrees(240, 1.0, 1.0)  # Blue
packet = create_setcolor_packet(source, target, color, duration=1000)
```

### Packet Parsing Functions

```python
from lifx_protocol import (
    parse_lifx_header,
    parse_state_service,
    parse_state_label,
    parse_light_state,
    parse_state_version,
    parse_state_hostfirmware,
    parse_state_wifiinfo,
    parse_state_info,
    parse_state_location,
    parse_state_group,
    parse_state_infrared,
    parse_state_zone,
    parse_state_multizone,
    parse_state_extended_color_zones,
    parse_state_multizone_effect,
)

# Example: Parse a received packet
header = parse_lifx_header(data)
if header and header['type'] == LIGHTSTATE_TYPE:
    state = parse_light_state(header['payload'])
    print(f"Label: {state['label']}, Power: {state['power']}")
```

### Example: Custom Script

```python
#!/usr/bin/env python3
"""Example: Blink all lights red 3 times."""

import socket
import time
from lifx_protocol import (
    LIFX_PORT,
    STATESERVICE_TYPE,
    SERVICE_UDP,
    HSBK,
    get_broadcast_address,
    generate_source_id,
    create_getservice_packet,
    create_setcolor_packet,
    parse_lifx_header,
    parse_state_service,
)

def discover_devices(subnet="192.168.64.0/24"):
    """Discover LIFX devices on the network."""
    source = generate_source_id()
    broadcast = get_broadcast_address(subnet)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(('', 0))
    sock.settimeout(1.0)
    
    packet = create_getservice_packet(source)
    sock.sendto(packet, (broadcast, LIFX_PORT))
    
    devices = []
    try:
        while True:
            data, addr = sock.recvfrom(1024)
            header = parse_lifx_header(data)
            if header and header['type'] == STATESERVICE_TYPE:
                service_info = parse_state_service(header['payload'])
                if service_info and service_info[0] == SERVICE_UDP:
                    devices.append((addr[0], service_info[1], header['serial']))
    except socket.timeout:
        pass
    
    sock.close()
    return devices

def set_all_color(devices, hsbk, source):
    """Set color on all devices."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for ip, port, serial in devices:
        parts = serial.split(':')
        target = bytes(int(p, 16) for p in parts) + b'\x00\x00'
        packet = create_setcolor_packet(source, target, hsbk, duration=0)
        sock.sendto(packet, (ip, port))
    sock.close()

if __name__ == '__main__':
    devices = discover_devices()
    print(f"Found {len(devices)} devices")
    
    source = generate_source_id()
    red = HSBK.from_degrees(0, 1.0, 1.0)
    off = HSBK.from_degrees(0, 0, 0)
    
    for _ in range(3):
        set_all_color(devices, red, source)
        time.sleep(0.5)
        set_all_color(devices, off, source)
        time.sleep(0.5)
```

---

## Protocol Reference

This implementation follows the [LIFX LAN Protocol](https://lan.developer.lifx.com/docs/packet-contents).

### Supported Message Types

| Category | Messages |
|----------|----------|
| Discovery | GetService (2), StateService (3) |
| Device | GetPower (20), SetPower (21), GetLabel (23), StateLabel (25) |
| Device Info | GetHostFirmware (14), GetWifiInfo (16), GetVersion (32), GetInfo (34), GetLocation (48), GetGroup (51) |
| Light | GetColor (101), SetColor (102), SetWaveform (103), LightState (107), SetLightPower (117) |
| Infrared | GetInfrared (120), StateInfrared (121) |
| MultiZone | GetColorZones (502), GetExtendedColorZones (511), GetMultiZoneEffect (507) |

---

## Troubleshooting

**No devices found:**
- Verify devices are powered on and connected to WiFi
- Check the subnet matches your network (`ip addr` or `ifconfig`)
- Try increasing timeout: `-t 5`
- Check firewall allows UDP port 56700

**Device not responding to commands:**
- Ensure you're using the correct device identifier (label, serial, or IP)
- Try running `scan` first to refresh device list
- Check device is not in "cloud only" mode

**Unknown product ID:**
- Some newer LIFX products may not be in the product registry
- The device will still work, just show "Unknown (ID)" for product name

---

## License

MIT License - feel free to use and modify.

## References

- [LIFX LAN Protocol Documentation](https://lan.developer.lifx.com/docs)
- [LIFX Products JSON](https://github.com/LIFX/products/blob/master/products.json)
