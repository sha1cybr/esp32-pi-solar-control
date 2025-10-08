import sys

# ruff: noqa: E402
sys.path.append("")

import asyncio
import json

import aioble
import bluetooth
from micropython import const

# org.bluetooth.service.environmental_sensing
_ENV_SENSE_UUID = bluetooth.UUID(0x181A)
# org.bluetooth.characteristic.temperature
_ENV_SENSE_TEMP_UUID = bluetooth.UUID(0x2A6E)
# org.bluetooth.characteristic.gap.appearance.xml
_ADV_APPEARANCE_GENERIC_THERMOMETER = const(768)
_ADV_INTERVAL_MS = 250_000

_PI_SERVICE_UUID = bluetooth.UUID("12345678-1234-1234-1234-123456789abc")
_COMMAND_CHAR_UUID = bluetooth.UUID("87654321-4321-4321-4321-cba987654321")

class Sensor:
    def __init__(self, server="solar"):
        self._service = aioble.Service(_ENV_SENSE_UUID)
        self._temp_char = aioble.Characteristic(self._service, _ENV_SENSE_TEMP_UUID, read=True, notify=True)
        self._server = server
        
        aioble.register_services(self._service)
        self._event = asyncio.Event()
    
    async def send_json(self, obj):
        print(f"Publishing {obj}")
        self._event.clear()
        self._temp_char.write(json.dumps(obj), send_update=True)
        await self._event.wait()
    
    async def advertise(self):
        asyncio.create_task(self._advertise_task())
        
    async def _advertise_task(self):
        async with await aioble.advertise(
            _ADV_INTERVAL_MS,
            name=self._server,
            services=[_ENV_SENSE_UUID],
            appearance=_ADV_APPEARANCE_GENERIC_THERMOMETER,
        ) as connection:
            print("Connection from", connection.device)
            await connection.disconnected(timeout_ms=None)
            self._event.set()
            print("Disconnected", connection.device)
                
    async def scan_and_read_commands(self, callback, server_name="pi"):
        print("Scanning for 'pi' service...")
        async with aioble.scan(duration_ms=2000, interval_us=30000, window_us=30000, active=True) as scanner:
            async for result in scanner:
                if result.name() == server_name:
                    print("Found pi device!")
                    try:
                        # Connect
                        connection = await result.device.connect(timeout_ms=5000)
                        print("Connected to", result.device)
                        try:
                            await connection.exchange_mtu(256)
                        except:
                            pass
                        
                        # Discover service
                        service = await connection.service(_PI_SERVICE_UUID)
                        
                        if not service:
                            print("Service not found")
                            await connection.disconnect()
                            continue

                        # Discover characteristic
                        command_char = await service.characteristic(_COMMAND_CHAR_UUID)
                        if not command_char:
                            print("Command characteristic not found")
                            await connection.disconnect()
                            continue

                        # Read the characteristic
                        while True:
                            value = await command_char.read()
                            cmd = json.loads(value)
                            if cmd.get('type') != 'eof':
                                print("Command value:", value)
                                await callback(cmd)
                            else:
                                print("End of commands")
                                break

                        await connection.disconnect()
                        return json.loads(value)

                    except Exception as e:
                        print("Error:", e)
                        sys.print_exception(e)

        print("No 'pi' service found")
        return None



