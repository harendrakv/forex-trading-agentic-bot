import pandas as pd
import numpy as np
import ta # Assuming 'ta' is installed and used elsewhere, but not strictly needed for this file's functions

# --- UTILITY FUNCTION: Average True Range (ATR) ---
# Note: The ATR calculation here is used by all modules.

def atr(df, n=14):
    """Calculates the Average True Range (ATR) for the last candle."""
    df = df.copy()
    
    # Calculate True Range (TR)
    df['tr'] = np.maximum(df['high'] - df['low'],
                          np.maximum(abs(df['high'] - df['close'].shift()), 
                                     abs(df['low'] - df['close'].shift())))
    
    # Return the last 14-period ATR value
    return df['tr'].rolling(n).mean().iloc[-1]

# --- 1. LIQUIDITY SWEEP DETECTOR (Refined) ---

def detect_liquidity_sweep(df):
    """
    Detects a high-probability liquidity sweep (stop hunt) based on strong rejection.
    Refinements: Dynamic SL, better rejection criteria.
    """
    if len(df) < 2:
        return None
        
    last = df.iloc[-1]
    prev = df.iloc[-2]
    atr_val = atr(df)
    
    # --- Bullish liquidity sweep (Reversal from Low) ---
    if last['low'] < prev['low']: # Swept previous low
        
        # Check for strong bullish rejection (close in the top 60% of the entire candle range)
        candle_range = last['high'] - last['low']
        rejection_close_position = last['close'] - last['low']
        
        if (last['close'] > last['open']) and (rejection_close_position > 0.6 * candle_range):
            return {
                "type": "liq_sweep_buy",
                "direction": "buy",
                "entry": last['close'],
                # Dynamic SL: Last low minus a small fraction of ATR for noise buffer
                "sl": last['low'] - 0.1 * atr_val,
                "tp": last['close'] + 1.5 * atr_val, # Standard ATR TP for R:R
                "confidence": 0.7, # Base confidence before dynamic adjustment
                "reason": "bullish liquidity sweep with strong rejection"
            }

    # --- Bearish liquidity sweep (Reversal from High) ---
    if last['high'] > prev['high']: # Swept previous high
        
        # Check for strong bearish rejection (close in the bottom 60% of the entire candle range)
        candle_range = last['high'] - last['low']
        rejection_close_position = last['high'] - last['close']
        
        if (last['close'] < last['open']) and (rejection_close_position > 0.6 * candle_range):
            return {
                "type": "liq_sweep_sell",
                "direction": "sell",
                "entry": last['close'],
                # Dynamic SL: Last high plus a small fraction of ATR for noise buffer
                "sl": last['high'] + 0.1 * atr_val,
                "tp": last['close'] - 1.5 * atr_val, # Standard ATR TP for R:R
                "confidence": 0.7, # Base confidence before dynamic adjustment
                "reason": "bearish liquidity sweep with strong rejection"
            }

    return None

# --- 2. VOLATILITY PULSE (Continuation) DETECTOR ---

def detect_volatility_pulse(df):
    """
    Detects continuation after a large impulse candle and trades the retracement.
    Refinements: Dynamic SL/TP based on ATR.
    """
    if len(df) < 2:
        return None
        
    last = df.iloc[-1]
    prev = df.iloc[-2]

    atr_val = atr(df)
    body = abs(last['close'] - last['open'])

    # Condition: Large impulse candle (1.3x ATR is a good threshold)
    if body > 1.3 * atr_val:

        # Lookback retracement zone (e.g., 40% to 70% retracement)
        zone_diff = last['close'] - last['open']
        zone_low = last['open'] + 0.4 * zone_diff
        zone_high = last['open'] + 0.7 * zone_diff

        current_entry_price = prev['close']
        
        # SL is behind the open of the impulse candle (the start of the move)
        sl_distance = 0.4 * atr_val # Dynamic SL distance
        tp_distance = 1.6 * atr_val # Dynamic TP distance
        
        # BUY continuation (Impulse candle closed bullish)
        if last['close'] > last['open'] and zone_low <= current_entry_price <= zone_high:
            return {
                "type": "vol_pulse_buy",
                "direction": "buy",
                "entry": current_entry_price,
                "sl": last['open'] - sl_distance,
                "tp": current_entry_price + tp_distance,
                "confidence": 0.65,
                "reason": "volatility pulse buy continuation (retracement)"
            }

        # SELL continuation (Impulse candle closed bearish)
        if last['close'] < last['open'] and zone_high >= current_entry_price >= zone_low:
            return {
                "type": "vol_pulse_sell",
                "direction": "sell",
                "entry": current_entry_price,
                "sl": last['open'] + sl_distance,
                "tp": current_entry_price - tp_distance,
                "confidence": 0.65,
                "reason": "volatility pulse sell continuation (retracement)"
            }

    return None

