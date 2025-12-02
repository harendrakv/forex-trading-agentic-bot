import MetaTrader5 as mt5
from datetime import datetime
import json
import os

from core.logging import log_trade_close

OPEN_FILE = "logs/open_trades.json"

class TradeCloser:
    def __init__(self, client):
        self.client = client

    def load_open_trades(self):
        if not os.path.exists(OPEN_FILE):
            return {}
        with open(OPEN_FILE, "r") as f:
            return json.load(f)

    def save_open_trades(self, data):
        with open(OPEN_FILE, "w") as f:
            json.dump(data, f, indent=4)

    def check_and_log_closed(self):
        # Get complete history
        closed = mt5.history_deals_get(datetime(2022, 1, 1), datetime.now())
        if closed is None:
            return

        open_trades = self.load_open_trades()

        for deal in closed:
            if deal.entry == mt5.DEAL_ENTRY_OUT:  # closed trade

                ticket = deal.position_id  # closing deal refers to position ID
                exit_price = deal.price
                pnl = deal.profit

                if str(ticket) not in open_trades:
                    continue  # we don't know this trade, skip

                original_trade = open_trades[str(ticket)]

                # Log close with full details
                log_trade_close(
                    ticket=ticket,
                    trade=original_trade,
                    exit_price=exit_price,
                    pnl=pnl,
                )

                # remove from open_trades after closing
                del open_trades[str(ticket)]

        # save updated open trades
        self.save_open_trades(open_trades)
