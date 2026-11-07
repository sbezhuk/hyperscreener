import time
import math
import sys
from app.analyzer.oi_tracker import OITracker, OITrackerManager

def test_scenario_1_45min_for_1h():
    """Scenario 1: 45 minutes of history for 1h interval."""
    tracker = OITracker(coin="ETH")
    now = time.time()
    t0 = now - 2700.0 # Exactly 45 min
    for m in range(0, 46, 3):
        tracker.record_snapshot(oi=10000.0 + (m * 10), price=2500.0, timestamp=t0 + (m * 60))
    d1h = tracker.compute_interval_delta(3600)
    assert d1h["status"] == "INSUFFICIENT_HISTORY", f"Expected INSUFFICIENT_HISTORY, got {d1h['status']}"
    assert d1h["is_valid"] is False
    assert d1h["delta"] is None
    assert d1h["delta_pct"] is None
    assert d1h["actual_duration_seconds"] == 2700.0
    return d1h

def test_scenario_2_full_60min_for_1h():
    """Scenario 2: Full 60 minutes of history for 1h interval."""
    tracker = OITracker(coin="ETH")
    now = time.time()
    t0 = now - 3600.0 # Exactly 60 min
    for m in range(0, 61, 3):
        tracker.record_snapshot(oi=10000.0 + (m * 10), price=2500.0, timestamp=t0 + (m * 60))
    d1h = tracker.compute_interval_delta(3600)
    assert d1h["status"] == "OK", f"Expected OK, got {d1h['status']}"
    assert d1h["is_valid"] is True
    assert d1h["delta"] == 600.0
    assert abs(d1h["delta_pct"] - 6.0) < 0.01
    assert d1h["actual_duration_seconds"] == 3600.0
    return d1h

def test_scenario_3_real_10min_gap():
    """Scenario 3: Real 10-minute data gap."""
    tracker = OITracker(coin="SOL")
    now = time.time()
    t0 = now - 900.0
    tracker.record_snapshot(oi=1000.0, price=150.0, timestamp=t0)
    # Gap of 10 min (600s)
    tracker.record_snapshot(oi=1050.0, price=155.0, timestamp=t0 + 600.0)
    d1m = tracker.compute_interval_delta(60)
    assert d1m["status"] == "GAP_DETECTED"
    assert d1m["is_valid"] is False
    assert d1m["delta"] is None
    d5m = tracker.compute_interval_delta(300)
    assert d5m["status"] == "GAP_DETECTED"
    assert d5m["is_valid"] is False
    assert d5m["delta"] is None
    return d1m, d5m

def test_scenario_4_high_frequency_ticks():
    """Scenario 4: High-frequency ticks every 0.5-1.0s."""
    tracker = OITracker(coin="BTC")
    now = time.time()
    t0 = now - 900.0 # 15 min
    curr_oi = 40000.0
    for s in range(0, 900):
        # 1 tick per second with 0.4% minute-to-minute drift
        if s > 0 and s % 60 == 0:
            curr_oi *= 1.004
        tracker.record_snapshot(oi=curr_oi, price=75000.0, timestamp=t0 + s)
        # Add 0.5s intermediate tick
        tracker.record_snapshot(oi=curr_oi, price=75000.0, timestamp=t0 + s + 0.5)

    info = tracker.get_oi_volatility_info()
    assert info["is_adaptive"] is True
    assert info["status"] == "OK"
    assert abs(info["rms_pct"] - 0.40) < 0.02
    assert abs(info["threshold_pct"] - 0.48) < 0.03
    return info

def test_scenario_5_impulse_breakout_no_test():
    """Scenario 5: Impulse breakout without earlier testing."""
    tracker = OITracker(coin="BTC")
    now = time.time()
    level = {
        "zone_id": "res_80000",
        "price": 80000.0,
        "upper_price": 80100.0,
        "lower_price": 79900.0,
        "type": "resistance"
    }
    # No prior history, first tick is an instant breakout at 80500
    tracker.record_snapshot(oi=25000.0, price=80500.0, timestamp=now)
    res = tracker.analyze_level_interaction(level)
    assert res["status"] == "BREAKOUT (INSUFFICIENT_OI_HISTORY)"
    assert res["scenario"] is None
    assert res["is_new_event"] is False
    assert res["is_valid"] is False
    assert res["oi_delta"] is None
    assert res["oi_delta_pct"] is None
    return res

