# scripts/run_bot.py
import logging
from datetime import datetime
import MetaTrader5 as mt5

from scripts.mt_client import MT5Client
from core.model_router import ModelRouter
from core.trade_logic import detect_trade, position_size_by_risk
from config.config_loader import load_config
from agents.trend_detector_agent import TrendDetectorAgent
from core.logging import init_logs, log_trade_open
from core.trade_closer import TradeCloser
from core.pnl_reporter import write_daily_pnl_report
from core.trade_manager import TradeManager
from core.cooldown import CooldownManager

cooldown = CooldownManager()

# -------------------------------
# UTF-8 FILTER
# -------------------------------
class SafeUTF8Filter(logging.Filter):
    def filter(self, record):
        # convert any unsupported dash-like unicode to "-"
        txt = str(record.msg)
        txt = txt.replace("\u2011", "-")
        txt = txt.replace("\u2013", "-")
        txt = txt.replace("\u2014", "-")
        record.msg = txt.encode("ascii", "ignore").decode("ascii")
        return True


# -------------------------------
# GLOBAL LOGGER
# -------------------------------
run_logger = logging.getLogger("bot")
run_logger.setLevel(logging.INFO)

# console handler
console = logging.StreamHandler()
console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
console.addFilter(SafeUTF8Filter())
run_logger.addHandler(console)

# file handler
file_handler = logging.FileHandler("logs/bot_runs.log")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
file_handler.addFilter(SafeUTF8Filter())
run_logger.addHandler(file_handler)

run_logger.propagate = False


# init other logs
init_logs()

# -----------------------------------
# MAIN EXECUTION LOOP (1 cycle)
# -----------------------------------
def run_cycle():


    run_logger.info("Bot run started.")

    cfg = load_config("config/settings.yaml")

    router = ModelRouter(cfg)
    
    client = MT5Client(
        login = cfg['mt5_login']['login'],
        password=cfg['mt5_login']['password'],
        server=cfg['mt5_login']['server'],
    )
    client.connect()

    symbol = cfg["trade"]["symbol"]

    # Fetch candles
    df_ht = client.get_data(symbol, mt5.TIMEFRAME_M30)
    df1m = client.get_data(symbol, mt5.TIMEFRAME_M1)

    # Trend
    trend_agent = TrendDetectorAgent()
    trend_raw = trend_agent.detect_trend(df_ht)
    run_logger.info(f"Trend: {trend_raw}")

    # Build entry candidate
    candidate = detect_trade(df1m, trend_raw)

    run_logger.info(f"Candidate: {candidate}")

    # Model instructions
    context = f"""
        You are an objective, risk-aware trading analyst. Analyze the input data carefully as an expert. 
        You are provided details along with fibs levels and trend data from another agent. Return ONLY a JSON object:
        - final_decision: "buy"|"sell"|"skip"
        - entry: number
        - sl: number
        - tp: number
        - position_lots: number
        - confidence: number (0-1)
        - rationale: [three short strings]

        If unsure: final_decision="skip", return all numeric value null but confidence non null.

        Candidate:
        {candidate}
        """

    # Call LLMs
    if candidate is not None:
        groq_summary, final_json = router.groq_then_openai_for_final(context)
        final = final_json if final_json else groq_summary

        run_logger.info(f"Final decision: {final}")
    else:
        final = {"final_decision": "skip"}
        run_logger.info("No valid candidate, skipping trade decision.")

    # ----------------------------------
    # EXECUTE TRADE
    # ----------------------------------

    if final["final_decision"] in ["buy", "sell"]:
        trade_type = final.get("type", final["final_decision"])   # breakout_buy / pullback_buy etc.
        direction = final["final_decision"]
        entry = final["entry"]

        if not cooldown.allowed(
            trade_type=trade_type,
            direction=direction,
            entry_price=entry,
            direction_cooldown_minutes=8,
            type_cooldown_minutes=12,
            price_scope=0.15  # adjust based on symbol volatility
        ):
            run_logger.info(f"Cooldown active — skipping {trade_type}")
            return

        lot = position_size_by_risk(
            equity=client.get_balance(),
            risk_pct=cfg["risk"]["risk_per_trade_pct"],
            entry=final["entry"],
            stop=final["sl"],
            symbol_tick_value=client.get_tick_value(symbol)
        )

        order_type = mt5.ORDER_TYPE_BUY if final["final_decision"] == "buy" else mt5.ORDER_TYPE_SELL

        ticket = client.send_order(
            symbol=symbol,
            lot=lot,
            order_type=order_type,
            sl=final["sl"],
            tp=final["tp"]
        )

        if ticket:
            final["direction"] = final["final_decision"]
            final["atr"] = candidate.get("atr")
            final["confidence"] = candidate.get("confidence")

            if final["final_decision"] == "buy":
                final["rr"] = round((final["tp"] - final["entry"]) / (final["entry"] - final["sl"]), 2)
            else:
                final["rr"] = round((final["entry"] - final["tp"]) / (final["sl"] - final["entry"]), 2)

            log_trade_open(ticket, final)
            run_logger.info(f"Trade opened: {ticket}")

            cooldown.record(trade_type, direction, entry)

    else:
        run_logger.info("LLM -> SKIP")


    # ----------------------------------
    # CLOSE TRADE DETECTOR
    # ----------------------------------
    trade_closer = TradeCloser(client)
    trade_closer.check_and_log_closed()
    
    trade_manager = TradeManager(client)
    trade_manager.update_sl_for_open_trades(symbol)
    run_logger.info("Updated SLs for running positions if swing levels changed")

    # ----------------------------------
    # DAILY PNL REPORT (once per day)
    # ----------------------------------
    now = datetime.now()
    if now.hour == 23 and now.minute == 59:
        write_daily_pnl_report()
        run_logger.info("Daily PnL report saved.")
