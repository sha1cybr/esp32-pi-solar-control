# esp32-pi-solar-control

A Python-based project for monitoring solar energy data using BLE sensors and displaying the information through a web server.

## Project Overview

This project collects data from BLE sensors, processes it through a monitoring system, and makes it available via a web server. The data appears to be related to solar energy logging.


## Project Structure

```
├── poetry.lock              # Poetry dependency lock file
├── pyproject.toml           # Poetry project configuration
├── README.md                # This file
├── esp32_sensor/            # BLE sensor communication modules
│   ├── ble_client.py        # Bluetooth LE client implementation
│   ├── monitor.py           # Sensor monitoring implementation
│   └── boot.py              # ESP32 boot file
├── pizero/                  # Core functionality
│   ├── __init__.py
│   ├── solar_logger         # Data logging implementation
│   ├── server.py            # Core logic for the dashboard/metric collection
│   └── static/              # Web UI assets
```

## Installation
### PI ZERO
Use the following to run the server.py on your pi zero (or any other microcomputer etc)

```bash
pip install poetry
poetry install
poetry run python server.py
```

The web interface will be available at http://localhost:8000 (or your configured port).

### ESP32
Use a serial-compatible Python IDE like [Thonny](https://thonny.org/) and push `esp32_sensor` to it.

## Dependencies

Dependencies are managed by Poetry. See 

pyproject.toml

 for the complete list.

## License

esp32-pi-solar-control is released under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
