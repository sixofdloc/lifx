# LIFX LAN Controller

A comprehensive Python library and tools for controlling LIFX smart lights over the local network using the LIFX LAN Protocol.

## Features

- **Device Discovery** - Scan your network to find all LIFX devices
- **Power Control** - Turn lights on/off with optional fade transitions
- **Color Control** - Set colors using names, hex, RGB, HSB, or HSBK values
- **Waveform Effects** - Hardware-controlled effects (pulse, breathe, strobe)
- **Software Effects** - Rainbow, disco, party, candle, sunrise/sunset, and more
- **Matrix Support** - Individual pixel control for LIFX Ceiling, Tile, and Candle devices
- **MultiZone Support** - Zone colors on LIFX Z strips, Beam, Neon, and String lights
- **Web Interface** - Control lights from any browser on your LAN
- **Terminal UI** - Interactive Textual-based interface
- **CLI Tool** - Full command-line control
- **No Cloud Required** - Direct LAN communication, works offline

## Requirements

- Python 3.10+
- LIFX devices on the same local network
- UDP port 56700 accessible (not blocked by firewall)

Core tools use only Python standard library. Optional dependencies:
- `textual` - For the TUI interface

## Files

| File | Description |
|------|-------------|
| `lifx_protocol.py` | Shared library with protocol implementation |
| `lifx_effects.py` | Effects library (rainbow, candle, matrix effects, etc.) |
| `lifx_scanner.py` | Simple device discovery tool |
| `lifx_control.py` | Full-featured device controller |
| `lifx_cli.py` | Modern CLI with effect support |
| `lifx_tui.py` | Interactive terminal user interface |
| `lifx_web.py` | HTTP server for web-based control |
| `web/index.html` | Web UI frontend |
| `lifx-web.service` | Systemd service file |

---

## Quick Start

```bash
# Discover devices on your network
python3 lifx_scanner.py

# Launch the interactive TUI
pip install textual  # One-time setup
python3 lifx_tui.py

# Start the web interface
python3 lifx_web.py
# Then open http://localhost:6969 in your browser

# CLI commands
python3 lifx_cli.py list
python3 lifx_cli.py Office on
python3 lifx_cli.py "Living Room" color red
python3 lifx_cli.py all effect rainbow --loop
```

---

## Interfaces

### Web Interface (`lifx_web.py`)

A lightweight HTTP server for controlling LIFX lights from any browser on your LAN.

```bash
# Start the server (default port 6969)
python3 lifx_web.py

# Custom port and subnet
python3 lifx_web.py --port 8080 --subnet 192.168.1.0/24
```

**Features:**
- Device list with power toggle
- HSB color sliders with live preview
- Color temperature (Kelvin) control
- Color and white presets
- All effects including matrix effects for Ceiling/Tile devices
- Works on mobile browsers

**API Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Web UI |
| GET | `/api/devices` | List all devices |
| POST | `/api/refresh` | Re-scan for devices |
| POST | `/api/device/<serial>/power` | Set power `{"on": true}` |
| POST | `/api/device/<serial>/color` | Set color `{"h":0-360, "s":0-100, "b":0-100, "k":1500-9000}` |
| POST | `/api/device/<serial>/preset` | Apply preset `{"preset": "red"}` |
| POST | `/api/device/<serial>/effect` | Run effect `{"effect": "rainbow", "loop": true}` |
| POST | `/api/device/<serial>/stop` | Stop running effect |
| POST | `/api/all/power` | Set all devices power |
| POST | `/api/all/color` | Set all devices color |

**Running as a System Service:**

```bash
# Copy the service file
sudo cp lifx-web.service /etc/systemd/system/

# Edit to set correct path and user
sudo nano /etc/systemd/system/lifx-web.service

# Enable and start
sudo systemctl enable lifx-web
sudo systemctl start lifx-web
```

---

### Terminal UI (`lifx_tui.py`)

Interactive terminal interface with device sidebar and control panel.

```bash
pip install textual  # One-time setup
python3 lifx_tui.py
```

**Features:**
- Device list sidebar with power indicators
- Tabbed interface: Color, Presets, Effects
- Real-time HSB and Kelvin sliders
- Color preview
- All waveform, color, ambient, and matrix effects

**Keyboard Shortcuts:**
| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Refresh devices |
| `↑/↓` | Navigate device list |
| `Tab` | Switch between panels |

---

### CLI (`lifx_cli.py`)

Modern command-line interface with full effect support.

```bash
# List devices
python3 lifx_cli.py list

# Show available effects
python3 lifx_cli.py effects

# Power control
python3 lifx_cli.py Office on
python3 lifx_cli.py "Living Room" off
python3 lifx_cli.py all on

# Set color by name
python3 lifx_cli.py Office color red
python3 lifx_cli.py Office color "#ff5500"

# Set HSB values
python3 lifx_cli.py Office hsb 180 100 50  # Hue Sat Bright

# Set white temperature
python3 lifx_cli.py Office kelvin 2700 80  # Kelvin Brightness%

# Run effects
python3 lifx_cli.py Office effect rainbow
python3 lifx_cli.py Office effect candle --loop
python3 lifx_cli.py Office effect matrix_flame --loop

# Stop effects
python3 lifx_cli.py Office stop
```

**Options:**
| Option | Description | Default |
|--------|-------------|---------|
| `-s, --subnet` | Network subnet | 192.168.64.0/24 |
| `-d, --duration` | Transition duration (ms) | 250 |
| `-p, --period` | Effect period (ms) | 1000 |
| `-c, --cycles` | Effect cycles | 10 |
| `-l, --loop` | Loop effect indefinitely | False |

---

## Effects

### Waveform Effects (Hardware)

These effects run on the bulb's firmware. They oscillate between the current color and a target color.

