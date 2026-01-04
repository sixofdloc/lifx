#!/usr/bin/env python3
"""
LIFX Effects Library

Software-controlled lighting effects for LIFX devices.
Provides effects like rainbow, candle flicker, sunrise/sunset, etc.

These effects work by sending sequences of color commands to the device,
as opposed to hardware waveforms which only oscillate between two colors.
"""

import random
import socket
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

from lifx_protocol import (
    HSBK,
    LIFXDevice,
    Waveform,
    generate_source_id,
    create_setcolor_packet,
    create_setwaveform_packet,
    create_set64_packet,
    create_settileeffect_packet,
    TileEffect,
    get_device_matrix_size,
    LIFX_PRODUCTS,
)


# =============================================================================
# Effect Types
# =============================================================================

class EffectType(Enum):
    """Available effect types."""
    # Hardware waveform effects (handled by bulb)
    PULSE = auto()
    BREATHE = auto()
    STROBE = auto()
    SAW = auto()
    TRIANGLE = auto()
    
    # Software-controlled effects (color sequences)
    RAINBOW = auto()
    CANDLE = auto()
    DISCO = auto()
    SUNRISE = auto()
    SUNSET = auto()
    POLICE = auto()
    PARTY = auto()
    RELAX = auto()
    
    # Matrix-specific effects (for tile/ceiling/candle devices)
    MATRIX_RAINBOW = auto()
    MATRIX_WAVE = auto()
    MATRIX_FLAME = auto()
    MATRIX_MORPH = auto()
    MATRIX_SKY = auto()
    

# =============================================================================
# Effect Runner
# =============================================================================

@dataclass
class EffectConfig:
    """Configuration for running an effect."""
    effect_type: EffectType
    period: int = 1000        # Base period in ms
    cycles: float = 10        # Number of cycles (0 = infinite)
    brightness: float = 1.0   # Max brightness (0-1)
    saturation: float = 1.0   # Saturation (0-1)
    kelvin: int = 3500        # Color temperature
    speed: float = 1.0        # Speed multiplier
    

