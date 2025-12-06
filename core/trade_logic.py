# core/trade_logic.py
import math
import pandas as pd
import numpy as np

def atr(df, n=14):
    df = df.copy()
    df['tr'] = np.maximum(df['high'] - df['low'],
                          np.maximum(abs(df['high'] - df['close'].shift()), abs(df['low'] - df['close'].shift())))
    return df['tr'].rolling(n).mean().iloc[-1]

def fib_levels(high, low):
    diff = high - low
    return {
        "38.2": high - diff * 0.382,
        "50": high - diff * 0.50,
        "61.8": high - diff * 0.618,
        "78.6": high - diff * 0.786,
        "1.2_ext": high + diff * 0.20
    }

def position_size_by_risk(equity, risk_pct, entry, stop, symbol_tick_value=1.0, pip_size=0.01):
    risk_amount = equity * (risk_pct / 100.0)
    pip_distance = abs(entry - stop) / pip_size
    if pip_distance == 0:
        return 0.0
    lot = risk_amount / (pip_distance * symbol_tick_value)
    return round(lot, 2)

def detect_breakout(df, trend_data, lookback=30):
    """
    Detect fresh breakout on df (assumes df timeframe is the entry TF like M1/M5).
    - Excludes the current candle when computing recent high/low.
    - Requires current close to exceed prior range (fresh breakout).
    - Uses momentum filter (body vs ATR).
    """
    trend = trend_data["trend"].lower()
    # safety
    if len(df) < lookback + 2:
        return None

    closes = df['close']
    close = float(closes.iloc[-1])
    prev_close = float(closes.iloc[-2])

    # compute range excluding current candle
    recent_high = float(df['high'].iloc[-lookback-1:-1].max())
    recent_low  = float(df['low'].iloc[-lookback-1:-1].min())

    atr_val = atr(df)
    if atr_val is None or atr_val <= 0:
        return None

    # momentum (real body) relative to ATR
    body = abs(close - float(df['open'].iloc[-1]))
    strong_momentum = body >= 0.45 * atr_val

    # require breakout candle to close beyond prior range by a tiny buffer
    breakout_buffer = 0.0005  # 0.05% buffer; adjust for each symbol if needed

    # ---------------------------
    # BULLISH BREAKOUT
    # ---------------------------
    if trend == "bullish":
        # fresh breakout: current close > prior high (excluding current)
        if close > recent_high * (1 + breakout_buffer) and prev_close <= recent_high * (1 + breakout_buffer) and strong_momentum:
            sl = float(df['low'].iloc[-5:].min())
            tp = close + 2.5 * atr_val

            # sanity: SL must be below current price
            if sl >= close:
                sl = close - 0.5 * atr_val

            return {
                "type": "breakout_buy",
                "direction": "buy",
                "entry": close,
                "sl": sl,
                "tp": tp,
                "confidence": 0.82,
                "atr": atr_val,
                "reason": f"close {close:.5f} > recent_high {recent_high:.5f}, body={body:.5f}",
                "trend_data": trend_data
            }

    # ---------------------------
    # BEARISH BREAKOUT
    # ---------------------------
    if trend == "bearish":
        if close < recent_low * (1 - breakout_buffer) and prev_close >= recent_low * (1 - breakout_buffer) and strong_momentum:
            sl = float(df['high'].iloc[-5:].max())
            tp = close - 2.5 * atr_val

            if sl <= close:
                sl = close + 0.5 * atr_val

            return {
                "type": "breakout_sell",
                "direction": "sell",
                "entry": close,
                "sl": sl,
                "tp": tp,
                "confidence": 0.82,
                "atr": atr_val,
                "reason": f"close {close:.5f} < recent_low {recent_low:.5f}, body={body:.5f}",
                "trend_data": trend_data
            }

    return None
def pullback_ended(df, direction, atr_val):
    close = df['close'].iloc[-1]
    prev_close = df['close'].iloc[-2]
    body = abs(df['close'].iloc[-1] - df['open'].iloc[-1])

    # strong candle definition
    strong_body = body > 0.45 * atr_val

    # micro structure
    recent_high = df['high'].rolling(5).max().iloc[-2]
    recent_low = df['low'].rolling(5).min().iloc[-2]

    if direction == "buy":
        bullish_engulf = (df['close'].iloc[-1] > df['open'].iloc[-1] and 
                          df['close'].iloc[-1] > df['open'].iloc[-2] and
                          df['open'].iloc[-1] < df['close'].iloc[-2])

        break_micro_structure = close > recent_high

        return (strong_body and bullish_engulf and break_micro_structure)

    if direction == "sell":
        bearish_engulf = (df['close'].iloc[-1] < df['open'].iloc[-1] and 
                          df['close'].iloc[-1] < df['open'].iloc[-2] and
                          df['open'].iloc[-1] > df['close'].iloc[-2])

        break_micro_structure = close < recent_low

        return (strong_body and bearish_engulf and break_micro_structure)

    return False