# --- 3. MARKET MICRO STRUCTURE (MMS) DETECTOR (Refined) ---
def detect_mms(df):
    """
    Detects change in market micro-structure (Higher Lows / Lower Highs).
    Refinements: Increased rolling window from 3 to 7, Dynamic R:R based on structure.
    """
    if len(df) < 7:
        return None

    # Constants
    TARGET_RR = 1.5 # Set your desired Risk-to-Reward ratio
    ATR_BUFFER = 0.1 # The ATR buffer used for SL/TP placement
    
    atr_val = atr(df)
    current_close = df['close'].iloc[-1]

    # Increased window to 7 for more stable swing points on M1
    swing_low = df['low'].rolling(7).min()
    swing_high = df['high'].rolling(7).max()
    
    # HL → Buy scalp
    if swing_low.iloc[-1] > swing_low.iloc[-3]:
        
        sl_anchor = swing_low.iloc[-2] # Previous structural low
        
        # 1. Calculate the structural risk (distance from entry to the anchor)
        structural_risk_units = current_close - sl_anchor
        
        # 2. Total Risk (R) = Structural Risk + ATR Buffer
        # We must add the buffer since the SL is placed below the anchor.
        total_risk = structural_risk_units + (ATR_BUFFER * atr_val)
        
        # 3. Total Reward (TP distance) = Total Risk * Target R:R
        tp_distance = total_risk * TARGET_RR
        
        return {
            "type": "mms_buy",
            "direction": "buy",
            "entry": current_close,
            # SL is placed below the structural anchor, offset by the ATR buffer
            "sl": sl_anchor - (ATR_BUFFER * atr_val), 
            # TP is placed above the entry by the calculated TP distance
            "tp": current_close + tp_distance,
            "confidence": 0.6,
            "reason": "market micro structure Higher Low buy scalp"
        }

    # LH → Sell scalp
    if swing_high.iloc[-1] < swing_high.iloc[-3]:
        
        sl_anchor = swing_high.iloc[-2] # Previous structural high
        
        # 1. Calculate the structural risk (distance from anchor to entry)
        structural_risk_units = sl_anchor - current_close 
        
        # 2. Total Risk (R) = Structural Risk + ATR Buffer
        # We must add the buffer since the SL is placed above the anchor.
        total_risk = structural_risk_units + (ATR_BUFFER * atr_val)
        
        # 3. Total Reward (TP distance) = Total Risk * Target R:R
        tp_distance = total_risk * TARGET_RR
        
        return {
            "type": "mms_sell",
            "direction": "sell",
            "entry": current_close,
            # SL is placed above the structural anchor, offset by the ATR buffer
            "sl": sl_anchor + (ATR_BUFFER * atr_val), 
            # TP is placed below the entry by the calculated TP distance
            "tp": current_close - tp_distance,
            "confidence": 0.6,
            "reason": "market micro structure Lower High sell scalp"
        }

    return None

# --- 4. FAIR VALUE GAP (FVG) DETECTOR ---

