import json
import os
import sys
import time

import aioble
import ds18x20
import neopixel
import onewire
import uasyncio as asyncio
from ble_client import Sensor
from machine import Pin, deepsleep

TEMP_THRESHOLD = 0.5 # celcius
NUM_LEDS = 1
DATA_PIN = 5
# Define the GPIO pins connected to the DS18B20 sensors / valve control
SOLAR_PIN = 13
TANK_PIN = 14
VALVE_CONTROL_PIN = 15

# File to store general state
STATE_FILE = "device_state.json"

np = neopixel.NeoPixel(Pin(DATA_PIN), NUM_LEDS)

def set_pixel(r, g, b, brightness=0.05):
    """brightness: 0.0–1.0"""
    r = int(r * brightness)
    g = int(g * brightness)
    b = int(b * brightness)
    np[0] = (r, g, b)
    np.write()

class StateManager:
    """Manages persistent state across deep sleep cycles"""
    
    def __init__(self):
        self.state = {
            'valve_open': False,
            'deepsleep_duration': 10,  # Default 10 seconds
        }
        self._load_state()
    
    def _load_state(self):
        """Load state from file"""
        try:
            with open(STATE_FILE, 'r') as f:
                saved_state = json.load(f)
                self.state.update(saved_state)
                print(f"Loaded state from file: {self.state}")
        except (OSError, ValueError, KeyError):
            print("No valid state file found, using defaults")
            self._save_state()  # Create initial state file
    
    def _save_state(self):
        """Save state to file"""
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f)
            print(f"Saved state: {self.state}")
        except OSError as e:
            print(f"Error saving state: {e}")
    
    def get(self, key, default=None):
        """Get a state value"""
        return self.state.get(key, default)
    
    def set(self, key, value):
        """Set a state value and persist it"""
        self.state[key] = value
        self._save_state()
    
    def update(self, updates):
        """Update multiple state values and persist them"""
        self.state.update(updates)
        self._save_state()

# Global state manager
state_manager = StateManager()

class TemperatureSensor:
    def __init__(self, pin, name):
        self.name = name
        self.ow = onewire.OneWire(Pin(pin))
        self.ds = ds18x20.DS18X20(self.ow)
        self.roms = self.ds.scan()
        print(f'Found {name} DS18B20 devices:', self.roms)
        
    async def read_temp(self):
        if not self.roms:
            return None
            
        self.ds.convert_temp()
        await asyncio.sleep(1)  # Allow time for conversion
        
        for rom in self.roms:
            temp = self.ds.read_temp(rom)
            return round(temp, 2)
        return None
 
class ValveControl:
    def __init__(self, pin: int = VALVE_CONTROL_PIN):
        self._pin = Pin(pin, Pin.OUT)
        
        # Load persisted state
        self._is_open = state_manager.get('valve_open', False)
        
        # Set the physical pin to match the persisted state
        self._pin.value(1 if self._is_open else 0)
        print(f"Valve initialized - State: {'Open' if self._is_open else 'Closed'}")
    
    def toggle(self, open: bool):
        try:
            if open:
                self._open()
            else:
                self._close()
        except Exception as e:
            print("Error toggling valve:", e)
    
    def _open(self):
        if self._is_open:
            print("Valve already open")
            return
        
        print("Opening valve")
        self._is_open = True
        self._pin.value(1)
        state_manager.set('valve_open', True)
    
    def _close(self):
        if not self._is_open:
            print("Valve already closed")
            return
        
        print("Closing valve")
        self._is_open = False
        self._pin.value(0)
        state_manager.set('valve_open', False)
    
    @property
    def is_open(self):
        return self._is_open

def handle_command(cmd):
    """Handle incoming commands"""
    if not cmd or not isinstance(cmd, dict):
        return
    
    cmd_type = cmd.get('type')
    
    if cmd_type == 'deepsleep_duration':
        duration = cmd.get('value')
        if duration and isinstance(duration, (int, float)) and duration > 0:
            print(f"Setting deepsleep_duration to {duration} seconds")
            state_manager.set('deepsleep_duration', duration)
        else:
            print("Invalid deepsleep_duration value")
    else:
        print(f"Unknown command type: {cmd_type}")

# Background task to read temperatures
async def read_temperature_loop():
    solar_sensor = TemperatureSensor(SOLAR_PIN, "SOLAR")
    tank_sensor = TemperatureSensor(TANK_PIN, "TANK")
    valve = ValveControl()
    set_pixel(255, 0, 0)
            
    new_client = Sensor(server="solar")
    await new_client.advertise()
    
    while True:
        try:
            
            solar_temp = await solar_sensor.read_temp()
            tank_temp = await tank_sensor.read_temp()
            
            print(f"SOLAR: {solar_temp}°C, TANK: {tank_temp}°C")
            should_open = solar_temp + TEMP_THRESHOLD > tank_temp
            valve.toggle(should_open)
            payload = {
                "solar": solar_temp,
                "tank": tank_temp,
                "faucet_closed": not should_open
            }
            
            set_pixel(0, 255, 0)
            # Need to make sure this is read!
            await new_client.send_json(payload)
            print("Reading commands from pi")
            cmd = await new_client.scan_and_read_command()
            if cmd:
                print(f"Got command {json.dumps(cmd)}")
                handle_command(cmd)
            
            set_pixel(0, 0, 0)
            
        except Exception as e:
            print("Error reading temperature:", e)
            sys.print_exception(e)
        
        # Use the persistent sample interval
        deepsleep_duration = state_manager.get('deepsleep_duration', 10)
        print(f"Going to deep sleep for {deepsleep_duration} seconds")
        deepsleep(deepsleep_duration * 1000)

async def main():
    # Start temperature reading task
    task = asyncio.create_task(read_temperature_loop())
    
    await task

def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program stopped by user")

# Start the application if this file is executed directly
if __name__ == "__main__":
    run()
