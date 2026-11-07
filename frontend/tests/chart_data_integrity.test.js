import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

describe('Chart Data Lifecycle & Race Condition Integrity Tests', () => {

  describe('1. Timestamp Sanitization & Ascending Sort', () => {
    function sanitizeCandles(rawCandles) {
      const uniqueMap = new Map();
      for (const c of rawCandles) {
        const rawTime = Number(c.time);
        if (!isNaN(rawTime) && rawTime > 0) {
          const timeSec = rawTime > 1e11 ? Math.floor(rawTime / 1000) : rawTime;
          uniqueMap.set(timeSec, { ...c, time: timeSec });
        }
      }
      return Array.from(uniqueMap.values()).sort((a, b) => Number(a.time) - Number(b.time));
    }

    test('correctly normalizes millisecond timestamps to seconds and dedupes', () => {
      const input = [
        { time: 1700000000000, open: 10, high: 12, low: 9, close: 11 }, // ms
        { time: 1700000000, open: 10, high: 12, low: 9, close: 11 },    // duplicate in sec
        { time: 1700000060, open: 11, high: 13, low: 10, close: 12 },   // sec
        { time: NaN, open: 0, high: 0, low: 0, close: 0 },              // invalid
      ];
      const result = sanitizeCandles(input);
      assert.equal(result.length, 2);
      assert.equal(result[0].time, 1700000000);
      assert.equal(result[1].time, 1700000060);
      assert.ok(result[0].time < result[1].time);
    });
  });

  describe('2. Chart Viewport Range Calculation', () => {
    function computeViewportRange(candleCount) {
      const fromIndex = Math.max(0, candleCount - 100);
      const toIndex = candleCount + 12;
      return { fromIndex, toIndex, totalVisibleBars: toIndex - fromIndex };
    }

    test('12 candles viewport (new listing like XTEN)', () => {
      const range = computeViewportRange(12);
      assert.equal(range.fromIndex, 0);
      assert.equal(range.toIndex, 24);
      assert.ok(range.toIndex >= 12, 'Includes right offset margin');
    });

    test('61 candles viewport (medium history like USELESS)', () => {
      const range = computeViewportRange(61);
      assert.equal(range.fromIndex, 0);
      assert.equal(range.toIndex, 73);
    });

    test('601 candles viewport (full history like BTC / ETH)', () => {
      const range = computeViewportRange(601);
      assert.equal(range.fromIndex, 501);
      assert.equal(range.toIndex, 613);
      assert.equal(range.toIndex - range.fromIndex, 112);
    });
  });

  describe('3. History Replacement vs Live Tick Logic (setData vs update)', () => {
    function evaluateChartAction({
      candles,
      coin,
      interval,
      prevContext,
      prevCandlesLen,
      prevFirstCandleTime,
      prevLastCandleTime,
      initialized,
    }) {
      const isContextChanged =
        prevContext.coin.toUpperCase() !== coin.toUpperCase() ||
        prevContext.interval.toLowerCase() !== interval.toLowerCase();

      const firstCandleTime = Number(candles[0]?.time || 0);
      const lastCandleTime = Number(candles[candles.length - 1]?.time || 0);

      const isPrependedEarlier =
        initialized &&
        !isContextChanged &&
        prevFirstCandleTime !== 0 &&
        firstCandleTime < prevFirstCandleTime;

      if (isPrependedEarlier) {
        return { action: 'PAGINATION_PREPEND', method: 'setData', resetRange: false };
      }

      if (isContextChanged || !initialized) {
        return { action: 'NEW_CONTEXT_LOAD', method: 'setData', resetRange: true };
      }

      // Same coin & timeframe
      const isLiveTickUpdate =
        firstCandleTime === prevFirstCandleTime &&
        (lastCandleTime === prevLastCandleTime ||
          (candles.length === prevCandlesLen + 1 && lastCandleTime > prevLastCandleTime));

      if (isLiveTickUpdate) {
        return { action: 'LIVE_TICK', method: 'update', resetRange: false };
      }

      return { action: 'FULL_REFRESH', method: 'setData', resetRange: false };
    }

    test('Coin change with identical candle count (ETH -> BTC, both 601 bars) MUST trigger setData & range reset', () => {
      const ethCandles = Array.from({ length: 601 }, (_, i) => ({ time: 1700000000 + i * 86400, close: 2500 }));
      const btcCandles = Array.from({ length: 601 }, (_, i) => ({ time: 1700000000 + i * 86400, close: 75000 }));

      // Previous state was ETH
      const prevContext = { coin: 'ETH', interval: '1d' };
      const prevCandlesLen = 601;
      const prevFirstCandleTime = 1700000000;
      const prevLastCandleTime = 1700000000 + 600 * 86400;

      // New coin is BTC
      const result = evaluateChartAction({
        candles: btcCandles,
        coin: 'BTC',
        interval: '1d',
        prevContext,
        prevCandlesLen,
        prevFirstCandleTime,
        prevLastCandleTime,
        initialized: true,
      });

      assert.equal(result.action, 'NEW_CONTEXT_LOAD');
      assert.equal(result.method, 'setData');
      assert.equal(result.resetRange, true, 'Must reset visible range on coin change');
    });

    test('Live tick on same coin MUST call update without range reset', () => {
      const candles = Array.from({ length: 601 }, (_, i) => ({ time: 1700000000 + i * 86400, close: 2500 }));
      const prevContext = { coin: 'ETH', interval: '1d' };

      const result = evaluateChartAction({
        candles,
        coin: 'ETH',
        interval: '1d',
        prevContext,
        prevCandlesLen: 601,
        prevFirstCandleTime: 1700000000,
        prevLastCandleTime: 1700000000 + 600 * 86400,
        initialized: true,
      });

      assert.equal(result.action, 'LIVE_TICK');
      assert.equal(result.method, 'update');
      assert.equal(result.resetRange, false);
    });

    test('Scrolling left to prepend older history MUST call setData without resetting viewport to end', () => {
      // Prepended 100 older bars
      const olderCandles = Array.from({ length: 701 }, (_, i) => ({ time: 1700000000 - 100 * 86400 + i * 86400, close: 2500 }));
      const prevContext = { coin: 'ETH', interval: '1d' };

      const result = evaluateChartAction({
        candles: olderCandles,
        coin: 'ETH',
        interval: '1d',
        prevContext,
        prevCandlesLen: 601,
        prevFirstCandleTime: 1700000000,
        prevLastCandleTime: 1700000000 + 600 * 86400,
        initialized: true,
      });

      assert.equal(result.action, 'PAGINATION_PREPEND');
      assert.equal(result.method, 'setData');
      assert.equal(result.resetRange, false);
    });
  });

  describe('4. Race Conditions: Rapid Coin Switching (BTC -> ETH -> SOL)', () => {
    test('Obsolete in-flight response cannot overwrite newly selected coin', () => {
      let currentSelectedCoin = 'SOL'; // User ended on SOL
      let currentSelectedTf = '1d';
      let analysisState = null;

      function onFastPathReturn(coin, interval, candles) {
        if (coin.toUpperCase() !== currentSelectedCoin.toUpperCase() || interval.toLowerCase() !== currentSelectedTf.toLowerCase()) {
          return; // Discarded!
        }
        analysisState = { coin, interval, candles };
      }

      function onFullAnalysisReturn(coin, interval, data) {
        if (coin.toUpperCase() !== currentSelectedCoin.toUpperCase() || interval.toLowerCase() !== currentSelectedTf.toLowerCase()) {
          return; // Discarded!
        }
        analysisState = data;
      }

      // BTC completes after user moved to SOL
      onFastPathReturn('BTC', '1d', [{ time: 100, close: 70000 }]);
      assert.equal(analysisState, null, 'BTC fast-path must be discarded');

      onFullAnalysisReturn('BTC', '1d', { coin: 'BTC', interval: '1d', candles: [{ time: 100, close: 70000 }] });
      assert.equal(analysisState, null, 'BTC full analysis must be discarded');

      // ETH completes after user moved to SOL
      onFastPathReturn('ETH', '1d', [{ time: 100, close: 2500 }]);
      assert.equal(analysisState, null, 'ETH fast-path must be discarded');

      // SOL completes -> Accepted!
      onFullAnalysisReturn('SOL', '1d', { coin: 'SOL', interval: '1d', candles: [{ time: 100, close: 90 }] });
      assert.notEqual(analysisState, null);
      assert.equal(analysisState.coin, 'SOL');
    });

    test('Fast-path must NOT overwrite full analysis if full analysis arrived first', () => {
      let state = null;

      // 1. Full analysis arrives first
      state = {
        isFastPath: false,
        coin: 'SOL',
        interval: '1d',
        candles: [{ time: 100, close: 90 }],
        levels: { resistances: [{ price: 95 }] },
      };

      // 2. Delayed fast-path arrives second
      function applyFastPath(prev, incomingCandles) {
        if (prev && prev.coin === 'SOL' && prev.interval === '1d' && !prev.isFastPath) {
          return prev; // Do NOT overwrite!
        }
        return { isFastPath: true, coin: 'SOL', interval: '1d', candles: incomingCandles };
      }

      const updated = applyFastPath(state, [{ time: 100, close: 90 }]);
      assert.equal(updated.isFastPath, false, 'Must keep full analysis');
      assert.ok(updated.levels, 'Levels from full analysis preserved');
    });

    test('Timeframe change in-flight discards old timeframe response', () => {
      let currentSelectedCoin = 'SOL';
      let currentTimeframe = '5m'; // User switched to 5m
      let state = null;

      function onResponse(coin, interval, data) {
        if (coin.toUpperCase() !== currentSelectedCoin.toUpperCase() || interval.toLowerCase() !== currentTimeframe.toLowerCase()) {
          return; // Discard!
        }
        state = data;
      }

      // Old 1d response arrives
      onResponse('SOL', '1d', { coin: 'SOL', interval: '1d', candles: [1, 2, 3] });
      assert.equal(state, null, '1d response must be discarded when active tf is 5m');

      // 5m response arrives
      onResponse('SOL', '5m', { coin: 'SOL', interval: '5m', candles: [4, 5, 6] });
      assert.notEqual(state, null);
      assert.equal(state.interval, '5m');
    });
  });

});
