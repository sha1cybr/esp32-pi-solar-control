import json
from time import time

DATA_FILE = 'temp_data.json'
FAUCET_EVENTS_FILE = 'faucet_events.json'

TIMESTAMP = 'ts'
SOLAR_TEMP = 's'
TANK_TEMP = 't'
CLOSED = "c"
MAX_DATA_AGE = 7 * 24 * 60 * 60  # 1 week in seconds

class SolarEventLogger:
    def __init__(self):
        self.data = []
        self.faucet_events = []
        self.load_data()
        
    def load_data(self):
        try:
            with open(DATA_FILE, 'r') as f:
                self.data = json.loads(f.read())
                print(f"Loaded {len(self.data)} data points")
        except (OSError, ValueError):
            print("No existing data file or invalid format")
            self.data = []
            
        try:
            with open(FAUCET_EVENTS_FILE, 'r') as f:
                self.faucet_events = json.loads(f.read())
                print(f"Loaded {len(self.faucet_events)} faucet events")
        except (OSError, ValueError):
            print("No existing faucet events file or invalid format")
            self.faucet_events = []
            
    def save_data(self):
        with open(DATA_FILE, 'w') as f:
            f.write(json.dumps(self.data))
            
        with open(FAUCET_EVENTS_FILE, 'w') as f:
            f.write(json.dumps(self.faucet_events))
            
    def add_reading(self, solar_temp=0, tank_temp=0):
        current_time = time()
        self.data.append({
            TIMESTAMP: current_time,
            SOLAR_TEMP: solar_temp,
            TANK_TEMP: tank_temp
        })
        
        # Maintain only 1 week of data
        cutoff_time = current_time - MAX_DATA_AGE
        self.data = [entry for entry in self.data if entry[TIMESTAMP] > cutoff_time]
        
        self.save_data()
        
    def add_faucet_event(self, closed):
        current_time = time()
        self.faucet_events.append({
            TIMESTAMP: current_time,
            CLOSED: closed
        })
        
        # Maintain only 1 week of faucet events
        cutoff_time = current_time - MAX_DATA_AGE
        self.faucet_events = [event for event in self.faucet_events if event[TIMESTAMP] > cutoff_time]
        
        self.save_data()
        
    def get_data(self, timeframe='hour'):
        current_time = time()
        
        if timeframe == 'day':
            cutoff = current_time - 24 * 60 * 60
        elif timeframe == 'hour':
            cutoff = current_time - 60 * 60
        elif timeframe == 'minute':
            cutoff = current_time - 60
        elif timeframe == 'week':
            cutoff = current_time - 7 * 24 * 60 * 60
        else:  # Default to all data within the week
            cutoff = current_time - MAX_DATA_AGE
            
        filtered_data = [entry for entry in self.data if entry[TIMESTAMP] > cutoff]
        filtered_events = [event for event in self.faucet_events if event[TIMESTAMP] > cutoff]
        
        return {
            "temperature_data": filtered_data,
            "faucet_events": filtered_events
        }