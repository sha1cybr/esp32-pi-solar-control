import aioble
import ds18x20
import onewire
import uasyncio as asyncio
from ble.client import BLEClient
from machine import Pin, deepsleep

from pizero.utils import connect_to_wifi

SAMPLE_INTERVAL = 5  # seconds
TEMP_THRESHOLD = 0.5 # celcius

# Define the GPIO pins connected to the DS18B20 sensors
SOLAR_PIN = 13
TANK_PIN = 14


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
 
def handle_message(obj):
    print(f"Gotr message from server {obj}")
    
# Background task to read temperatures
async def read_temperature_loop():
    faucet_closed = False
    solar_sensor = TemperatureSensor(SOLAR_PIN, "SOLAR")
    tank_sensor = TemperatureSensor(TANK_PIN, "TANK")
    
    from ble.new_client import Sensor
    new_client = Sensor(server="solar")
    await new_client.advertise()
    
    while True:
        try:
            solar_temp = await solar_sensor.read_temp()
            tank_temp = await tank_sensor.read_temp()
            
            print(f"SOLAR: {solar_temp}°C, TANK: {tank_temp}°C")
            should_open = solar_temp + TEMP_THRESHOLD > tank_temp
            
            payload = {
                "solar": solar_temp,
                "tank": tank_temp,
                "faucet_closed": not should_open
            }
            
            # Need to make sure this is read!
            new_client.send_json(payload)
            
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

