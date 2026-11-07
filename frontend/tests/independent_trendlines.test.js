import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

describe('Independent Trendlines Per Timeframe Tests', () => {

  describe('1. Timeframe Isolation in Liquidity & Trendlines Filter', () => {
    function filterLiquidityForTimeframe(liquidity, activeTimeframe, trendlinesOverride) {
      if (!liquidity) return undefined;
      const baseTrendlines = trendlinesOverride || liquidity.trendlines || [];
      const currentTf = activeTimeframe.toLowerCase();
      const timeframeTrendlines = baseTrendlines.filter(
        (tl) => !tl.timeframe || tl.timeframe.toLowerCase() === currentTf
      );
      return {
        ...liquidity,
        trendlines: timeframeTrendlines,
      };
    }

    test('Strictly isolates trendlines: 15m chart only receives 15m trendlines', () => {
      const liquidity = {
        sweeps: [],
        pools: [],
        trendlines: [
          {
            timeframe: '15m',
            direction: 'DESCENDING',
            line_type: 'resistance_trendline',
            label: 'Наклонка (Опір)',
            start_point: { time: 100, price: 2500 },
            end_point: { time: 200, price: 2450 },
            p1: { time: 100, price: 2500 },
            p2: { time: 200, price: 2450 },
            status: 'ACTIVE'
          },
          {
            timeframe: '1h',
            direction: 'ASCENDING',
            line_type: 'support_trendline',
            label: 'Наклонка (Підтримка)',
            start_point: { time: 50, price: 2000 },
            end_point: { time: 300, price: 2100 },
            p1: { time: 50, price: 2000 },
            p2: { time: 300, price: 2100 },
            status: 'ACTIVE'
          },
          {
            timeframe: '4h',
            direction: 'ASCENDING',
            line_type: 'support_trendline',
            label: 'Наклонка (Підтримка)',
            start_point: { time: 10, price: 1500 },
            end_point: { time: 500, price: 1600 },
            p1: { time: 10, price: 1500 },
            p2: { time: 500, price: 1600 },
            status: 'ACTIVE'
          }
        ]
      };

      const result15m = filterLiquidityForTimeframe(liquidity, '15m');
      assert.equal(result15m.trendlines.length, 1);
      assert.equal(result15m.trendlines[0].timeframe, '15m');
      assert.equal(result15m.trendlines[0].start_point.price, 2500);

      // 1h trendlines must NOT appear on 15m
      const has1h = result15m.trendlines.some(tl => tl.timeframe === '1h');
      assert.equal(has1h, false);

      // 4h trendlines must NOT appear on 15m
      const has4h = result15m.trendlines.some(tl => tl.timeframe === '4h');
      assert.equal(has4h, false);
    });

    test('Switching timeframe updates the trendline set to the new timeframe', () => {
      const allTrendlines = {
        '15m': [{ timeframe: '15m', direction: 'DESCENDING', start_point: { price: 2500 }, end_point: { price: 2450 } }],
        '1h': [{ timeframe: '1h', direction: 'ASCENDING', start_point: { price: 2100 }, end_point: { price: 2200 } }],
        '4h': [{ timeframe: '4h', direction: 'ASCENDING', start_point: { price: 1500 }, end_point: { price: 1600 } }],
      };

      const tf1 = '15m';
      const filtered1 = filterLiquidityForTimeframe({ sweeps: [], pools: [] }, tf1, allTrendlines[tf1]);
      assert.equal(filtered1.trendlines[0].timeframe, '15m');
      assert.equal(filtered1.trendlines[0].direction, 'DESCENDING');

      // User switches to 1h
      const tf2 = '1h';
      const filtered2 = filterLiquidityForTimeframe({ sweeps: [], pools: [] }, tf2, allTrendlines[tf2]);
      assert.equal(filtered2.trendlines[0].timeframe, '1h');
      assert.equal(filtered2.trendlines[0].direction, 'ASCENDING');
      assert.equal(filtered2.trendlines[0].start_point.price, 2100);
    });
  });

  describe('2. Canvas Primitive Rendering Guard Tests', () => {
    function shouldDrawTrendline(tl, currentTf) {
      if (currentTf && tl.timeframe && tl.timeframe.toLowerCase() !== currentTf.toLowerCase()) {
        return false;
      }
      const pt1 = tl.start_point || tl.p1;
      const pt2 = tl.end_point || tl.p2;
      if (!pt1 || !pt2) return false;
      return true;
    }

    test('Canvas primitive rejects trendlines from mismatched timeframes', () => {
      const tl1h = { timeframe: '1h', p1: { time: 10, price: 100 }, p2: { time: 20, price: 90 } };
      const tl15m = { timeframe: '15m', p1: { time: 10, price: 100 }, p2: { time: 20, price: 90 } };

      assert.equal(shouldDrawTrendline(tl1h, '15m'), false, '1h trendline must be rejected on 15m chart');
      assert.equal(shouldDrawTrendline(tl15m, '15m'), true, '15m trendline must be accepted on 15m chart');
      assert.equal(shouldDrawTrendline(tl1h, '1h'), true, '1h trendline must be accepted on 1h chart');
    });

    test('Correctly falls back between start_point/end_point and p1/p2', () => {
      const modernTl = {
        timeframe: '5m',
        start_point: { time: 100, price: 200 },
        end_point: { time: 200, price: 190 },
      };
      const legacyTl = {
        timeframe: '5m',
        p1: { time: 100, price: 200 },
        p2: { time: 200, price: 190 },
      };
      assert.equal(shouldDrawTrendline(modernTl, '5m'), true);
      assert.equal(shouldDrawTrendline(legacyTl, '5m'), true);
    });
  });

  describe('3. Multi-Timeframe Trendline Cache Independence', () => {
    test('Cache keys (coin:timeframe) maintain separate entries without cross-pollution', () => {
      const cache = new Map();

      cache.set('ETH:15m', {
        trendlines: [{ timeframe: '15m', direction: 'DESCENDING', price: 2450 }],
        timestamp: 1000
      });
      cache.set('ETH:1h', {
        trendlines: [{ timeframe: '1h', direction: 'ASCENDING', price: 2200 }],
        timestamp: 1000
      });

      const cached15m = cache.get('ETH:15m');
      const cached1h = cache.get('ETH:1h');

      assert.notDeepEqual(cached15m.trendlines, cached1h.trendlines);
      assert.equal(cached15m.trendlines[0].timeframe, '15m');
      assert.equal(cached1h.trendlines[0].timeframe, '1h');
    });
  });

});
