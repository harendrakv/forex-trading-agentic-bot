# scripts/run_bot.py
import logging
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
from trends.trend_multi_tf import MultiTFTrend
from core.micro_trade_detector import generate_mean_reversion_signal
from core.scalp_detector import detect_scalp
from templates.final_prompt import FINAL_PROMPT
import json

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

import datetime
# --- GLOBAL STATE VARIABLES ---
LAST_M15_CHECK_TIME = datetime.datetime.min
M15_INTERVAL_SECONDS = 900 # 15 minutes

def run_cycle():
    global LAST_M15_CHECK_TIME 
    
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
    
    # --- 1. Fetch M1 data for all M1/M15/H1 analysis ---
    df1m = client.get_data(symbol, mt5.TIMEFRAME_M1)

    # --- 2. Determine High-Timeframe Trend ---
    trend_manager = MultiTFTrend(client, run_logger)
    trend_raw = trend_manager.get_final_trend(symbol)
    run_logger.info(f"Combined Trend: {trend_raw}")

    candidate = None # Initialize candidate

    # ------------------------------------------------------------------
    # --- PRIORITY 1: PRIMARY TRADE (Breakout/Pullback) ---
    # NOTE: You need to implement/define 'detect_trade' for this.
    # We will assume 'detect_trade' is the trend-following logic.
    # ------------------------------------------------------------------
    candidate = detect_trade(df1m, trend_raw) 
    
    # ------------------------------------------------------------------
    # --- PRIORITY 2: SECONDARY TRADE (M15 Mean Reversion) ---
    # --- Runs ONLY if Primary trade fails. ---
    # ------------------------------------------------------------------
    if not candidate:
        
        current_time = datetime.datetime.now()
        current_ts = int(current_time.timestamp())
        
        # Check time alignment for M15 close
        last_m15_close_ts = (current_ts // M15_INTERVAL_SECONDS) * M15_INTERVAL_SECONDS
        last_m15_close_time = datetime.datetime.fromtimestamp(last_m15_close_ts)
        
        if last_m15_close_time > LAST_M15_CHECK_TIME:
            
            # Trend Check: Run if confidence is low (indicates Range/Weak Trend)
            if trend_raw.get("confidence", 100) < 75:
                run_logger.info("Primary skipped. Running M15 Mean Reversion check (Secondary)...")
                
                # Fetch M15 and H1 data 
                df15m = client.get_data(symbol, mt5.TIMEFRAME_M15)
                df1H = client.get_data(symbol, mt5.TIMEFRAME_H1)
                
                candidate = generate_mean_reversion_signal(df15m, df1H)
                
                if candidate and candidate.get("direction") != "none":
                    candidate['trend_raw'] = trend_raw
                    
                LAST_M15_CHECK_TIME = last_m15_close_time
            else:
                run_logger.info(f"Mean Reversion skipped: Trend is strong ({trend_raw.get('confidence', 100)}%).")
        else:
            run_logger.info("Mean Reversion skipped: M15 candle has not closed yet.")
            
    # ------------------------------------------------------------------
    # --- PRIORITY 3: TERTIARY TRADE (M1 Scalp Detector) ---
    # --- Runs ONLY if Primary and Secondary trades fail. ---
    # ------------------------------------------------------------------
    if not candidate:
        run_logger.info("Primary & Secondary skipped. Running M1 Scalp check (Tertiary)...")
        # Use the highly refined detect_scalp logic here
        candidate = detect_scalp(df1m, trend_raw)
        
        if candidate and candidate.get("direction") != "none":
            candidate['trend_raw'] = trend_raw


    run_logger.info(f"Candidate: {candidate}")
    
    # Call LLMs
    # Check if a valid trade candidate was found by ANY of the three strategies
    if candidate is not None and candidate.get("direction") != "none":
        candidate_json_string = json.dumps(candidate, indent=2)
        prompt = FINAL_PROMPT.format(candidate=candidate_json_string)
        groq_summary, final_json = router.groq_then_openai_for_final(prompt)
        final = final_json if final_json else groq_summary

        run_logger.info(f"Final decision: {final}")
    else:
        final = {"final_decision": "skip"}
        run_logger.info("No valid candidate, skipping trade decision.")
    
    # ----------------------------------
    # EXECUTE TRADE (Rest of the code remains the same)
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
    now = datetime.datetime.now()
    if now.hour == 23 and now.minute == 59:
        write_daily_pnl_report()
        run_logger.info("Daily PnL report saved.")
