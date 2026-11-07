"""
Dedicated False Breakout (Хибний пробій) Detection Module.

Supports:
- False Breakout Up / Bearish Sweep (Хибний пробій опору) -> Potential reversal DOWN (SHORT)
- False Breakout Down / Bullish Sweep (Хибний пробій підтримки) -> Potential reversal UP (LONG)
- Both single-candle (wick-based) and multi-candle (breakout candle + confirmation candle) detection
- Volume confirmation and level significance (touches, strength score)
- Closed candles only analysis to prevent false signals during candle formation
- Deterministic and duplicate-free signal generation
- Works across all timeframes independently
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

FALSE_BREAKOUT_CONFIG = {
    # Default parameters per interval or fallback
    "default": {
        "min_wick_pct": 0.04,        # Minimum % price exceeded level to count as breakout
        "max_breakout_atr": 3.0,     # If breakout goes further than 3 ATR, it's a true impulse/breakout, not a trap
        "vol_multiplier": 0.8,       # Volume filter ratio relative to 20-candle SMA
    }
}

# Maximum age in bars for a false breakout to remain actively relevant on chart
TIMEFRAME_RECENCY_BARS = {
    "1m": 60,
    "3m": 60,
    "5m": 60,
    "15m": 50,
    "30m": 45,
    "1h": 40,
    "2h": 35,
    "4h": 30,
    "1d": 25,
}

INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
}


@dataclass
class FalseBreakoutOIConfig:
    """
    Configuration parameters for Open Interest (OI) false breakout confirmation.
    All parameters are dynamically configurable and not hardcoded.
    """
    min_oi_drop_pct: float = 0.25          # Minimum relative drop in OI (%) required for confirmation
    comparison_period_bars: int = 1        # Number of bars before breakout to establish baseline OI
    max_wait_bars: int = 3                 # Maximum bars after breakout piercing for return confirmation
    noise_threshold_pct: float = 0.05      # Noise boundary: fluctuations within ±noise_threshold_pct are noise
    stale_oi_max_age_seconds: int = 300    # Maximum tolerance for snapshot age vs candle time
    require_oi_confirmation: bool = True   # Confirmation strictly requires OI drop

    def get_stale_tolerance(self, interval: str) -> float:
        sec = INTERVAL_SECONDS.get(interval.lower(), 300)
        return max(float(self.stale_oi_max_age_seconds), sec * 1.5)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_oi_drop_pct": self.min_oi_drop_pct,
            "comparison_period_bars": self.comparison_period_bars,
            "max_wait_bars": self.max_wait_bars,
            "noise_threshold_pct": self.noise_threshold_pct,
            "stale_oi_max_age_seconds": self.stale_oi_max_age_seconds,
            "require_oi_confirmation": self.require_oi_confirmation,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]] = None) -> "FalseBreakoutOIConfig":
        if not data:
            return cls()
        return cls(
            min_oi_drop_pct=float(data.get("min_oi_drop_pct", 0.25)),
            comparison_period_bars=int(data.get("comparison_period_bars", 1)),
            max_wait_bars=int(data.get("max_wait_bars", 3)),
            noise_threshold_pct=float(data.get("noise_threshold_pct", 0.05)),
            stale_oi_max_age_seconds=int(data.get("stale_oi_max_age_seconds", 300)),
            require_oi_confirmation=bool(data.get("require_oi_confirmation", True)),
        )


DEFAULT_OI_CONFIG = FalseBreakoutOIConfig()


def evaluate_false_breakout_oi(
    candles: List[Dict[str, Any]],
    breakout_idx: int,
    conf_idx: int,
    interval: str = "5m",
    oi_tracker: Optional[Any] = None,
    oi_snapshots: Optional[List[Any]] = None,
    config: Optional[FalseBreakoutOIConfig] = None,
    coin: Optional[str] = None,
    is_potential_pending: bool = False,
    is_candle_closed: bool = True,
    cutoff_timestamp: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Evaluates Open Interest (OI) dynamics for a false breakout pattern without look-ahead bias.
    Determines whether positions were closed/reduced (OI decrease) or opened (OI increase/neutral).

    Properly handles candle timestamps:
    - Candle timestamp represents the OPEN time (t_open).
    - Pre-breakout baseline OI is captured at or before the breakout candle opened.
    - Post-return confirmation OI is captured at the confirmation moment (candle close for historical,
      or current tick time for live, strictly bounded to prevent look-ahead bias).

    Returns three distinct states:
    - CONFIRMED: price returned, candle closed, and OI significantly dropped (oi_delta_pct <= -min_oi_drop_pct)
    - UNCONFIRMED: OI increased, stayed within noise, or data is missing/stale
    - POTENTIAL: price pattern formed or forming on open candle, awaiting final close/OI confirmation
    """
    cfg = config or DEFAULT_OI_CONFIG

    if is_potential_pending:
        return {
            "status": "POTENTIAL",
            "status_label": "Потенційний хибний пробій",
            "is_confirmed": False,
            "oi_before": None,
            "oi_after": None,
            "oi_delta": None,
            "oi_delta_pct": None,
            "reason": "PENDING_CONFIRMATION",
            "reason_desc": "Цінова модель виявлена, очікується підтвердження зміною Open Interest",
        }

    interval_sec = INTERVAL_SECONDS.get(interval.lower(), 300)
    pre_idx = max(0, breakout_idx - cfg.comparison_period_bars)
    c_pre = candles[pre_idx]
    c_conf = candles[conf_idx]
    breakout_c = candles[breakout_idx]

    t_breakout_open = float(breakout_c["time"])
    t_conf_open = float(c_conf["time"])

    # 1. Determine baseline pre-breakout time boundary:
    # Baseline must be taken at or before the breakout candle opened
    if cfg.comparison_period_bars > 1:
        t_pre_target = float(c_pre["time"])
    else:
        t_pre_target = t_breakout_open

    # 2. Determine confirmation cutoff timestamp:
    # For a completed confirmation candle, it closed when the next candle opened or at t_conf_open + interval_sec
    if conf_idx < len(candles) - 1:
        t_conf_target = float(candles[conf_idx + 1]["time"])
    else:
        if is_candle_closed:
            t_conf_target = t_conf_open + interval_sec
        else:
            t_conf_target = cutoff_timestamp if cutoff_timestamp is not None else t_conf_open

    if cutoff_timestamp is not None:
        t_conf_target = min(t_conf_target, float(cutoff_timestamp))

    # 1. Try reading directly from candles if attached
    oi_pre = c_pre.get("open_interest")
    if oi_pre is None:
        oi_pre = c_pre.get("oi")
    oi_conf = c_conf.get("open_interest")
    if oi_conf is None:
        oi_conf = c_conf.get("oi")

    # 2. If not attached or if tracker/snapshots provided, lookup via time-series
    if oi_tracker is None and oi_snapshots is None and coin:
        try:
            from .oi_tracker import oi_manager
            oi_tracker = oi_manager.get_tracker(coin)
        except Exception:
            pass

    snap_pre = None
    snap_conf = None
    if oi_snapshots:
        def _get_ts(s: Any) -> float:
            return s.timestamp if hasattr(s, "timestamp") else float(s.get("timestamp", 0.0))

        ts_list = [_get_ts(s) for s in oi_snapshots]
        import bisect
        idx_pre = bisect.bisect_right(ts_list, t_pre_target)
        if idx_pre > 0:
            snap_pre = oi_snapshots[idx_pre - 1]
        # Strictly look at snapshots at or before t_conf_target (guarantees zero look-ahead bias)
        idx_conf = bisect.bisect_right(ts_list, t_conf_target)
        if idx_conf > 0:
            snap_conf = oi_snapshots[idx_conf - 1]
    elif oi_tracker and hasattr(oi_tracker, "_find_snapshot_at_or_before"):
        snap_pre = oi_tracker._find_snapshot_at_or_before(t_pre_target)
        snap_conf = oi_tracker._find_snapshot_at_or_before(t_conf_target)

    stale_tol = cfg.get_stale_tolerance(interval)

    # Check snapshot staleness if used
    if oi_pre is None and snap_pre:
        ts_pre_actual = snap_pre.timestamp if hasattr(snap_pre, "timestamp") else float(snap_pre.get("timestamp", 0.0))
        if abs(t_pre_target - ts_pre_actual) > stale_tol:
            return {
                "status": "UNCONFIRMED",
                "status_label": "Непідтверджений хибний пробій",
                "is_confirmed": False,
                "oi_before": None,
                "oi_after": None,
                "oi_delta": None,
                "oi_delta_pct": None,
                "reason": "STALE_DATA",
                "reason_desc": "Дані Open Interest застарілі відносно моменту пробою",
            }
        oi_pre = snap_pre.oi if hasattr(snap_pre, "oi") else snap_pre.get("oi")

    if oi_conf is None and snap_conf:
        ts_conf_actual = snap_conf.timestamp if hasattr(snap_conf, "timestamp") else float(snap_conf.get("timestamp", 0.0))
        if abs(t_conf_target - ts_conf_actual) > stale_tol:
            return {
                "status": "UNCONFIRMED",
                "status_label": "Непідтверджений хибний пробій",
                "is_confirmed": False,
                "oi_before": None,
                "oi_after": None,
                "oi_delta": None,
                "oi_delta_pct": None,
                "reason": "STALE_DATA",
                "reason_desc": "Дані Open Interest застарілі для моменту підтвердження",
            }
        oi_conf = snap_conf.oi if hasattr(snap_conf, "oi") else snap_conf.get("oi")

    if oi_pre is None or oi_conf is None:
        return {
            "status": "UNCONFIRMED",
            "status_label": "Непідтверджений хибний пробій",
            "is_confirmed": False,
            "oi_before": None,
            "oi_after": None,
            "oi_delta": None,
            "oi_delta_pct": None,
            "reason": "MISSING_DATA",
            "reason_desc": "Дані Open Interest (OI) відсутні для періоду пробою",
        }

    try:
        oi_pre_val = float(oi_pre)
        oi_conf_val = float(oi_conf)
    except (ValueError, TypeError):
        return {
            "status": "UNCONFIRMED",
            "status_label": "Непідтверджений хибний пробій",
            "is_confirmed": False,
            "oi_before": None,
            "oi_after": None,
            "oi_delta": None,
            "oi_delta_pct": None,
            "reason": "INVALID_DATA",
            "reason_desc": "Некоректний формат значень Open Interest (OI)",
        }

    if (
        math.isnan(oi_pre_val) or math.isnan(oi_conf_val)
        or math.isinf(oi_pre_val) or math.isinf(oi_conf_val)
        or oi_pre_val <= 0 or oi_conf_val <= 0
    ):
        return {
            "status": "UNCONFIRMED",
            "status_label": "Непідтверджений хибний пробій",
            "is_confirmed": False,
            "oi_before": None,
            "oi_after": None,
            "oi_delta": None,
            "oi_delta_pct": None,
            "reason": "INVALID_DATA",
            "reason_desc": "Значення Open Interest (OI) мають бути додатними дійсними числами",
        }

    delta = oi_conf_val - oi_pre_val
    delta_pct = (delta / oi_pre_val) * 100.0

    # If the confirmation candle is still unclosed (live open candle), it is strictly POTENTIAL
    if not is_candle_closed:
        return {
            "status": "POTENTIAL",
            "status_label": "Потенційний хибний пробій",
            "is_confirmed": False,
            "oi_before": oi_pre_val,
            "oi_after": oi_conf_val,
            "oi_delta": round(delta, 4),
            "oi_delta_pct": round(delta_pct, 4),
            "reason": "PENDING_CANDLE_CLOSE",
            "reason_desc": f"Потенційна зміна OI ({delta_pct:+.2f}%) — очікується закриття свічки для фінального підтвердження",
        }

    # Confirmation criteria for closed candles: OI must drop by at least min_oi_drop_pct
    if delta_pct <= -cfg.min_oi_drop_pct:
        return {
            "status": "CONFIRMED",
            "status_label": "Підтверджений хибний пробій",
            "is_confirmed": True,
            "oi_before": oi_pre_val,
            "oi_after": oi_conf_val,
            "oi_delta": round(delta, 4),
            "oi_delta_pct": round(delta_pct, 4),
            "reason": "OI_DROP_CONFIRMED",
            "reason_desc": f"Скорочення відкритого інтересу на {delta_pct:.2f}% — частина відкритих позицій була закрита",
        }
    elif delta_pct > cfg.noise_threshold_pct:
        return {
            "status": "UNCONFIRMED",
            "status_label": "Непідтверджений хибний пробій",
            "is_confirmed": False,
            "oi_before": oi_pre_val,
            "oi_after": oi_conf_val,
            "oi_delta": round(delta, 4),
            "oi_delta_pct": round(delta_pct, 4),
            "reason": "OI_INCREASE",
            "reason_desc": f"OI зріс на +{delta_pct:.2f}% (позиції нарощувалися, а не закривалися)",
        }
    else:
        return {
            "status": "UNCONFIRMED",
            "status_label": "Непідтверджений хибний пробій",
            "is_confirmed": False,
            "oi_before": oi_pre_val,
            "oi_after": oi_conf_val,
            "oi_delta": round(delta, 4),
            "oi_delta_pct": round(delta_pct, 4),
            "reason": "OI_NOISE",
            "reason_desc": f"Зміна OI ({delta_pct:+.2f}%) в межах шуму (поріг чутливості -{cfg.min_oi_drop_pct:.2f}%)",
        }



