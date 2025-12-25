#!/usr/bin/env python3
"""
LIFX Web Controller

A lightweight HTTP server for controlling LIFX lights from any browser on your LAN.

Usage:
    python3 lifx_web.py
    python3 lifx_web.py --port 6969 --subnet 192.168.1.0/24

Endpoints:
    GET  /                      - Web UI
    GET  /api/devices           - List all devices
    POST /api/refresh           - Re-scan for devices
    POST /api/device/<serial>/power     - Set power (body: {"on": true/false})
    POST /api/device/<serial>/color     - Set color (body: {"h":0-360, "s":0-100, "b":0-100, "k":1500-9000})
    POST /api/device/<serial>/preset    - Apply preset (body: {"preset": "red"})
    POST /api/all/power         - Set all devices power
    POST /api/all/color         - Set all devices color
"""

import argparse
import json
import os
import socket
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread, Lock
from typing import Optional
from urllib.parse import urlparse, parse_qs

from lifx_protocol import (
    LIFX_PORT,
    STATESERVICE_TYPE,
    LIGHTSTATE_TYPE,
    SERVICE_UDP,
    LIFXDevice,
    HSBK,
    Waveform,
    get_broadcast_address,
    generate_source_id,
    create_getservice_packet,
    create_getcolor_packet,
    create_setcolor_packet,
    create_setpower_packet,
    create_setlightpower_packet,
    create_setwaveform_packet,
    parse_lifx_header,
    parse_state_service,
    parse_light_state,
)


# =============================================================================
# LIFX Manager (shared state)
# =============================================================================

