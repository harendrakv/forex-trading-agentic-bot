import MetaTrader5 as mt5
from datetime import datetime
from .trade_logic import atr as calculate_atr

class TradeManager:
    def __init__(self, client, lookback=50):
        self.client = client
        self.lookback = lookback

    def update_sl_for_open_trades(self, symbol):
        positions = self.client.get_open_positions(symbol)
        if not positions:
            return

        df = self.client.get_data(symbol, mt5.TIMEFRAME_M1)
        df_recent = df.tail(self.lookback)

        for pos in positions:
            # MT5 position object: pos.ticket, pos.type, pos.price_open, pos.sl, pos.tp
            atr_val = calculate_atr(df_recent)
            if pos.type == mt5.ORDER_TYPE_BUY:
                new_swing_low = df_recent['low'].min()
                new_sl = new_swing_low - 0.2 * atr_val
                if new_sl > pos.sl:  # only move up
                    res = self.client.modify_order_sl(pos.ticket, new_sl, pos.tp)
                    if not res:
                        print(f"Failed to modify SL for ticket {pos.ticket}")

            elif pos.type == mt5.ORDER_TYPE_SELL:
                new_swing_high = df_recent['high'].max()
                new_sl = new_swing_high + 0.2 * atr_val
                if new_sl < pos.sl:  # only move down
                    res = self.client.modify_order_sl(pos.ticket, new_sl, pos.tp)
                    if not res:
                        print(f"Failed to modify SL for ticket {pos.ticket}")
