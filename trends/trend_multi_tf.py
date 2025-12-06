from agents.trend_detector_agent import TrendDetectorAgent
from .trend_cache import TrendCache
import MetaTrader5 as mt5

class MultiTFTrend:
    def __init__(self, client, logger):
        self.client = client
        self.logger = logger
        self.cache = TrendCache()

    def get_cached_or_calc(self, symbol, timeframe, tf_name):
        """
        timeframe = mt5 constant
        tf_name    = "H4", "H1", etc
        """
        df = self.client.get_data(symbol, timeframe)
        last_open = df.index[-1].strftime("%Y-%m-%d %H:%M")

        cached = self.cache.get_trend(tf_name, last_open)

        if cached:
            self.logger.info(f"{tf_name} trend cached → {cached}")
            return cached

        # compute new trend
        agent = TrendDetectorAgent()
        trend = agent.detect_trend(df)

        self.cache.save_trend(tf_name, last_open, trend)
        self.logger.info(f"{tf_name} trend NEW → {trend}")

        return trend

    def combine(self, h4, h1):
        """
        Combine logic:
        - If both bullish → bullish
        - If both bearish → bearish
        - If mixed → range
        Final confidence = average of both
        """

        t1 = h4["trend"].lower()
        t2 = h1["trend"].lower()

        if "bullish" in t1 and "bullish" in t2:
            final_trend = "bullish"
        elif "bearish" in t1 and "bearish" in t2:
            final_trend = "bearish"
        else:
            final_trend = "range"

        final_conf = round((h4["confidence"] + h1["confidence"]) / 2, 2)

        return {
            "trend": final_trend,
            "confidence": final_conf,
            "h4": h4,
            "h1": h1
        }

    def get_final_trend(self, symbol):
        h4 = self.get_cached_or_calc(symbol, timeframe=mt5.TIMEFRAME_H4, tf_name="H4")
        h1 = self.get_cached_or_calc(symbol, timeframe=mt5.TIMEFRAME_H1, tf_name="H1")
        return self.combine(h4, h1)
