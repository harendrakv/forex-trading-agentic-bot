import pandas as pd
import numpy as np
import ta

# --- 1. H1 MOMENTUM FILTER HELPER FUNCTION ---

def check_h1_momentum_filter(df_h1: pd.DataFrame, intended_signal: str) -> bool:
    """
    Checks the last 3 H1 closed candles for strong consecutive momentum that contradicts 
    the intended M15 trade (e.g., blocks a BUY if H1 has 3 consecutive bearish candles).
    Returns True if the filter is passed (trade allowed), False if blocked.
    """
    # Requires at least 4 candles for the last 3 *closed* candles
    if len(df_h1) < 4:
        return True # Cannot check filter, assume allowed
        
    # Get the last 3 closed H1 candles
    last_three_closed = df_h1.iloc[-4:-1].copy() 
    
    # Determine Candle Color
    is_bearish = (last_three_closed['close'] < last_three_closed['open']).all()
    is_bullish = (last_three_closed['close'] > last_three_closed['open']).all()

    if intended_signal == 'BUY':
        # Block BUY if momentum is overwhelmingly DOWN
        return not is_bearish 
            
    elif intended_signal == 'SELL':
        # Block SELL if momentum is overwhelmingly UP
        return not is_bullish
        
    return True 

# --- 2. MAIN SIGNAL GENERATOR FUNCTION (All Calculations Inside) ---

def generate_mean_reversion_signal(
    df_m15: pd.DataFrame, 
    df_h1: pd.DataFrame, 
    atr_multiplier: float = 1.5,
    confidence_level: float = 0.7 
) -> dict:
    """
    Generates a structured trading signal based on M15 Mean Reversion logic 
    (BB + RSI) and filters the output using H1 momentum.
    """
    
    # Check for minimum data requirements
    if len(df_m15) < 20: # Need 20 candles for BB calculation
        return {
            "type": "NO_DATA", "direction": "none", "entry": 0.0, "sl": 0.0, 
            "confidence": 0.0, "reason": "Insufficient M15 data for indicators."
        }
    
    # --- CALCULATE INDICATORS ON M15 DATA ---
    
    # Bollinger Bands (BB): 20 period, 2.0 Standard Deviations
    df_m15.loc[:, 'BB_High'] = ta.volatility.bollinger_hband(df_m15['close'], window=20, window_dev=2)
    df_m15.loc[:, 'BB_Low'] = ta.volatility.bollinger_lband(df_m15['close'], window=20, window_dev=2)
    
    # Relative Strength Index (RSI): 14 period
    df_m15.loc[:, 'RSI'] = ta.momentum.rsi(df_m15['close'], window=14)
    
    # Average True Range (ATR): 14 period
    df_m15.loc[:, 'ATR'] = ta.volatility.average_true_range(df_m15['high'], df_m15['low'], df_m15['close'], window=14)
    
    # --- GET LATEST CANDLE DATA ---
    last_candle = df_m15.iloc[-2] # Second to last candle for signal confirmation
    
    # --- DETERMINE DYNAMIC RISK/REWARD ---
    current_atr = last_candle['ATR']
    stop_loss_distance = current_atr * atr_multiplier
    # TP is 1.0x ATR for a slightly higher chance of hitting target during a range
    take_profit_distance = current_atr * 1.0 
    
    # --- CHECK MEAN REVERSION SIGNAL LOGIC ---
    
    intended_signal = 'NO_TRADE'
    
    # BUY Signal: Close below Lower BB AND RSI < 30
    if (last_candle['close'] < last_candle['BB_Low']) and (last_candle['RSI'] < 30):
        intended_signal = 'BUY'
        
    # SELL Signal: Close above Upper BB AND RSI > 70
    elif (last_candle['close'] > last_candle['BB_High']) and (last_candle['RSI'] > 70):
        intended_signal = 'SELL'
        
    # --- APPLY H1 MOMENTUM FILTER ---
    
    if intended_signal != 'NO_TRADE':
        # If the H1 Momentum Filter returns False, the trade is blocked
        if not check_h1_momentum_filter(df_h1, intended_signal):
            return {
                "type": "FILTER_BLOCKED", 
                "direction": "none", 
                "entry": 0.0, 
                "sl": 0.0, 
                "confidence": 0.3, # Low confidence assigned to blocked signal
                "reason": f"M15 Reversal blocked by strong 3-candle H1 {intended_signal} momentum."
            }

    # --- FORMAT FINAL OUTPUT ---
    entry = last_candle['open']
    
    if intended_signal == 'BUY':
        return {
            "type": "bb_rsi_reversal", # Descriptive type of the strategy
            "direction": "buy",
            "entry": entry,
            "sl": entry - stop_loss_distance, 
            "tp": entry + take_profit_distance, # Added TP to match full trade details
            "confidence": confidence_level,
            "reason": "Mean Reversion Buy: Price oversold (RSI<30) and outside Lower BB. H1 filter passed."
        }
        
    elif intended_signal == 'SELL':
        return {
            "type": "bb_rsi_reversal",
            "direction": "sell",
            "entry": entry,
            "sl": entry + stop_loss_distance, 
            "tp": entry - take_profit_distance, # Added TP to match full trade details
            "confidence": confidence_level,
            "reason": "Mean Reversion Sell: Price overbought (RSI>70) and outside Upper BB. H1 filter passed."
        }
        
    # Default for NO_TRADE
    return {
        "type": "NO_SIGNAL", 
        "direction": "none", 
        "entry": 0.0, 
        "sl": 0.0, 
        "tp": 0.0, # Added TP
        "confidence": 0.0, 
        "reason": "No Mean Reversion setup found on M15."
    }