class EffectRunner:
    """
    Runs lighting effects on LIFX devices.
    
    Effects can be hardware-based (waveforms) or software-controlled
    (color sequences sent over time).
    """
    
    def __init__(self, subnet: str = "192.168.64.0/24"):
        self.source = generate_source_id()
        self.sequence = 0
        self._running: dict[str, bool] = {}  # serial -> running
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
    
    def _next_sequence(self) -> int:
        seq = self.sequence
        self.sequence = (self.sequence + 1) % 256
        return seq
    
    def _send_color(self, device: LIFXDevice, hsbk: HSBK, duration: int = 0):
        """Send a color command to a device."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        try:
            packet = create_setcolor_packet(
                self.source, device.target_bytes, hsbk, duration, self._next_sequence()
            )
            sock.sendto(packet, (device.ip_address, device.port))
        finally:
            sock.close()
    
    def _send_waveform(self, device: LIFXDevice, hsbk: HSBK, waveform: Waveform,
                       period: int, cycles: float, transient: bool = True,
                       skew_ratio: float = 0.5):
        """Send a waveform command to a device."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        try:
            packet = create_setwaveform_packet(
                self.source, device.target_bytes, hsbk,
                transient=transient, period=period, cycles=cycles,
                waveform=waveform, skew_ratio=skew_ratio,
                sequence=self._next_sequence()
            )
            sock.sendto(packet, (device.ip_address, device.port))
        finally:
            sock.close()
    
    def is_running(self, device: LIFXDevice) -> bool:
        """Check if an effect is running on a device."""
        with self._lock:
            return self._running.get(device.serial, False)
    
    def stop(self, device: LIFXDevice):
        """Stop any running effect on a device."""
        with self._lock:
            self._running[device.serial] = False
        
        # Wait for thread to finish
        thread = self._threads.get(device.serial)
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
    
    def stop_all(self):
        """Stop all running effects."""
        with self._lock:
            for serial in self._running:
                self._running[serial] = False
        
        for thread in self._threads.values():
            if thread.is_alive():
                thread.join(timeout=1.0)
    
    def run_effect(self, device: LIFXDevice, config: EffectConfig,
                   on_complete: Optional[Callable] = None):
        """
        Run an effect on a device.
        
        Args:
            device: The LIFX device to control
            config: Effect configuration
            on_complete: Optional callback when effect completes
        """
        # Stop any existing effect
        self.stop(device)
        
        # Check if this is a hardware waveform effect
        if config.effect_type in (EffectType.PULSE, EffectType.BREATHE,
                                   EffectType.STROBE, EffectType.SAW,
                                   EffectType.TRIANGLE):
            self._run_waveform_effect(device, config)
            return
        
        # Software effect - run in thread
        with self._lock:
            self._running[device.serial] = True
        
        def run():
            try:
                self._run_software_effect(device, config)
            finally:
                with self._lock:
                    self._running[device.serial] = False
                if on_complete:
                    on_complete()
        
        thread = threading.Thread(target=run, daemon=True)
        self._threads[device.serial] = thread
        thread.start()
    
    def _run_waveform_effect(self, device: LIFXDevice, config: EffectConfig):
        """Run a hardware waveform effect."""
        # Map effect type to waveform
        waveform_map = {
            EffectType.PULSE: Waveform.PULSE,
            EffectType.BREATHE: Waveform.SINE,
            EffectType.STROBE: Waveform.PULSE,
            EffectType.SAW: Waveform.SAW,
            EffectType.TRIANGLE: Waveform.TRIANGLE,
        }
        waveform = waveform_map.get(config.effect_type, Waveform.SINE)
        
        # Calculate target color (dim version of current)
        target_brightness = 0 if config.effect_type in (EffectType.PULSE, EffectType.STROBE) else int(device.brightness * 0.2)
        
        hsbk = HSBK(
            hue=device.hue,
            saturation=device.saturation,
            brightness=target_brightness,
            kelvin=device.kelvin
        )
        
        # Adjust period for strobe
        period = config.period
        if config.effect_type == EffectType.STROBE:
            period = min(period, 100)
        
        self._send_waveform(device, hsbk, waveform, period, config.cycles)
    
    def _run_software_effect(self, device: LIFXDevice, config: EffectConfig):
        """Run a software-controlled effect (color sequence)."""
        effect_map = {
            EffectType.RAINBOW: self._effect_rainbow,
            EffectType.CANDLE: self._effect_candle,
            EffectType.DISCO: self._effect_disco,
            EffectType.SUNRISE: self._effect_sunrise,
            EffectType.SUNSET: self._effect_sunset,
            EffectType.POLICE: self._effect_police,
            EffectType.PARTY: self._effect_party,
            EffectType.RELAX: self._effect_relax,
            EffectType.MATRIX_RAINBOW: self._effect_matrix_rainbow,
            EffectType.MATRIX_WAVE: self._effect_matrix_wave,
            EffectType.MATRIX_FLAME: self._effect_matrix_flame,
            EffectType.MATRIX_MORPH: self._effect_matrix_morph,
            EffectType.MATRIX_SKY: self._effect_matrix_sky,
        }
        
        effect_func = effect_map.get(config.effect_type)
        if effect_func:
            effect_func(device, config)
    
    def _effect_rainbow(self, device: LIFXDevice, config: EffectConfig):
        """
        Rainbow effect - smoothly cycle through all hues.
        
        Uses the device's current brightness and cycles through colors.
        """
        # Calculate step timing
        # Full rainbow takes (period * cycles) milliseconds
        # We send updates every ~50ms for smoothness
        update_interval = 0.05  # 50ms
        total_duration = (config.period / 1000) * config.cycles / config.speed
        steps_per_cycle = int(config.period / 1000 / update_interval)
        hue_step = 65535 / steps_per_cycle
        
        brightness = int(config.brightness * 65535)
        saturation = int(config.saturation * 65535)
        
        current_hue = 0.0
        cycles_done = 0
        
        while self._running.get(device.serial, False):
            # Send color
            hsbk = HSBK(
                hue=int(current_hue) % 65535,
                saturation=saturation,
                brightness=brightness,
                kelvin=config.kelvin
            )
            self._send_color(device, hsbk, int(update_interval * 1000))
            
            # Advance hue
            current_hue += hue_step * config.speed
            if current_hue >= 65535:
                current_hue -= 65535
                cycles_done += 1
                if config.cycles > 0 and cycles_done >= config.cycles:
                    break
            
            time.sleep(update_interval)
    
    def _effect_candle(self, device: LIFXDevice, config: EffectConfig):
        """
        Candle flicker effect - warm light with random brightness variations.
        """
        base_brightness = config.brightness * 0.7
        brightness_range = config.brightness * 0.3
        
        # Warm candle color
        base_hue = int(35 / 360 * 65535)  # Warm orange
        hue_range = int(15 / 360 * 65535)  # Slight variation
        
        update_interval = 0.08 + random.random() * 0.12  # 80-200ms, irregular
        cycles_done = 0
        
        while self._running.get(device.serial, False):
            # Random flicker
            brightness = base_brightness + random.random() * brightness_range
            hue = base_hue + random.randint(-hue_range // 2, hue_range // 2)
            
            hsbk = HSBK(
                hue=hue % 65535,
                saturation=int(0.6 * 65535),
                brightness=int(brightness * 65535),
                kelvin=2200
            )
            duration = int(update_interval * 1000 * 0.8)
            self._send_color(device, hsbk, duration)
            
            cycles_done += 1
            if config.cycles > 0 and cycles_done >= config.cycles * 10:
                break
            
            time.sleep(update_interval)
            update_interval = 0.08 + random.random() * 0.12
    
    def _effect_disco(self, device: LIFXDevice, config: EffectConfig):
        """
        Disco effect - rapid random color changes.
        """
        interval = (config.period / 1000) / config.speed
        interval = max(0.1, min(interval, 0.5))  # Clamp to 100-500ms
        
        cycles_done = 0
        last_hue = 0
        
        while self._running.get(device.serial, False):
            # Random hue, but avoid similar colors
            hue = random.randint(0, 65535)
            while abs(hue - last_hue) < 10000:
                hue = random.randint(0, 65535)
            last_hue = hue
            
            hsbk = HSBK(
                hue=hue,
                saturation=65535,
                brightness=int(config.brightness * 65535),
                kelvin=config.kelvin
            )
            self._send_color(device, hsbk, int(interval * 500))
            
            cycles_done += 1
            if config.cycles > 0 and cycles_done >= config.cycles:
                break
            
            time.sleep(interval)
    
    def _effect_sunrise(self, device: LIFXDevice, config: EffectConfig):
        """
        Sunrise effect - gradually brighten with warm colors transitioning to daylight.
        """
        # Total duration from config
        total_duration = (config.period / 1000) * config.cycles / config.speed
        total_duration = max(10, total_duration)  # At least 10 seconds
        
        update_interval = 0.5  # Update every 500ms
        steps = int(total_duration / update_interval)
        
        for i in range(steps):
            if not self._running.get(device.serial, False):
                break
            
            progress = i / steps
            
            # Brightness: 0% -> 100%
            brightness = progress * config.brightness
            
            # Color temperature: 1500K (deep red) -> 2700K (warm) -> 4000K (neutral)
            if progress < 0.5:
                # Red/orange phase
                kelvin = int(1500 + progress * 2 * 1200)  # 1500 -> 2700
                hue = int(15 / 360 * 65535)  # Deep orange
                saturation = 0.9 - progress * 0.6  # High to medium saturation
            else:
                # Warm white phase
                kelvin = int(2700 + (progress - 0.5) * 2 * 1300)  # 2700 -> 4000
                hue = int(30 / 360 * 65535)  # Warm
                saturation = 0.6 - (progress - 0.5) * 1.2  # Fade to white
            
            hsbk = HSBK(
                hue=hue,
                saturation=int(max(0, saturation) * 65535),
                brightness=int(brightness * 65535),
                kelvin=kelvin
            )
            self._send_color(device, hsbk, int(update_interval * 1000))
            
            time.sleep(update_interval)
    
    def _effect_sunset(self, device: LIFXDevice, config: EffectConfig):
        """
        Sunset effect - gradually dim with colors transitioning to warm/off.
        """
        total_duration = (config.period / 1000) * config.cycles / config.speed
        total_duration = max(10, total_duration)
        
        update_interval = 0.5
        steps = int(total_duration / update_interval)
        
        for i in range(steps):
            if not self._running.get(device.serial, False):
                break
            
            progress = i / steps
            
            # Brightness: 100% -> 0%
            brightness = (1 - progress) * config.brightness
            
            # Color temperature: 4000K -> 2700K -> 1500K (deep red)
            if progress < 0.5:
                kelvin = int(4000 - progress * 2 * 1300)  # 4000 -> 2700
                hue = int(30 / 360 * 65535)
                saturation = progress * 1.2
            else:
                kelvin = int(2700 - (progress - 0.5) * 2 * 1200)  # 2700 -> 1500
                hue = int(15 / 360 * 65535)  # Deep orange/red
                saturation = 0.6 + (progress - 0.5) * 0.6
            
            hsbk = HSBK(
                hue=hue,
                saturation=int(min(1, saturation) * 65535),
                brightness=int(brightness * 65535),
                kelvin=max(1500, kelvin)
            )
            self._send_color(device, hsbk, int(update_interval * 1000))
            
            time.sleep(update_interval)
    
    def _effect_police(self, device: LIFXDevice, config: EffectConfig):
        """
        Police lights effect - alternating red and blue flashes.
        """
        interval = (config.period / 1000) / config.speed / 4
        interval = max(0.05, min(interval, 0.3))
        
        red = HSBK(hue=0, saturation=65535, brightness=int(config.brightness * 65535), kelvin=config.kelvin)
        blue = HSBK(hue=int(240/360*65535), saturation=65535, brightness=int(config.brightness * 65535), kelvin=config.kelvin)
        off = HSBK(hue=0, saturation=0, brightness=0, kelvin=config.kelvin)
        
        cycles_done = 0
        
        while self._running.get(device.serial, False):
            # Red flashes
            for _ in range(2):
                if not self._running.get(device.serial, False):
                    return
                self._send_color(device, red, 0)
                time.sleep(interval)
                self._send_color(device, off, 0)
                time.sleep(interval * 0.5)
            
            # Blue flashes
            for _ in range(2):
                if not self._running.get(device.serial, False):
                    return
                self._send_color(device, blue, 0)
                time.sleep(interval)
                self._send_color(device, off, 0)
                time.sleep(interval * 0.5)
            
            cycles_done += 1
            if config.cycles > 0 and cycles_done >= config.cycles:
                break
    
    def _effect_party(self, device: LIFXDevice, config: EffectConfig):
        """
        Party effect - random bright colors with beat-like timing.
        """
        beat_interval = (config.period / 1000) / config.speed
        beat_interval = max(0.2, min(beat_interval, 1.0))
        
        colors = [0, 30, 60, 120, 180, 240, 280, 330]  # Hue values in degrees
        cycles_done = 0
        last_color = -1
        
        while self._running.get(device.serial, False):
            # Pick a different color
            color_idx = random.choice([i for i in range(len(colors)) if i != last_color])
            last_color = color_idx
            hue = int(colors[color_idx] / 360 * 65535)
            
            hsbk = HSBK(
                hue=hue,
                saturation=65535,
                brightness=int(config.brightness * 65535),
                kelvin=config.kelvin
            )
            self._send_color(device, hsbk, int(beat_interval * 200))
            
            cycles_done += 1
            if config.cycles > 0 and cycles_done >= config.cycles:
                break
            
            time.sleep(beat_interval)
    
    def _effect_relax(self, device: LIFXDevice, config: EffectConfig):
        """
        Relax effect - slow, gentle color transitions in warm tones.
        """
        cycle_duration = (config.period / 1000) / config.speed
        cycle_duration = max(5, cycle_duration)  # At least 5 seconds per color
        
        update_interval = 0.2
        steps_per_color = int(cycle_duration / update_interval)
        
        # Relaxing warm colors
        colors = [
            (30, 0.4, 2700),   # Warm white
            (20, 0.5, 2500),   # Soft amber
            (280, 0.3, 3000),  # Soft lavender
            (180, 0.2, 3500),  # Soft cyan
        ]
        
        color_idx = 0
        cycles_done = 0
        
        while self._running.get(device.serial, False):
            current = colors[color_idx]
            next_idx = (color_idx + 1) % len(colors)
            next_color = colors[next_idx]
            
            for step in range(steps_per_color):
                if not self._running.get(device.serial, False):
                    return
                
                progress = step / steps_per_color
                
                # Interpolate between colors
                hue = current[0] + (next_color[0] - current[0]) * progress
                sat = current[1] + (next_color[1] - current[1]) * progress
                kelvin = int(current[2] + (next_color[2] - current[2]) * progress)
                
                hsbk = HSBK(
                    hue=int(hue / 360 * 65535),
                    saturation=int(sat * 65535),
                    brightness=int(config.brightness * 0.7 * 65535),
                    kelvin=kelvin
                )
                self._send_color(device, hsbk, int(update_interval * 1000))
                
                time.sleep(update_interval)
            
            color_idx = next_idx
            cycles_done += 1
            if config.cycles > 0 and cycles_done >= config.cycles:
                break

    # =========================================================================
    # Matrix Effects (for tile/ceiling/candle devices with pixel control)
    # =========================================================================

    def _send_matrix_colors(self, device: LIFXDevice, colors: list, duration: int = 0):
        """Send 64 pixel colors to a matrix device."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        try:
            packet = create_set64_packet(
                self.source, device.target_bytes, colors,
                duration=duration, sequence=self._next_sequence()
            )
            sock.sendto(packet, (device.ip_address, device.port))
        finally:
            sock.close()

    def _send_tile_effect(self, device: LIFXDevice, effect: TileEffect,
                          speed: int = 3000, palette: list = None):
        """Send a firmware-controlled tile effect."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        try:
            packet = create_settileeffect_packet(
                self.source, device.target_bytes,
                effect=effect, speed=speed, palette=palette,
                sequence=self._next_sequence()
            )
            sock.sendto(packet, (device.ip_address, device.port))
        finally:
            sock.close()

    def _is_matrix_device(self, device: LIFXDevice) -> bool:
        """Check if the device supports matrix pixel control."""
        if hasattr(device, 'product_id'):
            return get_device_matrix_size(device.product_id) is not None
        return False

    def _effect_matrix_rainbow(self, device: LIFXDevice, config: EffectConfig):
        """
        Matrix rainbow effect - animated rainbow across 64 pixels.
        Creates a moving rainbow pattern across the matrix.
        """
        update_interval = 0.1 / config.speed
        offset = 0
        cycles_done = 0
        
        brightness = int(config.brightness * 65535)
        saturation = int(config.saturation * 65535)
        
        while self._running.get(device.serial, False):
            colors = []
            for i in range(64):
                row = i // 8
                col = i % 8
                # Diagonal rainbow pattern
                hue = int(((row + col + offset) / 16) * 65535) % 65535
                colors.append((hue, saturation, brightness, config.kelvin))
            
            self._send_matrix_colors(device, colors, int(update_interval * 1000))
            
            offset += 1
            if offset >= 16:
                offset = 0
                cycles_done += 1
                if config.cycles > 0 and cycles_done >= config.cycles:
                    break
            
            time.sleep(update_interval)

    def _effect_matrix_wave(self, device: LIFXDevice, config: EffectConfig):
        """
        Matrix wave effect - color wave moving across the pixels.
        """
        update_interval = 0.08 / config.speed
        phase = 0.0
        cycles_done = 0
        
        import math
        
        # Use a single hue that shifts over time
        base_hue = 0
        
        brightness = int(config.brightness * 65535)
        saturation = int(config.saturation * 65535)
        
        while self._running.get(device.serial, False):
            colors = []
            for i in range(64):
                row = i // 8
                col = i % 8
                
                # Create wave effect with varying brightness
                wave = (math.sin((col + phase) * 0.8) + 1) / 2
                wave2 = (math.sin((row + phase * 0.7) * 0.6) + 1) / 2
                combined = (wave + wave2) / 2
                
                pixel_brightness = int(brightness * (0.3 + 0.7 * combined))
                hue = int((base_hue + col * 8 + row * 8) / 360 * 65535) % 65535
                
                colors.append((hue, saturation, pixel_brightness, config.kelvin))
            
            self._send_matrix_colors(device, colors, int(update_interval * 1000))
            
            phase += 0.3
            base_hue = (base_hue + 2) % 360
            
            if phase >= 2 * math.pi:
                phase -= 2 * math.pi
                cycles_done += 1
                if config.cycles > 0 and cycles_done >= config.cycles:
                    break
            
            time.sleep(update_interval)

    def _effect_matrix_flame(self, device: LIFXDevice, config: EffectConfig):
        """
        Matrix flame effect - use hardware FLAME effect if available,
        otherwise simulate with software.
        """
        # Try hardware effect first (more efficient)
        try:
            self._send_tile_effect(device, TileEffect.FLAME, speed=4000)
            # For hardware effects, we just wait and check periodically
            cycles_done = 0
            while self._running.get(device.serial, False):
                time.sleep(0.5)
                cycles_done += 1
                if config.cycles > 0 and cycles_done >= config.cycles * 2:
                    break
            # Turn off effect when done
            self._send_tile_effect(device, TileEffect.OFF)
            return
        except Exception:
            pass  # Fall through to software implementation
        
        # Software flame simulation
        update_interval = 0.1
        
        # Fire palette - dark red to yellow
        def fire_color(intensity: float) -> tuple:
            if intensity < 0.2:
                return (0, 65535, int(intensity * 5 * 65535 * 0.3), 2000)
            elif intensity < 0.5:
                hue = int(15 / 360 * 65535)  # Orange-red
                return (hue, 65535, int(intensity * 65535 * config.brightness), 2000)
            else:
                hue = int(30 / 360 * 65535)  # Orange-yellow
                return (hue, int(65535 * 0.7), int(intensity * 65535 * config.brightness), 2200)
        
        # Initialize heat map
        heat = [[0.0 for _ in range(8)] for _ in range(8)]
        cycles_done = 0
        
        while self._running.get(device.serial, False):
            # Cool down
            for row in range(8):
                for col in range(8):
                    heat[row][col] = max(0, heat[row][col] - random.uniform(0.05, 0.15))
            
            # Add heat at bottom
            for col in range(8):
                heat[7][col] = min(1.0, heat[7][col] + random.uniform(0.3, 0.7))
            
            # Propagate heat upward
            for row in range(7):
                for col in range(8):
                    neighbors = [heat[row + 1][col]]
                    if col > 0:
                        neighbors.append(heat[row + 1][col - 1])
                    if col < 7:
                        neighbors.append(heat[row + 1][col + 1])
                    heat[row][col] = max(heat[row][col], sum(neighbors) / len(neighbors) * 0.7)
            
            # Convert to colors
            colors = []
            for row in range(8):
                for col in range(8):
                    colors.append(fire_color(heat[row][col]))
            
            self._send_matrix_colors(device, colors, int(update_interval * 1000))
            
            cycles_done += 1
            if config.cycles > 0 and cycles_done >= config.cycles * 10:
                break
            
            time.sleep(update_interval)

    def _effect_matrix_morph(self, device: LIFXDevice, config: EffectConfig):
        """
        Matrix morph effect - use hardware MORPH effect for smooth color blending.
        """
        # Create a palette of colors that will morph between each other
        palette = [
            (0, 65535, int(config.brightness * 65535), config.kelvin),      # Red
            (int(60/360*65535), 65535, int(config.brightness * 65535), config.kelvin),   # Yellow
            (int(120/360*65535), 65535, int(config.brightness * 65535), config.kelvin),  # Green
            (int(180/360*65535), 65535, int(config.brightness * 65535), config.kelvin),  # Cyan
            (int(240/360*65535), 65535, int(config.brightness * 65535), config.kelvin),  # Blue
            (int(300/360*65535), 65535, int(config.brightness * 65535), config.kelvin),  # Magenta
        ]
        
        try:
            speed = int(config.period / config.speed)
            self._send_tile_effect(device, TileEffect.MORPH, speed=speed, palette=palette)
            # Wait and check periodically
            cycles_done = 0
            while self._running.get(device.serial, False):
                time.sleep(0.5)
                cycles_done += 1
                if config.cycles > 0 and cycles_done >= config.cycles * 2:
                    break
            # Turn off effect when done
            self._send_tile_effect(device, TileEffect.OFF)
        except Exception as e:
            # If hardware effect fails, just run rainbow as fallback
            self._effect_matrix_rainbow(device, config)

    def _effect_matrix_sky(self, device: LIFXDevice, config: EffectConfig):
        """
        Matrix sky effect - use hardware SKY effect for sunrise/sunset/clouds.
        """
        try:
            speed = int(config.period / config.speed)
            self._send_tile_effect(device, TileEffect.SKY, speed=speed)
            # Wait and check periodically
            cycles_done = 0
            while self._running.get(device.serial, False):
                time.sleep(0.5)
                cycles_done += 1
                if config.cycles > 0 and cycles_done >= config.cycles * 2:
                    break
            # Turn off effect when done
            self._send_tile_effect(device, TileEffect.OFF)
        except Exception:
            # Fallback to software sunrise
            self._effect_sunrise(device, config)


# =============================================================================
# Convenience Functions
# =============================================================================

# Global effect runner instance
_effect_runner: Optional[EffectRunner] = None


def get_effect_runner() -> EffectRunner:
    """Get or create the global effect runner."""
    global _effect_runner
    if _effect_runner is None:
        _effect_runner = EffectRunner()
    return _effect_runner


def run_effect(device: LIFXDevice, effect_name: str, period: int = 1000,
               cycles: float = 10, brightness: float = 1.0, **kwargs) -> bool:
    """
    Run a named effect on a device.
    
    Args:
        device: The LIFX device
        effect_name: Name of the effect (rainbow, candle, disco, etc.)
        period: Base period in milliseconds
        cycles: Number of cycles (0 = infinite)
        brightness: Brightness level (0-1)
        **kwargs: Additional effect parameters
    
    Returns:
        True if effect started, False if unknown effect
    """
    effect_map = {
        'pulse': EffectType.PULSE,
        'breathe': EffectType.BREATHE,
        'strobe': EffectType.STROBE,
        'saw': EffectType.SAW,
        'triangle': EffectType.TRIANGLE,
        'rainbow': EffectType.RAINBOW,
        'candle': EffectType.CANDLE,
        'disco': EffectType.DISCO,
        'sunrise': EffectType.SUNRISE,
        'sunset': EffectType.SUNSET,
        'police': EffectType.POLICE,
        'party': EffectType.PARTY,
        'relax': EffectType.RELAX,
        # Matrix effects
        'matrix_rainbow': EffectType.MATRIX_RAINBOW,
        'matrix_wave': EffectType.MATRIX_WAVE,
        'matrix_flame': EffectType.MATRIX_FLAME,
        'matrix_morph': EffectType.MATRIX_MORPH,
        'matrix_sky': EffectType.MATRIX_SKY,
    }
    
    effect_type = effect_map.get(effect_name.lower())
    if not effect_type:
        return False
    
    config = EffectConfig(
        effect_type=effect_type,
        period=period,
        cycles=cycles,
        brightness=brightness,
        saturation=kwargs.get('saturation', 1.0),
        kelvin=kwargs.get('kelvin', 3500),
        speed=kwargs.get('speed', 1.0),
    )
    
    runner = get_effect_runner()
    runner.run_effect(device, config)
    return True


def stop_effect(device: LIFXDevice):
    """Stop any running effect on a device."""
    runner = get_effect_runner()
    runner.stop(device)


def stop_all_effects():
    """Stop all running effects."""
    runner = get_effect_runner()
    runner.stop_all()


def list_effects() -> list[str]:
    """Get list of available effect names."""
    return [
        'pulse', 'breathe', 'strobe', 'saw', 'triangle',
        'rainbow', 'candle', 'disco', 'sunrise', 'sunset',
        'police', 'party', 'relax',
        'matrix_rainbow', 'matrix_wave', 'matrix_flame', 'matrix_morph', 'matrix_sky'
    ]


def list_matrix_effects() -> list[str]:
    """Get list of matrix-specific effects (for tile/ceiling devices)."""
    return ['matrix_rainbow', 'matrix_wave', 'matrix_flame', 'matrix_morph', 'matrix_sky']


if __name__ == '__main__':
    # Quick test
    print("Available effects:", list_effects())
