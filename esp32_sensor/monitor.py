import aioble
import ds18x20
import onewire
import uasyncio as asyncio
from ble.client import BLEClient
from ble.new_client import Sensor
from machine import Pin, deepsleep

SAMPLE_INTERVAL = 60 * 3  # seconds
TEMP_THRESHOLD = 0.5 # celcius

# Define the GPIO pins connected to the DS18B20 sensors / valve control
SOLAR_PIN = 13
TANK_PIN = 14
VALVE_CONTROL_PIN = 15

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
        self._pin.value(0)
        self._is_open: bool = False

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

    def _close(self):
        if not self._is_open:
            print("Valve already closed")
            return
        
        print("Closing valve")
        self._is_open = False
        self._pin.value(0)

    @property
    def is_open(self):
        return self._is_open

def handle_message(obj):
    print(f"Gotr message from server {obj}")
    
# Background task to read temperatures
async def read_temperature_loop():
    solar_sensor = TemperatureSensor(SOLAR_PIN, "SOLAR")
    tank_sensor = TemperatureSensor(TANK_PIN, "TANK")
    valve = ValveControl()

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
            
            # Need to make sure this is read!
            await new_client.send_json(payload)
            
        except Exception as e:
            print("Error reading temperature:", e)
            
        deepsleep(SAMPLE_INTERVAL * 1000)
        #await asyncio.sleep(SAMPLE_INTERVAL)

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

