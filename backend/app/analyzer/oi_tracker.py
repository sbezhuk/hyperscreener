"""
Open Interest (OI) Delta Tracking and Breakout Confirmation Engine.

Provides:
- Real-time time-series buffer of genuine Hyperliquid Open Interest snapshots (timestamp, oi, price).
- Multi-interval absolute and percentage delta calculation (1m, 5m, 15m, 1h) with strict tolerance and gap detection.
- Fast O(log N) bisect snapshot lookups.
- Discrete 1-minute bucketed adaptive volatility calculation with outlier filtering.
- Impulse breakout tracking (determining pre-breakout baseline when price gaps over levels).
- Breakout latching/debouncing to prevent repeated event generation on every tick.
- Neutral, factual signal interpretations without unsubstantiated intent assertions.
"""

from __future__ import annotations

import bisect
import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any


@dataclass(frozen=True)
class OISnapshot:
    timestamp: float  # Unix timestamp in seconds
    oi: float         # Open Interest in contract/base token units
    price: float      # Mark or traded price at that timestamp


class LevelTestState:
    """State tracking for a specific price level being tested or broken."""
    def __init__(self, level_id: str, level_price: float, level_type: str):
        self.level_id = level_id
        self.level_price = level_price
        self.level_type = level_type.lower()  # 'resistance' or 'support'
        self.is_testing: bool = False
        self.test_start_time: Optional[float] = None
        self.test_start_price: Optional[float] = None
        self.test_start_oi: Optional[float] = None
        self.has_fired_breakout: bool = False  # Latch guard: single event per breakout
        self.has_fired_buildup: bool = False   # Latch guard: single event per test period for Scenario D
        self.last_breakout_time: Optional[float] = None
        self.last_status: str = "INACTIVE"
        self.last_scenario: Optional[str] = None
        self.last_analysis: Optional[Dict[str, Any]] = None

    def reset_breakout_latch(self):
        """Allows firing a new breakout event once price returns inside test zone or retraces."""
        self.has_fired_breakout = False
        self.has_fired_buildup = False
        self.is_testing = False
        self.test_start_time = None
        self.test_start_price = None
        self.test_start_oi = None


