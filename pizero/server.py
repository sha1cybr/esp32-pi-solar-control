#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import socket

import aiohttp_cors
# Web server imports
from aiohttp import web
# BLE imports
from bleak import BleakClient, BleakScanner
from pydantic import BaseModel

from solar_logger.solar_logger import SolarEventLogger

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TARGET_SERVICE_UUID = "0000181a-0000-1000-8000-00805f9b34fb"
TEMPERATURE_CHAR_UUID = "00002a6e-0000-1000-8000-00805f9b34fb"

class Metrics(BaseModel):
    solar: float = 0.0
    tank: float = 0.0
    faucet_closed: bool = False
    timestamp: int = 0

class TemperatureServer:
    """Combined BLE and Web Server implementation for Raspberry Pi"""
    
    def __init__(self, name="Raspberry Pi Server", web_port=8080):
        self.name = name
        self.web_port = web_port

        self._solar_logger = SolarEventLogger()
        self._last_known_metrics = Metrics()
    
    async def start(self):
        """Start both servers"""
        # Start both servers concurrently
        await asyncio.gather(
            self.start_web_server(),
            self.start_ble_discovery()
        )
    
    async def start_ble_discovery(self):
        logger.info("Starting BLE discovery...")
        
        while True:
            try:
                devices = await BleakScanner.discover(timeout=5.0)

                target_device = None
                for device in devices:
                    if TARGET_SERVICE_UUID in device.metadata.get("uuids", []):
                        target_device = device
                        logger.info(f"Found matching device: {device.name} ({device.address})")
                        break

                if not target_device:
                    logger.info("No device with Environmental Sensing Service found.")
                    continue

                async with BleakClient(target_device.address) as client:
                    logger.info(f"Connected to {target_device.name}")
                    # logger.info("Services and characteristics:")

                    # for service in client.services:
                    #     logger.info(f"- Service: {service.uuid}")
                    #     for char in service.characteristics:
                    #         logger.info(f"  - Char: {char.uuid} | Properties: {char.properties}")

                    try:
                        temperature_bytes = await client.read_gatt_char(TEMPERATURE_CHAR_UUID)
                        payload = json.loads(temperature_bytes.decode('utf-8'))
                        logger.info(f"Payload: {payload}")
                        if self._last_known_metrics.faucet_closed != payload.get("faucet_closed", False): 
                            logger.info("Faucet closed")
                            self._solar_logger.add_faucet_event(self._last_known_metrics.faucet_closed)

                        self._last_known_metrics.faucet_closed = payload.get("faucet_closed", False)
                        self._last_known_metrics.solar = payload.get("solar", 0.0)
                        self._last_known_metrics.tank = payload.get("tank", 0.0)
                        self._last_known_metrics.timestamp = payload.get("timestamp", 0)
                        self._solar_logger.add_reading(self._last_known_metrics.solar, self._last_known_metrics.tank)
                    except Exception as e:
                        logger.info(f"Failed to read temperature: {e}")
            except Exception as e:
                logger.error(f"BLE discovery error: {e}")
    
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
        logger.info(f"Starting web server on port {self.web_port}...")
        
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
        app.router.add_static('/static/', path='static', name='static')

        # Add API routes
        api_routes = [
            web.get('/api/status', self.handle_status),
            web.get('/api/data', self.handle_get_data)
        ]
        
        # Apply CORS to all API routes
        for route in api_routes:
            app.router.add_route(route.method, route.path, route.handler)
            cors.add(app.router.add_resource(route.path))
        
        # Start the web server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.web_port)
        await site.start()
        
        logger.info(f"Web server running at http://{self.get_local_ip()}:{self.web_port}")
        
        # Keep the server running
        while True:
            await asyncio.sleep(3600)  # Just keep it alive
    
    # Web Server Handlers
    async def handle_index(self, request):
        """Handle requests to the root URL"""
        # Redirect to the static index.html
        return web.FileResponse(os.path.join("static", "index.html"))
    
    async def handle_status(self, request):
        """Handle status API requests"""
        return web.json_response(self._last_known_metrics.model_dump())
    
    async def handle_get_data(self, request):
        # Get all queryparams from the request
        query_params = request.query
        timeframe = query_params.get('timeframe', 'week')
        
        if 'timeframe' in query_params:
            timeframe = query_params['timeframe']

        # Get data for the specified timeframe
        filtered_data = self._solar_logger.get_data(timeframe)
        # Return the JSON data as a response
        return web.json_response(filtered_data)
    
    async def stop(self):
        """Stop all servers"""
        logger.info("Stopping servers...")
        
        # Stop BLE server
        self.ble_running = False


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
        logger.error(f"Server error: {e}")
    finally:
        try:
            await server.stop()
        except Exception as e:
            logger.error(f"Error stopping server: {e}")


if __name__ == "__main__":
    # Run the server
    asyncio.run(main())