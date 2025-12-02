import MetaTrader5 as mt5
import pandas as pd

class MT5Client:
    def __init__(self, login, password, server):
        self.login = login
        self.password = password
        self.server = server

    def connect(self):
    
        mt5.initialize()
        authorized = mt5.login(self.login, self.password, self.server)
        if not authorized:
            raise Exception("MT5 login failed")
        return True

    def get_data(self, symbol, timeframe, n=500):
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        return df

    def send_order(self, symbol, lot, order_type, sl, tp):
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "sl": sl,
            "tp": tp,
            "magic": 123456,
            "comment": "agentic-bot"
        }
        return mt5.order_send(request)
    def get_balance(self):
        account_info = mt5.account_info()
        return account_info.balance if account_info else 0.0
    
    def get_tick_value(self, symbol):
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return 1.0
        return symbol_info.trade_tick_value if symbol_info.trade_tick_value else 1.0
    def get_open_positions(self, symbol=None):
        """Return all open positions (or for a specific symbol)"""
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return []
        return positions
    def modify_order_sl(self, ticket, new_sl, tp):
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": new_sl,
            "tp": tp,
            "magic": 123456,
            "comment": "Modify SL by agentic-bot"
        }
        return mt5.order_send(request)