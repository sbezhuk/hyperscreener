import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import {
  STORAGE_KEYS,
  getInitialCoin,
  saveSelectedCoin,
  getInitialTimeframe,
  saveSelectedTimeframe,
  getInitialFormation,
  saveActiveFormation,
  getInitialSelectedTfs,
  saveSelectedTfs,
  getInitialMinStrength,
  saveMinStrength,
  getInitialConfirmedOi,
  saveConfirmedOi,
  syncUrlState,
  loadCoinDrawings,
  saveCoinDrawings,
  saveDrawing,
  removeDrawing,
  clearCoinDrawings,
  ChartDrawing,
} from '../src/utils/storage';

describe('State Persistence & Asset/Formation Preservation Tests', () => {
  let dom: JSDOM;

  beforeEach(() => {
    dom = new JSDOM('<!doctype html><html><body></body></html>', {
      url: 'http://localhost:3000/',
    });
    global.window = dom.window as any;
    global.document = dom.window.document as any;
    global.localStorage = dom.window.localStorage as any;
    dom.window.localStorage.clear();
  });

  test('1. Default Fallbacks: Returns ETH, 1D, CASCADE when storage and URL are empty', () => {
    assert.equal(getInitialCoin('ETH'), 'ETH');
    assert.equal(getInitialTimeframe('1D'), '1D');
    assert.equal(getInitialFormation('CASCADE'), 'CASCADE');
    assert.deepEqual(getInitialSelectedTfs('1d'), ['1d']);
    assert.equal(getInitialMinStrength(50), 50);
    assert.equal(getInitialConfirmedOi(false), false);
  });

  test('2. Asset Persistence: Remembers selected coin across page reloads via localStorage', () => {
    // User switches to SOL
    saveSelectedCoin('SOL');
    assert.equal(global.localStorage.getItem(STORAGE_KEYS.SELECTED_COIN), 'SOL');

    // Simulate page reload (reading from storage)
    const restoredCoin = getInitialCoin();
    assert.equal(restoredCoin, 'SOL', 'Must restore SOL instead of reverting to ETH');

    // User switches to BTC
    saveSelectedCoin('btc');
    assert.equal(getInitialCoin(), 'BTC', 'Must sanitize to uppercase');
  });

  test('3. Formation Persistence: Remembers active formation across page reloads', () => {
    // User selects SWEEP formation
    saveActiveFormation('SWEEP');
    assert.equal(global.localStorage.getItem(STORAGE_KEYS.ACTIVE_FORMATION), 'SWEEP');

    // Simulate page reload
    assert.equal(getInitialFormation(), 'SWEEP', 'Must restore SWEEP formation');

    // User selects TRENDLINE
    saveActiveFormation('TRENDLINE');
    assert.equal(getInitialFormation(), 'TRENDLINE');

    // User selects FVG
    saveActiveFormation('FVG');
    assert.equal(getInitialFormation(), 'FVG');

    // User selects NONE
    saveActiveFormation('NONE');
    assert.equal(getInitialFormation(), 'NONE');
  });

  test('4. Formation Filters Persistence: Remembers selectedTfs, minStrength, and confirmed OI toggle', () => {
    saveSelectedTfs(['15m', '1h']);
    saveMinStrength(70);
    saveConfirmedOi(true);

    assert.deepEqual(getInitialSelectedTfs('1d'), ['15m', '1h']);
    assert.equal(getInitialMinStrength(), 70);
    assert.equal(getInitialConfirmedOi(), true);
  });

  test('5. Timeframe Persistence: Remembers timeframe across reloads', () => {
    saveSelectedTimeframe('15m');
    assert.equal(getInitialTimeframe(), '15m');

    saveSelectedTimeframe('4h');
    assert.equal(getInitialTimeframe(), '4h');
  });

  test('6. URL Priority: URL parameters take precedence over localStorage on direct navigation / sharing', () => {
    // LocalStorage has ETH and CASCADE
    saveSelectedCoin('ETH');
    saveActiveFormation('CASCADE');
    saveSelectedTimeframe('1D');

    // Simulate user navigating to a link with ?coin=SOL&interval=15m&formation=SWEEP
    dom.reconfigure({
      url: 'http://localhost:3000/?coin=SOL&interval=15m&formation=SWEEP',
    });

    assert.equal(getInitialCoin(), 'SOL', 'URL coin parameter must take precedence');
    assert.equal(getInitialTimeframe(), '15m', 'URL interval parameter must take precedence');
    assert.equal(getInitialFormation(), 'SWEEP', 'URL formation parameter must take precedence');
  });

  test('7. Safe Graceful Fallback: Invalid formation or timeframe in URL/Storage falls back safely', () => {
    dom.reconfigure({
      url: 'http://localhost:3000/?coin=DOGE&interval=invalid_tf&formation=INVALID_FORMATION',
    });

    assert.equal(getInitialCoin(), 'DOGE');
    assert.equal(getInitialTimeframe('1D'), '4h'); // normalizeTimeframe fallback
    assert.equal(getInitialFormation('CASCADE'), 'CASCADE');
  });

  test('8. syncUrlState: Updates browser URL query parameters without reloading', () => {
    syncUrlState({ coin: 'AVAX', timeframe: '1h', formation: 'TRENDLINE' });

    const currentUrl = new URL(global.window.location.href);
    assert.equal(currentUrl.searchParams.get('coin'), 'AVAX');
    assert.equal(currentUrl.searchParams.get('interval'), '1h');
    assert.equal(currentUrl.searchParams.get('formation'), 'TRENDLINE');
  });

  test('9. TradingView Drawing Tools Persistence Interface: Saves and partitions drawings per asset', () => {
    const btcTrendline: ChartDrawing = {
      id: 'draw-1',
      type: 'trendline',
      coin: 'BTC',
      timeframe: '15m',
      points: [
        { time: 1700000000, price: 65000 },
        { time: 1700003600, price: 66000 },
      ],
      color: '#0ecb81',
      lineWidth: 2,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    const ethHorizontalLine: ChartDrawing = {
      id: 'draw-2',
      type: 'horizontal_line',
      coin: 'ETH',
      points: [{ time: 1700000000, price: 3500 }],
      color: '#f6465d',
      lineWidth: 1,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    // Save drawings for BTC
    saveDrawing('BTC', btcTrendline);

    // Save drawings for ETH
    saveDrawing('ETH', ethHorizontalLine);

    // Drawings must be partitioned per coin
    const btcDrawings = loadCoinDrawings('BTC');
    assert.equal(btcDrawings.length, 1);
    assert.equal(btcDrawings[0].id, 'draw-1');
    assert.equal(btcDrawings[0].coin, 'BTC');

    const ethDrawings = loadCoinDrawings('ETH');
    assert.equal(ethDrawings.length, 1);
    assert.equal(ethDrawings[0].id, 'draw-2');
    assert.equal(ethDrawings[0].coin, 'ETH');

    // Removing a drawing
    removeDrawing('BTC', 'draw-1');
    assert.equal(loadCoinDrawings('BTC').length, 0);
    assert.equal(loadCoinDrawings('ETH').length, 1, 'ETH drawings must remain intact');

    // Clearing drawings
    clearCoinDrawings('ETH');
    assert.equal(loadCoinDrawings('ETH').length, 0);
  });
});