def detect_fvg(df):
    """
    Detects a three-candle Fair Value Gap (Imbalance).
    Refinements: Dynamic TP based on ATR.
    """
    if len(df) < 3:
        return None
        
    # Three-candle lookback
    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    atr_val = atr(df)

    # Bullish imbalance (FVG)
    # Price should close bullish to trade the FVG
    if c2['low'] > c1['high'] and c3['close'] > c2['open']:
        return {
            "type": "fvg_buy",
            "direction": "buy",
            "entry": c3['close'],
            # SL is the low of the middle candle (c2), slightly adjusted by ATR
            "sl": c2['low'] - 0.1 * atr_val, 
            "tp": c3['close'] + 1.4 * atr_val,
            "confidence": 0.65,
            "reason": "bullish fair value gap continuation"
        }

    # Bearish imbalance (FVG)
    # Price should close bearish to trade the FVG
    if c2['high'] < c1['low'] and c3['close'] < c2['open']:
        return {
            "type": "fvg_sell",
            "direction": "sell",
            "entry": c3['close'],
            # SL is the high of the middle candle (c2), slightly adjusted by ATR
            "sl": c2['high'] + 0.1 * atr_val, 
            "tp": c3['close'] - 1.4 * atr_val,
            "confidence": 0.65,
            "reason": "bearish fair value gap continuation"
        }

    return None

# --- 5. CONFIDENCE SCORING FUNCTION ---

def compute_confidence(df, direction, trend_raw, entry):
    """
    Returns confidence (0.0 – 1.0) based on multi-factor confluence.
    (No changes were made here, as the logic is robust.)
    """

    score = 0

    # ---- 1. Trend alignment (H4/H1) ----
    h4_trend = trend_raw.get("h4", {}).get("trend", "")
    h1_trend = trend_raw.get("h1", {}).get("trend", "")

    if direction == "buy":
        if "bullish" in h4_trend: score += 0.25
        if "bullish" in h1_trend: score += 0.25
    if direction == "sell":
        if "bearish" in h4_trend: score += 0.25
        if "bearish" in h1_trend: score += 0.25

    # ---- 2. Market regime (Avoid mid-range chop) ----
    # Penalize if trend confidence is too low/market is explicitly 'range'
    if trend_raw.get("trend") == "range":
        score -= 0.20 
    else:
        score += 0.20

    # ---- 3. Volatility health (ATR check) ----
    current_atr = atr(df)
    last_range = df['high'].iloc[-1] - df['low'].iloc[-1]

    if last_range > 0.8 * current_atr:
        score += 0.20 # good volatility for scalp
    else:
        score -= 0.10

    # ---- 4. Location in structure: avoid mid-range ----
    # Requires enough data (50 candles for 50-period rolling max/min)
    if len(df) >= 50:
        high = df['high'].rolling(50).max().iloc[-1]
        low = df['low'].rolling(50).min().iloc[-1]
        mid = (high + low) / 2

        if direction == "sell" and entry > mid:
            score += 0.15 # selling near range top = good
        elif direction == "buy" and entry < mid:
            score += 0.15 # buying near range bottom = good
        else:
            score -= 0.10 # mid-range is bad

    # ---- Clamp between 0–1 ----
    score = max(0.0, min(1.0, score))

    return round(score, 2)


# --- 6. AGGREGATOR FUNCTION (detect_trade/detect_scalp) ---

def detect_scalp(df, trend_raw):
    """
    Runs all scalp modules in priority order and computes dynamic confidence.
    """
    modules = [
        detect_liquidity_sweep,
        detect_volatility_pulse,
        detect_mms,
        detect_fvg
    ]

    for mod in modules:
        res = mod(df)
        if res:
            res["type"] = "scalp_" + res["type"]

            # Dynamically compute and apply confidence score
            res["confidence"] = compute_confidence(
                df=df,
                direction=res["direction"],
                trend_raw=trend_raw,
                entry=res["entry"]
            )
            
            # REMOVED: The fixed confidence override (res['confidence'] = 80)
            
            return res

    return None

# Assuming your main run_cycle calls detect_trade, so this will be the final function used.
#detect_trade = detect_scalp