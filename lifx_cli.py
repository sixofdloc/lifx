#!/usr/bin/env python3
"""
LIFX CLI - Command-line interface for LIFX lights

Control your LIFX lights from the command line with full support for
colors, presets, and effects.

Usage:
    lifx list                           # List all devices
    lifx <name> on/off                  # Turn light on/off
    lifx <name> color red               # Set color preset
    lifx <name> color #ff5500           # Set hex color
    lifx <name> hsb 180 100 50          # Set HSB (hue sat bright)
    lifx <name> kelvin 2700 80          # Set white temp and brightness
    lifx <name> effect rainbow          # Run rainbow effect
    lifx <name> effect candle --loop    # Run candle effect forever
    lifx <name> effect matrix_rainbow   # Matrix rainbow (Ceiling/Tile)
    lifx <name> stop                    # Stop any running effect
    lifx all on                         # Turn all lights on
    lifx all effect disco               # Run effect on all lights

Effects:
    Waveform: pulse, breathe, strobe, saw, triangle
    Color:    rainbow, disco, party, police
    Ambient:  candle, relax, sunrise, sunset
    Matrix:   matrix_rainbow, matrix_wave, matrix_flame,
              matrix_morph, matrix_sky (Ceiling/Tile devices)
"""

import argparse
import socket
import sys
import time
from typing import Optional

from lifx_protocol import (
    LIFX_PORT,
    STATESERVICE_TYPE,
    LIGHTSTATE_TYPE,
    SERVICE_UDP,
    LIFXDevice,
    HSBK,
    NAMED_COLORS,
    get_broadcast_address,
    generate_source_id,
    create_getservice_packet,
    create_getcolor_packet,
    create_setcolor_packet,
    create_setlightpower_packet,
    parse_lifx_header,
    parse_state_service,
    parse_light_state,
)

from lifx_effects import run_effect, stop_effect, list_effects


class LIFXController:
    """Simple LIFX controller for CLI use."""
    
    def __init__(self, subnet: str = "192.168.64.0/24", timeout: float = 1.0):
        self.subnet = subnet
        self.timeout = timeout
        self.source = generate_source_id()
        self.sequence = 0
        self._devices: dict[str, LIFXDevice] = {}
    
    def _next_sequence(self) -> int:
        seq = self.sequence
        self.sequence = (self.sequence + 1) % 256
        return seq
    
    def discover(self) -> list[LIFXDevice]:
        """Discover LIFX devices on the network."""
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
            self._get_device_state(device)
        
        self._devices = discovered
        return list(discovered.values())
    
    def _get_device_state(self, device: LIFXDevice):
        """Get device label and color state."""
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
    
    def find_device(self, name: str) -> Optional[LIFXDevice]:
        """Find device by name (case-insensitive, partial match)."""
        name_lower = name.lower()
        for device in self._devices.values():
            label = device.label.lower() if device.label else device.serial.lower()
            if name_lower in label or name_lower in device.serial.lower():
                return device
        return None
    
    def get_all_devices(self) -> list[LIFXDevice]:
        """Get all discovered devices."""
        return list(self._devices.values())
    
    def set_power(self, device: LIFXDevice, on: bool, duration: int = 250):
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
        finally:
            sock.close()
    
    def set_color(self, device: LIFXDevice, hsbk: HSBK, duration: int = 250):
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
        finally:
            sock.close()


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


def print_device_status(device: LIFXDevice):
    """Print device status."""
    power = "ON" if device.power else "OFF"
    hue = round(device.hue / 65535 * 360)
    sat = round(device.saturation / 65535 * 100)
    bright = round(device.brightness / 65535 * 100)
    
    name = device.label or device.serial[:12]
    print(f"  {name:<20} {device.ip_address:<15} {power:<4} H:{hue:>3} S:{sat:>3}% B:{bright:>3}% K:{device.kelvin}")


