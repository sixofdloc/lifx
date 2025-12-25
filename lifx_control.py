#!/usr/bin/env python3
"""
LIFX Device Controller

Scans and controls LIFX devices on the local network using the LIFX LAN Protocol.
Supports discovery, power control, color changes, and waveform effects.

Protocol documentation: https://lan.developer.lifx.com/docs/packet-contents
"""

import argparse
import ipaddress
import math
import re
import socket
import struct
import sys
import time
from typing import Optional

from lifx_protocol import (
    # Constants
    LIFX_PORT,
    SERVICE_UDP,
    LIFX_PRODUCTS,
    NAMED_COLORS,
    
    # Message Types
    STATESERVICE_TYPE,
    SETPOWER_TYPE,
    SETLIGHTPOWER_TYPE,
    SETCOLOR_TYPE,
    SETWAVEFORM_TYPE,
    LIGHTSTATE_TYPE,
    SETWAVEFORMOPTIONAL_TYPE,
    STATEVERSION_TYPE,
    STATEHOSTFIRMWARE_TYPE,
    STATEWIFIINFO_TYPE,
    STATEINFO_TYPE,
    STATELOCATION_TYPE,
    STATEGROUP_TYPE,
    STATEINFRARED_TYPE,
    STATEZONE_TYPE,
    STATEMULTIZONE_TYPE,
    STATEEXTENDEDCOLORZONES_TYPE,
    STATEMULTIZONEEFFECT_TYPE,
    ACKNOWLEDGEMENT_TYPE,
    
    # Enums and Classes
    Waveform,
    LIFXDevice,
    HSBK,
    
    # Utility Functions
    get_broadcast_address,
    generate_source_id,
    
    # Packet Creation Functions
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
    
    # Packet Parsing Functions
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


# =============================================================================
# Network Communication
# =============================================================================

class LIFXController:
    """Controller for LIFX device communication."""
    
    def __init__(self, subnet: str = "192.168.64.0/24", timeout: float = 2.0, verbose: bool = False):
        self.subnet = subnet
        self.timeout = timeout
        self.verbose = verbose
        self.source = generate_source_id()
        self.sequence = 0
        self.devices: dict[str, LIFXDevice] = {}
        self.sock: Optional[socket.socket] = None
    
    def _next_sequence(self) -> int:
        """Get next sequence number (wraps at 255)."""
        seq = self.sequence
        self.sequence = (self.sequence + 1) % 256
        return seq
    
    def _create_socket(self) -> socket.socket:
        """Create and configure UDP socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', 0))
        return sock
    
    def _get_broadcast_address(self) -> str:
        """Calculate broadcast address for subnet."""
        return get_broadcast_address(self.subnet)
    
    def _send_and_receive(self, packet: bytes, target_ip: str = None, 
                          target_port: int = LIFX_PORT, 
                          wait_for_type: int = None,
                          max_responses: int = 100) -> list[tuple]:
        """
        Send packet and collect responses.
        
        Returns list of (header_dict, address) tuples.
        """
        sock = self._create_socket()
        sock.settimeout(self.timeout)
        
        responses = []
        
        try:
            if target_ip is None:
                target_ip = self._get_broadcast_address()
            
            sock.sendto(packet, (target_ip, target_port))
            
            end_time = time.time() + self.timeout
            while time.time() < end_time and len(responses) < max_responses:
                try:
                    remaining = end_time - time.time()
                    if remaining <= 0:
                        break
                    sock.settimeout(remaining)
                    
                    data, addr = sock.recvfrom(1024)
                    header = parse_lifx_header(data)
                    
                    if header and (wait_for_type is None or header['type'] == wait_for_type):
                        responses.append((header, addr))
                        if wait_for_type is not None and len(responses) >= 1:
                            break
                            
                except socket.timeout:
                    break
        finally:
            sock.close()
        
        return responses
    
    def discover(self, retries: int = 3) -> list[LIFXDevice]:
        """
        Discover LIFX devices on the network.
        
        Returns list of discovered devices.
        """
        if self.verbose:
            print(f"Scanning subnet: {self.subnet}")
            print(f"Broadcast address: {self._get_broadcast_address()}")
        
        discovered: dict[str, LIFXDevice] = {}
        
        for attempt in range(retries):
            if self.verbose:
                print(f"Broadcast attempt {attempt + 1}/{retries}...")
            
            packet = create_getservice_packet(self.source, self._next_sequence())
            responses = self._send_and_receive(packet, wait_for_type=None)
            
            for header, addr in responses:
                if header['type'] != STATESERVICE_TYPE:
                    continue
                
                service_info = parse_state_service(header['payload'])
                if service_info is None or service_info[0] != SERVICE_UDP:
                    continue
                
                serial = header['serial']
                if serial not in discovered:
                    device = LIFXDevice(
                        ip_address=addr[0],
                        port=service_info[1],
                        serial=serial,
                        service=service_info[0]
                    )
                    discovered[serial] = device
                    if self.verbose:
                        print(f"  Found: {serial} @ {addr[0]}")
        
        # Get labels and state for each device
        for device in discovered.values():
            self._update_device_state(device)
        
        self.devices = discovered
        return list(discovered.values())
    
    def _update_device_state(self, device: LIFXDevice):
        """Update device label and color state."""
        # Get color state (includes label)
        packet = create_getcolor_packet(self.source, device.target_bytes, self._next_sequence())
        responses = self._send_and_receive(packet, device.ip_address, device.port, LIGHTSTATE_TYPE)
        
        for header, _ in responses:
            state = parse_light_state(header['payload'])
            if state:
                device.label = state['label']
                device.power = state['power']
                device.hue = state['hue']
                device.saturation = state['saturation']
                device.brightness = state['brightness']
                device.kelvin = state['kelvin']
                break
    
    def get_device(self, identifier: str) -> Optional[LIFXDevice]:
        """
        Find device by serial, IP, or label.
        
        Args:
            identifier: Device serial (xx:xx:xx:xx:xx:xx), IP address, or label
        """
        identifier_lower = identifier.lower()
        
        for device in self.devices.values():
            if device.serial.lower() == identifier_lower:
                return device
            if device.ip_address == identifier:
                return device
            if device.label.lower() == identifier_lower:
                return device
        
        return None
    
    def get_all_devices(self) -> list[LIFXDevice]:
        """Get all discovered devices."""
        return list(self.devices.values())
    
    def set_power(self, device: LIFXDevice, on: bool, duration: int = 0) -> bool:
        """
        Set device power state.
        
        Args:
            device: Target device
            on: True for on, False for off
            duration: Transition time in milliseconds
        """
        level = 65535 if on else 0
        
        if duration > 0:
            packet = create_setlightpower_packet(
                self.source, device.target_bytes, level, duration, self._next_sequence()
            )
        else:
            packet = create_setpower_packet(
                self.source, device.target_bytes, level, self._next_sequence()
            )
        
        responses = self._send_and_receive(packet, device.ip_address, device.port, ACKNOWLEDGEMENT_TYPE)
        
        if responses:
            device.power = level
            return True
        return False
    
    def set_color(self, device: LIFXDevice, hsbk: HSBK, duration: int = 0) -> bool:
        """
        Set device color.
        
        Args:
            device: Target device
            hsbk: Target color
            duration: Transition time in milliseconds
        """
        packet = create_setcolor_packet(
            self.source, device.target_bytes, hsbk, duration, self._next_sequence()
        )
        
        responses = self._send_and_receive(packet, device.ip_address, device.port, ACKNOWLEDGEMENT_TYPE)
        
        if responses:
            device.hue = hsbk.hue
            device.saturation = hsbk.saturation
            device.brightness = hsbk.brightness
            device.kelvin = hsbk.kelvin
            return True
        return False
    
    def set_waveform(
        self,
        device: LIFXDevice,
        hsbk: HSBK,
        waveform: Waveform = Waveform.SINE,
        period: int = 1000,
        cycles: float = 5.0,
        transient: bool = True,
        skew_ratio: int = 0
    ) -> bool:
        """
        Run waveform effect on device.
        
        Args:
            device: Target device
            hsbk: Target color for effect
            waveform: Effect type (SAW, SINE, HALF_SINE, TRIANGLE, PULSE)
            period: Time for one cycle in milliseconds
            cycles: Number of cycles to run
            transient: Return to original color after effect
            skew_ratio: Duty cycle for PULSE (-32768 to 32767, 0 = 50%)
        """
        packet = create_setwaveform_packet(
            self.source, device.target_bytes, hsbk,
            transient=transient,
            period=period,
            cycles=cycles,
            skew_ratio=skew_ratio,
            waveform=waveform,
            sequence=self._next_sequence()
        )
        
        responses = self._send_and_receive(packet, device.ip_address, device.port, ACKNOWLEDGEMENT_TYPE)
        return len(responses) > 0
    
    def broadcast_power(self, on: bool, duration: int = 0) -> int:
        """
        Broadcast power command to all devices.
        
        Returns number of devices that acknowledged.
        """
        level = 65535 if on else 0
        
        # Create broadcast packet with tagged=True
        packet = create_lifx_header(
            message_type=SETLIGHTPOWER_TYPE if duration > 0 else SETPOWER_TYPE,
            source=self.source,
            target=b'\x00' * 8,
            tagged=True,
            ack_required=False,
            sequence=self._next_sequence(),
            payload_size=6 if duration > 0 else 2
        )
        if duration > 0:
            packet += struct.pack('<HI', level, duration)
        else:
            packet += struct.pack('<H', level)
        
        sock = self._create_socket()
        try:
            sock.sendto(packet, (self._get_broadcast_address(), LIFX_PORT))
        finally:
            sock.close()
        
        return len(self.devices)
    
    def broadcast_color(self, hsbk: HSBK, duration: int = 0) -> int:
        """
        Broadcast color command to all devices.
        
        Returns number of devices.
        """
        payload = struct.pack('<B', 0) + hsbk.to_bytes() + struct.pack('<I', duration)
        packet = create_lifx_header(
            message_type=SETCOLOR_TYPE,
            source=self.source,
            target=b'\x00' * 8,
            tagged=True,
            ack_required=False,
            sequence=self._next_sequence(),
            payload_size=len(payload)
        ) + payload
        
        sock = self._create_socket()
        try:
            sock.sendto(packet, (self._get_broadcast_address(), LIFX_PORT))
        finally:
            sock.close()
        
        return len(self.devices)

    def get_device_info(self, device: LIFXDevice) -> dict:
        """
        Query comprehensive information about a device.
        
        Returns dict with version, firmware, wifi, location, group, and uptime info.
        """
        info = {
            'label': device.label,
            'serial': device.serial,
            'ip_address': device.ip_address,
            'port': device.port,
        }
        
        # Get version info (vendor, product)
        packet = create_getversion_packet(self.source, device.target_bytes, self._next_sequence())
        responses = self._send_and_receive(packet, device.ip_address, device.port, STATEVERSION_TYPE)
        for header, _ in responses:
            version = parse_state_version(header['payload'])
            if version:
                info['vendor'] = version['vendor']
                info['product_id'] = version['product']
                # Look up product name and features
                product = LIFX_PRODUCTS.get(version['product'], {})
                info['product_name'] = product.get('name', f"Unknown ({version['product']})")
                info['features'] = product.get('features', {})
                break
        
        # Get firmware version
        packet = create_gethostfirmware_packet(self.source, device.target_bytes, self._next_sequence())
        responses = self._send_and_receive(packet, device.ip_address, device.port, STATEHOSTFIRMWARE_TYPE)
        for header, _ in responses:
            firmware = parse_state_hostfirmware(header['payload'])
            if firmware:
                info['firmware_version'] = f"{firmware['version_major']}.{firmware['version_minor']}"
                info['firmware_build'] = firmware['build']
                break
        
        # Get WiFi info
        packet = create_getwifiinfo_packet(self.source, device.target_bytes, self._next_sequence())
        responses = self._send_and_receive(packet, device.ip_address, device.port, STATEWIFIINFO_TYPE)
        for header, _ in responses:
            wifi = parse_state_wifiinfo(header['payload'])
            if wifi:
                # Signal is in milliwatts, convert to dBm for readability
                signal_mw = wifi['signal']
                if signal_mw > 0:
                    signal_dbm = 10 * math.log10(signal_mw / 1000)
                    info['wifi_signal_dbm'] = round(signal_dbm, 1)
                info['wifi_signal_mw'] = signal_mw
                break
        
        # Get device uptime/runtime info
        packet = create_getinfo_packet(self.source, device.target_bytes, self._next_sequence())
        responses = self._send_and_receive(packet, device.ip_address, device.port, STATEINFO_TYPE)
        for header, _ in responses:
            device_info = parse_state_info(header['payload'])
            if device_info:
                # Convert nanoseconds to human-readable
                uptime_ns = device_info['uptime']
                uptime_secs = uptime_ns / 1_000_000_000
                days = int(uptime_secs // 86400)
                hours = int((uptime_secs % 86400) // 3600)
                minutes = int((uptime_secs % 3600) // 60)
                secs = int(uptime_secs % 60)
                info['uptime'] = f"{days}d {hours}h {minutes}m {secs}s"
                info['uptime_seconds'] = uptime_secs
                info['downtime_seconds'] = device_info['downtime'] / 1_000_000_000
                break
        
        # Get location
        packet = create_getlocation_packet(self.source, device.target_bytes, self._next_sequence())
        responses = self._send_and_receive(packet, device.ip_address, device.port, STATELOCATION_TYPE)
        for header, _ in responses:
            location = parse_state_location(header['payload'])
            if location:
                info['location'] = location['label']
                info['location_id'] = location['location_id']
                break
        
        # Get group
        packet = create_getgroup_packet(self.source, device.target_bytes, self._next_sequence())
        responses = self._send_and_receive(packet, device.ip_address, device.port, STATEGROUP_TYPE)
        for header, _ in responses:
            group = parse_state_group(header['payload'])
            if group:
                info['group'] = group['label']
                info['group_id'] = group['group_id']
                break
        
        # Check capabilities and query if supported
        features = info.get('features', {})
        
        # Get infrared level if device supports it
        if features.get('infrared'):
            packet = create_getinfrared_packet(self.source, device.target_bytes, self._next_sequence())
            responses = self._send_and_receive(packet, device.ip_address, device.port, STATEINFRARED_TYPE)
            for header, _ in responses:
                ir_info = parse_state_infrared(header['payload'])
                if ir_info:
                    info['infrared_brightness'] = ir_info['brightness']
                    info['infrared_percent'] = round(ir_info['brightness'] / 65535 * 100, 1)
                    break
        
        # Get multizone info if device supports it
        if features.get('multizone'):
            # Try extended color zones first (more efficient)
            if features.get('extended_multizone'):
                packet = create_getextendedcolorzones_packet(self.source, device.target_bytes, self._next_sequence())
                responses = self._send_and_receive(packet, device.ip_address, device.port, STATEEXTENDEDCOLORZONES_TYPE)
                for header, _ in responses:
                    zones_info = parse_state_extended_color_zones(header['payload'])
                    if zones_info:
                        info['zones_count'] = zones_info['zones_count']
                        info['zones'] = zones_info['zones']
                        break
            else:
                # Fall back to regular GetColorZones
                packet = create_getcolorzones_packet(self.source, device.target_bytes, 0, 255, self._next_sequence())
                responses = self._send_and_receive(packet, device.ip_address, device.port, wait_for_type=None)
                all_zones = []
                zones_count = 0
                for header, _ in responses:
                    if header['type'] == STATEZONE_TYPE:
                        zone_info = parse_state_zone(header['payload'])
                        if zone_info:
                            zones_count = zone_info['zones_count']
                            all_zones.extend(zone_info['zones'])
                    elif header['type'] == STATEMULTIZONE_TYPE:
                        zone_info = parse_state_multizone(header['payload'])
                        if zone_info:
                            zones_count = zone_info['zones_count']
                            all_zones.extend(zone_info['zones'])
                if all_zones:
                    info['zones_count'] = zones_count
                    info['zones'] = sorted(all_zones, key=lambda z: z['index'])
            
            # Get multizone effect status
            packet = create_getmultizoneeffect_packet(self.source, device.target_bytes, self._next_sequence())
            responses = self._send_and_receive(packet, device.ip_address, device.port, STATEMULTIZONEEFFECT_TYPE)
            for header, _ in responses:
                effect_info = parse_state_multizone_effect(header['payload'])
                if effect_info:
                    info['multizone_effect'] = effect_info
                    break
        
        return info


# =============================================================================
# Color Parsing Utilities
# =============================================================================

def parse_color(color_str: str, kelvin: int = 3500) -> HSBK:
    """
    Parse color string to HSBK.
    
    Supports:
    - Named colors: red, green, blue, white, etc.
    - Hex: #FF0000 or FF0000
    - RGB: rgb(255, 0, 0)
    - HSB: hsb(0, 100, 100) - hue in degrees, sat/bright in percent
    - HSBK: hsbk(0, 100, 100, 3500)
    """
    color_str = color_str.strip().lower()
    
    # Named colors
    if color_str in NAMED_COLORS:
        h, s, b = NAMED_COLORS[color_str]
        if color_str == 'warm_white':
            kelvin = 2700
        elif color_str == 'cool_white':
            kelvin = 6500
        return HSBK.from_degrees(h, s, b, kelvin)
    
    # Hex color
    if color_str.startswith('#') or re.match(r'^[0-9a-f]{6}$', color_str):
        return HSBK.from_hex(color_str, kelvin)
    
    # RGB
    rgb_match = re.match(r'rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', color_str)
    if rgb_match:
        r, g, b = map(int, rgb_match.groups())
        return HSBK.from_rgb(r, g, b, kelvin)
    
    # HSB
    hsb_match = re.match(r'hsb\s*\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)', color_str)
    if hsb_match:
        h, s, b = map(float, hsb_match.groups())
        return HSBK.from_degrees(h, s / 100, b / 100, kelvin)
    
    # HSBK
    hsbk_match = re.match(r'hsbk\s*\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*(\d+)\s*\)', color_str)
    if hsbk_match:
        h, s, b, k = hsbk_match.groups()
        return HSBK.from_degrees(float(h), float(s) / 100, float(b) / 100, int(k))
    
    raise ValueError(f"Unknown color format: {color_str}")


# =============================================================================
# CLI Interface
# =============================================================================

def cmd_scan(args, controller: LIFXController):
    """Handle scan command."""
    devices = controller.discover(retries=args.retries)
    
    if args.json:
        import json
        result = {
            'subnet': args.subnet,
            'devices': [
                {
                    'ip_address': d.ip_address,
                    'port': d.port,
                    'serial': d.serial,
                    'label': d.label,
                    'power': 'on' if d.power else 'off',
                    'hue': d.hue,
                    'saturation': d.saturation,
                    'brightness': d.brightness,
                    'kelvin': d.kelvin
                }
                for d in devices
            ]
        }
        print(json.dumps(result, indent=2))
    else:
        if devices:
            print(f"Found {len(devices)} LIFX device(s):")
            print("-" * 60)
            for device in sorted(devices, key=lambda d: d.label or d.serial):
                power_str = "ON" if device.power else "OFF"
                print(f"  Label:   {device.label or '(no label)'}")
                print(f"  Serial:  {device.serial}")
                print(f"  IP:      {device.ip_address}:{device.port}")
                print(f"  Power:   {power_str}")
                print(f"  Color:   H:{device.hue} S:{device.saturation} B:{device.brightness} K:{device.kelvin}")
                print("-" * 60)
        else:
            print("No LIFX devices found.")


def cmd_on(args, controller: LIFXController):
    """Handle on command."""
    controller.discover(retries=1)
    
    duration = int(args.duration * 1000) if args.duration else 0
    
    if args.device == 'all':
        count = controller.broadcast_power(True, duration)
        print(f"Sent power ON to all devices")
    else:
        device = controller.get_device(args.device)
        if not device:
            print(f"Device not found: {args.device}", file=sys.stderr)
            sys.exit(1)
        
        if controller.set_power(device, True, duration):
            print(f"Turned ON: {device.label or device.serial}")
        else:
            print(f"Failed to turn on device", file=sys.stderr)
            sys.exit(1)


def cmd_off(args, controller: LIFXController):
    """Handle off command."""
    controller.discover(retries=1)
    
    duration = int(args.duration * 1000) if args.duration else 0
    
    if args.device == 'all':
        controller.broadcast_power(False, duration)
        print(f"Sent power OFF to all devices")
    else:
        device = controller.get_device(args.device)
        if not device:
            print(f"Device not found: {args.device}", file=sys.stderr)
            sys.exit(1)
        
        if controller.set_power(device, False, duration):
            print(f"Turned OFF: {device.label or device.serial}")
        else:
            print(f"Failed to turn off device", file=sys.stderr)
            sys.exit(1)


def cmd_color(args, controller: LIFXController):
    """Handle color command."""
    controller.discover(retries=1)
    
    try:
        hsbk = parse_color(args.color, args.kelvin)
    except ValueError as e:
        print(f"Invalid color: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Override kelvin if specified
    if args.kelvin:
        hsbk.kelvin = args.kelvin
    
    # Override brightness if specified
    if args.brightness is not None:
        hsbk.brightness = int(args.brightness / 100 * 65535)
    
    duration = int(args.duration * 1000) if args.duration else 0
    
    if args.device == 'all':
        controller.broadcast_color(hsbk, duration)
        print(f"Set color on all devices")
    else:
        device = controller.get_device(args.device)
        if not device:
            print(f"Device not found: {args.device}", file=sys.stderr)
            sys.exit(1)
        
        if controller.set_color(device, hsbk, duration):
            print(f"Set color on: {device.label or device.serial}")
        else:
            print(f"Failed to set color", file=sys.stderr)
            sys.exit(1)


def cmd_waveform(args, controller: LIFXController):
    """Handle waveform command."""
    controller.discover(retries=1)
    
    try:
        hsbk = parse_color(args.color, args.kelvin)
    except ValueError as e:
        print(f"Invalid color: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.kelvin:
        hsbk.kelvin = args.kelvin
    
    if args.brightness is not None:
        hsbk.brightness = int(args.brightness / 100 * 65535)
    
    try:
        waveform = Waveform[args.waveform.upper()]
    except KeyError:
        print(f"Invalid waveform: {args.waveform}", file=sys.stderr)
        print(f"Valid options: {', '.join(w.name for w in Waveform)}")
        sys.exit(1)
    
    period = int(args.period * 1000)
    
    # Convert duty cycle (0-1) to skew_ratio (-32768 to 32767)
    skew_ratio = int((args.duty_cycle - 0.5) * 65535)
    
    if args.device == 'all':
        for device in controller.get_all_devices():
            controller.set_waveform(
                device, hsbk, waveform=waveform,
                period=period, cycles=args.cycles,
                transient=args.transient, skew_ratio=skew_ratio
            )
        print(f"Started {waveform.name} waveform on all devices")
    else:
        device = controller.get_device(args.device)
        if not device:
            print(f"Device not found: {args.device}", file=sys.stderr)
            sys.exit(1)
        
        if controller.set_waveform(
            device, hsbk, waveform=waveform,
            period=period, cycles=args.cycles,
            transient=args.transient, skew_ratio=skew_ratio
        ):
            print(f"Started {waveform.name} waveform on: {device.label or device.serial}")
        else:
            print(f"Failed to start waveform", file=sys.stderr)
            sys.exit(1)


def cmd_info(args, controller: LIFXController):
    """Handle info command."""
    controller.discover(retries=1)
    
    if args.device == 'all':
        devices = controller.get_all_devices()
    else:
        device = controller.get_device(args.device)
        if not device:
            print(f"Device not found: {args.device}", file=sys.stderr)
            sys.exit(1)
        devices = [device]
    
    if args.json:
        import json
        result = {'devices': []}
        for device in devices:
            info = controller.get_device_info(device)
            result['devices'].append(info)
        print(json.dumps(result, indent=2))
    else:
        for device in sorted(devices, key=lambda d: d.label or d.serial):
            info = controller.get_device_info(device)
            
            print("=" * 60)
            print(f"  Device: {info.get('label', '(no label)')}")
            print("=" * 60)
            
            # Basic info
            print(f"  Serial:       {info.get('serial', 'N/A')}")
            print(f"  IP Address:   {info.get('ip_address', 'N/A')}:{info.get('port', 'N/A')}")
            print()
            
            # Product info
            print(f"  Product:      {info.get('product_name', 'Unknown')}")
            print(f"  Product ID:   {info.get('product_id', 'N/A')}")
            print(f"  Vendor:       {info.get('vendor', 'N/A')}")
            print()
            
            # Firmware
            print(f"  Firmware:     v{info.get('firmware_version', 'N/A')}")
            print()
            
            # Features
            features = info.get('features', {})
            if features:
                caps = []
                if features.get('color'):
                    caps.append('Color')
                else:
                    caps.append('White only')
                if features.get('infrared'):
                    caps.append('Infrared')
                if features.get('multizone'):
                    caps.append('Multizone')
                if features.get('matrix'):
                    caps.append('Matrix')
                if features.get('chain'):
                    caps.append('Chain')
                if features.get('hev'):
                    caps.append('HEV (Clean)')
                if features.get('buttons'):
                    caps.append('Buttons')
                if features.get('relays'):
                    caps.append('Relays')
                print(f"  Capabilities: {', '.join(caps)}")
                
                temp_range = features.get('temperature_range')
                if temp_range:
                    print(f"  Temp Range:   {temp_range[0]}K - {temp_range[1]}K")
                print()
            
            # Network
            if 'wifi_signal_dbm' in info:
                signal = info['wifi_signal_dbm']
                # Signal strength indicator
                if signal >= -50:
                    strength = "Excellent"
                elif signal >= -60:
                    strength = "Good"
                elif signal >= -70:
                    strength = "Fair"
                else:
                    strength = "Poor"
                print(f"  WiFi Signal:  {signal} dBm ({strength})")
            print()
            
            # Location/Group
            if info.get('location') or info.get('group'):
                if info.get('location'):
                    print(f"  Location:     {info['location']}")
                if info.get('group'):
                    print(f"  Group:        {info['group']}")
                print()
            
            # Infrared (for Night Vision bulbs)
            if 'infrared_brightness' in info:
                print(f"  Infrared:     {info['infrared_percent']}%")
                print()
            
            # MultiZone info (for strips, beams, etc.)
            if 'zones_count' in info:
                print(f"  Zones:        {info['zones_count']} zones")
                if info.get('multizone_effect'):
                    effect = info['multizone_effect']
                    print(f"  Zone Effect:  {effect['type_name']}")
                    if effect['type'] != 0:  # Not OFF
                        print(f"    Speed:      {effect['speed']} ms/cycle")
                
                # Show zone colors summary (first few and last few)
                zones = info.get('zones', [])
                if zones:
                    print(f"  Zone Colors:")
                    max_display = 8
                    if len(zones) <= max_display:
                        for z in zones:
                            h_deg = round(z['hue'] / 65535 * 360)
                            s_pct = round(z['saturation'] / 65535 * 100)
                            b_pct = round(z['brightness'] / 65535 * 100)
                            print(f"    [{z['index']:2d}] H:{h_deg:3d}° S:{s_pct:3d}% B:{b_pct:3d}% K:{z['kelvin']}")
                    else:
                        # Show first 4 and last 4
                        for z in zones[:4]:
                            h_deg = round(z['hue'] / 65535 * 360)
                            s_pct = round(z['saturation'] / 65535 * 100)
                            b_pct = round(z['brightness'] / 65535 * 100)
                            print(f"    [{z['index']:2d}] H:{h_deg:3d}° S:{s_pct:3d}% B:{b_pct:3d}% K:{z['kelvin']}")
                        print(f"    ... ({len(zones) - 8} more zones) ...")
                        for z in zones[-4:]:
                            h_deg = round(z['hue'] / 65535 * 360)
                            s_pct = round(z['saturation'] / 65535 * 100)
                            b_pct = round(z['brightness'] / 65535 * 100)
                            print(f"    [{z['index']:2d}] H:{h_deg:3d}° S:{s_pct:3d}% B:{b_pct:3d}% K:{z['kelvin']}")
                print()
            
            # Uptime
            if 'uptime' in info:
                print(f"  Uptime:       {info['uptime']}")
            
            print()


def main():
    parser = argparse.ArgumentParser(
        description='LIFX Device Controller - Scan and control LIFX devices on your network.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  scan                 Discover LIFX devices on the network
  on DEVICE            Turn device on (use 'all' for all devices)
  off DEVICE           Turn device off (use 'all' for all devices)
  color DEVICE COLOR   Set device color
  waveform DEVICE COLOR  Run waveform effect
  info DEVICE          Show device info and capabilities

Color formats:
  Named:   red, green, blue, cyan, magenta, yellow, orange, purple, 
           pink, white, warm_white, cool_white
  Hex:     #FF0000 or FF0000
  RGB:     rgb(255, 0, 0)
  HSB:     hsb(hue, sat, bright)  (hue degrees, saturation %%, brightness %%)
  HSBK:    hsbk(hue, sat, bright, kelvin)

Waveform types:
  SAW, SINE, HALF_SINE, TRIANGLE, PULSE

Examples:
  lifx_control.py scan
  lifx_control.py on all
  lifx_control.py off "Living Room"
  lifx_control.py color all red
  lifx_control.py color all "#FF6600" -d 2
  lifx_control.py color all "hsb(120, 100, 50)" -k 4000
  lifx_control.py waveform all blue --waveform pulse --cycles 10
  lifx_control.py waveform "Kitchen" red --waveform sine --period 2 --cycles 5
  lifx_control.py info "Office"
  lifx_control.py info all --json
        """
    )
    
    # Global options
    parser.add_argument('-s', '--subnet', default='192.168.64.0/24',
                        help='Network subnet (default: 192.168.64.0/24)')
    parser.add_argument('-t', '--timeout', type=float, default=1.0,
                        help='Response timeout in seconds (default: 1.0)')
    parser.add_argument('-r', '--retries', type=int, default=2,
                        help='Discovery retries (default: 2)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output')
    parser.add_argument('--json', action='store_true',
                        help='JSON output (for scan)')
    
    subparsers = parser.add_subparsers(dest='command', help='Command')
    
    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Discover devices')
    
    # On command
    on_parser = subparsers.add_parser('on', help='Turn device on')
    on_parser.add_argument('device', help='Device (serial, IP, label, or "all")')
    on_parser.add_argument('-d', '--duration', type=float, default=0,
                           help='Transition duration in seconds')
    
    # Off command
    off_parser = subparsers.add_parser('off', help='Turn device off')
    off_parser.add_argument('device', help='Device (serial, IP, label, or "all")')
    off_parser.add_argument('-d', '--duration', type=float, default=0,
                            help='Transition duration in seconds')
    
    # Color command
    color_parser = subparsers.add_parser('color', help='Set device color')
    color_parser.add_argument('device', help='Device (serial, IP, label, or "all")')
    color_parser.add_argument('color', help='Color (name, hex, rgb(), hsb(), hsbk())')
    color_parser.add_argument('-d', '--duration', type=float, default=0,
                              help='Transition duration in seconds')
    color_parser.add_argument('-k', '--kelvin', type=int, default=3500,
                              help='Color temperature (1500-9000, default: 3500)')
    color_parser.add_argument('-b', '--brightness', type=float,
                              help='Brightness override (0-100)')
    
    # Waveform command
    wave_parser = subparsers.add_parser('waveform', help='Run waveform effect')
    wave_parser.add_argument('device', help='Device (serial, IP, label, or "all")')
    wave_parser.add_argument('color', help='Target color')
    wave_parser.add_argument('-w', '--waveform', default='sine',
                             choices=['saw', 'sine', 'half_sine', 'triangle', 'pulse'],
                             help='Waveform type (default: sine)')
    wave_parser.add_argument('-p', '--period', type=float, default=1.0,
                             help='Cycle period in seconds (default: 1.0)')
    wave_parser.add_argument('-c', '--cycles', type=float, default=5.0,
                             help='Number of cycles (default: 5.0)')
    wave_parser.add_argument('--transient', action='store_true', default=True,
                             help='Return to original color (default: True)')
    wave_parser.add_argument('--no-transient', action='store_false', dest='transient',
                             help='Stay at target color after effect')
    wave_parser.add_argument('--duty-cycle', type=float, default=0.5,
                             help='Duty cycle for PULSE (0-1, default: 0.5)')
    wave_parser.add_argument('-k', '--kelvin', type=int, default=3500,
                             help='Color temperature (default: 3500)')
    wave_parser.add_argument('-b', '--brightness', type=float,
                             help='Brightness override (0-100)')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Get device info and capabilities')
    info_parser.add_argument('device', help='Device (serial, IP, label, or "all")')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # Validate subnet
    try:
        ipaddress.ip_network(args.subnet, strict=False)
    except ValueError as e:
        print(f"Invalid subnet: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Create controller
    controller = LIFXController(
        subnet=args.subnet,
        timeout=args.timeout,
        verbose=args.verbose
    )
    
    # Execute command
    commands = {
        'scan': cmd_scan,
        'on': cmd_on,
        'off': cmd_off,
        'color': cmd_color,
        'waveform': cmd_waveform,
        'info': cmd_info,
    }
    
    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args, controller)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
