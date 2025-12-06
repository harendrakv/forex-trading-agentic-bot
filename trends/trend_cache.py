import json
import os
from datetime import datetime

class TrendCache:
    def __init__(self, filename="trend_cache.json"):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.path = os.path.join(base_dir, filename)

        # create file if missing
        if not os.path.exists(self.path):
            with open(self.path, "w") as f:
                json.dump({}, f)
    def load(self):
        with open(self.path, "r") as f:
            return json.load(f)

    def save(self, data):
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def get_trend(self, timeframe, candle_time):
        data = self.load()
        key = f"{timeframe}_{candle_time}"
        return data.get(key)

    def save_trend(self, timeframe, candle_time, value):
        data = self.load()
        key = f"{timeframe}_{candle_time}"
        data[key] = value
        self.save(data)
