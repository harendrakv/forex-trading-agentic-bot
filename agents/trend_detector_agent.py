import json
from groq import Groq
from openai import OpenAI
from config.config_loader import load_config
from templates.trend_detection_prompt import TREND_DETECTION_PROMPT

cfg = load_config("config/settings.yaml")

def extract_structure_context(df, lookback=40):
    """
    Extract clean price-action context from a dataframe.
    Works for 4H, 1H, 5M equally.

    Produces:
    - recent candles compressed
    - swing highs/lows
    - HH/HL/LH/LL pattern
    - BOS/CHOCH detection
    - momentum
    - ATR%
    - wick pressure
    """
    df = df.copy().tail(lookback)

    # -----------------------------------------------------
    # 1. Recent candles text compression
    # -----------------------------------------------------
    recent = df[['open','high','low','close']].round(2).to_dict(orient='records')

    # -----------------------------------------------------
    # 2. Swings (very reliable + compact)
    # -----------------------------------------------------
    def is_swing_high(i):
        if i < 2 or i > len(df)-3: return False
        return df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1]

    def is_swing_low(i):
        if i < 2 or i > len(df)-3: return False
        return df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1]

    swing_highs = []
    swing_lows = []

    for i in range(len(df)):
        if is_swing_high(i):
            swing_highs.append(df['high'].iloc[i])
        if is_swing_low(i):
            swing_lows.append(df['low'].iloc[i])

    # -----------------------------------------------------
    # 3. Structure Pattern (HH/HL/LH/LL)
    # -----------------------------------------------------
    structure_pattern = "unknown"
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        last_HH = swing_highs[-1] > swing_highs[-2]
        last_LL = swing_lows[-1] < swing_lows[-2]

        last_HL = swing_lows[-1] > swing_lows[-2]
        last_LH = swing_highs[-1] < swing_highs[-2]

        if last_HH and last_HL:
            structure_pattern = "HH-HL (bullish)"
        elif last_LL and last_LH:
            structure_pattern = "LL-LH (bearish)"
        elif last_HH and last_LL:
            structure_pattern = "mixed"
        else:
            structure_pattern = "range"

    # -----------------------------------------------------
    # 4. BOS / CHOCH detection
    # -----------------------------------------------------
    bos = "none"
    choch = "none"

    if len(swing_highs) >= 3:
        if swing_highs[-1] > swing_highs[-2] and swing_highs[-2] < swing_highs[-3]:
            bos = "up"

    if len(swing_lows) >= 3:
        if swing_lows[-1] < swing_lows[-2] and swing_lows[-2] > swing_lows[-3]:
            bos = "down"

    # simple CHOCH check
    if structure_pattern.startswith("HH-HL") and bos == "down":
        choch = "bearish"
    elif structure_pattern.startswith("LL-LH") and bos == "up":
        choch = "bullish"

    # -----------------------------------------------------
    # 5. Momentum (simple rate of change)
    # -----------------------------------------------------
    momentum = round(df['close'].iloc[-1] - df['close'].iloc[-10], 2)

    # -----------------------------------------------------
    # 6. ATR% (volatility health)
    # -----------------------------------------------------
    df["tr"] = (df["high"] - df["low"]).abs()
    atr = df["tr"].rolling(14).mean().iloc[-1]
    atr_percent = round((atr / df['close'].iloc[-1]) * 100, 2)

    # -----------------------------------------------------
    # 7. Wick Pressure (buyer/seller aggression)
    # -----------------------------------------------------
    upper_wicks = (df['high'] - df['close']).clip(lower=0)
    lower_wicks = (df['close'] - df['low']).clip(lower=0)

    upper_wick_avg = round(upper_wicks.mean(), 2)
    lower_wick_avg = round(lower_wicks.mean(), 2)

    # -----------------------------------------------------
    # Final Packaged Context
    # -----------------------------------------------------
    return {
        "recent_candles": recent,
        "swing_highs": [round(x,2) for x in swing_highs[-5:]],  # limit to last 5
        "swing_lows": [round(x,2) for x in swing_lows[-5:]],
        "structure_pattern": structure_pattern,
        "bos": bos,
        "choch": choch,
        "momentum": momentum,
        "atr_percent": atr_percent,
        "upper_wick": upper_wick_avg,
        "lower_wick": lower_wick_avg
    }


class TrendDetectorAgent:

    def __init__(self):
        
        self.client = OpenAI(api_key=cfg['models']['groq']['api_key'], base_url=cfg['models']['groq']['endpoint'])
        self.model_name = cfg['models']['groq']['model_name']

    def build_agent_prompt(self, df):
        """
        Convert candles + structure into compact input for the LLM.
        """
        ctx = extract_structure_context(df)
        prompt = f"""
        Price Action Trend Context:

        Recent Candles (OHLC last 40):
        {ctx['recent_candles']}

        Market Structure:
        - Swing Highs: {ctx['swing_highs']}
        - Swing Lows: {ctx['swing_lows']}
        - Structure Pattern: {ctx['structure_pattern']}

        Momentum:
        - 10-bar momentum: {ctx['momentum']}

        Volatility:
        - ATR%14: {ctx['atr_percent']}%

        Wick Pressure:
        - Upper wick avg: {ctx['upper_wick']}
        - Lower wick avg: {ctx['lower_wick']}

        Provide JSON only.
        """
        return prompt

    def detect_trend(self, df):
        """
        Runs the Groq LLM to classify trend.
        """
        user_prompt = self.build_agent_prompt(df)

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": TREND_DETECTION_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.15,
                max_tokens=2000
            )
            raw = response.choices[0].message.content
            return json.loads(raw)

        except Exception as e:
            return {
                "trend": "range",
                "confidence": 0,
                "reason": f"Fallback due to error: {str(e)}"
            }
