import os
import csv
from datetime import datetime

LOG_DIR = "logs"
OPEN_FILE = os.path.join(LOG_DIR, "trades.csv")
CLOSED_FILE = os.path.join(LOG_DIR, "closed_trades.csv")


def init_logs():
    """Ensure folders + CSV files are initialized with headers."""
    os.makedirs(LOG_DIR, exist_ok=True)

    if not os.path.exists(OPEN_FILE):
        with open(OPEN_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "ticket", "direction", "entry", "sl", "tp", 
                "atr", "rr", "confidence", "status"
            ])

    if not os.path.exists(CLOSED_FILE):
        with open(CLOSED_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp_open", "timestamp_close", "ticket", 
                "direction", "entry", "exit_price",
                "sl", "tp", "pnl", "atr", "rr", "confidence"
            ])
def log_trade_open(ticket, trade):
    with open(OPEN_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ticket,
            trade["direction"],
            trade["entry"],
            trade["sl"],
            trade["tp"],
            trade["atr"],
            trade.get("rr", None),
            trade.get("confidence", None),
            "OPEN"
        ])


def log_trade_close(ticket, trade, exit_price, pnl):
    with open(CLOSED_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            trade.get("timestamp_open", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ticket,
            trade["direction"],
            trade["entry"],
            exit_price,
            trade["sl"],
            trade["tp"],
            pnl,
            trade["atr"],
            trade.get("rr", None),
            trade.get("confidence", None)
        ])