| Effect | Description |
|--------|-------------|
| `pulse` | Quick on/off flash |
| `breathe` | Smooth fade in/out (sine wave) |
| `strobe` | Rapid flashing |
| `saw` | Gradual on, instant off |
| `triangle` | Linear fade in and out |

### Color Effects (Software)

These effects send color commands over time for full color cycling.

| Effect | Description |
|--------|-------------|
| `rainbow` | Smooth cycle through all hues |
| `disco` | Random color changes |
| `party` | Beat-synchronized color changes |
| `police` | Red/blue alternating flash |

### Ambient Effects (Software)

| Effect | Description |
|--------|-------------|
| `candle` | Warm flickering flame simulation |
| `relax` | Slow transitions in warm tones |
| `sunrise` | Gradual warm-to-daylight wake-up |
| `sunset` | Gradual daylight-to-warm wind-down |

### Matrix Effects (For Ceiling/Tile/Candle devices)

These effects control individual pixels on matrix-capable devices like LIFX Ceiling (8x8 grid = 64 pixels), LIFX Tile, and LIFX Candle.

| Effect | Description |
|--------|-------------|
| `matrix_rainbow` | Animated diagonal rainbow pattern |
| `matrix_wave` | Color wave with brightness variation |
| `matrix_flame` | Fire simulation with rising heat |
| `matrix_morph` | Smooth color blending (hardware) |
| `matrix_sky` | Sunrise/sunset/clouds (hardware) |

---

## Matrix/Tile Pixel Control

Devices like the LIFX Ceiling have individually controllable pixels. The Ceiling has 64 pixels in an 8x8 grid.

### Programmatic Control

```python
from lifx_protocol import create_set64_packet, generate_source_id

source = generate_source_id()
target = bytes.fromhex('d073d5879243') + b'\x00\x00'  # Device MAC

# Create 64 colors (8x8 grid)
colors = []
for row in range(8):
    for col in range(8):
        hue = int((row + col) / 16 * 65535)  # Diagonal gradient
        saturation = 65535
        brightness = 32768
        kelvin = 3500
        colors.append((hue, saturation, brightness, kelvin))

# Send to device
packet = create_set64_packet(source, target, colors, duration=500)
sock.sendto(packet, (device_ip, 56700))
```

### Supported Matrix Devices

| Product | Pixels | Grid |
|---------|--------|------|
| LIFX Ceiling | 64 | 8×8 |
| LIFX Ceiling 13×26" | 64 | 8×8 |
| LIFX Tile | 64 | 8×8 |
| LIFX Candle | 8 | 8×1 |
| LIFX Tube | 64 | 8×8 |
| LIFX Luna | 64 | 8×8 |

---

## Protocol Library (`lifx_protocol.py`)

The core library provides:

### Constants
- `LIFX_PORT` (56700)
- Message type constants (GETSERVICE_TYPE, SETCOLOR_TYPE, etc.)
- `LIFX_PRODUCTS` - Product database with feature flags

### Data Classes
- `LIFXDevice` - Represents a discovered device
- `HSBK` - Color representation (hue, saturation, brightness, kelvin)

### Packet Creation
```python
from lifx_protocol import (
    create_getservice_packet,    # Discovery
    create_setcolor_packet,      # Set color
    create_setlightpower_packet, # Power control
    create_setwaveform_packet,   # Waveform effects
    create_set64_packet,         # Matrix pixel control
    create_settileeffect_packet, # Hardware matrix effects
)
```

### Parsing Functions
```python
from lifx_protocol import (
    parse_lifx_header,
    parse_light_state,
    parse_state64,
    parse_state_device_chain,
)
```

### Helper Functions
```python
from lifx_protocol import (
    generate_source_id,
    get_broadcast_address,
    get_device_matrix_size,   # Returns (width, height) for matrix devices
)
```

---

## Effects Library (`lifx_effects.py`)

High-level effects API used by all interfaces.

```python
from lifx_effects import run_effect, stop_effect, list_effects, list_matrix_effects

# Run an effect
run_effect(device, 'rainbow', period=2000, cycles=0, brightness=0.8)

# Stop an effect
stop_effect(device)

# Get available effects
print(list_effects())         # All effects
print(list_matrix_effects())  # Matrix-only effects
```

---

## Network Configuration

### Finding Your Subnet

```bash
# Linux
ip addr show | grep "inet "

# macOS
ifconfig | grep "inet "

# Example output: inet 192.168.64.100/24
# Your subnet is: 192.168.64.0/24
```

### Firewall

Ensure UDP port 56700 is open:

```bash
# Linux (ufw)
sudo ufw allow 56700/udp

# Linux (firewalld)
sudo firewall-cmd --add-port=56700/udp --permanent
sudo firewall-cmd --reload
```

---

## Troubleshooting

### No devices found

1. Check that your LIFX lights are connected to WiFi and powered on
2. Verify your computer is on the same network as the lights
3. Try a different subnet: `python3 lifx_scanner.py -s 192.168.1.0/24`
4. Check firewall isn't blocking UDP 56700
5. Increase timeout: `python3 lifx_scanner.py -t 5`

### Effects not working

1. Make sure the light is powered on first
2. For matrix effects, verify the device supports matrix (Ceiling, Tile, Candle)
3. Software effects require the script to keep running

### Web interface not accessible from other devices

1. Check that you're accessing via IP, not localhost
2. Verify firewall allows the port (default 6969)
3. Use `--host 0.0.0.0` if binding issues occur

---

## References

- [LIFX LAN Protocol Documentation](https://lan.developer.lifx.com/docs)
- [LIFX Products JSON](https://github.com/LIFX/products/blob/master/products.json)
- [Textual Framework](https://textual.textualize.io/)

## License

MIT License - Use freely for personal and commercial projects.