def detect_trade(df, trend_data):
    """
    Combined signal generator:
    1) Breakout detection
    2) Pullback detection
    """

    # -----------------------------
    # Normalize Trend
    # -----------------------------
    def normalize_trend(agent_output):
        trend = agent_output["trend"].lower()
        conf = agent_output["confidence"]
        if "bullish" in trend and conf >= 60:
            return "bullish"
        if "bearish" in trend and conf >= 60:
            return "bearish"
        return "range"

    trend = normalize_trend(trend_data)
    confidence = trend_data["confidence"]

    if confidence < 55:
        return None

    # -----------------------------
    # ATR
    # -----------------------------
    atr_val = atr(df)
    if atr_val < 0.05:
        return None

    # -----------------------------
    # 1) BREAKOUT DETECTION
    # -----------------------------
    breakout = detect_breakout(df, trend_data, lookback=30)
    if breakout:
        breakout["atr"] = atr_val
        # scale confidence with trend agent confidence (optional)
        breakout["confidence"] = min(0.95, 0.5 + 0.01 * confidence) if confidence else breakout.get("confidence", 0.8)
        breakout["rr"] = round((breakout["tp"] - breakout["entry"]) / max(1e-8, abs(breakout["entry"] - breakout["sl"])), 2) if breakout["direction"] == "buy" else round((breakout["entry"] - breakout["tp"]) / max(1e-8, abs(breakout["sl"] - breakout["entry"])), 2)
        return breakout

    # -----------------------------
    # 2) PULLBACK DETECTION (your original logic)
    # -----------------------------
    high = df['high'].max()
    low = df['low'].min()
    fibs = fib_levels(high, low)
    current = df['close'].iloc[-1]

    # Dynamic RR based on confidence
    if confidence > 80:
        rr = 3.5
    elif confidence > 70:
        rr = 3.0
    elif confidence > 60:
        rr = 2.0
    else:
        rr = 1.5

    # ================================
    # BUY LOGIC (pullback)
    # ================================
    if trend == "bullish" and fibs["78.6"] <= current <= fibs["38.2"]:
        
        if not pullback_ended(df, "buy", atr_val):
                print("Pullback not finished")
                return None   # ← pullback not finished
        
        # Check strong bullish candle confirmation
        last_close = df['close'].iloc[-1]
        last_open = df['open'].iloc[-1]
        bull_body = last_close - last_open

        # must be > 40% ATR
        if bull_body < 0.4 * atr_val:
            print("Bullish body too small")
            return None

        # must close above previous candle high
        prev_high = df['high'].iloc[-2]
        if last_close <= prev_high:
            print("Did not close above previous high")
            return None
        
        swing_low = df['low'].rolling(10).min().iloc[-1]
        sl = swing_low - 0.8 * atr_val
        tp = current + rr * (current - sl)

        if tp > current and (current - sl) >= 0.1 * atr_val:
            return {
                "type": "pullback_buy",
                "entry": current,
                "sl": sl,
                "tp": tp,
                "atr": atr_val,
                "confidence": confidence,
                "rr": rr,
                "direction": "buy",
                "fibs": fibs,
                "trend_data": trend_data
            }

    # ================================
    # SELL LOGIC (pullback)
    # ================================
    if trend == "bearish" and fibs["38.2"] >= current >= fibs["78.6"]:

        if not pullback_ended(df, "sell", atr_val):
            print("Pullback not finished")
            return None   # ← pullback not finished
        
        last_close = df['close'].iloc[-1]
        last_open = df['open'].iloc[-1]
        bear_body = last_open - last_close

        if bear_body < 0.4 * atr_val:
            print("Bearish body too small")
            return None

        prev_low = df['low'].iloc[-2]
        if last_close >= prev_low:
            print("Did not close below previous low")
            return None
        
        swing_high = df['high'].rolling(10).max().iloc[-1]
        sl = swing_high + 0.8 * atr_val
        tp = current - rr * (sl - current)

        if tp < current and (sl - current) >= 0.1 * atr_val:
            return {
                "type": "pullback_sell",
                "entry": current,
                "sl": sl,
                "tp": tp,
                "atr": atr_val,
                "confidence": confidence,
                "rr": rr,
                "direction": "sell",
                "fibs": fibs,
                "trend_data": trend_data
            }

    # -----------------------------
    # No signal
    # -----------------------------
    return None



