#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import socket
from typing import Any

import aiohttp_cors
# Web server imports
from aiohttp import web
# BLE imports
from bleak import BleakClient, BleakScanner
from bless import BlessGATTCharacteristic, BlessServer, GATTAttributePermissions, GATTCharacteristicProperties
from pydantic import BaseModel

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress known bleak/dbus issues that don't affect functionality
logging.getLogger('dbus_fast.message_bus').setLevel(logging.CRITICAL)
logging.getLogger('bleak.backends.bluezdbus.manager').setLevel(logging.CRITICAL)

TARGET_SERVICE_UUID = "0000181a-0000-1000-8000-00805f9b34fb"
TEMPERATURE_CHAR_UUID = "00002a6e-0000-1000-8000-00805f9b34fb"

# Pi peripheral service and characteristic UUIDs
PI_SERVICE_UUID = "12345678-1234-1234-1234-123456789abc"
COMMAND_CHAR_UUID = "87654321-4321-4321-4321-cba987654321"

def command_read_request(characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
    """Handle read requests for the command characteristic"""
    logger.debug(f"BLE client reading command characteristic: {characteristic.value}")
    return characteristic.value

class Metrics(BaseModel):
    solar: float = 0.0
    tank: float = 0.0
    faucet_closed: bool = False
    timestamp: int = 0

class Command(BaseModel):
    type: str
    value: Any

class TemperatureServer:
    """Combined BLE and Web Server implementation for Raspberry Pi"""
    
    def __init__(self, name="Raspberry Pi Server", web_port=8080):
        self._name = name
        self._web_port = web_port
        self._last_known_metrics = Metrics()
        self._current_command = []  # Changed to list for command queue
        self._ble_server = None

        self._command_ready_event = asyncio.Event()
        self._command_read_event = asyncio.Event()

    
    async def start(self):
        """Start both servers"""
        # Start all servers concurrently
        await asyncio.gather(
            self.start_web_server(),
            self.start_ble_discovery(),
            self.start_ble_peripheral()
        )

    async def start_ble_discovery(self):
        logger.info("Starting BLE discovery...")
        
        while True:
            try:
                devices = await BleakScanner.discover(timeout=5.0)

                target_device = None
                for device in devices:
                    try:
                        if hasattr(device, 'metadata') and device.metadata and TARGET_SERVICE_UUID in device.metadata.get("uuids", []):
                            target_device = device
                            logger.info(f"Found matching device: {device.name} ({device.address})")
                            break
                        elif device.name == 'solar':
                            target_device = device
                            logger.info(f"Found device by name: {device.name} ({device.address})")
                            break
                    except (AttributeError, KeyError) as e:
                        # Skip devices that cause issues
                        logger.debug(f"Skipping problematic device: {e}")
                        continue
                        
                if not target_device:
                    logger.info("No device with Environmental Sensing Service found.")
                    await asyncio.sleep(2)  # Wait before retrying
                    continue

                async with BleakClient(target_device.address) as client:
                    logger.info(f"Connected to {target_device.name}")

                    try:
                        temperature_bytes = await client.read_gatt_char(TEMPERATURE_CHAR_UUID)
                        payload = json.loads(temperature_bytes.decode('utf-8'))
                        logger.info(f"Payload: {payload}")
                        self._last_known_metrics.faucet_closed = payload.get("faucet_closed", False)
                        self._last_known_metrics.solar = payload.get("solar", 0.0)
                        self._last_known_metrics.tank = payload.get("tank", 0.0)
                        self._last_known_metrics.timestamp = int(asyncio.get_event_loop().time())
                    except Exception as e:
                        logger.info(f"Failed to read temperature: {e}")
                        
                # Wait before next reading
                await asyncio.sleep(20)
                    
            except Exception as e:
                logger.error(f"BLE discovery error: {e}")
                await asyncio.sleep(10)  # Wait longer on error
    
    def _command_read_request(self, characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
        """Handle read requests for the command characteristic"""
        logger.debug(f"BLE client reading command characteristic: {characteristic.value}")
        self._command_read_event.set()
        return characteristic.value
    
    async def start_ble_peripheral(self):
        """Start the BLE peripheral server"""
        logger.info("Starting BLE peripheral...")
        
        while True:
            await self._command_ready_event.wait()

            try:
                # Initialize BLE server with the current loop (using working configuration)
                self._ble_server = BlessServer(name="pi", loop=asyncio.get_running_loop())
                self._ble_server.read_request_func = self._command_read_request
                self._ble_server.write_request_func = self._command_write_request

                # Add the Pi service
                await self._ble_server.add_new_service(PI_SERVICE_UUID)
                logger.info(f"Added service: {PI_SERVICE_UUID}")
                
                # Add the command characteristic with working flags and permissions
                char_flags = (GATTCharacteristicProperties.read | 
                            GATTCharacteristicProperties.write | 
                            GATTCharacteristicProperties.notify)
                permissions = GATTAttributePermissions.readable | GATTAttributePermissions.writeable
                
                await self._ble_server.add_new_characteristic(
                    PI_SERVICE_UUID,
                    COMMAND_CHAR_UUID,
                    char_flags,
                    bytearray(json.dumps({"type": "none", "value": ""}).encode('utf-8')),  # Set initial value
                    permissions
                )
                logger.info(f"Added characteristic: {COMMAND_CHAR_UUID}")
                
                # Start the server
                await self._ble_server.start()
                # Give it time to start advertising properly
                await asyncio.sleep(3)
                
                logger.info("=" * 60)
                logger.info("BLE PERIPHERAL STARTED SUCCESSFULLY!")
                logger.info("=" * 60)
                logger.info(f"Device Name: pi")
                logger.info(f"Service UUID: {PI_SERVICE_UUID}")
                logger.info(f"Characteristic UUID: {COMMAND_CHAR_UUID}")
                logger.info("The 'pi' service should now be visible in BLE scanners!")
                logger.info("=" * 60)

                # Keep the peripheral running and update characteristic when needed
                while self._current_command:  # Process all commands in queue
                    command = self._current_command.pop(0)  # Get first command
                    command_json = json.dumps(command.model_dump())
                    logger.info(f"Updating BLE characteristic with command: {command_json}")
                    
                    # Update the characteristic value
                    char = self._ble_server.get_characteristic(COMMAND_CHAR_UUID)
                    char.value = bytearray(command_json.encode('utf-8'))

                    # Wait for a read request from the client
                    await self._command_read_event.wait()
                    logger.info("BLE command characteristic was read by client.")
                    self._command_read_event.clear()

                # Send EOF command when no more commands
                if not self._current_command:
                    eof_command = {"type": "eof", "value": ""}
                    eof_json = json.dumps(eof_command)
                    logger.info(f"Sending EOF command: {eof_json}")
                    
                    char = self._ble_server.get_characteristic(COMMAND_CHAR_UUID)
                    char.value = bytearray(eof_json.encode('utf-8'))
                    
                    # Wait for EOF to be read
                    await self._command_read_event.wait()
                    logger.info("EOF command was read by client.")
                    self._command_read_event.clear()

            except Exception as e:
                logger.error(f"BLE peripheral initialization error: {e}")
                logger.warning("BLE peripheral functionality will be disabled.")
                self._ble_server = None
            finally:
                if self._ble_server:
                    await self._ble_server.stop()
                    logger.info("BLE peripheral stopped")

            self._command_ready_event.clear()
        
    
    def _command_write_request(self, characteristic, value, **kwargs):
        """Handle BLE write requests to the command characteristic"""
        try:
            # Decode the received command
            command_str = value.decode('utf-8')
            logger.info(f"BLE command received: {command_str}")
            
            # Parse JSON command
            command_data = json.loads(command_str)
            command = Command(**command_data)
            
            # Add the command to the queue
            self._current_command.append(command)
            
            logger.info(f"BLE command added to queue: {command.model_dump()}")
            
        except Exception as e:
            logger.error(f"Error processing BLE write request: {e}")
        
        # Update the characteristic value to confirm receipt
        characteristic.value = value
    
    def get_local_ip(self):
        try:
            # Create a temporary socket to an external address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Use Google's DNS server
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            return f"Error: {e}"
    
    async def start_web_server(self):
        """Start the web server"""
        logger.info(f"Starting web server on port {self._web_port}...")
        
        # Create the web application
        app = web.Application()
        
        # Set up CORS to allow all origins (for API access)
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*"
            )
        })
        
        # Set up routes
        app.router.add_get('/', self.handle_index)
        # Get static path relative to this file
        static_path = os.path.join(os.path.dirname(__file__), 'static')
        app.router.add_static('/static/', path=static_path, name='static')

        # Add API routes with CORS
        app.router.add_get('/api/metrics', self.handle_get_metrics)
        app.router.add_get('/api/command', self.handle_get_command)
        app.router.add_post('/api/command', self.handle_post_command)
        
        # Add CORS to all routes
        for resource in app.router.resources():
            cors.add(resource)
        
        # Start the web server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self._web_port)
        await site.start()
        
        logger.info(f"Web server running at http://{self.get_local_ip()}:{self._web_port}")
        
        # Keep the server running
        while True:
            await asyncio.sleep(3600)  # Just keep it alive
    
    # Web Server Handlers
    async def handle_index(self, request):
        """Handle requests to the root URL"""
        # Redirect to the static index.html
        return web.FileResponse(os.path.join("static", "index.html"))
    
    async def handle_get_metrics(self, request):
        """Handle status API requests"""
        return web.json_response(self._last_known_metrics.model_dump())
    
    async def handle_get_command(self, request):
        """Handle GET /api/command requests"""
        if self._current_command:
            # Return all commands in queue
            commands = [cmd.model_dump() for cmd in self._current_command]
            return web.json_response({"commands": commands, "count": len(commands)})
        else:
            return web.json_response({"commands": [], "count": 0})
    
    async def handle_post_command(self, request):
        """Handle POST /api/command requests"""
        try:
            data = await request.json()
            
            # Validate the command structure
            if "type" not in data or "value" not in data:
                return web.json_response(
                    {"error": "Command must have 'type' and 'value' fields"}, 
                    status=400
                )
            
            # Create command object
            command = Command(type=data["type"], value=data["value"])
            self._current_command.append(command)  # Add to queue
            logger.info(f"New command added to queue: {command.model_dump()}")
            logger.info(f"Command queue length: {len(self._current_command)}")
            self._command_ready_event.set()

            return web.json_response({
                "success": True, 
                "command": command.model_dump(),
                "queue_length": len(self._current_command)
            })
            
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"Error handling command: {e}")
            return web.json_response({"error": str(e)}, status=500)

    
    async def stop(self):
        """Stop all servers"""
        logger.info("Stopping servers...")
        
        # Stop BLE peripheral
        if self._ble_server:
            try:
                await self._ble_server.stop()
                logger.info("BLE peripheral stopped")
            except Exception as e:
                logger.error(f"Error stopping BLE peripheral: {e}")


# Example usage
async def main():
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Combined BLE and Web Server")
    parser.add_argument("--port", type=int, default=8080, help="Web server port")
    parser.add_argument("--name", type=str, default="solar", help="BLE device name")
    args = parser.parse_args()
    
    # Create and start the server
    server = TemperatureServer(
        name=args.name,
        web_port=args.port
    )
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Server interrupted")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
    finally:
        try:
            await server.stop()
        except Exception as e:
            logger.error(f"Error stopping server: {e}")


if __name__ == "__main__":
    # Run the server
    asyncio.run(main())