from typing import List, Dict, Any
from .levels import find_pivot_points

def analyze_market_structure(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Identifies market trend, HH/HL or LH/LL sequence, and structure shifts (BOS / CHoCH).
    """
    if len(candles) < 20:
        return {"trend": "NEUTRAL", "structureEvents": [], "summary": "Недостатньо даних"}

    pivots = find_pivot_points(candles, left_bars=3, right_bars=3)
    highs = pivots["highs"]
    lows = pivots["lows"]

    if len(highs) < 2 or len(lows) < 2:
        return {"trend": "NEUTRAL", "structureEvents": [], "summary": "Флет / Консолідація"}

    # Compare last two swing highs and lows
    last_h = highs[-1]["price"]
    prev_h = highs[-2]["price"]
    last_l = lows[-1]["price"]
    prev_l = lows[-2]["price"]

    current_price = candles[-1]["close"]

    # Trend determination
    is_hh = last_h > prev_h
    is_hl = last_l > prev_l
    is_lh = last_h < prev_h
    is_ll = last_l < prev_l

    if is_hh and is_hl:
        trend = "BULLISH"
        summary = "Висхідний тренд (HH + HL)"
    elif is_lh and is_ll:
        trend = "BEARISH"
        summary = "Низхідний тренд (LH + LL)"
    elif is_hh and is_ll:
        trend = "EXPANDING"
        summary = "Розширюваний діапазон"
    else:
        trend = "CONSOLIDATING"
        summary = "Звуження / Боковик"

    # Detect Structure Events on recent candles
    events = []
    # If in downtrend and close broke above prev_h -> CHoCH (Bullish Reversal)
    if current_price > prev_h and trend != "BULLISH":
        events.append({
            "type": "CHoCH_BULLISH",
            "name": "CHoCH (Зміна характеру в Лонг)",
            "level": prev_h,
            "desc": f"Пробій попереднього свінг-хаю {prev_h:.4f} на зміну тренду"
        })
    # If in uptrend and close broke below prev_l -> CHoCH (Bearish Reversal)
    elif current_price < prev_l and trend != "BEARISH":
        events.append({
            "type": "CHoCH_BEARISH",
            "name": "CHoCH (Зміна характеру в Шорт)",
            "level": prev_l,
            "desc": f"Пробій попереднього свінг-лою {prev_l:.4f} на зміну тренду"
        })

    return {
        "trend": trend,
        "summary": summary,
        "events": events,
        "recentHigh": last_h,
        "recentLow": last_l
    }
