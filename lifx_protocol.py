#!/usr/bin/env python3
"""
LIFX LAN Protocol Library

Shared protocol implementation for LIFX device communication.
Provides constants, data structures, and packet handling functions.

Protocol documentation: https://lan.developer.lifx.com/docs/packet-contents
"""

import colorsys
import ipaddress
import random
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


# =============================================================================
# Protocol Constants
# =============================================================================

LIFX_PORT = 56700
PROTOCOL_NUMBER = 1024


# =============================================================================
# Message Types
# =============================================================================

# Discovery
GETSERVICE_TYPE = 2
STATESERVICE_TYPE = 3

# Device
GETPOWER_TYPE = 20
SETPOWER_TYPE = 21
STATEPOWER_TYPE = 22
GETLABEL_TYPE = 23
SETLABEL_TYPE = 24
STATELABEL_TYPE = 25

# Device Info
GETHOSTFIRMWARE_TYPE = 14
STATEHOSTFIRMWARE_TYPE = 15
GETWIFIINFO_TYPE = 16
STATEWIFIINFO_TYPE = 17
GETVERSION_TYPE = 32
STATEVERSION_TYPE = 33
GETINFO_TYPE = 34
STATEINFO_TYPE = 35
GETLOCATION_TYPE = 48
STATELOCATION_TYPE = 50
GETGROUP_TYPE = 51
STATEGROUP_TYPE = 53

# Light
GETCOLOR_TYPE = 101
SETCOLOR_TYPE = 102
SETWAVEFORM_TYPE = 103
LIGHTSTATE_TYPE = 107
GETLIGHTPOWER_TYPE = 116
SETLIGHTPOWER_TYPE = 117
STATELIGHTPOWER_TYPE = 118
SETWAVEFORMOPTIONAL_TYPE = 119

# Light (Infrared)
GETINFRARED_TYPE = 120
STATEINFRARED_TYPE = 121

# MultiZone
GETCOLORZONES_TYPE = 502
STATEZONE_TYPE = 503
STATEMULTIZONE_TYPE = 506
GETMULTIZONEEFFECT_TYPE = 507
STATEMULTIZONEEFFECT_TYPE = 509
GETEXTENDEDCOLORZONES_TYPE = 511
STATEEXTENDEDCOLORZONES_TYPE = 512

# Tile/Matrix
GETDEVICECHAIN_TYPE = 701
STATEDEVICECHAIN_TYPE = 702
GET64_TYPE = 707
SET64_TYPE = 715
STATE64_TYPE = 711
GETTILEEFFECT_TYPE = 718
SETTILEEFFECT_TYPE = 719
STATETILEEFFECT_TYPE = 720

# Acknowledgement
ACKNOWLEDGEMENT_TYPE = 45


# =============================================================================
# Service Types
# =============================================================================

SERVICE_UDP = 1
SERVICE_RESERVED1 = 2
SERVICE_RESERVED2 = 3
SERVICE_RESERVED3 = 4
SERVICE_RESERVED4 = 5


# =============================================================================
# Enums
# =============================================================================

class Waveform(IntEnum):
    """Waveform types for SetWaveform commands."""
    SAW = 0
    SINE = 1
    HALF_SINE = 2
    TRIANGLE = 3
    PULSE = 4


# =============================================================================
# Named Colors
# =============================================================================

# Named colors (hue in degrees 0-360, saturation 0-1, brightness 0-1)
NAMED_COLORS = {
    'red': (0, 1.0, 1.0),
    'orange': (30, 1.0, 1.0),
    'yellow': (60, 1.0, 1.0),
    'lime': (90, 1.0, 1.0),
    'green': (120, 1.0, 1.0),
    'teal': (150, 1.0, 1.0),
    'cyan': (180, 1.0, 1.0),
    'sky': (210, 1.0, 1.0),
    'blue': (240, 1.0, 1.0),
    'purple': (270, 1.0, 1.0),
    'magenta': (300, 1.0, 1.0),
    'pink': (330, 1.0, 1.0),
    'white': (0, 0.0, 1.0),
    'warm_white': (0, 0.0, 1.0),  # Use kelvin 2700
    'cool_white': (0, 0.0, 1.0),  # Use kelvin 6500
}


# =============================================================================
# Product Registry
# =============================================================================

