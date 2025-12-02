# core/cooldown_manager.py

from datetime import datetime, timedelta

class CooldownManager:
    def __init__(self):
        self.last_trade_time = {
            "buy": None,
            "sell": None,
            "breakout_buy": None,
            "breakout_sell": None,
            "pullback_buy": None,
            "pullback_sell": None,
        }

        self.last_entry_price = {
            "buy": None,
            "sell": None,
        }

    def allowed(self, trade_type, direction, entry_price,
                direction_cooldown_minutes=8,
                type_cooldown_minutes=12,
                price_scope=5):
        """
        price_scope = minimum distance between current entry & last entry.
        """

        now = datetime.now()

        # ----------- 1) DIRECTION COOLDOWN -------------
        last_dir_time = self.last_trade_time.get(direction)
        if last_dir_time:
            if now - last_dir_time < timedelta(minutes=direction_cooldown_minutes):
                return False

        # ----------- 2) TRADE-TYPE COOLDOWN -------------
        last_type_time = self.last_trade_time.get(trade_type)
        if last_type_time:
            if now - last_type_time < timedelta(minutes=type_cooldown_minutes):
                return False

        # ----------- 3) PRICE-BASED COOLDOWN -------------
        last_price = self.last_entry_price.get(direction)
        if last_price:
            if abs(entry_price - last_price) < price_scope:
                # too close to previous entry price
                return False

        return True

    def record(self, trade_type, direction, entry_price):
        now = datetime.now()
        self.last_trade_time[direction] = now
        self.last_trade_time[trade_type] = now
        self.last_entry_price[direction] = entry_price
