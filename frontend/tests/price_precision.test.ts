import { test, describe } from 'node:test';
import assert from 'node:assert';
import { getAssetPricePrecision, formatPrice } from '../src/types';

describe('Price Precision & Dynamic Formatting Tests', () => {
  test('1. getAssetPricePrecision correctly resolves precision for $1.34 price tier (as seen in user report)', () => {
    // 4-decimal candles around $1.34 (e.g. SUI / XRP / NEAR tier)
    const candles4d = [
      { open: 1.3412, high: 1.3520, low: 1.3390, close: 1.3425 },
      { open: 1.3425, high: 1.3480, low: 1.3400, close: 1.3418 },
    ];
    const res4d = getAssetPricePrecision(candles4d);
    assert.strictEqual(res4d.precision, 4, 'Should have precision: 4 for $1.34 asset');
    assert.strictEqual(res4d.minMove, 0.0001, 'Should have minMove: 0.0001 for $1.34 asset');

    // If candle data provides 5 decimals for tighter spreads (e.g. 1.34125)
    const candles5d = [
      { open: 1.34125, high: 1.35200, low: 1.33900, close: 1.34255 },
    ];
    const res5d = getAssetPricePrecision(candles5d);
    assert.strictEqual(res5d.precision, 5, 'Should adapt to 5 decimals from data');
    assert.strictEqual(res5d.minMove, 0.00001, 'Should have minMove: 0.00001');

    // Fallback when only currentPrice is passed (e.g. before candles load)
    const resFallback = getAssetPricePrecision(null, 1.34);
    assert.strictEqual(resFallback.precision, 4);
    assert.strictEqual(resFallback.minMove, 0.0001);
  });

  test('2. getAssetPricePrecision covers all asset price tiers accurately', () => {
    // BTC Tier (>= 10,000)
    const btc = getAssetPricePrecision([{ open: 75940.0, high: 75950.0, low: 75930.0, close: 75943.0 }]);
    assert.strictEqual(btc.precision, 1);
    assert.strictEqual(btc.minMove, 0.1);

    // ETH Tier (1,000 - 10,000)
    const eth = getAssetPricePrecision([{ open: 2235.0, high: 2240.0, low: 2230.0, close: 2236.9 }]);
    assert.strictEqual(eth.precision, 2);
    assert.strictEqual(eth.minMove, 0.01);

    // SOL Tier (10 - 100 with 3 decimals like 89.293)
    const sol = getAssetPricePrecision([{ open: 89.100, high: 89.500, low: 88.900, close: 89.293 }]);
    assert.strictEqual(sol.precision, 3);
    assert.strictEqual(sol.minMove, 0.001);

    // Sub-dollar Tier (0.1 - 1 like ENA 0.15333)
    const ena = getAssetPricePrecision([{ open: 0.15300, high: 0.15400, low: 0.15200, close: 0.15333 }]);
    assert.strictEqual(ena.precision, 5);
    assert.strictEqual(ena.minMove, 0.00001);

    // Micro-cap Tier (PUMP 0.003653)
    const pump = getAssetPricePrecision([{ open: 0.003600, high: 0.003700, low: 0.003500, close: 0.003653 }]);
    assert.ok(pump.precision >= 6, 'PUMP should have precision >= 6');
    assert.ok(pump.minMove <= 0.000001, 'PUMP minMove should be <= 1e-6');
  });

  test('3. formatPrice formats prices with appropriate precision and handles edge cases', () => {
    // $1.34 tier assets
    assert.strictEqual(formatPrice(1.34), '1.3400');
    assert.strictEqual(formatPrice(1.3412), '1.3412');
    assert.strictEqual(formatPrice(1.3425), '1.3425');

    // BTC, ETH, SOL, micro-caps
    assert.strictEqual(formatPrice(75943.0), '75943.0');
    assert.strictEqual(formatPrice(2236.9), '2236.90');
    assert.strictEqual(formatPrice(89.293), '89.293');
    assert.strictEqual(formatPrice(0.15333), '0.15333');
    assert.strictEqual(formatPrice(0.003653), '0.003653');

    // Null / NaN / 0 handling
    assert.strictEqual(formatPrice(null), '---');
    assert.strictEqual(formatPrice(undefined), '---');
    assert.strictEqual(formatPrice(0), '---');
    assert.strictEqual(formatPrice(-5), '---');
  });
});
