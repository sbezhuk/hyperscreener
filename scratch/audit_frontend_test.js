const assert = require('assert');

// 1. formatOiDeltaPct logic
function formatOiDeltaPct(pct) {
  if (pct === null || pct === undefined || Number.isNaN(pct)) {
    return '...';
  }
  const formatted = pct.toFixed(3);
  if (formatted === '0.000' || formatted === '-0.000') {
    return '0.000%';
  }
  return pct > 0 ? `+${formatted}%` : `${formatted}%`;
}

console.log("=== FRONTEND TEST: formatOiDeltaPct ===");
assert.strictEqual(formatOiDeltaPct(null), '...');
assert.strictEqual(formatOiDeltaPct(undefined), '...');
assert.strictEqual(formatOiDeltaPct(0), '0.000%');
assert.strictEqual(formatOiDeltaPct(0.0001), '0.000%');
assert.strictEqual(formatOiDeltaPct(0.0226), '+0.023%');
assert.strictEqual(formatOiDeltaPct(-0.0226), '-0.023%');
assert.strictEqual(formatOiDeltaPct(1.2346), '+1.235%');
assert.strictEqual(formatOiDeltaPct(-5.6789), '-5.679%');
console.log("formatOiDeltaPct tests passed!");

// 2. Cache timestamp preservation logic
console.log("\n=== FRONTEND TEST: Cache Timestamp Reconciliation ===");
const cleanCoin = 'BTC';
const prev = {
  coin: 'BTC',
  oi: {
    timestamp: 1794068798.986,
    current_oi: 41104.5,
    deltas: { '1m': { status: 'OK', delta_pct: -0.023 } }
  }
};

const cachedEntry = {
  data: {
    coin: 'BTC',
    oi: {
      timestamp: 1794068730.0, // Older by 68s (e.g. captured during INSUFFICIENT_HISTORY)
      current_oi: 41113.6,
      deltas: { '1m': { status: 'INSUFFICIENT_HISTORY', delta_pct: null } }
    }
  }
};

const prevOi = prev?.coin?.toUpperCase() === cleanCoin ? prev.oi : undefined;
const cachedOi = cachedEntry.data.oi;
const shouldUsePrevOi = prevOi && (!cachedOi || (prevOi.timestamp ?? 0) >= (cachedOi.timestamp ?? 0));
const resolvedOi = shouldUsePrevOi ? prevOi : cachedOi;

assert.strictEqual(shouldUsePrevOi, true);
assert.strictEqual(resolvedOi.timestamp, 1794068798.986);
assert.strictEqual(resolvedOi.deltas['1m'].status, 'OK');
console.log("Cache timestamp reconciliation passed!");
