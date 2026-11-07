import time
from app.analyzer.oi_tracker import OITracker, OITrackerManager

def run_tests():
    print("=== TEST 1: IMPULSE BREAKOUT WITHOUT PRIOR HISTORY ===")
    tracker = OITracker(coin="BTC")
    now = time.time()
    res_level = {
        "zone_id": "res_80000",
        "price": 80000.0,
        "upper_price": 80100.0,
        "lower_price": 79900.0,
        "type": "resistance"
    }
    # First snapshot is already above 80100 (breakout)
    tracker.record_snapshot(oi=10000.0, price=80500.0, timestamp=now)
    res = tracker.analyze_level_interaction(res_level)
    print("Impulse with no baseline:", res)
    assert res["status"] == "BREAKOUT (INSUFFICIENT_OI_HISTORY)"
    assert res["scenario"] is None
    assert res["is_new_event"] == False
    assert res["is_valid"] == False
    assert res["oi_delta"] is None
    assert res["oi_delta_pct"] is None

    print("\n=== TEST 2: IMPULSE BREAKOUT WITH VALID BASELINE ===")
    # Add snapshot prior to breakout
    tracker2 = OITracker(coin="ETH")
    tracker2.record_snapshot(oi=5000.0, price=2900.0, timestamp=now - 50)
    tracker2.record_snapshot(oi=5200.0, price=3050.0, timestamp=now) # Breakout through 3000
    res_eth = tracker2.analyze_level_interaction({
        "zone_id": "res_3000",
        "price": 3000.0,
        "upper_price": 3010.0,
        "lower_price": 2990.0,
        "type": "resistance"
    }, threshold_pct=0.5)
    print("Impulse with baseline:", res_eth)
    assert res_eth["status"] == "BREAKOUT + OI INCREASE"
    assert res_eth["scenario"] == "SCENARIO_A"
    assert res_eth["test_start_oi"] == 5000.0
    assert abs(res_eth["oi_delta_pct"] - 4.0) < 0.01

    print("\n=== TEST 3: EXACTLY ONE EVENT FIRED & LATCHED ===")
    assert res_eth["is_new_event"] == True
    # Tick 2, 3, 4:
    for i in range(1, 10):
        tracker2.record_snapshot(oi=5200.0 + i, price=3055.0, timestamp=now + i)
        sub_res = tracker2.analyze_level_interaction({
            "zone_id": "res_3000",
            "price": 3000.0,
            "upper_price": 3010.0,
            "lower_price": 2990.0,
            "type": "resistance"
        }, threshold_pct=0.5)
        assert sub_res["is_new_event"] == False

    print("\n=== TEST 4: RETRACEMENT AND RE-ARMING ===")
    # Price falls back inside test zone (3000)
    tracker2.record_snapshot(oi=5210.0, price=3000.0, timestamp=now + 20)
    res_retraced = tracker2.analyze_level_interaction({
        "zone_id": "res_3000",
        "price": 3000.0,
        "upper_price": 3010.0,
        "lower_price": 2990.0,
        "type": "resistance"
    }, threshold_pct=0.5)
    assert res_retraced["is_breakout"] == False

    # Second breakout occurs:
    tracker2.record_snapshot(oi=5500.0, price=3060.0, timestamp=now + 35)
    res_breakout2 = tracker2.analyze_level_interaction({
        "zone_id": "res_3000",
        "price": 3000.0,
        "upper_price": 3010.0,
        "lower_price": 2990.0,
        "type": "resistance"
    }, threshold_pct=0.5)
    print("Second breakout event:", res_breakout2)
    assert res_breakout2["is_breakout"] == True
    assert res_breakout2["is_new_event"] == True

    print("\n=== TEST 5: ISOLATION ACROSS LEVELS & COINS ===")
    mgr = OITrackerManager()
    mgr.record_tick("BTC", 40000.0, 75000.0, now)
    mgr.record_tick("ETH", 900000.0, 2200.0, now)
    btc_t = mgr.get_tracker("BTC")
    eth_t = mgr.get_tracker("ETH")
    assert btc_t.coin == "BTC"
    assert eth_t.coin == "ETH"
    assert len(btc_t._level_states) == 0
    assert len(eth_t._level_states) == 0

    print("\nALL BREAKOUT AUDIT TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