# Product data from https://github.com/LIFX/products/blob/master/products.json
LIFX_PRODUCTS = {
    1: {"name": "LIFX Original 1000", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    3: {"name": "LIFX Color 650", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    10: {"name": "LIFX White 800 (Low Voltage)", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2700, 6500]}},
    11: {"name": "LIFX White 800 (High Voltage)", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2700, 6500]}},
    15: {"name": "LIFX Color 1000", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    18: {"name": "LIFX White 900 BR30 (Low Voltage)", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    19: {"name": "LIFX White 900 BR30 (High Voltage)", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    20: {"name": "LIFX Color 1000 BR30", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    22: {"name": "LIFX Color 1000", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    27: {"name": "LIFX A19", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    28: {"name": "LIFX BR30", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    29: {"name": "LIFX A19 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    30: {"name": "LIFX BR30 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    31: {"name": "LIFX Z", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": True, "hev": False, "temperature_range": [2500, 9000]}},
    32: {"name": "LIFX Z", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": True, "hev": False, "temperature_range": [2500, 9000]}},
    36: {"name": "LIFX Downlight", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    37: {"name": "LIFX Downlight", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    38: {"name": "LIFX Beam", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": True, "hev": False, "temperature_range": [2500, 9000]}},
    39: {"name": "LIFX Downlight White to Warm", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    40: {"name": "LIFX Downlight", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    43: {"name": "LIFX A19", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    44: {"name": "LIFX BR30", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    45: {"name": "LIFX A19 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    46: {"name": "LIFX BR30 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    49: {"name": "LIFX Mini Color", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    50: {"name": "LIFX Mini White to Warm", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    51: {"name": "LIFX Mini White", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2700, 2700]}},
    52: {"name": "LIFX GU10", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    53: {"name": "LIFX GU10", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    55: {"name": "LIFX Tile", "features": {"color": True, "chain": True, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    57: {"name": "LIFX Candle", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    59: {"name": "LIFX Mini Color", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    60: {"name": "LIFX Mini White to Warm", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    61: {"name": "LIFX Mini White", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2700, 2700]}},
    62: {"name": "LIFX A19", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    63: {"name": "LIFX BR30", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    64: {"name": "LIFX A19 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    65: {"name": "LIFX BR30 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    66: {"name": "LIFX Mini White", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2700, 2700]}},
    68: {"name": "LIFX Candle", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    70: {"name": "LIFX Switch", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "buttons": True, "relays": True}},
    71: {"name": "LIFX Switch", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "buttons": True, "relays": True}},
    81: {"name": "LIFX Candle White to Warm", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 6500]}},
    82: {"name": "LIFX Filament Clear", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2100, 2100]}},
    85: {"name": "LIFX Filament Amber", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2000, 2000]}},
    87: {"name": "LIFX Mini White", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2700, 2700]}},
    88: {"name": "LIFX Mini White", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2700, 2700]}},
    89: {"name": "LIFX Switch", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "buttons": True, "relays": True}},
    90: {"name": "LIFX Clean", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": True, "temperature_range": [2500, 9000]}},
    91: {"name": "LIFX Color", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    92: {"name": "LIFX Color", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    93: {"name": "LIFX A19 Night Vision Intl", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    94: {"name": "LIFX BR30 Night Vision Intl", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    96: {"name": "LIFX A19 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    97: {"name": "LIFX BR30 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    98: {"name": "LIFX Mini White to Warm", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    99: {"name": "LIFX Mini White to Warm", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    100: {"name": "LIFX Candle Color", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    101: {"name": "LIFX A19 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    102: {"name": "LIFX BR30 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    109: {"name": "LIFX A19 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    110: {"name": "LIFX BR30 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    111: {"name": "LIFX A19 Night Vision", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    112: {"name": "LIFX BR30 Night Vision Intl", "features": {"color": True, "chain": False, "matrix": False, "infrared": True, "multizone": False, "hev": False, "temperature_range": [2500, 9000]}},
    113: {"name": "LIFX Mini White to Warm", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    114: {"name": "LIFX Mini White to Warm", "features": {"color": False, "chain": False, "matrix": False, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    115: {"name": "LIFX String", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": True, "extended_multizone": True, "hev": False, "temperature_range": [1500, 9000]}},
    116: {"name": "LIFX String", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": True, "extended_multizone": True, "hev": False, "temperature_range": [1500, 9000]}},
    117: {"name": "LIFX String", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": True, "extended_multizone": True, "hev": False, "temperature_range": [1500, 9000]}},
    118: {"name": "LIFX String", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": True, "extended_multizone": True, "hev": False, "temperature_range": [1500, 9000]}},
    119: {"name": "LIFX Neon", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": True, "extended_multizone": True, "hev": False, "temperature_range": [1500, 9000]}},
    120: {"name": "LIFX Neon", "features": {"color": True, "chain": False, "matrix": False, "infrared": False, "multizone": True, "extended_multizone": True, "hev": False, "temperature_range": [1500, 9000]}},
    137: {"name": "LIFX Candle Color US", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    138: {"name": "LIFX Candle Colour Intl", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    171: {"name": "LIFX Round Spot US", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    173: {"name": "LIFX Round Path US", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    174: {"name": "LIFX Square Path US", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    176: {"name": "LIFX Ceiling US", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    177: {"name": "LIFX Ceiling Intl", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    201: {"name": "LIFX Ceiling 13x26\" US", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    202: {"name": "LIFX Ceiling 13x26\" Intl", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    217: {"name": "LIFX Tube US", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    218: {"name": "LIFX Tube Intl", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "temperature_range": [1500, 9000]}},
    219: {"name": "LIFX Luna US", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "buttons": True, "temperature_range": [1500, 9000]}},
    220: {"name": "LIFX Luna Intl", "features": {"color": True, "chain": False, "matrix": True, "infrared": False, "multizone": False, "hev": False, "buttons": True, "temperature_range": [1500, 9000]}},
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LIFXDevice:
    """Represents a discovered LIFX device."""
    ip_address: str
    port: int
    serial: str
    service: int
    label: str = ""
    power: int = 0
    hue: int = 0
    saturation: int = 0
    brightness: int = 0
    kelvin: int = 3500
    
    def __str__(self) -> str:
        if self.label:
            name = self.label
            power_str = "ON" if self.power else "OFF"
            return f"{name} ({self.ip_address}) - {power_str}"
        else:
            service_name = "UDP" if self.service == SERVICE_UDP else f"Unknown({self.service})"
            return f"Device: {self.serial} @ {self.ip_address}:{self.port} (Service: {service_name})"
    
    @property
    def target_bytes(self) -> bytes:
        """Convert serial to target bytes for addressing."""
        parts = self.serial.split(':')
        target = bytes(int(p, 16) for p in parts) + b'\x00\x00'
        return target


@dataclass
class HSBK:
    """HSBK color representation."""
    hue: int = 0           # 0-65535 (maps to 0-360 degrees)
    saturation: int = 0    # 0-65535 (maps to 0-100%)
    brightness: int = 65535  # 0-65535 (maps to 0-100%)
    kelvin: int = 3500     # 1500-9000
    
    @classmethod
    def from_degrees(cls, hue: float, saturation: float, brightness: float, kelvin: int = 3500) -> 'HSBK':
        """Create HSBK from human-readable values (hue: 0-360, sat/bright: 0-1)."""
        return cls(
            hue=int(round(0x10000 * hue / 360)) % 0x10000,
            saturation=int(round(0xFFFF * saturation)),
            brightness=int(round(0xFFFF * brightness)),
            kelvin=kelvin
        )
    
    @classmethod
    def from_rgb(cls, r: int, g: int, b: int, kelvin: int = 3500) -> 'HSBK':
        """Create HSBK from RGB values (0-255)."""
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        return cls.from_degrees(h * 360, s, v, kelvin)
    
    @classmethod
    def from_hex(cls, hex_color: str, kelvin: int = 3500) -> 'HSBK':
        """Create HSBK from hex color string (#RRGGBB or RRGGBB)."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return cls.from_rgb(r, g, b, kelvin)
    
    def to_bytes(self) -> bytes:
        """Pack HSBK to bytes."""
        return struct.pack('<HHHH', self.hue, self.saturation, self.brightness, self.kelvin)


# =============================================================================
# Utility Functions
# =============================================================================

def get_broadcast_address(subnet: str) -> str:
    """Calculate the broadcast address for a given subnet."""
    network = ipaddress.ip_network(subnet, strict=False)
    return str(network.broadcast_address)


def generate_source_id() -> int:
    """Generate random source identifier (avoid 0 and 1 per LIFX docs)."""
    return random.randint(2, 0xFFFFFFFF)


# =============================================================================
# Packet Creation Functions
# =============================================================================

def create_lifx_header(
    message_type: int,
    source: int,
    target: bytes = b'\x00' * 8,
    tagged: bool = False,
    ack_required: bool = False,
    res_required: bool = False,
    sequence: int = 0,
    payload_size: int = 0
) -> bytes:
    """
    Create a LIFX protocol header.
    
    Header structure (36 bytes total):
    - Frame Header (8 bytes)
    - Frame Address (16 bytes)
    - Protocol Header (12 bytes)
    
    All values are little-endian.
    
    Args:
        message_type: Packet type number
        source: Unique client identifier
        target: 8-byte target address (all zeros for broadcast)
        tagged: True for broadcast messages
        ack_required: Request acknowledgement
        res_required: Request response
        sequence: Sequence number (0-255)
        payload_size: Size of payload in bytes
    
    Returns:
        36-byte header as bytes
    """
    # Calculate total message size (header + payload)
    size = 36 + payload_size
    
    # Frame Header (8 bytes)
    # Bytes 0-1: size (uint16)
    # Byte 2: protocol (lower 8 bits)
    # Byte 3: protocol (upper 4 bits) | addressable (bit 4) | tagged (bit 5) | origin (bits 6-7)
    # Bytes 4-7: source (uint32)
    
    protocol_and_flags = PROTOCOL_NUMBER  # 12 bits for protocol
    protocol_and_flags |= (1 << 12)  # addressable = 1 (bit 12)
    if tagged:
        protocol_and_flags |= (1 << 13)  # tagged (bit 13)
    # origin = 0 (bits 14-15)
    
    frame_header = struct.pack('<HHI', size, protocol_and_flags, source)
    
    # Frame Address (16 bytes)
    # Bytes 8-15: target (8 bytes)
    # Bytes 16-21: reserved (6 bytes)
    # Byte 22: res_required (bit 0) | ack_required (bit 1) | reserved (bits 2-7)
    # Byte 23: sequence (uint8)
    
    reserved6 = b'\x00' * 6
    flags_byte = 0
    if res_required:
        flags_byte |= 0x01
    if ack_required:
        flags_byte |= 0x02
    
    frame_address = target + reserved6 + struct.pack('<BB', flags_byte, sequence)
    
    # Protocol Header (12 bytes)
    # Bytes 24-31: reserved (8 bytes)
    # Bytes 32-33: type (uint16)
    # Bytes 34-35: reserved (2 bytes)
    
    protocol_header = struct.pack('<QHBB', 0, message_type, 0, 0)
    
    return frame_header + frame_address + protocol_header


def create_getservice_packet(source: int, sequence: int = 0) -> bytes:
    """Create GetService (packet 2) for discovery."""
    return create_lifx_header(
        message_type=GETSERVICE_TYPE,
        source=source,
        target=b'\x00' * 8,
        tagged=True,
        sequence=sequence
    )


def create_getlabel_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetLabel (packet 23) to get device label."""
    return create_lifx_header(
        message_type=GETLABEL_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


def create_getcolor_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetColor (packet 101) to get device color state."""
    return create_lifx_header(
        message_type=GETCOLOR_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


def create_setpower_packet(source: int, target: bytes, level: int, 
                           sequence: int = 0, ack_required: bool = True) -> bytes:
    """
    Create SetPower (packet 21) to turn device on/off.
    
    Args:
        level: 0 = off, 65535 = on
    """
    payload = struct.pack('<H', level)
    header = create_lifx_header(
        message_type=SETPOWER_TYPE,
        source=source,
        target=target,
        ack_required=ack_required,
        sequence=sequence,
        payload_size=len(payload)
    )
    return header + payload


def create_setlightpower_packet(source: int, target: bytes, level: int, duration: int = 0,
                                 sequence: int = 0, ack_required: bool = True) -> bytes:
    """
    Create SetLightPower (packet 117) with duration.
    
    Args:
        level: 0 = off, 65535 = on
        duration: Transition time in milliseconds
    """
    payload = struct.pack('<HI', level, duration)
    header = create_lifx_header(
        message_type=SETLIGHTPOWER_TYPE,
        source=source,
        target=target,
        ack_required=ack_required,
        sequence=sequence,
        payload_size=len(payload)
    )
    return header + payload


def create_setcolor_packet(source: int, target: bytes, hsbk: HSBK, duration: int = 0,
                           sequence: int = 0, ack_required: bool = True) -> bytes:
    """
    Create SetColor (packet 102) to set device color.
    
    Args:
        hsbk: Target color
        duration: Transition time in milliseconds
    """
    payload = struct.pack('<B', 0) + hsbk.to_bytes() + struct.pack('<I', duration)
    header = create_lifx_header(
        message_type=SETCOLOR_TYPE,
        source=source,
        target=target,
        ack_required=ack_required,
        sequence=sequence,
        payload_size=len(payload)
    )
    return header + payload


def create_setwaveform_packet(
    source: int,
    target: bytes,
    hsbk: HSBK,
    transient: bool = True,
    period: int = 1000,
    cycles: float = 5.0,
    skew_ratio: int = 0,
    waveform: Waveform = Waveform.SINE,
    sequence: int = 0,
    ack_required: bool = True
) -> bytes:
    """
    Create SetWaveform (packet 103) for waveform effects.
    
    Args:
        hsbk: Target color for effect
        transient: Return to original color after effect
        period: Time for one cycle in milliseconds
        cycles: Number of cycles (use float for partial)
        skew_ratio: Duty cycle for PULSE (-32768 to 32767, 0 = 50%)
        waveform: Effect type (SAW, SINE, HALF_SINE, TRIANGLE, PULSE)
    """
    payload = struct.pack(
        '<BBHHHHIfhB',
        0,                  # reserved
        1 if transient else 0,
        hsbk.hue,
        hsbk.saturation,
        hsbk.brightness,
        hsbk.kelvin,
        period,
        cycles,
        skew_ratio,
        waveform.value if hasattr(waveform, 'value') else waveform
    )
    header = create_lifx_header(
        message_type=SETWAVEFORM_TYPE,
        source=source,
        target=target,
        ack_required=ack_required,
        sequence=sequence,
        payload_size=len(payload)
    )
    return header + payload


# Device Info Query Packets

def create_getversion_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetVersion (packet 32) to get device version info."""
    return create_lifx_header(
        message_type=GETVERSION_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


def create_gethostfirmware_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetHostFirmware (packet 14) to get firmware version."""
    return create_lifx_header(
        message_type=GETHOSTFIRMWARE_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


def create_getwifiinfo_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetWifiInfo (packet 16) to get WiFi signal strength."""
    return create_lifx_header(
        message_type=GETWIFIINFO_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


def create_getinfo_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetInfo (packet 34) to get device runtime info."""
    return create_lifx_header(
        message_type=GETINFO_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


def create_getlocation_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetLocation (packet 48) to get device location."""
    return create_lifx_header(
        message_type=GETLOCATION_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


def create_getgroup_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetGroup (packet 51) to get device group."""
    return create_lifx_header(
        message_type=GETGROUP_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


def create_getinfrared_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetInfrared (packet 120) to get infrared brightness level."""
    return create_lifx_header(
        message_type=GETINFRARED_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


def create_getcolorzones_packet(source: int, target: bytes, start_index: int = 0, 
                                 end_index: int = 255, sequence: int = 0) -> bytes:
    """
    Create GetColorZones (packet 502) to get multizone colors.
    
    Args:
        start_index: First zone to get (0-255)
        end_index: Last zone to get (0-255, use 255 to get all)
    """
    payload = struct.pack('<BB', start_index, end_index)
    header = create_lifx_header(
        message_type=GETCOLORZONES_TYPE,
        source=source,
        target=target,
        sequence=sequence,
        payload_size=len(payload)
    )
    return header + payload


def create_getextendedcolorzones_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetExtendedColorZones (packet 511) to get all zone colors at once."""
    return create_lifx_header(
        message_type=GETEXTENDEDCOLORZONES_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


def create_getmultizoneeffect_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetMultiZoneEffect (packet 507) to get current firmware effect."""
    return create_lifx_header(
        message_type=GETMULTIZONEEFFECT_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


# =============================================================================
# Packet Parsing Functions
# =============================================================================

def parse_lifx_header(data: bytes) -> Optional[dict]:
    """
    Parse a LIFX protocol header from received data.
    
    Returns a dictionary with header fields, or None if parsing fails.
    """
    if len(data) < 36:
        return None
    
    try:
        # Frame Header
        size, protocol_flags, source = struct.unpack('<HHI', data[0:8])
        
        protocol = protocol_flags & 0x0FFF
        addressable = (protocol_flags >> 12) & 0x01
        tagged = (protocol_flags >> 13) & 0x01
        origin = (protocol_flags >> 14) & 0x03
        
        # Frame Address
        target = data[8:16]
        reserved = data[16:22]
        flags_byte = data[22]
        sequence = data[23]
        
        res_required = flags_byte & 0x01
        ack_required = (flags_byte >> 1) & 0x01
        
        # Protocol Header
        reserved64, message_type, reserved16a, reserved16b = struct.unpack('<QHBB', data[24:36])
        
        # Extract serial number from target (first 6 bytes)
        serial = ':'.join(f'{b:02x}' for b in target[0:6])
        
        return {
            'size': size,
            'protocol': protocol,
            'addressable': addressable,
            'tagged': tagged,
            'origin': origin,
            'source': source,
            'target': target,
            'serial': serial,
            'res_required': res_required,
            'ack_required': ack_required,
            'sequence': sequence,
            'type': message_type,
            'payload': data[36:size] if size > 36 else b''
        }
    except struct.error:
        return None


def parse_state_service(payload: bytes) -> Optional[tuple]:
    """Parse StateService (packet 3) payload."""
    if len(payload) < 5:
        return None
    try:
        service, port = struct.unpack('<BI', payload[0:5])
        return service, port
    except struct.error:
        return None


def parse_state_label(payload: bytes) -> Optional[str]:
    """Parse StateLabel (packet 25) payload."""
    if len(payload) < 32:
        return None
    try:
        label = payload[0:32].rstrip(b'\x00').decode('utf-8', errors='replace')
        return label
    except:
        return None


def parse_light_state(payload: bytes) -> Optional[dict]:
    """Parse LightState (packet 107) payload."""
    if len(payload) < 52:
        return None
    try:
        hue, saturation, brightness, kelvin = struct.unpack('<HHHH', payload[0:8])
        # Skip reserved (2 bytes)
        power = struct.unpack('<H', payload[10:12])[0]
        label = payload[12:44].rstrip(b'\x00').decode('utf-8', errors='replace')
        return {
            'hue': hue,
            'saturation': saturation,
            'brightness': brightness,
            'kelvin': kelvin,
            'power': power,
            'label': label
        }
    except struct.error:
        return None


def parse_state_version(payload: bytes) -> Optional[dict]:
    """Parse StateVersion (packet 33) payload."""
    if len(payload) < 12:
        return None
    try:
        vendor, product = struct.unpack('<II', payload[0:8])
        return {
            'vendor': vendor,
            'product': product
        }
    except struct.error:
        return None


def parse_state_hostfirmware(payload: bytes) -> Optional[dict]:
    """Parse StateHostFirmware (packet 15) payload."""
    if len(payload) < 20:
        return None
    try:
        build = struct.unpack('<Q', payload[0:8])[0]
        version_minor, version_major = struct.unpack('<HH', payload[16:20])
        return {
            'build': build,
            'version_major': version_major,
            'version_minor': version_minor
        }
    except struct.error:
        return None


def parse_state_wifiinfo(payload: bytes) -> Optional[dict]:
    """Parse StateWifiInfo (packet 17) payload."""
    if len(payload) < 14:
        return None
    try:
        signal = struct.unpack('<f', payload[0:4])[0]
        return {
            'signal': signal
        }
    except struct.error:
        return None


def parse_state_info(payload: bytes) -> Optional[dict]:
    """Parse StateInfo (packet 35) payload."""
    if len(payload) < 24:
        return None
    try:
        time_ns, uptime_ns, downtime_ns = struct.unpack('<QQQ', payload[0:24])
        return {
            'time': time_ns,
            'uptime': uptime_ns,
            'downtime': downtime_ns
        }
    except struct.error:
        return None


def parse_state_location(payload: bytes) -> Optional[dict]:
    """Parse StateLocation (packet 50) payload."""
    if len(payload) < 56:
        return None
    try:
        location_id = payload[0:16]
        label = payload[16:48].rstrip(b'\x00').decode('utf-8', errors='replace')
        updated_at = struct.unpack('<Q', payload[48:56])[0]
        return {
            'location_id': location_id.hex(),
            'label': label,
            'updated_at': updated_at
        }
    except struct.error:
        return None


def parse_state_group(payload: bytes) -> Optional[dict]:
    """Parse StateGroup (packet 53) payload."""
    if len(payload) < 56:
        return None
    try:
        group_id = payload[0:16]
        label = payload[16:48].rstrip(b'\x00').decode('utf-8', errors='replace')
        updated_at = struct.unpack('<Q', payload[48:56])[0]
        return {
            'group_id': group_id.hex(),
            'label': label,
            'updated_at': updated_at
        }
    except struct.error:
        return None


def parse_state_infrared(payload: bytes) -> Optional[dict]:
    """Parse StateInfrared (packet 121) payload."""
    if len(payload) < 2:
        return None
    try:
        brightness = struct.unpack('<H', payload[0:2])[0]
        return {
            'brightness': brightness
        }
    except struct.error:
        return None


def parse_state_zone(payload: bytes) -> Optional[dict]:
    """Parse StateZone (packet 503) payload - single zone response."""
    if len(payload) < 10:
        return None
    try:
        zones_count, zone_index = struct.unpack('<BB', payload[0:2])
        hue, saturation, brightness, kelvin = struct.unpack('<HHHH', payload[2:10])
        return {
            'zones_count': zones_count,
            'zone_index': zone_index,
            'zones': [{
                'index': zone_index,
                'hue': hue,
                'saturation': saturation,
                'brightness': brightness,
                'kelvin': kelvin
            }]
        }
    except struct.error:
        return None


def parse_state_multizone(payload: bytes) -> Optional[dict]:
    """Parse StateMultiZone (packet 506) payload - 8 zones per packet."""
    if len(payload) < 66:
        return None
    try:
        zones_count, zone_index = struct.unpack('<BB', payload[0:2])
        zones = []
        for i in range(8):
            offset = 2 + i * 8
            if offset + 8 > len(payload):
                break
            hue, sat, bright, kelvin = struct.unpack('<HHHH', payload[offset:offset+8])
            zones.append({
                'index': zone_index + i,
                'hue': hue,
                'saturation': sat,
                'brightness': bright,
                'kelvin': kelvin
            })
        return {
            'zones_count': zones_count,
            'zone_index': zone_index,
            'zones': zones
        }
    except struct.error:
        return None


def parse_state_extended_color_zones(payload: bytes) -> Optional[dict]:
    """Parse StateExtendedColorZones (packet 512) payload - up to 82 zones."""
    if len(payload) < 5:
        return None
    try:
        zones_count, zone_index = struct.unpack('<HH', payload[0:4])
        colors_count = payload[4]
        zones = []
        for i in range(min(colors_count, 82)):
            offset = 5 + i * 8
            if offset + 8 > len(payload):
                break
            hue, sat, bright, kelvin = struct.unpack('<HHHH', payload[offset:offset+8])
            zones.append({
                'index': zone_index + i,
                'hue': hue,
                'saturation': sat,
                'brightness': bright,
                'kelvin': kelvin
            })
        return {
            'zones_count': zones_count,
            'zone_index': zone_index,
            'colors_count': colors_count,
            'zones': zones
        }
    except struct.error:
        return None


def parse_state_multizone_effect(payload: bytes) -> Optional[dict]:
    """Parse StateMultiZoneEffect (packet 509) payload."""
    if len(payload) < 59:
        return None
    try:
        instanceid = struct.unpack('<I', payload[0:4])[0]
        effect_type = payload[4]
        speed = struct.unpack('<I', payload[7:11])[0]
        duration = struct.unpack('<Q', payload[11:19])[0]
        
        effect_names = {
            0: 'OFF',
            1: 'MOVE'
        }
        
        return {
            'instanceid': instanceid,
            'type': effect_type,
            'type_name': effect_names.get(effect_type, f'UNKNOWN({effect_type})'),
            'speed': speed,
            'duration': duration
        }
    except struct.error:
        return None


# =============================================================================
# Tile/Matrix Functions
# =============================================================================

def create_getdevicechain_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetDeviceChain (packet 701) to get tile chain information."""
    return create_lifx_header(
        message_type=GETDEVICECHAIN_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


def create_get64_packet(source: int, target: bytes, tile_index: int = 0, 
                        length: int = 1, x: int = 0, y: int = 0, width: int = 8,
                        sequence: int = 0) -> bytes:
    """
    Create Get64 (packet 707) to get 64 pixel colors from a tile.
    
    Args:
        tile_index: Index of the tile in the chain (0-15)
        length: Number of tiles to query (1-16)
        x: Starting x coordinate (0-7)
        y: Starting y coordinate (0-7) 
        width: Width of the area to read (1-8)
    """
    payload = struct.pack('<BBBBBB', tile_index, length, 0, x, y, width)
    header = create_lifx_header(
        message_type=GET64_TYPE,
        source=source,
        target=target,
        sequence=sequence,
        payload_size=len(payload)
    )
    return header + payload


def create_set64_packet(source: int, target: bytes, colors: list,
                        tile_index: int = 0, length: int = 1, 
                        x: int = 0, y: int = 0, width: int = 8,
                        duration: int = 0, sequence: int = 0,
                        ack_required: bool = False) -> bytes:
    """
    Create Set64 (packet 715) to set 64 pixel colors on a tile.
    
    Args:
        colors: List of 64 HSBK tuples/objects [(h,s,b,k), ...] or [HSBK, ...]
        tile_index: Index of the tile in the chain (0-15)
        length: Number of tiles to set (usually 1)
        x: Starting x coordinate (0-7)
        y: Starting y coordinate (0-7)
        width: Width of the pixel area (1-8)
        duration: Transition time in milliseconds
    """
    # Pack colors - need exactly 64 HSBK values
    colors_data = b''
    for i in range(64):
        if i < len(colors):
            c = colors[i]
            if hasattr(c, 'to_bytes'):
                colors_data += c.to_bytes()
            elif isinstance(c, (tuple, list)):
                colors_data += struct.pack('<HHHH', c[0], c[1], c[2], c[3])
            else:
                colors_data += struct.pack('<HHHH', 0, 0, 0, 3500)  # default
        else:
            colors_data += struct.pack('<HHHH', 0, 0, 0, 3500)  # pad with black
    
    payload = struct.pack('<BBBBBBI', tile_index, length, 0, x, y, width, duration) + colors_data
    header = create_lifx_header(
        message_type=SET64_TYPE,
        source=source,
        target=target,
        ack_required=ack_required,
        sequence=sequence,
        payload_size=len(payload)
    )
    return header + payload


def create_gettileeffect_packet(source: int, target: bytes, sequence: int = 0) -> bytes:
    """Create GetTileEffect (packet 718) to get current tile firmware effect."""
    return create_lifx_header(
        message_type=GETTILEEFFECT_TYPE,
        source=source,
        target=target,
        sequence=sequence
    )


class TileEffect(IntEnum):
    """Tile effect types for firmware-controlled effects."""
    OFF = 0
    RESERVED1 = 1
    MORPH = 2
    FLAME = 3
    RESERVED2 = 4
    SKY = 5


def create_settileeffect_packet(
    source: int,
    target: bytes,
    effect: TileEffect = TileEffect.OFF,
    speed: int = 3000,
    duration: int = 0,
    sky_type: int = 0,
    cloud_saturation_min: int = 0,
    cloud_saturation_max: int = 0,
    palette: list = None,
    sequence: int = 0,
    ack_required: bool = False
) -> bytes:
    """
    Create SetTileEffect (packet 719) for firmware-controlled tile effects.
    
    Args:
        effect: Effect type (OFF, MORPH, FLAME, SKY)
        speed: Effect speed in milliseconds (3000-10000 typical)
        duration: Effect duration in nanoseconds (0 = infinite)
        sky_type: For SKY effect (0=sunrise, 1=sunset, 2=clouds)
        palette: List of up to 16 HSBK colors for MORPH effect
    """
    instanceid = random.randint(1, 0xFFFFFFFF)
    
    # Build palette (16 colors max, 8 bytes each = 128 bytes)
    palette_data = b''
    if palette:
        for i in range(16):
            if i < len(palette):
                c = palette[i]
                if hasattr(c, 'to_bytes'):
                    palette_data += c.to_bytes()
                elif isinstance(c, (tuple, list)):
                    palette_data += struct.pack('<HHHH', c[0], c[1], c[2], c[3])
                else:
                    palette_data += struct.pack('<HHHH', 0, 0, 0, 0)
            else:
                palette_data += struct.pack('<HHHH', 0, 0, 0, 0)
    else:
        palette_data = b'\x00' * 128
    
    palette_count = min(len(palette), 16) if palette else 0
    
    # Payload structure:
    # reserved(1), reserved(1), instanceid(4), type(1), speed(4), duration(8),
    # reserved(4), reserved(4), parameters[32], palette_count(1), palette[16*8]
    # Total: 1+1+4+1+4+8+4+4+32+1+128 = 188 bytes
    
    # Parameters for SKY effect
    parameters = struct.pack('<BBBH', sky_type, 0, cloud_saturation_min, cloud_saturation_max)
    parameters += b'\x00' * (32 - len(parameters))  # Pad to 32 bytes
    
    payload = struct.pack(
        '<BBIBIQ',
        0,  # reserved
        0,  # reserved  
        instanceid,
        effect.value if hasattr(effect, 'value') else effect,
        speed,
        duration
    )
    payload += struct.pack('<II', 0, 0)  # reserved
    payload += parameters
    payload += struct.pack('<B', palette_count)
    payload += palette_data
    
    header = create_lifx_header(
        message_type=SETTILEEFFECT_TYPE,
        source=source,
        target=target,
        ack_required=ack_required,
        sequence=sequence,
        payload_size=len(payload)
    )
    return header + payload


def parse_state_device_chain(payload: bytes) -> Optional[dict]:
    """Parse StateDeviceChain (packet 702) payload - tile chain information."""
    if len(payload) < 882:  # 1 + (55 * 16) + 1 = 882 bytes minimum
        return None
    try:
        start_index = payload[0]
        
        # Parse up to 16 tile_device structures (55 bytes each)
        tiles = []
        for i in range(16):
            offset = 1 + i * 55
            if offset + 55 > len(payload):
                break
            
            tile_data = payload[offset:offset+55]
            accel_x, accel_y, accel_z = struct.unpack('<hhh', tile_data[0:6])
            # reserved(2)
            user_x = struct.unpack('<f', tile_data[8:12])[0]
            user_y = struct.unpack('<f', tile_data[12:16])[0]
            width = tile_data[16]
            height = tile_data[17]
            # reserved(1)
            vendor = struct.unpack('<I', tile_data[19:23])[0]
            product = struct.unpack('<I', tile_data[23:27])[0]
            version = struct.unpack('<I', tile_data[27:31])[0]
            
            # Only add if the tile has valid dimensions
            if width > 0 or height > 0:
                tiles.append({
                    'index': i,
                    'accel_x': accel_x,
                    'accel_y': accel_y,
                    'accel_z': accel_z,
                    'user_x': user_x,
                    'user_y': user_y,
                    'width': width,
                    'height': height,
                    'vendor': vendor,
                    'product': product,
                    'version': version
                })
        
        total_count = payload[881] if len(payload) > 881 else len(tiles)
        
        return {
            'start_index': start_index,
            'total_count': total_count,
            'tiles': tiles
        }
    except struct.error:
        return None


def parse_state64(payload: bytes) -> Optional[dict]:
    """Parse State64 (packet 711) payload - 64 pixel colors from a tile."""
    if len(payload) < 517:  # 5 + 512 = 517 bytes
        return None
    try:
        tile_index = payload[0]
        # reserved(1)
        x = payload[2]
        y = payload[3]
        width = payload[4]
        
        colors = []
        for i in range(64):
            offset = 5 + i * 8
            if offset + 8 > len(payload):
                break
            h, s, b, k = struct.unpack('<HHHH', payload[offset:offset+8])
            colors.append(HSBK(h, s, b, k))
        
        return {
            'tile_index': tile_index,
            'x': x,
            'y': y,
            'width': width,
            'colors': colors
        }
    except struct.error:
        return None


def parse_state_tile_effect(payload: bytes) -> Optional[dict]:
    """Parse StateTileEffect (packet 720) payload."""
    if len(payload) < 187:
        return None
    try:
        instanceid = struct.unpack('<I', payload[2:6])[0]
        effect_type = payload[6]
        speed = struct.unpack('<I', payload[7:11])[0]
        duration = struct.unpack('<Q', payload[11:19])[0]
        
        effect_names = {
            0: 'OFF',
            1: 'RESERVED1',
            2: 'MORPH',
            3: 'FLAME',
            4: 'RESERVED2',
            5: 'SKY'
        }
        
        return {
            'instanceid': instanceid,
            'type': effect_type,
            'type_name': effect_names.get(effect_type, f'UNKNOWN({effect_type})'),
            'speed': speed,
            'duration': duration
        }
    except struct.error:
        return None


def get_device_matrix_size(product_id: int) -> Optional[tuple]:
    """
    Get the matrix dimensions for a product if it has matrix support.
    
    Returns (width, height) tuple or None if not a matrix device.
    """
    product_info = LIFX_PRODUCTS.get(product_id)
    if not product_info:
        return None
    
    features = product_info.get('features', {})
    if not features.get('matrix'):
        return None
    
    # Known matrix device dimensions
    matrix_sizes = {
        55: (8, 8),   # LIFX Tile
        57: (8, 1),   # LIFX Candle (single row of 8 LEDs)
        68: (8, 1),   # LIFX Candle
        100: (8, 1),  # LIFX Candle Color
        137: (8, 1),  # LIFX Candle Color US
        138: (8, 1),  # LIFX Candle Colour Intl
        171: (8, 8),  # LIFX Round Spot US
        173: (8, 8),  # LIFX Round Path US
        174: (8, 8),  # LIFX Square Path US
        176: (8, 8),  # LIFX Ceiling US
        177: (8, 8),  # LIFX Ceiling Intl
        201: (8, 8),  # LIFX Ceiling 13x26" US
        202: (8, 8),  # LIFX Ceiling 13x26" Intl
        217: (8, 8),  # LIFX Tube US
        218: (8, 8),  # LIFX Tube Intl
        219: (8, 8),  # LIFX Luna US
        220: (8, 8),  # LIFX Luna Intl
    }
    
    return matrix_sizes.get(product_id, (8, 8))  # Default to 8x8
