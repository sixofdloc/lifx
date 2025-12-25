#!/usr/bin/env python3
"""
LIFX TUI Controller

A terminal user interface for controlling LIFX lights.
Uses the Textual framework for the TUI and lifx_protocol for device communication.

Requirements:
    pip install textual

Usage:
    python3 lifx_tui.py
    python3 lifx_tui.py -s 192.168.1.0/24
"""

import argparse
import socket
import sys
import time
from threading import Thread, Lock
from typing import Optional

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
    from textual.widgets import (
        Header, Footer, Static, Button, ListView, ListItem, 
        Label, ProgressBar, Switch, Rule, Input, TabbedContent, TabPane
    )
    from textual.reactive import reactive
    from textual.message import Message
    from textual.binding import Binding
except ImportError:
    print("Error: textual library required. Install with:")
    print("  pip install textual")
    sys.exit(1)

from lifx_protocol import (
    LIFX_PORT,
    STATESERVICE_TYPE,
    LIGHTSTATE_TYPE,
    ACKNOWLEDGEMENT_TYPE,
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
# LIFX Communication Layer
# =============================================================================

class LIFXManager:
    """Manages LIFX device communication for the TUI."""
    
    def __init__(self, subnet: str = "192.168.64.0/24", timeout: float = 1.0):
        self.subnet = subnet
        self.timeout = timeout
        self.source = generate_source_id()
        self.sequence = 0
        self.devices: dict[str, LIFXDevice] = {}
        self.lock = Lock()
    
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
            self._update_device_state(device)
        
        with self.lock:
            self.devices = discovered
        
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
    
    def refresh_device(self, device: LIFXDevice):
        """Refresh a single device's state."""
        self._update_device_state(device)
    
    def set_power(self, device: LIFXDevice, on: bool, duration: int = 0) -> bool:
        """Set device power state."""
        level = 65535 if on else 0
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        
        try:
            if duration > 0:
                packet = create_setlightpower_packet(
                    self.source, device.target_bytes, level, duration, self._next_sequence()
                )
            else:
                packet = create_setpower_packet(
                    self.source, device.target_bytes, level, self._next_sequence()
                )
            
            sock.sendto(packet, (device.ip_address, device.port))
            
            # Wait for acknowledgement
            try:
                data, _ = sock.recvfrom(1024)
                header = parse_lifx_header(data)
                if header and header['type'] == ACKNOWLEDGEMENT_TYPE:
                    device.power = level
                    return True
            except socket.timeout:
                pass
        finally:
            sock.close()
        
        return False
    
    def set_color(self, device: LIFXDevice, hsbk: HSBK, duration: int = 0) -> bool:
        """Set device color."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        
        try:
            packet = create_setcolor_packet(
                self.source, device.target_bytes, hsbk, duration, self._next_sequence()
            )
            sock.sendto(packet, (device.ip_address, device.port))
            
            # Wait for acknowledgement
            try:
                data, _ = sock.recvfrom(1024)
                header = parse_lifx_header(data)
                if header and header['type'] == ACKNOWLEDGEMENT_TYPE:
                    device.hue = hsbk.hue
                    device.saturation = hsbk.saturation
                    device.brightness = hsbk.brightness
                    device.kelvin = hsbk.kelvin
                    return True
            except socket.timeout:
                pass
        finally:
            sock.close()
        
        return False
    
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
        finally:
            sock.close()


# =============================================================================
# Custom Widgets
# =============================================================================

class Slider(Static):
    """A simple slider widget with arrow buttons."""
    
    DEFAULT_CSS = """
    Slider {
        height: 3;
        margin: 0 1;
    }
    Slider .slider-row {
        height: 1;
    }
    Slider .slider-label {
        text-style: bold;
        width: 12;
    }
    Slider .slider-btn {
        width: 3;
        min-width: 3;
        height: 1;
        padding: 0;
        margin: 0;
        border: none;
    }
    Slider .slider-track {
        width: 24;
    }
    Slider .slider-value {
        text-align: right;
        width: 8;
    }
    """
    
    value = reactive(0.0)
    
    class Changed(Message):
        """Slider value changed message."""
        def __init__(self, slider: "Slider", value: float) -> None:
            self.slider = slider
            self.value = value
            super().__init__()
    
    def __init__(
        self,
        label: str,
        min_value: float = 0.0,
        max_value: float = 100.0,
        value: float = 0.0,
        unit: str = "",
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id)
        self.label = label
        self.min_value = min_value
        self.max_value = max_value
        self._initial_value = value
        self.unit = unit
        self.can_focus = True
    
    def compose(self) -> ComposeResult:
        with Horizontal(classes="slider-row"):
            yield Static(self.label, classes="slider-label")
            yield Button("◀", classes="slider-btn", id="btn-dec")
            yield Static("", classes="slider-track", id="track")
            yield Button("▶", classes="slider-btn", id="btn-inc")
            yield Static("", classes="slider-value", id="value-display")
    
    def on_mount(self) -> None:
        self.value = self._initial_value
        self._update_display()
    
    def watch_value(self, value: float) -> None:
        if self.is_mounted:
            self._update_display()
            self.post_message(self.Changed(self, value))
    
    def _update_display(self) -> None:
        # Calculate percentage
        range_val = self.max_value - self.min_value
        if range_val > 0:
            pct = (self.value - self.min_value) / range_val
        else:
            pct = 0
        
        # Update track visualization
        track = self.query_one("#track", Static)
        width = 20
        filled = int(pct * width)
        track.update("█" * filled + "░" * (width - filled))
        
        # Update value display
        value_display = self.query_one("#value-display", Static)
        if self.unit:
            value_display.update(f"{self.value:.0f}{self.unit}")
        else:
            value_display.update(f"{self.value:.0f}")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle arrow button presses."""
        event.stop()
        step = (self.max_value - self.min_value) / 20  # 5% steps
        if event.button.id == "btn-dec":
            self.decrement(step)
        elif event.button.id == "btn-inc":
            self.increment(step)
    
    def on_click(self, event) -> None:
        """Handle click on track to set value."""
        # Find the track widget and calculate click position relative to it
        try:
            track = self.query_one("#track", Static)
            # Get track's region
            track_region = track.region
            # Check if click is within track's vertical bounds
            if track_region.y <= event.screen_y < track_region.y + track_region.height:
                # Calculate relative x position within track
                rel_x = event.screen_x - track_region.x
                width = 20  # Track width in characters
                if 0 <= rel_x <= width:
                    pct = rel_x / width
                    pct = max(0, min(1, pct))
                    new_value = self.min_value + pct * (self.max_value - self.min_value)
                    self.value = new_value
        except Exception:
            pass
    
    def increment(self, amount: float = 1.0) -> None:
        """Increment the value."""
        self.value = min(self.max_value, self.value + amount)
    
    def decrement(self, amount: float = 1.0) -> None:
        """Decrement the value."""
        self.value = max(self.min_value, self.value - amount)


class DeviceListItem(ListItem):
    """A list item representing a LIFX device."""
    
    def __init__(self, device: LIFXDevice) -> None:
        super().__init__()
        self.device = device
    
    def compose(self) -> ComposeResult:
        power_icon = "●" if self.device.power else "○"
        label = self.device.label or self.device.serial[:17]
        yield Static(f"{power_icon} {label}")


class ColorPreview(Static):
    """Shows a preview of the current color."""
    
    DEFAULT_CSS = """
    ColorPreview {
        height: 3;
        margin: 1 2;
        border: solid $primary;
        content-align: center middle;
    }
    """
    
    def __init__(self, hue: int = 0, sat: int = 0, bright: int = 65535, kelvin: int = 3500, **kwargs):
        super().__init__(**kwargs)
        self.hue = hue
        self.sat = sat
        self.bright = bright
        self.kelvin = kelvin
    
    def update_color(self, hue: int, sat: int, bright: int, kelvin: int):
        self.hue = hue
        self.sat = sat
        self.bright = bright
        self.kelvin = kelvin
        self._update_display()
    
    def on_mount(self):
        self._update_display()
    
    def _update_display(self):
        # Convert HSBK to display
        h_deg = round(self.hue / 65535 * 360)
        s_pct = round(self.sat / 65535 * 100)
        b_pct = round(self.bright / 65535 * 100)
        
        if self.sat < 6553:  # Low saturation = white
            self.update(f"White  K:{self.kelvin}  B:{b_pct}%")
        else:
            self.update(f"H:{h_deg}°  S:{s_pct}%  B:{b_pct}%  K:{self.kelvin}")


# =============================================================================
# Main Panels
# =============================================================================

class DeviceSidebar(Container):
    """Sidebar showing discovered devices."""
    
    DEFAULT_CSS = """
    DeviceSidebar {
        width: 30;
        dock: left;
        border-right: solid $primary;
        padding: 1;
    }
    DeviceSidebar ListView {
        height: 1fr;
    }
    DeviceSidebar .sidebar-title {
        text-style: bold;
        text-align: center;
        padding: 1;
        background: $primary;
        color: $text;
    }
    DeviceSidebar Button {
        width: 100%;
        margin: 1 0;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Static("LIFX Devices", classes="sidebar-title")
        yield Button("Refresh", id="btn-refresh", variant="primary")
        yield ListView(id="device-list")
        yield Static("", id="device-count")
    
    def update_devices(self, devices: list[LIFXDevice]):
        """Update the device list."""
        list_view = self.query_one("#device-list", ListView)
        list_view.clear()
        
        for device in sorted(devices, key=lambda d: d.label or d.serial):
            list_view.append(DeviceListItem(device))
        
        count_label = self.query_one("#device-count", Static)
        count_label.update(f"{len(devices)} device(s)")


class ControlPanel(Container):
    """Main control panel for the selected device."""
    
    DEFAULT_CSS = """
    ControlPanel {
        padding: 0 1;
    }
    ControlPanel .panel-title {
        text-style: bold;
        text-align: center;
        padding: 1;
    }
    ControlPanel .no-device {
        text-align: center;
        padding: 4;
        color: $text-muted;
    }
    ControlPanel .power-row {
        height: auto;
        margin: 1 0;
    }
    ControlPanel .power-row Button {
        margin: 0 1;
    }
    ControlPanel .preset-row {
        height: auto;
        margin: 1 0;
    }
    ControlPanel .preset-row Button {
        margin: 0 1;
        min-width: 10;
    }
    ControlPanel .effect-row {
        height: auto;
        margin: 1 0;
    }
    ControlPanel .effect-row Button {
        margin: 0 1;
        min-width: 10;
    }
    ControlPanel TabbedContent {
        height: 1fr;
    }
    ControlPanel TabPane {
        padding: 1;
    }
    """
    
    current_device: reactive[Optional[LIFXDevice]] = reactive(None)
    
    def compose(self) -> ComposeResult:
        yield Static("Select a device", classes="panel-title", id="device-title")
        yield Static("← Choose a light from the sidebar", classes="no-device", id="no-device-msg")
        
        with Container(id="controls-container"):
            # Power controls at top (always visible)
            with Horizontal(classes="power-row"):
                yield Button("ON", id="btn-power-on", variant="success")
                yield Button("OFF", id="btn-power-off", variant="error")
                yield Static("", id="power-status")
            
            # Color preview
            yield ColorPreview(id="color-preview")
            
            # Tabbed content for the rest
            with TabbedContent():
                with TabPane("Color", id="tab-color"):
                    yield Slider("Hue", 0, 360, 0, "°", id="slider-hue")
                    yield Slider("Saturation", 0, 100, 0, "%", id="slider-sat")
                    yield Slider("Brightness", 0, 100, 100, "%", id="slider-bright")
                    yield Slider("Kelvin", 1500, 9000, 3500, "K", id="slider-kelvin")
                
                with TabPane("Presets", id="tab-presets"):
                    yield Static("Colors")
                    with Horizontal(classes="preset-row"):
                        yield Button("Red", id="preset-red")
                        yield Button("Orange", id="preset-orange")
                        yield Button("Yellow", id="preset-yellow")
                        yield Button("Green", id="preset-green")
                    with Horizontal(classes="preset-row"):
                        yield Button("Cyan", id="preset-cyan")
                        yield Button("Blue", id="preset-blue")
                        yield Button("Purple", id="preset-purple")
                        yield Button("Pink", id="preset-pink")
                    yield Static("Whites")
                    with Horizontal(classes="preset-row"):
                        yield Button("Warm", id="preset-warm")
                        yield Button("Neutral", id="preset-neutral")
                        yield Button("Cool", id="preset-cool")
                        yield Button("Daylight", id="preset-daylight")
                
                with TabPane("Effects", id="tab-effects"):
                    yield Slider("Period", 100, 5000, 1000, "ms", id="slider-period")
                    yield Slider("Cycles", 1, 50, 5, "", id="slider-cycles")
                    with Horizontal(classes="effect-row"):
                        yield Switch(value=False, id="switch-loop")
                        yield Static("Loop forever", id="loop-label")
                    with Horizontal(classes="effect-row"):
                        yield Button("Pulse", id="effect-pulse")
                        yield Button("Breathe", id="effect-breathe")
                        yield Button("Strobe", id="effect-strobe")
                    with Horizontal(classes="effect-row"):
                        yield Button("Stop", id="effect-stop", variant="error")
    
    def on_mount(self):
        self.query_one("#controls-container").display = False
    
    def watch_current_device(self, device: Optional[LIFXDevice]) -> None:
        """Update UI when device changes."""
        if device:
            self.query_one("#no-device-msg").display = False
            self.query_one("#controls-container").display = True
            
            label = device.label or device.serial
            self.query_one("#device-title").update(label)
            
            # Update power status
            power_str = "ON" if device.power else "OFF"
            self.query_one("#power-status", Static).update(f"  Status: {power_str}")
            
            # Update sliders
            self.query_one("#slider-hue", Slider).value = device.hue / 65535 * 360
            self.query_one("#slider-sat", Slider).value = device.saturation / 65535 * 100
            self.query_one("#slider-bright", Slider).value = device.brightness / 65535 * 100
            self.query_one("#slider-kelvin", Slider).value = device.kelvin
            
            # Update color preview
            self.query_one("#color-preview", ColorPreview).update_color(
                device.hue, device.saturation, device.brightness, device.kelvin
            )
        else:
            self.query_one("#no-device-msg").display = True
            self.query_one("#controls-container").display = False
            self.query_one("#device-title").update("Select a device")


# =============================================================================
# Main Application
# =============================================================================

class LIFXApp(App):
    """LIFX TUI Controller Application."""
    
    CSS = """
    Screen {
        layout: horizontal;
    }
    
    #main-area {
        width: 1fr;
        height: 100%;
    }
    
    ControlPanel {
        height: auto;
    }
    
    Footer {
        background: $primary;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("p", "toggle_power", "Power"),
        Binding("up", "slider_up", "Increase", show=False),
        Binding("down", "slider_down", "Decrease", show=False),
        Binding("left", "slider_down_big", "Decrease 10", show=False),
        Binding("right", "slider_up_big", "Increase 10", show=False),
    ]
    
    TITLE = "LIFX Controller"
    
    def __init__(self, subnet: str = "192.168.64.0/24"):
        super().__init__()
        self.lifx = LIFXManager(subnet=subnet)
        self.selected_device: Optional[LIFXDevice] = None
        self._updating = False  # Prevent feedback loops
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield DeviceSidebar()
        with ScrollableContainer(id="main-area"):
            yield ControlPanel()
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.action_refresh()
    
    def action_refresh(self) -> None:
        """Refresh device list."""
        self.notify("Scanning for devices...", timeout=1)
        
        def do_scan():
            devices = self.lifx.discover()
            self.call_from_thread(self._update_device_list, devices)
        
        Thread(target=do_scan, daemon=True).start()
    
    def _update_device_list(self, devices: list[LIFXDevice]) -> None:
        """Update the device list (called from thread)."""
        sidebar = self.query_one(DeviceSidebar)
        sidebar.update_devices(devices)
        self.notify(f"Found {len(devices)} device(s)")
    
    def action_toggle_power(self) -> None:
        """Toggle power on selected device."""
        if self.selected_device:
            new_state = not bool(self.selected_device.power)
            self.lifx.set_power(self.selected_device, new_state)
            self.selected_device.power = 65535 if new_state else 0
            self._update_control_panel()
    
    def action_slider_up(self) -> None:
        """Increase focused slider."""
        self._adjust_focused_slider(1)
    
    def action_slider_down(self) -> None:
        """Decrease focused slider."""
        self._adjust_focused_slider(-1)
    
    def action_slider_up_big(self) -> None:
        """Increase focused slider by 10."""
        self._adjust_focused_slider(10)
    
    def action_slider_down_big(self) -> None:
        """Decrease focused slider by 10."""
        self._adjust_focused_slider(-10)
    
    def _adjust_focused_slider(self, amount: int) -> None:
        """Adjust the value of focused slider."""
        focused = self.focused
        if isinstance(focused, Slider):
            if amount > 0:
                focused.increment(abs(amount))
            else:
                focused.decrement(abs(amount))
    
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle device selection from sidebar."""
        if isinstance(event.item, DeviceListItem):
            self.selected_device = event.item.device
            panel = self.query_one(ControlPanel)
            panel.current_device = self.selected_device
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        
        # Ignore slider internal buttons (they handle themselves)
        if button_id in ("btn-dec", "btn-inc"):
            return
        
        if button_id == "btn-refresh":
            self.action_refresh()
        elif button_id == "btn-power-on" and self.selected_device:
            self._set_power(True)
        elif button_id == "btn-power-off" and self.selected_device:
            self._set_power(False)
        elif button_id and button_id.startswith("preset-"):
            self._apply_preset(button_id.replace("preset-", ""))
        elif button_id and button_id.startswith("effect-"):
            effect_name = button_id.replace("effect-", "")
            if effect_name == "stop":
                self._stop_effect()
            else:
                self._apply_effect(effect_name)
    
    def _set_power(self, on: bool) -> None:
        """Set device power."""
        if self.selected_device:
            self.lifx.set_power(self.selected_device, on, duration=250)
            self.selected_device.power = 65535 if on else 0
            self._update_control_panel()
            self._refresh_sidebar_item()
    
    def _apply_preset(self, preset: str) -> None:
        """Apply a color preset."""
        if not self.selected_device:
            return
        
        presets = {
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
        
        if preset in presets:
            h, s, b, k = presets[preset]
            hsbk = HSBK.from_degrees(h, s / 100, b / 100, k)
            
            # Set updating flag to prevent slider change events from reverting
            self._updating = True
            
            # Update device state locally first
            self.selected_device.hue = hsbk.hue
            self.selected_device.saturation = hsbk.saturation
            self.selected_device.brightness = hsbk.brightness
            self.selected_device.kelvin = hsbk.kelvin
            
            # Update sliders to match
            self.query_one("#slider-hue", Slider).value = h
            self.query_one("#slider-sat", Slider).value = s
            self.query_one("#slider-bright", Slider).value = b
            self.query_one("#slider-kelvin", Slider).value = k
            
            # Update color preview
            self.query_one("#color-preview", ColorPreview).update_color(
                hsbk.hue, hsbk.saturation, hsbk.brightness, hsbk.kelvin
            )
            
            self._updating = False
            
            # Send to device
            self.lifx.set_color(self.selected_device, hsbk, duration=250)
    
    def _apply_effect(self, effect: str) -> None:
        """Apply an effect."""
        if not self.selected_device:
            return
        
        # Get effect parameters from sliders
        period = int(self.query_one("#slider-period", Slider).value)
        loop = self.query_one("#switch-loop", Switch).value
        
        # If loop is enabled, use a very large cycle count (effectively infinite)
        # Otherwise use the slider value
        if loop:
            cycles = 1000000.0  # ~11.5 days at 1 second period
        else:
            cycles = self.query_one("#slider-cycles", Slider).value
        
        # For effects, we create a target HSBK that defines the "off" state
        # The waveform oscillates between current color and this target
        
        if effect == "pulse":
            # Pulse to dim/off and back (brightness oscillation)
            hsbk = HSBK(
                hue=self.selected_device.hue,
                saturation=self.selected_device.saturation,
                brightness=0,  # Pulse to off
                kelvin=self.selected_device.kelvin
            )
            self.lifx.set_waveform(self.selected_device, hsbk, Waveform.PULSE, period=period, cycles=cycles)
        elif effect == "breathe":
            # Slow sine wave breathing (brightness oscillation)
            hsbk = HSBK(
                hue=self.selected_device.hue,
                saturation=self.selected_device.saturation,
                brightness=int(self.selected_device.brightness * 0.2),  # Breathe to 20%
                kelvin=self.selected_device.kelvin
            )
            self.lifx.set_waveform(self.selected_device, hsbk, Waveform.SINE, period=period, cycles=cycles)
        elif effect == "strobe":
            # Fast strobe effect (override period for safety)
            hsbk = HSBK(
                hue=self.selected_device.hue,
                saturation=self.selected_device.saturation,
                brightness=0,  # Strobe to off
                kelvin=self.selected_device.kelvin
            )
            # Strobe uses shorter period for quick flashing
            strobe_period = min(period, 200)  # Cap at 200ms for strobe
            self.lifx.set_waveform(self.selected_device, hsbk, Waveform.PULSE, period=strobe_period, cycles=cycles)
        
        if loop:
            self.notify(f"Effect: {effect} (looping)")
        else:
            self.notify(f"Effect: {effect} ({period}ms, {cycles:.0f}x)")
    
    def _stop_effect(self) -> None:
        """Stop any running effect by setting the light to its current color."""
        if not self.selected_device:
            return
        
        # Refresh the device state and set it to current values
        self.lifx.refresh_device(self.selected_device)
        hsbk = HSBK(
            hue=self.selected_device.hue,
            saturation=self.selected_device.saturation,
            brightness=self.selected_device.brightness,
            kelvin=self.selected_device.kelvin
        )
        self.lifx.set_color(self.selected_device, hsbk, duration=0)
        self.notify("Effect stopped")
    
    def on_slider_changed(self, event: Slider.Changed) -> None:
        """Handle slider changes."""
        if self._updating or not self.selected_device:
            return
        
        slider_id = event.slider.id
        
        # Get current values
        hue = int(self.query_one("#slider-hue", Slider).value / 360 * 65535) % 65536
        sat = int(self.query_one("#slider-sat", Slider).value / 100 * 65535)
        bright = int(self.query_one("#slider-bright", Slider).value / 100 * 65535)
        kelvin = int(self.query_one("#slider-kelvin", Slider).value)
        
        # Clamp values
        sat = max(0, min(65535, sat))
        bright = max(0, min(65535, bright))
        kelvin = max(1500, min(9000, kelvin))
        
        # Update preview
        self.query_one("#color-preview", ColorPreview).update_color(hue, sat, bright, kelvin)
        
        # Apply color (with small delay/debounce could be added)
        hsbk = HSBK(hue=hue, saturation=sat, brightness=bright, kelvin=kelvin)
        
        def apply():
            self.lifx.set_color(self.selected_device, hsbk, duration=100)
        
        Thread(target=apply, daemon=True).start()
    
    def _update_control_panel(self) -> None:
        """Update the control panel with current device state."""
        if self.selected_device:
            panel = self.query_one(ControlPanel)
            panel.current_device = self.selected_device
    
    def _update_sliders_from_device(self) -> None:
        """Update sliders from device state."""
        if self.selected_device:
            self._updating = True
            self.lifx.refresh_device(self.selected_device)
            
            self.query_one("#slider-hue", Slider).value = self.selected_device.hue / 65535 * 360
            self.query_one("#slider-sat", Slider).value = self.selected_device.saturation / 65535 * 100
            self.query_one("#slider-bright", Slider).value = self.selected_device.brightness / 65535 * 100
            self.query_one("#slider-kelvin", Slider).value = self.selected_device.kelvin
            
            self.query_one("#color-preview", ColorPreview).update_color(
                self.selected_device.hue,
                self.selected_device.saturation,
                self.selected_device.brightness,
                self.selected_device.kelvin
            )
            self._updating = False
    
    def _refresh_sidebar_item(self) -> None:
        """Refresh the sidebar to show updated power state."""
        if self.selected_device:
            devices = list(self.lifx.devices.values())
            sidebar = self.query_one(DeviceSidebar)
            sidebar.update_devices(devices)


# =============================================================================
# Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='LIFX TUI Controller - Control your LIFX lights from the terminal'
    )
    parser.add_argument(
        '-s', '--subnet',
        default='192.168.64.0/24',
        help='Network subnet (default: 192.168.64.0/24)'
    )
    args = parser.parse_args()
    
    app = LIFXApp(subnet=args.subnet)
    app.run()


if __name__ == "__main__":
    main()