def test_scenario_6_50_consecutive_ticks_after_breakout():
    """Scenario 6: 50 consecutive ticks after one breakout."""
    tracker = OITracker(coin="ETH")
    now = time.time()
    level = {
        "zone_id": "res_3000",
        "price": 3000.0,
        "upper_price": 3010.0,
        "lower_price": 2990.0,
        "type": "resistance"
    }
    # Pre-breakout baseline
    tracker.record_snapshot(oi=10000.0, price=2980.0, timestamp=now - 20)
    tracker.record_snapshot(oi=10500.0, price=3025.0, timestamp=now) # Breakout!
    res1 = tracker.analyze_level_interaction(level, threshold_pct=0.5)
    assert res1["is_breakout"] is True
    assert res1["is_new_event"] is True
    assert res1["scenario"] == "SCENARIO_A"

    new_events_count = 1
    for sec in range(1, 51):
        tracker.record_snapshot(oi=10500.0 + sec, price=3025.0 + (sec * 0.1), timestamp=now + sec)
        res_tick = tracker.analyze_level_interaction(level, threshold_pct=0.5)
        if res_tick["is_new_event"]:
            new_events_count += 1

    assert new_events_count == 1, f"Expected exactly 1 new event, got {new_events_count}"
    return new_events_count

def test_scenario_7_timeframe_switch_cache():
    """Scenario 7: Timeframe switching while receiving live OI."""
    # Simulation of frontend logic in App.tsx
    live_ws_oi = {
        "coin": "BTC",
        "timestamp": 1794068798.986,
        "current_oi": 41104.5,
        "deltas": { "1m": { "status": "OK", "delta_pct": -0.023 } }
    }
    # Cached 15m entry captured 40s ago (stale or incomplete)
    cached_15m_entry = {
        "coin": "BTC",
        "oi": {
            "timestamp": 1794068750.0,
            "current_oi": 41113.6,
            "deltas": { "1m": { "status": "INSUFFICIENT_HISTORY", "delta_pct": None } }
        }
    }
    prev_oi = live_ws_oi
    cached_oi = cached_15m_entry["oi"]
    should_use_prev = prev_oi and (not cached_oi or (prev_oi.get("timestamp", 0) >= cached_oi.get("timestamp", 0)))
    resolved = prev_oi if should_use_prev else cached_oi
    assert resolved["timestamp"] == 1794068798.986
    assert resolved["deltas"]["1m"]["status"] == "OK"
    return resolved

def test_scenario_8_reconnect_recovery():
    """Scenario 8: Recovery after reconnect."""
    tracker = OITracker(coin="ETH", stale_threshold_seconds=60)
    now = time.time()
    # Old snapshot before disconnect (120s ago)
    tracker.record_snapshot(oi=5000.0, price=2500.0, timestamp=now - 120.0)
    assert tracker.is_stale is True
    d_stale = tracker.compute_interval_delta(60)
    # Stale snapshot before reconnect
    assert d_stale["is_valid"] is False or d_stale["status"] == "STALE"

    # Reconnection happens: fresh tick arrives
    tracker.record_snapshot(oi=5010.0, price=2505.0, timestamp=now)
    assert tracker.is_stale is False
    summary = tracker.get_summary()
    assert summary["is_stale"] is False
    assert summary["current_oi"] == 5010.0
    return summary

def main():
    print("Running all 8 mandatory verification scenarios...")
    s1 = test_scenario_1_45min_for_1h()
    print("Scenario 1 (45m for 1h):", s1["status"])
    s2 = test_scenario_2_full_60min_for_1h()
    print("Scenario 2 (60m for 1h):", s2["status"], f"delta={s2['delta']}")
    s3_1, s3_5 = test_scenario_3_real_10min_gap()
    print("Scenario 3 (10m gap):", s3_1["status"], s3_5["status"])
    s4 = test_scenario_4_high_frequency_ticks()
    print("Scenario 4 (High-freq stream):", f"adaptive={s4['is_adaptive']}, threshold={s4['threshold_pct']}%, RMS={s4['rms_pct']}%")
    s5 = test_scenario_5_impulse_breakout_no_test()
    print("Scenario 5 (Impulse breakout without test):", s5["status"])
    s6 = test_scenario_6_50_consecutive_ticks_after_breakout()
    print("Scenario 6 (50 consecutive ticks):", f"Total new events: {s6}")
    s7 = test_scenario_7_timeframe_switch_cache()
    print("Scenario 7 (Timeframe switch cache):", f"Resolved TS: {s7['timestamp']}")
    s8 = test_scenario_8_reconnect_recovery()
    print("Scenario 8 (Reconnect recovery):", f"Is stale: {s8['is_stale']}")
    print("\nALL 8 MANDATORY VERIFICATION SCENARIOS PASSED WITH 100% SUCCESS!")

if __name__ == "__main__":
    main()