def _calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    n = len(candles)
    if n < 2:
        return 0.0
    true_ranges: List[float] = []
    for i in range(1, n):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        true_ranges.append(tr)
    window = true_ranges[-period:] if len(true_ranges) >= period else true_ranges
    return sum(window) / len(window) if window else 0.0


def _get_avg_volume(candles: List[Dict[str, Any]], idx: int, period: int = 20) -> float:
    start_idx = max(0, idx - period)
    vols = [candles[k].get("volume", 0.0) for k in range(start_idx, idx + 1)]
    return sum(vols) / len(vols) if vols else 1.0


def detect_false_breakouts(
    candles: List[Dict[str, Any]],
    levels: Optional[List[Dict[str, Any]]] = None,
    interval: str = "5m",
    min_touches: int = 1,
    max_history_bars: Optional[int] = None,
    min_wick_pct: float = 0.04,
    oi_tracker: Optional[Any] = None,
    oi_snapshots: Optional[List[Any]] = None,
    coin: Optional[str] = None,
    config: Optional[FalseBreakoutOIConfig] = None,
    min_oi_drop_pct: Optional[float] = None,
    comparison_period_bars: Optional[int] = None,
    max_wait_bars: Optional[int] = None,
    only_confirmed: bool = False,
) -> List[Dict[str, Any]]:
    """
    Identifies False Breakouts against confirmed support/resistance levels
    filtered and confirmed by Open Interest (OI) drop.
    """
    n = len(candles)
    if n < 3 or not levels:
        return []

    clean_interval = interval.lower()
    if max_history_bars is None:
        max_history_bars = TIMEFRAME_RECENCY_BARS.get(clean_interval, 40)

    # Resolve configurable parameters
    oi_cfg = config or DEFAULT_OI_CONFIG
    if min_oi_drop_pct is not None or comparison_period_bars is not None or max_wait_bars is not None:
        oi_cfg = FalseBreakoutOIConfig(
            min_oi_drop_pct=float(min_oi_drop_pct if min_oi_drop_pct is not None else oi_cfg.min_oi_drop_pct),
            comparison_period_bars=int(comparison_period_bars if comparison_period_bars is not None else oi_cfg.comparison_period_bars),
            max_wait_bars=int(max_wait_bars if max_wait_bars is not None else oi_cfg.max_wait_bars),
            noise_threshold_pct=oi_cfg.noise_threshold_pct,
            stale_oi_max_age_seconds=oi_cfg.stale_oi_max_age_seconds,
            require_oi_confirmation=oi_cfg.require_oi_confirmation,
        )

    atr = _calculate_atr(candles, 14)
    if atr <= 0:
        atr = candles[-1]["close"] * 0.001

    results: List[Dict[str, Any]] = []

    # Limit search to the last max_history_bars closed candles to ensure only ACTIVE & RELEVANT breakouts are shown
    start_idx = max(1, n - max_history_bars)

    for lvl in levels:
        level_px = float(lvl.get("center_price", lvl.get("price", 0.0)))
        if level_px <= 0:
            continue

        touches = int(lvl.get("touches", lvl.get("touches_count", 1)))
        if touches < min_touches:
            continue

        strength_score = float(lvl.get("strength_score", 50.0))
        level_type = str(lvl.get("type", "")).lower()  # "resistance" or "support"
        if not level_type:
            # Infer from relation if not explicitly tagged
            level_type = "resistance" if level_px >= candles[-1]["close"] else "support"

        # Search chronologically
        i = start_idx
        while i < n:
            c = candles[i]
            c_high = c["high"]
            c_low = c["low"]
            c_close = c["close"]
            c_time = c["time"]

            # -------------------------------------------------------------
            # 1. FALSE BREAKOUT UP (Resistance)
            # -------------------------------------------------------------
            if level_type == "resistance":
                # Condition: High breached the resistance level
                if c_high > level_px:
                    excess = (c_high - level_px) / level_px * 100
                    # Avoid micro fluctuations and avoid runaway pumps (> 3.5 ATR)
                    if excess >= min_wick_pct and (c_high - level_px) <= 3.5 * atr:
                        avg_vol = _get_avg_volume(candles, i)
                        c_vol = c.get("volume", 0.0)

                        # Case A: Same candle rejection (Wick sweep)
                        if c_close < level_px:
                            oi_eval = evaluate_false_breakout_oi(
                                candles=candles,
                                breakout_idx=i,
                                conf_idx=i,
                                interval=clean_interval,
                                oi_tracker=oi_tracker,
                                oi_snapshots=oi_snapshots,
                                config=oi_cfg,
                                coin=coin,
                            )

                            conf_status = oi_eval["status"]
                            oi_pct = oi_eval["oi_delta_pct"]

                            if conf_status == "CONFIRMED":
                                formation_title = "Підтверджений хибний пробій опору"
                                desc = f"Хибний пробій опору {level_px:.2f}: прокол тінню до {c_high:.2f}, повернення під рівень та скорочення OI {oi_pct:+.2f}%"
                            elif conf_status == "POTENTIAL":
                                formation_title = "Потенційний хибний пробій опору"
                                desc = f"Потенційний хибний пробій опору {level_px:.2f}: прокол тінню до {c_high:.2f}, очікується підтвердження OI"
                            else:
                                formation_title = "Непідтверджений хибний пробій опору"
                                oi_str = f"зміна OI {oi_pct:+.2f}%" if oi_pct is not None else "дані OI відсутні/застарілі"
                                desc = f"Хибний пробій опору {level_px:.2f}: повернення під рівень, але {oi_str}"

                            results.append({
                                "id": f"fb-up-{int(level_px * 100)}-{c_time}",
                                "type": "bearish_sweep",
                                "subType": "wick_rejection",
                                "formation": formation_title,
                                "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                                "sweepPrice": round(c_high, 2 if c_high > 10 else 4),
                                "breakoutTime": c_time,
                                "confirmationTime": c_time,
                                "time": c_time,
                                "direction": "SHORT",
                                "touches": touches,
                                "levelStrength": strength_score,
                                "volumeRatio": round(c_vol / max(avg_vol, 1e-6), 2),
                                "desc": desc,
                                "confirmationStatus": conf_status,
                                "statusLabel": oi_eval["status_label"],
                                "oiConfirmed": oi_eval["is_confirmed"],
                                "oiDelta": oi_eval["oi_delta"],
                                "oiDeltaPct": oi_eval["oi_delta_pct"],
                                "oiBefore": oi_eval["oi_before"],
                                "oiAfter": oi_eval["oi_after"],
                                "oiReason": oi_eval["reason"],
                                "oiReasonDesc": oi_eval["reason_desc"],
                            })
                            i += 1
                            continue

                        # Case B: Multi-candle breakout (Candle i closed above, returns & closes below within max_wait_bars)
                        elif c_close >= level_px:
                            # Search forward up to max_wait_bars for price return
                            return_offset = None
                            for offset in range(1, min(oi_cfg.max_wait_bars + 1, n - i)):
                                ret_c = candles[i + offset]
                                # Check if moved excessively away (> 3.5 ATR) -> genuine breakout impulse
                                cur_max_h = max(candles[k]["high"] for k in range(i, i + offset + 1))
                                if (cur_max_h - level_px) > 3.5 * atr:
                                    break
                                if ret_c["close"] < level_px:
                                    return_offset = offset
                                    break

                            if return_offset is not None:
                                conf_idx = i + return_offset
                                conf_c = candles[conf_idx]
                                conf_time = conf_c["time"]
                                next_vol = conf_c.get("volume", 0.0)
                                max_high = max(candles[k]["high"] for k in range(i, conf_idx + 1))

                                oi_eval = evaluate_false_breakout_oi(
                                    candles=candles,
                                    breakout_idx=i,
                                    conf_idx=conf_idx,
                                    interval=clean_interval,
                                    oi_tracker=oi_tracker,
                                    oi_snapshots=oi_snapshots,
                                    config=oi_cfg,
                                    coin=coin,
                                )

                                conf_status = oi_eval["status"]
                                oi_pct = oi_eval["oi_delta_pct"]

                                if conf_status == "CONFIRMED":
                                    formation_title = f"Підтверджений хибний пробій опору ({return_offset + 1} свічки)"
                                    desc = f"Хибний пробій опору {level_px:.2f}: вихід тілом свічки, повернення під рівень та скорочення OI {oi_pct:+.2f}%"
                                elif conf_status == "POTENTIAL":
                                    formation_title = f"Потенційний хибний пробій опору ({return_offset + 1} свічки)"
                                    desc = f"Потенційний хибний пробій опору {level_px:.2f}: повернення під рівень, очікується підтвердження OI"
                                else:
                                    formation_title = f"Непідтверджений хибний пробій опору ({return_offset + 1} свічки)"
                                    oi_str = f"зміна OI {oi_pct:+.2f}%" if oi_pct is not None else "дані OI відсутні/застарілі"
                                    desc = f"Хибний пробій опору {level_px:.2f}: повернення під рівень, але {oi_str}"

                                results.append({
                                    "id": f"fb-up-{int(level_px * 100)}-{conf_time}",
                                    "type": "bearish_sweep",
                                    "subType": "two_candle_reversal" if return_offset == 1 else "multi_candle_reversal",
                                    "formation": formation_title,
                                    "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                                    "sweepPrice": round(max_high, 2 if max_high > 10 else 4),
                                    "breakoutTime": c_time,
                                    "confirmationTime": conf_time,
                                    "time": conf_time,
                                    "direction": "SHORT",
                                    "touches": touches,
                                    "levelStrength": strength_score,
                                    "volumeRatio": round(next_vol / max(avg_vol, 1e-6), 2),
                                    "desc": desc,
                                    "confirmationStatus": conf_status,
                                    "statusLabel": oi_eval["status_label"],
                                    "oiConfirmed": oi_eval["is_confirmed"],
                                    "oiDelta": oi_eval["oi_delta"],
                                    "oiDeltaPct": oi_eval["oi_delta_pct"],
                                    "oiBefore": oi_eval["oi_before"],
                                    "oiAfter": oi_eval["oi_after"],
                                    "oiReason": oi_eval["reason"],
                                    "oiReasonDesc": oi_eval["reason_desc"],
                                })
                                i = conf_idx + 1
                                continue

            # -------------------------------------------------------------
            # 2. FALSE BREAKOUT DOWN (Support)
            # -------------------------------------------------------------
            elif level_type == "support":
                # Condition: Low breached the support level
                if c_low < level_px:
                    excess = (level_px - c_low) / level_px * 100
                    # Avoid micro fluctuations and runaway dumps (> 3.5 ATR)
                    if excess >= min_wick_pct and (level_px - c_low) <= 3.5 * atr:
                        avg_vol = _get_avg_volume(candles, i)
                        c_vol = c.get("volume", 0.0)

                        # Case A: Same candle rejection (Wick sweep / откуп)
                        if c_close > level_px:
                            oi_eval = evaluate_false_breakout_oi(
                                candles=candles,
                                breakout_idx=i,
                                conf_idx=i,
                                interval=clean_interval,
                                oi_tracker=oi_tracker,
                                oi_snapshots=oi_snapshots,
                                config=oi_cfg,
                                coin=coin,
                            )

                            conf_status = oi_eval["status"]
                            oi_pct = oi_eval["oi_delta_pct"]

                            if conf_status == "CONFIRMED":
                                formation_title = "Підтверджений хибний пробій підтримки"
                                desc = f"Хибний пробій підтримки {level_px:.2f}: прокол тінню до {c_low:.2f}, відкуп вище рівня та скорочення OI {oi_pct:+.2f}%"
                            elif conf_status == "POTENTIAL":
                                formation_title = "Потенційний хибний пробій підтримки"
                                desc = f"Потенційний хибний пробій підтримки {level_px:.2f}: прокол тінню до {c_low:.2f}, очікується підтвердження OI"
                            else:
                                formation_title = "Непідтверджений хибний пробій підтримки"
                                oi_str = f"зміна OI {oi_pct:+.2f}%" if oi_pct is not None else "дані OI відсутні/застарілі"
                                desc = f"Хибний пробій підтримки {level_px:.2f}: відкуп вище рівня, але {oi_str}"

                            results.append({
                                "id": f"fb-down-{int(level_px * 100)}-{c_time}",
                                "type": "bullish_sweep",
                                "subType": "wick_rejection",
                                "formation": formation_title,
                                "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                                "sweepPrice": round(c_low, 2 if c_low > 10 else 4),
                                "breakoutTime": c_time,
                                "confirmationTime": c_time,
                                "time": c_time,
                                "direction": "LONG",
                                "touches": touches,
                                "levelStrength": strength_score,
                                "volumeRatio": round(c_vol / max(avg_vol, 1e-6), 2),
                                "desc": desc,
                                "confirmationStatus": conf_status,
                                "statusLabel": oi_eval["status_label"],
                                "oiConfirmed": oi_eval["is_confirmed"],
                                "oiDelta": oi_eval["oi_delta"],
                                "oiDeltaPct": oi_eval["oi_delta_pct"],
                                "oiBefore": oi_eval["oi_before"],
                                "oiAfter": oi_eval["oi_after"],
                                "oiReason": oi_eval["reason"],
                                "oiReasonDesc": oi_eval["reason_desc"],
                            })
                            i += 1
                            continue

                        # Case B: Multi-candle breakout (Candle i closed below, returns & closes above within max_wait_bars)
                        elif c_close <= level_px:
                            return_offset = None
                            for offset in range(1, min(oi_cfg.max_wait_bars + 1, n - i)):
                                ret_c = candles[i + offset]
                                cur_min_l = min(candles[k]["low"] for k in range(i, i + offset + 1))
                                if (level_px - cur_min_l) > 3.5 * atr:
                                    break
                                if ret_c["close"] > level_px:
                                    return_offset = offset
                                    break

                            if return_offset is not None:
                                conf_idx = i + return_offset
                                conf_c = candles[conf_idx]
                                conf_time = conf_c["time"]
                                next_vol = conf_c.get("volume", 0.0)
                                min_low = min(candles[k]["low"] for k in range(i, conf_idx + 1))

                                oi_eval = evaluate_false_breakout_oi(
                                    candles=candles,
                                    breakout_idx=i,
                                    conf_idx=conf_idx,
                                    interval=clean_interval,
                                    oi_tracker=oi_tracker,
                                    oi_snapshots=oi_snapshots,
                                    config=oi_cfg,
                                    coin=coin,
                                )

                                conf_status = oi_eval["status"]
                                oi_pct = oi_eval["oi_delta_pct"]

                                if conf_status == "CONFIRMED":
                                    formation_title = f"Підтверджений хибний пробій підтримки ({return_offset + 1} свічки)"
                                    desc = f"Хибний пробій підтримки {level_px:.2f}: вихід тілом свічки, повернення вище рівня та скорочення OI {oi_pct:+.2f}%"
                                elif conf_status == "POTENTIAL":
                                    formation_title = f"Потенційний хибний пробій підтримки ({return_offset + 1} свічки)"
                                    desc = f"Потенційний хибний пробій підтримки {level_px:.2f}: повернення вище рівня, очікується підтвердження OI"
                                else:
                                    formation_title = f"Непідтверджений хибний пробій підтримки ({return_offset + 1} свічки)"
                                    oi_str = f"зміна OI {oi_pct:+.2f}%" if oi_pct is not None else "дані OI відсутні/застарілі"
                                    desc = f"Хибний пробій підтримки {level_px:.2f}: повернення вище рівня, але {oi_str}"

                                results.append({
                                    "id": f"fb-down-{int(level_px * 100)}-{conf_time}",
                                    "type": "bullish_sweep",
                                    "subType": "two_candle_reversal" if return_offset == 1 else "multi_candle_reversal",
                                    "formation": formation_title,
                                    "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                                    "sweepPrice": round(min_low, 2 if min_low > 10 else 4),
                                    "breakoutTime": c_time,
                                    "confirmationTime": conf_time,
                                    "time": conf_time,
                                    "direction": "LONG",
                                    "touches": touches,
                                    "levelStrength": strength_score,
                                    "volumeRatio": round(next_vol / max(avg_vol, 1e-6), 2),
                                    "desc": desc,
                                    "confirmationStatus": conf_status,
                                    "statusLabel": oi_eval["status_label"],
                                    "oiConfirmed": oi_eval["is_confirmed"],
                                    "oiDelta": oi_eval["oi_delta"],
                                    "oiDeltaPct": oi_eval["oi_delta_pct"],
                                    "oiBefore": oi_eval["oi_before"],
                                    "oiAfter": oi_eval["oi_after"],
                                    "oiReason": oi_eval["reason"],
                                    "oiReasonDesc": oi_eval["reason_desc"],
                                })
                                i = conf_idx + 1
                                continue

            i += 1

    # Filter out invalidated / historical false breakouts that have lost their trading relevance:
    active_results: List[Dict[str, Any]] = []
    for sig in results:
        conf_time = sig.get("confirmationTime", sig["time"])
        # Find index in candles
        c_idx = next((k for k in range(n - 1, -1, -1) if candles[k]["time"] <= conf_time), -1)
        if c_idx < 0:
            continue

        bars_ago = n - 1 - c_idx
        if bars_ago > max_history_bars:
            continue

        level_px = sig["levelPrice"]
        subsequent = candles[c_idx + 1:]

        # Invalidation check:
        # A false breakout is invalidated if price subsequently accepts beyond the level (closes on the wrong side)
        is_invalidated = False
        if sig["direction"] == "SHORT":
            if any(sc["close"] > level_px for sc in subsequent):
                is_invalidated = True
        else:
            if any(sc["close"] < level_px for sc in subsequent):
                is_invalidated = True

        if not is_invalidated:
            active_results.append(sig)

    # Optional filter: keep only confirmed if explicitly requested
    if only_confirmed:
        active_results = [r for r in active_results if r.get("oiConfirmed")]

    # Deduplicate and resolve overlapping levels:
    def _importance_score(sig: Dict[str, Any]) -> float:
        strength = float(sig.get("levelStrength", 50.0))
        touches = float(sig.get("touches", 1))
        vol = float(sig.get("volumeRatio", 1.0))
        oi_bonus = 60.0 if sig.get("oiConfirmed") else (15.0 if sig.get("confirmationStatus") == "POTENTIAL" else 0.0)
        time_score = (sig["time"] - candles[0]["time"]) / max(candles[-1]["time"] - candles[0]["time"], 1) * 10.0
        return (strength * 2.0) + (touches * 15.0) + (vol * 10.0) + oi_bonus + time_score

    # Sort candidates by importance descending
    candidates = sorted(active_results, key=_importance_score, reverse=True)
    deduped: List[Dict[str, Any]] = []

    min_price_dist_pct = 0.6
    min_atr_dist = 1.5 * atr

    for cand in candidates:
        cand_px = cand["levelPrice"]
        is_collision = False
        for chosen in deduped:
            chosen_px = chosen["levelPrice"]
            pct_diff = abs(cand_px - chosen_px) / chosen_px * 100
            atr_diff = abs(cand_px - chosen_px)
            if pct_diff < min_price_dist_pct or atr_diff < min_atr_dist:
                is_collision = True
                break

        if not is_collision:
            deduped.append(cand)

    # Sort final clean signals chronologically for consistent chart & timeline ordering
    deduped.sort(key=lambda s: s["time"])

    # Limit to top 4 most prominent non-overlapping breakouts on the chart
    if len(deduped) > 4:
        top_deduped = sorted(deduped, key=_importance_score, reverse=True)[:4]
        top_deduped.sort(key=lambda s: s["time"])
        return top_deduped

    return deduped