class LIFXManager:
    """Manages LIFX device communication."""
    
    def __init__(self, subnet: str = "192.168.64.0/24", timeout: float = 1.0):
        self.subnet = subnet
        self.timeout = timeout
        self.source = generate_source_id()
        self.sequence = 0
        self.devices: dict[str, LIFXDevice] = {}
        self.lock = Lock()
        self.last_scan = 0
    
    def _next_sequence(self) -> int:
        seq = self.sequence
        self.sequence = (self.sequence + 1) % 256
        return seq
    
    def discover(self, force: bool = False) -> list[LIFXDevice]:
        """Discover LIFX devices on the network."""
        # Don't scan more than once per 5 seconds unless forced
        if not force and time.time() - self.last_scan < 5:
            with self.lock:
                return list(self.devices.values())
        
        broadcast = get_broadcast_address(self.subnet)
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', 0))
        sock.settimeout(self.timeout)
        
        discovered: dict[str, LIFXDevice] = {}
        
        # Send discovery packet
        packet = create_getservice_packet(self.source, self._next_sequence())
        sock.sendto(packet, (broadcast, LIFX_PORT))
        
        # Collect responses
        end_time = time.time() + self.timeout
        while time.time() < end_time:
            try:
                remaining = end_time - time.time()
                if remaining <= 0:
                    break
                sock.settimeout(remaining)
                
                data, addr = sock.recvfrom(1024)
                header = parse_lifx_header(data)
                
                if header and header['type'] == STATESERVICE_TYPE:
                    service_info = parse_state_service(header['payload'])
                    if service_info and service_info[0] == SERVICE_UDP:
                        serial = header['serial']
                        if serial not in discovered:
                            device = LIFXDevice(
                                ip_address=addr[0],
                                port=service_info[1],
                                serial=serial,
                                service=service_info[0]
                            )
                            discovered[serial] = device
            except socket.timeout:
                break
        
        sock.close()
        
        # Get state for each device
        for device in discovered.values():
            self._update_device_state(device)
        
        with self.lock:
            self.devices = discovered
            self.last_scan = time.time()
        
        return list(discovered.values())
    
    def _update_device_state(self, device: LIFXDevice):
        """Update device label and color state."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        
        try:
            packet = create_getcolor_packet(self.source, device.target_bytes, self._next_sequence())
            sock.sendto(packet, (device.ip_address, device.port))
            
            data, _ = sock.recvfrom(1024)
            header = parse_lifx_header(data)
            
            if header and header['type'] == LIGHTSTATE_TYPE:
                state = parse_light_state(header['payload'])
                if state:
                    device.label = state['label']
                    device.power = state['power']
                    device.hue = state['hue']
                    device.saturation = state['saturation']
                    device.brightness = state['brightness']
                    device.kelvin = state['kelvin']
        except socket.timeout:
            pass
        finally:
            sock.close()
    
    def get_device(self, serial: str) -> Optional[LIFXDevice]:
        """Get device by serial."""
        with self.lock:
            return self.devices.get(serial)
    
    def get_devices(self) -> list[LIFXDevice]:
        """Get all devices."""
        with self.lock:
            return list(self.devices.values())
    
    def set_power(self, device: LIFXDevice, on: bool, duration: int = 250) -> bool:
        """Set device power state."""
        level = 65535 if on else 0
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        
        try:
            packet = create_setlightpower_packet(
                self.source, device.target_bytes, level, duration, self._next_sequence()
            )
            sock.sendto(packet, (device.ip_address, device.port))
            device.power = level
            return True
        except Exception:
            return False
        finally:
            sock.close()
    
    def set_color(self, device: LIFXDevice, hsbk: HSBK, duration: int = 250) -> bool:
        """Set device color."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        
        try:
            packet = create_setcolor_packet(
                self.source, device.target_bytes, hsbk, duration, self._next_sequence()
            )
            sock.sendto(packet, (device.ip_address, device.port))
            device.hue = hsbk.hue
            device.saturation = hsbk.saturation
            device.brightness = hsbk.brightness
            device.kelvin = hsbk.kelvin
            return True
        except Exception:
            return False
        finally:
            sock.close()
    
    def set_waveform(self, device: LIFXDevice, hsbk: HSBK, waveform: Waveform,
                     period: int = 1000, cycles: float = 5.0) -> bool:
        """Run waveform effect."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        
        try:
            packet = create_setwaveform_packet(
                self.source, device.target_bytes, hsbk,
                transient=True, period=period, cycles=cycles,
                waveform=waveform, sequence=self._next_sequence()
            )
            sock.sendto(packet, (device.ip_address, device.port))
            return True
        except Exception:
            return False
        finally:
            sock.close()


# =============================================================================
# HTTP Request Handler
# =============================================================================

# Color presets
PRESETS = {
    "red": (0, 100, 100, 3500),
    "orange": (30, 100, 100, 3500),
    "yellow": (60, 100, 100, 3500),
    "green": (120, 100, 100, 3500),
    "cyan": (180, 100, 100, 3500),
    "blue": (240, 100, 100, 3500),
    "purple": (280, 100, 100, 3500),
    "pink": (330, 100, 100, 3500),
    "warm": (0, 0, 100, 2700),
    "neutral": (0, 0, 100, 4000),
    "cool": (0, 0, 100, 5500),
    "daylight": (0, 0, 100, 6500),
}


class LIFXHandler(BaseHTTPRequestHandler):
    """HTTP request handler for LIFX API."""
    
    lifx: LIFXManager = None  # Set by server
    web_dir: str = None  # Set by server
    
    def log_message(self, format, *args):
        """Override to use simpler logging."""
        print(f"[{self.address_string()}] {args[0]}")
    
    def send_json(self, data: dict, status: int = 200):
        """Send JSON response."""
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)
    
    def send_file(self, filepath: str, content_type: str):
        """Send static file."""
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, 'File not found')
    
    def device_to_dict(self, device: LIFXDevice) -> dict:
        """Convert device to JSON-serializable dict."""
        return {
            'serial': device.serial,
            'label': device.label or device.serial[:12],
            'ip': device.ip_address,
            'power': device.power > 0,
            'hue': round(device.hue / 65535 * 360),
            'saturation': round(device.saturation / 65535 * 100),
            'brightness': round(device.brightness / 65535 * 100),
            'kelvin': device.kelvin,
        }
    
    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests."""
        path = urlparse(self.path).path
        
        # API endpoints
        if path == '/api/devices':
            devices = self.lifx.get_devices()
            if not devices:
                devices = self.lifx.discover()
            self.send_json({
                'devices': [self.device_to_dict(d) for d in sorted(devices, key=lambda x: x.label or x.serial)]
            })
            return
        
        # Static files
        if path == '/' or path == '/index.html':
            self.send_file(os.path.join(self.web_dir, 'index.html'), 'text/html')
            return
        
        if path.endswith('.css'):
            self.send_file(os.path.join(self.web_dir, path.lstrip('/')), 'text/css')
            return
        
        if path.endswith('.js'):
            self.send_file(os.path.join(self.web_dir, path.lstrip('/')), 'application/javascript')
            return
        
        self.send_error(404, 'Not found')
    
    def do_POST(self):
        """Handle POST requests."""
        path = urlparse(self.path).path
        
        # Read body
        content_length = int(self.headers.get('Content-Length', 0))
        body = {}
        if content_length > 0:
            try:
                body = json.loads(self.rfile.read(content_length))
            except json.JSONDecodeError:
                self.send_json({'error': 'Invalid JSON'}, 400)
                return
        
        # Refresh devices
        if path == '/api/refresh':
            devices = self.lifx.discover(force=True)
            self.send_json({
                'devices': [self.device_to_dict(d) for d in sorted(devices, key=lambda x: x.label or x.serial)]
            })
            return
        
        # All devices power
        if path == '/api/all/power':
            on = body.get('on', True)
            devices = self.lifx.get_devices()
            for device in devices:
                self.lifx.set_power(device, on)
            self.send_json({'success': True, 'count': len(devices)})
            return
        
        # All devices color
        if path == '/api/all/color':
            h = body.get('h', 0)
            s = body.get('s', 100)
            b = body.get('b', 100)
            k = body.get('k', 3500)
            hsbk = HSBK.from_degrees(h, s / 100, b / 100, k)
            devices = self.lifx.get_devices()
            for device in devices:
                self.lifx.set_color(device, hsbk)
            self.send_json({'success': True, 'count': len(devices)})
            return
        
        # Single device operations
        if path.startswith('/api/device/'):
            parts = path.split('/')
            if len(parts) >= 5:
                serial = parts[3]
                action = parts[4]
                
                device = self.lifx.get_device(serial)
                if not device:
                    self.send_json({'error': 'Device not found'}, 404)
                    return
                
                if action == 'power':
                    on = body.get('on', True)
                    self.lifx.set_power(device, on)
                    self.send_json({'success': True, 'power': on})
                    return
                
                if action == 'color':
                    h = body.get('h', 0)
                    s = body.get('s', 100)
                    b = body.get('b', 100)
                    k = body.get('k', 3500)
                    hsbk = HSBK.from_degrees(h, s / 100, b / 100, k)
                    self.lifx.set_color(device, hsbk)
                    self.send_json({'success': True})
                    return
                
                if action == 'preset':
                    preset = body.get('preset', 'warm')
                    if preset in PRESETS:
                        h, s, b, k = PRESETS[preset]
                        hsbk = HSBK.from_degrees(h, s / 100, b / 100, k)
                        self.lifx.set_color(device, hsbk)
                        self.send_json({'success': True, 'preset': preset})
                    else:
                        self.send_json({'error': 'Unknown preset'}, 400)
                    return
                
                if action == 'effect':
                    effect = body.get('effect', 'breathe')
                    period = body.get('period', 1000)
                    cycles = body.get('cycles', 5)
                    
                    target_brightness = 0 if effect in ('pulse', 'strobe') else int(device.brightness * 0.2)
                    hsbk = HSBK(
                        hue=device.hue,
                        saturation=device.saturation,
                        brightness=target_brightness,
                        kelvin=device.kelvin
                    )
                    
                    waveform = Waveform.SINE if effect == 'breathe' else Waveform.PULSE
                    if effect == 'strobe':
                        period = min(period, 200)
                    
                    self.lifx.set_waveform(device, hsbk, waveform, period=period, cycles=cycles)
                    self.send_json({'success': True, 'effect': effect})
                    return
        
        self.send_json({'error': 'Unknown endpoint'}, 404)


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='LIFX Web Controller')
    parser.add_argument('-p', '--port', type=int, default=6969, help='HTTP port (default: 6969)')
    parser.add_argument('-s', '--subnet', default='192.168.64.0/24', help='Network subnet')
    parser.add_argument('--host', default='0.0.0.0', help='Bind address (default: 0.0.0.0)')
    args = parser.parse_args()
    
    # Setup LIFX manager
    lifx = LIFXManager(subnet=args.subnet)
    
    # Find web directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    web_dir = os.path.join(script_dir, 'web')
    
    if not os.path.exists(web_dir):
        os.makedirs(web_dir)
        print(f"Created web directory: {web_dir}")
    
    # Configure handler
    LIFXHandler.lifx = lifx
    LIFXHandler.web_dir = web_dir
    
    # Initial device scan
    print(f"Scanning for LIFX devices on {args.subnet}...")
    devices = lifx.discover(force=True)
    print(f"Found {len(devices)} device(s)")
    
    # Start server
    server = HTTPServer((args.host, args.port), LIFXHandler)
    print(f"\nLIFX Web Controller running at http://{args.host}:{args.port}")
    print(f"Access from LAN: http://<your-ip>:{args.port}")
    print("Press Ctrl+C to stop\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == '__main__':
    main()
