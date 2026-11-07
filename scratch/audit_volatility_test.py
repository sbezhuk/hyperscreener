import time
import math
from app.analyzer.oi_tracker import OITracker

def run_tests():
    print("=== TEST 1: STABLE OI ===")
    tracker = OITracker(coin="BTC")
    t0 = time.time() - 900
    for i in range(16):
        tracker.record_snapshot(oi=10000.0, price=75000.0, timestamp=t0 + (i * 60))
    info = tracker.get_oi_volatility_info()
    print("Stable OI Info:", info)
    assert info["is_adaptive"] == True
    assert info["threshold_pct"] == 0.10, f"Expected 0.10% (min bound), got {info['threshold_pct']}"

    print("\n=== TEST 2: UNIFORM GROWTH (+0.30% per min) ===")
    tracker = OITracker(coin="ETH")
    curr_oi = 50000.0
    for i in range(16):
        tracker.record_snapshot(oi=curr_oi, price=2500.0, timestamp=t0 + (i * 60))
        curr_oi *= 1.003
    info = tracker.get_oi_volatility_info()
    print("Uniform Growth Info:", info)
    assert info["is_adaptive"] == True
    # RMS should be ~0.30%, threshold 1.2 * RMS = ~0.36%
    assert abs(info["rms_pct"] - 0.30) < 0.02
    assert abs(info["threshold_pct"] - 0.36) < 0.03

    print("\n=== TEST 3: UNIFORM DECREASE (-0.40% per min) ===")
    tracker = OITracker(coin="SOL")
    curr_oi = 50000.0
    for i in range(16):
        tracker.record_snapshot(oi=curr_oi, price=180.0, timestamp=t0 + (i * 60))
        curr_oi *= 0.996
    info = tracker.get_oi_volatility_info()
    print("Uniform Decrease Info:", info)
    assert info["is_adaptive"] == True
    assert abs(info["rms_pct"] - 0.40) < 0.02
    assert abs(info["threshold_pct"] - 0.48) < 0.03

    print("\n=== TEST 4: SHARP OI SPIKES (Outlier filtering / winsorization) ===")
    tracker = OITracker(coin="DOGE")
    curr_oi = 100000.0
    # 25 snapshots: mostly 0.2% drift, with one huge 15% spike
    for i in range(25):
        if i == 12:
            curr_oi *= 1.15 # 15% spike
        else:
            curr_oi *= 1.002 # 0.2%
        tracker.record_snapshot(oi=curr_oi, price=0.15, timestamp=t0 + (i * 60))
    info = tracker.get_oi_volatility_info()
    print("Sharp Spikes Info:", info)
    assert info["is_adaptive"] == True
    assert info["threshold_pct"] < 2.50
    # Spike was winsorized, so threshold is not blown up to 18%
    print(f"Winsorized RMS: {info['rms_pct']}%, threshold: {info['threshold_pct']}%")

    print("\n=== TEST 5: HIGH-FREQUENCY WS STREAM (0.5s ticks for 12 minutes) ===")
    tracker = OITracker(coin="HYPE")
    t_start = time.time() - 720
    curr_oi = 10000.0
    for s in range(0, 720):
        # 2 ticks per second = every 0.5s
        if s % 60 == 0 and s > 0:
            curr_oi *= 1.005 # 0.5% per minute
        tracker.record_snapshot(oi=curr_oi, price=10.0, timestamp=t_start + s)
        tracker.record_snapshot(oi=curr_oi, price=10.0, timestamp=t_start + s + 0.5)
    info = tracker.get_oi_volatility_info()
    print("High-frequency stream Info:", info)
    assert info["is_adaptive"] == True
    assert info["status"] == "OK"
    assert info["threshold_pct"] > 0.25 # Not stuck at fallback 0.25!

    print("\n=== TEST 6: INSUFFICIENT HISTORY (< 5 min) ===")
    tracker = OITracker(coin="BTC")
    t_short = time.time() - 180 # 3 min
    for s in range(4):
        tracker.record_snapshot(oi=10000.0, price=70000.0, timestamp=t_short + (s * 60))
    info = tracker.get_oi_volatility_info()
    print("Short History Info:", info)
    assert info["is_adaptive"] == False
    assert info["status"] == "INSUFFICIENT_HISTORY"
    assert info["threshold_pct"] == 0.25

    print("\nALL 6 VOLATILITY AUDIT TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
