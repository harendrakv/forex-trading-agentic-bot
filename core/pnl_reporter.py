import MetaTrader5 as mt5
from datetime import datetime, timedelta

def write_daily_pnl_report():
    today = datetime.now().date()
    start = datetime(today.year, today.month, today.day)
    end = start + timedelta(days=1)

    deals = mt5.history_deals_get(start, end)
    if deals is None:
        return

    profit = sum([d.profit for d in deals])
    print(f"Daily PnL for {today}: {profit}")
    with open("logs/daily_pnl.csv", "a") as f:
        f.write(f"{today},{profit}\n")