def main():
    parser = argparse.ArgumentParser(
        description='LIFX CLI - Control your LIFX lights',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        'target',
        nargs='?',
        default='list',
        help='Device name, "all", or "list"'
    )
    
    parser.add_argument(
        'command',
        nargs='?',
        help='Command: on, off, color, hsb, kelvin, effect, stop'
    )
    
    parser.add_argument(
        'args',
        nargs='*',
        help='Command arguments'
    )
    
    parser.add_argument(
        '-s', '--subnet',
        default='192.168.64.0/24',
        help='Network subnet (default: 192.168.64.0/24)'
    )
    
    parser.add_argument(
        '-d', '--duration',
        type=int,
        default=250,
        help='Transition duration in ms (default: 250)'
    )
    
    parser.add_argument(
        '-p', '--period',
        type=int,
        default=1000,
        help='Effect period in ms (default: 1000)'
    )
    
    parser.add_argument(
        '-c', '--cycles',
        type=float,
        default=10,
        help='Effect cycles (default: 10)'
    )
    
    parser.add_argument(
        '-l', '--loop',
        action='store_true',
        help='Loop effect indefinitely'
    )
    
    args = parser.parse_args()
    
    # Initialize controller
    controller = LIFXController(subnet=args.subnet)
    
    # List command
    if args.target == 'list':
        print("Scanning for LIFX devices...")
        devices = controller.discover()
        
        if not devices:
            print("No devices found.")
            return 1
        
        print(f"\nFound {len(devices)} device(s):")
        print("-" * 75)
        for device in sorted(devices, key=lambda d: d.label or d.serial):
            print_device_status(device)
        print("-" * 75)
        return 0
    
    # List effects command
    if args.target == 'effects':
        print("Available effects:")
        print("  Waveform: pulse, breathe, strobe, saw, triangle")
        print("  Color:    rainbow, disco, party, police")
        print("  Ambient:  candle, relax, sunrise, sunset")
        print("  Matrix:   matrix_rainbow, matrix_wave, matrix_flame,")
        print("            matrix_morph, matrix_sky (for Ceiling/Tile devices)")
        return 0
    
    # All other commands need device discovery
    devices = controller.discover()
    if not devices:
        print("No devices found.", file=sys.stderr)
        return 1
    
    # Determine target devices
    if args.target.lower() == 'all':
        targets = controller.get_all_devices()
    else:
        device = controller.find_device(args.target)
        if not device:
            print(f"Device '{args.target}' not found.", file=sys.stderr)
            print("Available devices:")
            for d in devices:
                name = d.label or d.serial[:12]
                print(f"  {name}")
            return 1
        targets = [device]
    
    # Handle commands
    command = (args.command or '').lower()
    
    if command == 'on':
        for device in targets:
            controller.set_power(device, True, args.duration)
            print(f"Turned on: {device.label or device.serial}")
    
    elif command == 'off':
        for device in targets:
            controller.set_power(device, False, args.duration)
            print(f"Turned off: {device.label or device.serial}")
    
    elif command == 'color':
        if not args.args:
            print("Usage: lifx <device> color <preset|#hex>", file=sys.stderr)
            print(f"Presets: {', '.join(PRESETS.keys())}")
            return 1
        
        color_arg = args.args[0].lower()
        
        if color_arg.startswith('#'):
            # Hex color
            hsbk = HSBK.from_hex(color_arg)
        elif color_arg in PRESETS:
            h, s, b, k = PRESETS[color_arg]
            hsbk = HSBK.from_degrees(h, s / 100, b / 100, k)
        else:
            print(f"Unknown color: {color_arg}", file=sys.stderr)
            print(f"Presets: {', '.join(PRESETS.keys())}")
            return 1
        
        for device in targets:
            controller.set_color(device, hsbk, args.duration)
            print(f"Set color on: {device.label or device.serial}")
    
    elif command == 'hsb':
        if len(args.args) < 3:
            print("Usage: lifx <device> hsb <hue> <sat> <bright> [kelvin]", file=sys.stderr)
            print("  hue: 0-360, sat: 0-100, bright: 0-100, kelvin: 1500-9000")
            return 1
        
        h = float(args.args[0])
        s = float(args.args[1])
        b = float(args.args[2])
        k = int(args.args[3]) if len(args.args) > 3 else 3500
        
        hsbk = HSBK.from_degrees(h, s / 100, b / 100, k)
        
        for device in targets:
            controller.set_color(device, hsbk, args.duration)
            print(f"Set HSB on: {device.label or device.serial}")
    
    elif command == 'kelvin' or command == 'white':
        if not args.args:
            print("Usage: lifx <device> kelvin <temp> [brightness]", file=sys.stderr)
            print("  temp: 1500-9000, brightness: 0-100")
            return 1
        
        k = int(args.args[0])
        b = float(args.args[1]) if len(args.args) > 1 else 100
        
        hsbk = HSBK.from_degrees(0, 0, b / 100, k)
        
        for device in targets:
            controller.set_color(device, hsbk, args.duration)
            print(f"Set white on: {device.label or device.serial}")
    
    elif command == 'effect':
        if not args.args:
            print("Usage: lifx <device> effect <name>", file=sys.stderr)
            print(f"Effects: {', '.join(list_effects())}")
            return 1
        
        effect_name = args.args[0].lower()
        cycles = 0 if args.loop else args.cycles
        
        for device in targets:
            brightness = device.brightness / 65535 if device.brightness else 1.0
            success = run_effect(
                device, effect_name,
                period=args.period,
                cycles=cycles,
                brightness=brightness
            )
            if success:
                loop_str = " (looping)" if args.loop else ""
                print(f"Running {effect_name}{loop_str} on: {device.label or device.serial}")
            else:
                print(f"Unknown effect: {effect_name}", file=sys.stderr)
                print(f"Effects: {', '.join(list_effects())}")
                return 1
    
    elif command == 'stop':
        for device in targets:
            stop_effect(device)
            # Restore to current color
            hsbk = HSBK(
                hue=device.hue,
                saturation=device.saturation,
                brightness=device.brightness,
                kelvin=device.kelvin
            )
            controller.set_color(device, hsbk, 0)
            print(f"Stopped effect on: {device.label or device.serial}")
    
    elif command == '' or command is None:
        # Just show status for the device
        for device in targets:
            print_device_status(device)
    
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print("Commands: on, off, color, hsb, kelvin, effect, stop")
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
