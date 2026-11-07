import time
from app.analyzer.oi_tracker import OITracker

def run_tests():
    print("=== TEST 1: STRICT 45 MIN HISTORY FOR 1H ===")
    tracker = OITracker(coin="ETH")
    now = time.time()
    t0 = now - 2700 # 45 minutes
    for m in range(0, 46, 3):
        tracker.record_snapshot(oi=10000.0 + m, price=2500.0, timestamp=t0 + (m * 60))
    d1h = tracker.compute_interval_delta(3600)
    print("1h result for 45 min history:", d1h)
    assert d1h["status"] == "INSUFFICIENT_HISTORY"
    assert d1h["is_valid"] == False
    assert d1h["delta"] is None
    assert d1h["delta_pct"] is None
    assert d1h["actual_duration_seconds"] == 2700.0

    print("\n=== TEST 2: FULL 60 MIN HISTORY FOR 1H ===")
    for m in range(48, 61, 3):
        tracker.record_snapshot(oi=10000.0 + m, price=2500.0, timestamp=t0 + (m * 60))
    d1h_full = tracker.compute_interval_delta(3600)
    print("1h result for 60 min history:", d1h_full)
    assert d1h_full["status"] == "OK"
    assert d1h_full["is_valid"] == True
    assert d1h_full["delta"] is not None

    print("\n=== TEST 3: GAP_DETECTED vs INSUFFICIENT_HISTORY ===")
    # History spans 70 minutes, but between 10m and 35m there is a 25-minute gap
    tracker2 = OITracker(coin="SOL")
    t_start = now - 4200 # 70 min ago
    # Block 1: 0 to 10 min
    for m in range(0, 11):
        tracker2.record_snapshot(oi=1000.0, price=150.0, timestamp=t_start + (m * 60))
    # Gap: 10m to 35m (no snapshots!)
    # Block 2: 35m to 70m
    for m in range(35, 71):
        tracker2.record_snapshot(oi=1050.0, price=152.0, timestamp=t_start + (m * 60))

    # Interval 1h requested at t_start + 4200 (70m):
    # Target start is 70m - 60m = 10m.
    # At 10m, there is a snapshot (at t_start + 600). So 1h is OK!
    d1h_gap = tracker2.compute_interval_delta(3600)
    print("1h on gap history:", d1h_gap)
    assert d1h_gap["status"] == "OK" # snapshot at target_start exists

    # BUT Interval 45m (2700s) requested at 70m:
    # Target start is 70m - 45m = 25m! (Inside the 10m-35m gap)
    # Closest snapshot is at 10m (15m deviation) or 35m (10m deviation).
    # Both deviate > 300s? Tolerance for 2700 is max(15, 2700*0.05) = 135s.
    # Deviation is 10 min = 600s > 135s tolerance -> must be GAP_DETECTED!
    d45m = tracker2.compute_interval_delta(2700)
    print("45m during gap traversal:", d45m)
    assert d45m["status"] == "GAP_DETECTED"
    assert d45m["is_valid"] == False
    assert d45m["delta"] is None

    print("\n=== TEST 4: LOOK-AHEAD BIAS CHECK ===")
    # Verify closest snapshot never picks a snapshot >= curr.timestamp
    tracker3 = OITracker(coin="BTC")
    tracker3.record_snapshot(oi=1000.0, price=70000.0, timestamp=now)
    # If someone asks for 1m delta when history has only 1 snapshot at `now`:
    d_short = tracker3.compute_interval_delta(60)
    print("Single snapshot delta:", d_short)
    assert d_short["status"] == "INSUFFICIENT_HISTORY"
    assert d_short["is_valid"] == False

    print("\n=== TEST 5: SYMMETRIC LOOKUP FALSE POSITIVE CHECK ===")
    # Target start = now - 60.
    # If snapshot is at now - 59s (+1s after target), deviation is 1s <= 15s tolerance.
    # Should be OK.
    tracker4 = OITracker(coin="BTC")
    tracker4.record_snapshot(oi=1000.0, price=70000.0, timestamp=now - 59.0)
    tracker4.record_snapshot(oi=1010.0, price=70000.0, timestamp=now)
    d_symm = tracker4.compute_interval_delta(60)
    print("Symmetric delta (+1s):", d_symm)
    assert d_symm["status"] == "OK"
    assert d_symm["is_valid"] == True
    assert d_symm["actual_duration_seconds"] == 59.0

    print("\nALL INTERVAL TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
