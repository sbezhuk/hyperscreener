from typing import List, Dict, Any

INTERVAL_MIN_GAP = {
    "1m": 0.20,
    "3m": 0.25,
    "5m": 0.30,
    "15m": 0.45,
    "30m": 0.60,
    "1h": 0.80,
    "2h": 1.00,
    "4h": 1.20,
    "1d": 1.80,
}

def detect_fvgs(candles: List[Dict[str, Any]], interval: str = "5m") -> List[Dict[str, Any]]:
    """
    Detects ONLY significant, FRESH (unmitigated) Fair Value Gaps (FVG) for the specific timeframe.
    Excludes filled or mitigated noise.
    Keeps only the top 2 closest Bullish and top 2 closest Bearish FVGs.
    """
    if len(candles) < 3:
        return []

    clean_interval = interval.lower()
    min_gap_pct = INTERVAL_MIN_GAP.get(clean_interval, 0.30)
    current_price = candles[-1]["close"]

    n = len(candles)
    bullish_fvgs = []
    bearish_fvgs = []

    for i in range(2, n):
        c1 = candles[i - 2]
        c2 = candles[i - 1]
        c3 = candles[i]

        # 1. Bullish FVG (c3.low > c1.high)
        if c3["low"] > c1["high"]:
            gap_size = c3["low"] - c1["high"]
            gap_pct = (gap_size / c1["high"]) * 100

            if gap_pct >= min_gap_pct:
                top = c3["low"]
                bottom = c1["high"]
                start_time = c2["time"]

                # Check if gap was tested/mitigated by ANY subsequent candle
                is_mitigated = False
                for k in range(i + 1, n):
                    if candles[k]["low"] <= top:
                        is_mitigated = True
                        break

                # ONLY keep unmitigated (fresh) FVGs!
                if not is_mitigated:
                    dist_to_gap = abs(current_price - ((top + bottom) / 2)) / current_price * 100
                    # Only keep if reasonably close (within 8% of price)
                    if dist_to_gap <= 8.0:
                        bullish_fvgs.append({
                            "type": "bullish",
                            "top": top,
                            "bottom": bottom,
                            "mid": round((top + bottom) / 2, 6),
                            "gapPct": round(gap_pct, 2),
                            "startTime": start_time,
                            "endTime": candles[-1]["time"],
                            "status": "unmitigated",
                            "dist": dist_to_gap,
                            "timeframe": interval
                        })

        # 2. Bearish FVG (c3.high < c1.low)
        elif c3["high"] < c1["low"]:
            gap_size = c1["low"] - c3["high"]
            gap_pct = (gap_size / c3["high"]) * 100

            if gap_pct >= min_gap_pct:
                top = c1["low"]
                bottom = c3["high"]
                start_time = c2["time"]

                is_mitigated = False
                for k in range(i + 1, n):
                    if candles[k]["high"] >= bottom:
                        is_mitigated = True
                        break

                if not is_mitigated:
                    dist_to_gap = abs(current_price - ((top + bottom) / 2)) / current_price * 100
                    if dist_to_gap <= 8.0:
                        bearish_fvgs.append({
                            "type": "bearish",
                            "top": top,
                            "bottom": bottom,
                            "mid": round((top + bottom) / 2, 6),
                            "gapPct": round(gap_pct, 2),
                            "startTime": start_time,
                            "endTime": candles[-1]["time"],
                            "status": "unmitigated",
                            "dist": dist_to_gap,
                            "timeframe": interval
                        })

    # Sort by proximity to current price and take at most 2 closest
    bullish_fvgs.sort(key=lambda x: x["dist"])
    bearish_fvgs.sort(key=lambda x: x["dist"])

    # Max 2 Bullish and Max 2 Bearish fresh FVGs to eliminate visual clutter
    clean_fvgs = bullish_fvgs[:2] + bearish_fvgs[:2]
    clean_fvgs.sort(key=lambda x: x["mid"])
    return clean_fvgs