class OITracker:
    """
    Tracks Open Interest time-series data for a single coin, computes interval deltas,
    adapts volatility threshold, and monitors level interactions.
    """

    # Maximum timestamp tolerance (in seconds) for each interval before flagging GAP_DETECTED
    INTERVAL_TOLERANCE_MAP = {
        60: 15.0,     # 1m: within +/- 15s
        300: 30.0,    # 5m: within +/- 30s
        900: 60.0,    # 15m: within +/- 60s
        3600: 180.0   # 1h: within +/- 180s
    }

    def __init__(self, coin: str, max_history_seconds: int = 7200, stale_threshold_seconds: int = 120):
        self.coin = coin.upper()
        self.max_history_seconds = max_history_seconds
        self.stale_threshold_seconds = stale_threshold_seconds
        # In-memory history maintained in strict timestamp ascending order for O(log N) bisect
        self._history: List[OISnapshot] = []
        self._timestamps: List[float] = []
        self._last_checkpoint_time: float = 0.0
        # Active level test states keyed by level identifier
        self._level_states: Dict[str, LevelTestState] = {}

    def clear(self):
        self._history.clear()
        self._timestamps.clear()
        self._last_checkpoint_time = 0.0
        self._level_states.clear()

    def record_snapshot(self, oi: float, price: float, timestamp: Optional[float] = None) -> bool:
        """
        Records a real Open Interest observation.
        Rejects invalid values (oi <= 0, price <= 0, nan, inf).
        Throttles duplicate identical snapshots while guaranteeing periodic checkpoints.
        """
        if timestamp is None:
            timestamp = time.time()

        if not isinstance(oi, (int, float)) or not isinstance(price, (int, float)):
            return False
        if math.isnan(oi) or math.isnan(price) or math.isinf(oi) or math.isinf(price):
            return False
        if oi <= 0 or price <= 0:
            return False

        oi_val = float(oi)
        px_val = float(price)

        if self._history:
            last = self._history[-1]
            last_ts = last.timestamp

            # Discard strictly out-of-order older samples
            if timestamp < last_ts:
                return False

            # Same microsecond or timestamp: update in place
            if abs(timestamp - last_ts) < 0.001:
                self._history[-1] = OISnapshot(timestamp=timestamp, oi=oi_val, price=px_val)
                self._timestamps[-1] = timestamp
                return True

            # If OI is identical and price changed by less than 0.01% within < 3 seconds
            # of the LAST RECORDED CHECKPOINT, update timestamp in-place to save memory.
            # Once 3.0s elapsed from last checkpoint, record a new checkpoint.
            is_identical_oi = abs(last.oi - oi_val) < 1e-9
            is_identical_px = abs(last.price - px_val) / max(px_val, 1e-9) < 0.0001
            if is_identical_oi and is_identical_px and (timestamp - self._last_checkpoint_time) < 3.0:
                self._history[-1] = OISnapshot(timestamp=timestamp, oi=oi_val, price=px_val)
                self._timestamps[-1] = timestamp
                return True

        self._history.append(OISnapshot(timestamp=timestamp, oi=oi_val, price=px_val))
        self._timestamps.append(timestamp)
        self._last_checkpoint_time = timestamp

        # Prune old snapshots beyond max_history_seconds
        cutoff = timestamp - self.max_history_seconds
        if self._timestamps[0] < cutoff:
            idx = bisect.bisect_left(self._timestamps, cutoff)
            if idx > 0:
                self._history = self._history[idx:]
                self._timestamps = self._timestamps[idx:]

        return True

    @property
    def latest(self) -> Optional[OISnapshot]:
        return self._history[-1] if self._history else None

    @property
    def is_stale(self) -> bool:
        """Data is stale if no fresh observation was received within stale_threshold_seconds."""
        if not self._history:
            return True
        return (time.time() - self._history[-1].timestamp) > self.stale_threshold_seconds

    def _find_snapshot_at_or_before(self, target_time: float) -> Optional[OISnapshot]:
        """
        Fast O(log N) bisect lookup for the snapshot closest to (at or immediately before) target_time.
        """
        if not self._history:
            return None
        if target_time >= self._timestamps[-1]:
            return self._history[-1]
        if target_time <= self._timestamps[0]:
            return self._history[0]

        idx = bisect.bisect_right(self._timestamps, target_time)
        return self._history[idx - 1] if idx > 0 else self._history[0]

    def _find_pre_breakout_snapshot(
        self,
        level_price: float,
        level_type: str,
        max_lookback_seconds: int = 300
    ) -> Optional[OISnapshot]:
        """
        Finds the most recent historical snapshot before an impulse crossed the level.
        Used to establish a baseline when price abruptly breaks out without earlier test tracking.
        """
        if not self._history or len(self._history) < 2:
            return None

        curr_time = self._history[-1].timestamp
        cutoff = curr_time - max_lookback_seconds

        # Iterate backwards to find last snapshot that was strictly on the opposite side of level
        for snap in reversed(self._history[:-1]):
            if snap.timestamp < cutoff:
                break
            if level_type == "resistance" and snap.price <= level_price:
                return snap
            if level_type == "support" and snap.price >= level_price:
                return snap

        # Fallback to snapshot closest to cutoff if within lookback
        cutoff_snap = self._find_snapshot_at_or_before(cutoff)
        if cutoff_snap and (curr_time - cutoff_snap.timestamp) <= (max_lookback_seconds + 30):
            return cutoff_snap

        return None

    def compute_interval_delta(self, interval_seconds: int) -> Dict[str, Any]:
        """
        Calculates absolute and percentage change between the beginning and the end of the interval.
        Strict verification:
        - Prevents substitution of one timeframe for another (e.g. 45 min history is NOT 1h).
        - Flags GAP_DETECTED if the closest historical snapshot deviates beyond allowed tolerance.
        """
        if not self._history:
            return {
                "interval_seconds": interval_seconds,
                "current_oi": None,
                "previous_oi": None,
                "delta": 0.0,
                "delta_pct": 0.0,
                "status": "NO_DATA",
                "is_valid": False,
                "start_time": None,
                "end_time": None,
                "actual_duration_seconds": 0
            }

        curr = self._history[-1]
        target_start = curr.timestamp - interval_seconds
        first_available = self._history[0]
        total_history_span = curr.timestamp - first_available.timestamp

        tolerance = self.INTERVAL_TOLERANCE_MAP.get(interval_seconds, max(15.0, interval_seconds * 0.05))

        # 1. Check history completeness: history must span at least (interval - tolerance)
        if total_history_span < (interval_seconds - tolerance):
            prev_oi = first_available.oi
            delta = curr.oi - prev_oi
            delta_pct = ((curr.oi - prev_oi) / prev_oi * 100.0) if prev_oi > 0 else 0.0
            return {
                "interval_seconds": interval_seconds,
                "current_oi": curr.oi,
                "previous_oi": prev_oi,
                "delta": round(delta, 4),
                "delta_pct": round(delta_pct, 4),
                "status": "INSUFFICIENT_HISTORY",
                "is_valid": False,
                "start_time": first_available.timestamp,
                "end_time": curr.timestamp,
                "actual_duration_seconds": round(total_history_span, 1)
            }

        start_snap = self._find_snapshot_at_or_before(target_start)
        if not start_snap:
            return {
                "interval_seconds": interval_seconds,
                "current_oi": curr.oi,
                "previous_oi": None,
                "delta": 0.0,
                "delta_pct": 0.0,
                "status": "NO_DATA",
                "is_valid": False,
                "start_time": None,
                "end_time": curr.timestamp,
                "actual_duration_seconds": 0
            }

        # 2. Check for time deviation (Gap Detection)
        actual_interval = curr.timestamp - start_snap.timestamp
        deviation = abs(actual_interval - interval_seconds)

        if deviation > tolerance:
            # Significant data gap occurred
            delta = curr.oi - start_snap.oi
            delta_pct = ((curr.oi - start_snap.oi) / start_snap.oi * 100.0) if start_snap.oi > 0 else 0.0
            return {
                "interval_seconds": interval_seconds,
                "current_oi": curr.oi,
                "previous_oi": start_snap.oi,
                "delta": round(delta, 4),
                "delta_pct": round(delta_pct, 4),
                "status": "GAP_DETECTED",
                "is_valid": False,
                "start_time": start_snap.timestamp,
                "end_time": curr.timestamp,
                "actual_duration_seconds": round(actual_interval, 1)
            }

        # 3. Check recency of latest snapshot
        if (time.time() - curr.timestamp) > self.stale_threshold_seconds:
            status = "STALE"
            is_valid = False
        else:
            status = "OK"
            is_valid = True

        delta = curr.oi - start_snap.oi
        delta_pct = ((curr.oi - start_snap.oi) / start_snap.oi * 100.0) if start_snap.oi > 0 else 0.0

        return {
            "interval_seconds": interval_seconds,
            "current_oi": curr.oi,
            "previous_oi": start_snap.oi,
            "delta": round(delta, 4),
            "delta_pct": round(delta_pct, 4),
            "status": status,
            "is_valid": is_valid,
            "start_time": start_snap.timestamp,
            "end_time": curr.timestamp,
            "actual_duration_seconds": round(actual_interval, 1)
        }

    def compute_all_deltas(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns OI Delta calculations across all standard intervals:
        1m (60s), 5m (300s), 15m (900s), 1h (3600s).
        """
        intervals = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600
        }
        res: Dict[str, Dict[str, Any]] = {}
        for label, secs in intervals.items():
            res[label] = self.compute_interval_delta(secs)
        return res

    def get_oi_volatility_info(self, sample_period_seconds: int = 3600) -> Dict[str, Any]:
        """
        Constructs discrete 1-minute bucketed observations over sample_period to compute
        a statistically robust standard deviation of percentage changes.
        Includes outlier filtering (winsorization at 95th percentile).
        Bounded between theta_min (0.10%) and theta_max (2.50%).
        """
        fallback_threshold = 0.25

        if len(self._history) < 10:
            return {
                "threshold_pct": fallback_threshold,
                "is_adaptive": False,
                "status": "INSUFFICIENT_HISTORY",
                "samples_count": len(self._history),
                "desc": "Недостатньо спостережень для адаптивного порога (використовується фіксований 0.25%)"
            }

        now = self._history[-1].timestamp
        first_ts = self._history[0].timestamp
        span = now - first_ts

        # Need at least 10 minutes of history for a stable adaptive threshold
        if span < 600:
            return {
                "threshold_pct": fallback_threshold,
                "is_adaptive": False,
                "status": "INSUFFICIENT_HISTORY",
                "samples_count": len(self._history),
                "desc": "Історія коротша за 10 хвилин (використовується фіксований 0.25%)"
            }

        effective_period = min(sample_period_seconds, int(span))
        minute_steps = effective_period // 60

        # Sample snapshots at discrete 1-minute steps backwards
        sampled_ois: List[float] = []
        for step in range(minute_steps + 1):
            t_target = now - (step * 60)
            snap = self._find_snapshot_at_or_before(t_target)
            if snap and abs(t_target - snap.timestamp) <= 25.0 and snap.oi > 0:
                sampled_ois.append(snap.oi)

        if len(sampled_ois) < 8:
            return {
                "threshold_pct": fallback_threshold,
                "is_adaptive": False,
                "status": "INSUFFICIENT_HISTORY",
                "samples_count": len(sampled_ois),
                "desc": "Недостатньо дискретних хвилинних зрізів (використовується 0.25%)"
            }

        # Compute step-by-step percentage changes
        pct_changes: List[float] = []
        for i in range(len(sampled_ois) - 1):
            prev = sampled_ois[i + 1]
            curr = sampled_ois[i]
            if prev > 0:
                pct = abs((curr - prev) / prev * 100.0)
                pct_changes.append(pct)

        if len(pct_changes) < 6:
            return {
                "threshold_pct": fallback_threshold,
                "is_adaptive": False,
                "status": "INSUFFICIENT_HISTORY",
                "samples_count": len(pct_changes),
                "desc": "Недостатньо змін для розрахунку дисперсії"
            }

        # Outlier filtering: winsorize extreme spikes above 95th percentile
        sorted_changes = sorted(pct_changes)
        p95_idx = int(len(sorted_changes) * 0.95)
        p95_val = sorted_changes[p95_idx]
        cleaned_changes = [min(x, p95_val) for x in pct_changes]

        # Use RMS (Root Mean Square) of cleaned percentage changes to capture magnitude of drift and noise
        rms = math.sqrt(sum(x ** 2 for x in cleaned_changes) / len(cleaned_changes))

        # Baseline threshold is 1.2 * RMS, bounded between 0.10% and 2.50%
        threshold = max(0.10, min(2.50, rms * 1.2))
        threshold_final = round(threshold, 3)

        return {
            "threshold_pct": threshold_final,
            "is_adaptive": True,
            "status": "OK",
            "samples_count": len(cleaned_changes),
            "rms_pct": round(rms, 4),
            "desc": f"Адаптивний поріг обчислено за {len(cleaned_changes)} хвилинними зрізами (RMS: {rms:.3f}%)"
        }

    def compute_oi_volatility(self, sample_period_seconds: int = 3600) -> float:
        """Returns the float threshold theta for level analysis."""
        info = self.get_oi_volatility_info(sample_period_seconds)
        return float(info["threshold_pct"])

    def analyze_level_interaction(
        self,
        level: Dict[str, Any],
        proximity_pct: float = 0.35,
        threshold_pct: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Tracks interaction between current price / OI and a support or resistance level.
        Includes:
        - Impulse breakout support (pre-breakout historical baseline lookup).
        - Breakout latching/debouncing: prevents spamming duplicate breakout events on each tick.
        - Factual, neutral signal interpretation without unsubstantiated intent assertions.
        """
        if not self._history:
            return {
                "level_id": level.get("zone_id") or str(level.get("price")),
                "status": "NO_OI_DATA",
                "scenario": None,
                "is_valid": False,
                "is_new_event": False,
                "desc": "Немає даних OI для аналізу рівня"
            }

        curr = self._history[-1]
        curr_price = curr.price
        curr_oi = curr.oi
        curr_time = curr.timestamp

        level_price = float(level.get("center_price", level.get("price", 0.0)))
        if level_price <= 0:
            return {"status": "INVALID_LEVEL", "scenario": None, "is_valid": False, "is_new_event": False}

        level_type = str(level.get("type", "resistance")).lower()
        level_id = str(level.get("zone_id") or f"{level_type}_{round(level_price, 4)}")

        state = self._level_states.get(level_id)
        if state is None:
            state = LevelTestState(level_id=level_id, level_price=level_price, level_type=level_type)
            self._level_states[level_id] = state

        if threshold_pct is None:
            threshold_pct = self.compute_oi_volatility()

        # Distance from level in percent
        dist_pct = ((curr_price - level_price) / level_price) * 100.0
        abs_dist_pct = abs(dist_pct)

        # Precise zone boundaries (without double expansion)
        upper_bound = float(level.get("upper_price", level_price * (1 + proximity_pct / 100.0)))
        lower_bound = float(level.get("lower_price", level_price * (1 - proximity_pct / 100.0)))
        in_test_zone = (lower_bound <= curr_price <= upper_bound)

        # Check breakout state
        is_breakout_up = (level_type == "resistance" and curr_price > upper_bound)
        is_breakout_down = (level_type == "support" and curr_price < lower_bound)
        is_breakout = is_breakout_up or is_breakout_down

        # Reset latch if price returned to test zone or back on original side of level
        if in_test_zone or (level_type == "resistance" and curr_price < lower_bound) or (level_type == "support" and curr_price > upper_bound):
            if state.has_fired_breakout:
                state.reset_breakout_latch()

        # Track entry into test zone
        if in_test_zone and not state.is_testing and not is_breakout:
            state.is_testing = True
            state.test_start_time = curr_time
            state.test_start_price = curr_price
            state.test_start_oi = curr_oi

        # Handle Impulse Breakout (breakout occurred without earlier test tracking)
        is_impulse_breakout = False
        if is_breakout and (state.test_start_time is None or state.test_start_oi is None):
            pre_snap = self._find_pre_breakout_snapshot(level_price, level_type, max_lookback_seconds=300)
            if pre_snap:
                state.test_start_time = pre_snap.timestamp
                state.test_start_price = pre_snap.price
                state.test_start_oi = pre_snap.oi
                is_impulse_breakout = True

        test_duration_seconds = max(0.0, curr_time - (state.test_start_time or curr_time))
        start_oi = state.test_start_oi if state.test_start_oi and state.test_start_oi > 0 else curr_oi
        oi_delta = curr_oi - start_oi
        oi_delta_pct = ((curr_oi - start_oi) / start_oi * 100.0) if start_oi > 0 else 0.0

        direction = "UP" if curr_price >= (state.test_start_price or curr_price) else "DOWN"

        scenario: Optional[str] = None
        status: str = "WATCHING"
        interpretation: str = ""
        badge_color: str = "gray"
        is_new_event: bool = False

        if is_breakout:
            state.is_testing = False

            if state.has_fired_breakout:
                # Already reported this breakout event; preserve status without duplicate alerting
                is_new_event = False
                scenario = state.last_scenario
                status = f"{state.last_status}"
                badge_color = state.last_analysis.get("badge_color", "gray") if state.last_analysis else "gray"
                interpretation = state.last_analysis.get("interpretation", "") if state.last_analysis else ""
            else:
                # Fresh breakout event
                state.has_fired_breakout = True
                state.last_breakout_time = curr_time
                is_new_event = True

                if oi_delta_pct > threshold_pct:
                    # Scenario A: Breakout with increasing OI
                    status = "BREAKOUT + OI INCREASE"
                    scenario = "SCENARIO_A"
                    badge_color = "green"
                    interpretation = (
                        f"Пробій рівня на фоні нарощування сукупної відкритої експозиції (+{oi_delta_pct:.2f}%)."
                    )
                elif oi_delta_pct < -threshold_pct:
                    # Scenario B: Breakout with decreasing OI
                    status = "BREAKOUT + OI DECREASE"
                    scenario = "SCENARIO_B"
                    badge_color = "red"
                    interpretation = (
                        f"Пробій рівня на фоні скорочення сукупної відкритої експозиції ({oi_delta_pct:.2f}%)."
                    )
                else:
                    # Scenario C: Breakout with neutral OI
                    status = "BREAKOUT + OI NEUTRAL"
                    scenario = "SCENARIO_C"
                    badge_color = "gray"
                    interpretation = (
                        f"Пробій рівня без істотної зміни відкритої експозиції ({oi_delta_pct:+.2f}%)."
                    )
        elif in_test_zone:
            # Inside test zone
            if oi_delta_pct > (threshold_pct * 1.5) and test_duration_seconds >= 30:
                # Scenario D: Price tests level but OI is rapidly increasing
                status = "LEVEL TEST + OI BUILDUP"
                scenario = "SCENARIO_D"
                badge_color = "amber"
                interpretation = (
                    f"Тестування рівня зі зростанням відкритої експозиції (+{oi_delta_pct:.2f}%) без розвитку цінового пробою."
                )
                if not state.has_fired_buildup:
                    state.has_fired_buildup = True
                    is_new_event = True
                else:
                    is_new_event = False
            else:
                status = "LEVEL TESTING"
                scenario = None
                badge_color = "blue"
                interpretation = f"Тестування зони рівня ({test_duration_seconds:.0f}s). Зміна OI: {oi_delta_pct:+.2f}%."
                is_new_event = False
        else:
            # Outside test zone
            state.is_testing = False
            state.has_fired_buildup = False
            status = "APPROACHING" if abs_dist_pct <= (proximity_pct * 2.0) else "FAR"
            badge_color = "gray"
            interpretation = f"Дистанція до рівня: {dist_pct:+.2f}%."
            is_new_event = False

        result = {
            "level_id": level_id,
            "level_price": round(level_price, 4),
            "level_type": level_type,
            "current_price": round(curr_price, 4),
            "test_start_price": round(state.test_start_price or curr_price, 4),
            "test_start_oi": round(start_oi, 4),
            "breakout_price": round(curr_price, 4) if is_breakout else None,
            "test_start_time": state.test_start_time,
            "current_time": curr_time,
            "duration_seconds": round(test_duration_seconds, 1),
            "direction": direction,
            "oi_delta": round(oi_delta, 4),
            "oi_delta_pct": round(oi_delta_pct, 4),
            "threshold_pct": threshold_pct,
            "status": status,
            "scenario": scenario,
            "badge_color": badge_color,
            "interpretation": interpretation,
            "is_breakout": is_breakout,
            "in_test_zone": in_test_zone,
            "is_new_event": is_new_event,
            "is_impulse": is_impulse_breakout,
            "is_valid": not self.is_stale and len(self._history) >= 2
        }

        state.last_status = status
        state.last_scenario = scenario
        state.last_analysis = result
        return result

    def get_summary(self, levels: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Generates full consolidated report for the coin including both token and USD notional values.
        """
        curr = self.latest
        all_deltas = self.compute_all_deltas()
        volatility_info = self.get_oi_volatility_info()
        volatility_thresh = float(volatility_info["threshold_pct"])
        is_stale = self.is_stale

        # Overall OI trend across 5m and 15m
        d5 = all_deltas.get("5m", {})
        d5_pct = d5.get("delta_pct", 0.0)
        if not d5.get("is_valid", False):
            oi_status = "COLLECTING" if len(self._history) < 10 else "STALE"
            oi_color = "gray"
        elif d5_pct > volatility_thresh:
            oi_status = "INCREASING"
            oi_color = "green"
        elif d5_pct < -volatility_thresh:
            oi_status = "DECREASING"
            oi_color = "red"
        else:
            oi_status = "NEUTRAL"
            oi_color = "gray"

        current_oi = curr.oi if curr else None
        current_price = curr.price if curr else None
        current_oi_usd = (current_oi * current_price) if (current_oi and current_price) else None

        # Analyze top nearby levels if provided
        level_analyses = []
        breakout_signals = []
        if levels and curr:
            for lvl in levels:
                analysis = self.analyze_level_interaction(lvl, threshold_pct=volatility_thresh)
                level_analyses.append(analysis)
                # Only include fresh/distinct breakout events in signal broadcasts
                if analysis.get("scenario") in ["SCENARIO_A", "SCENARIO_B", "SCENARIO_C", "SCENARIO_D"]:
                    breakout_signals.append(analysis)

        return {
            "coin": self.coin,
            "current_oi": current_oi,
            "current_oi_usd": round(current_oi_usd, 2) if current_oi_usd else None,
            "current_price": current_price,
            "timestamp": curr.timestamp if curr else None,
            "is_stale": is_stale,
            "samples_count": len(self._history),
            "deltas": all_deltas,
            "volatility_threshold_pct": volatility_thresh,
            "volatility_info": volatility_info,
            "oi_status": oi_status,
            "oi_color": oi_color,
            "level_analyses": level_analyses,
            "breakout_signals": breakout_signals
        }


class OITrackerManager:
    """Singleton manager maintaining OITracker instances per coin."""

    def __init__(self):
        self._trackers: Dict[str, OITracker] = {}

    def get_tracker(self, coin: str) -> OITracker:
        coin_key = coin.upper()
        if coin_key not in self._trackers:
            self._trackers[coin_key] = OITracker(coin=coin_key)
        return self._trackers[coin_key]

    def record_tick(self, coin: str, oi: float, price: float, timestamp: Optional[float] = None) -> bool:
        tracker = self.get_tracker(coin)
        return tracker.record_snapshot(oi=oi, price=price, timestamp=timestamp)

    def get_coin_oi_summary(self, coin: str, levels: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        tracker = self.get_tracker(coin)
        return tracker.get_summary(levels=levels)

    def clear(self):
        self._trackers.clear()


oi_manager = OITrackerManager()
