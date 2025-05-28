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
        while True:
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

