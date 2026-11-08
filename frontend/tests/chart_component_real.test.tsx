import { test, describe, before, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { JSDOM } from 'jsdom';
import { chartSpies, resetSpies } from './mock_lightweight_charts';
import { ThemeProvider } from '../src/context/ThemeContext';
import { Chart } from '../src/components/Chart';
import { SidebarLevels } from '../src/components/SidebarLevels';

// 1. Set up simulated DOM environment for React Testing Library
const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost:3000',
  pretendToBeVisual: true,
});

global.window = dom.window as any;
global.document = dom.window.document as any;
global.HTMLElement = dom.window.HTMLElement as any;
global.HTMLDivElement = dom.window.HTMLDivElement as any;
global.requestAnimationFrame = (cb: FrameRequestCallback) => setTimeout(cb, 0) as any;
global.cancelAnimationFrame = (id: number) => clearTimeout(id);

// Define matchMedia for ThemeProvider
(dom.window as any).matchMedia = (query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
});

global.localStorage = dom.window.localStorage;

describe('Chart.tsx Real Component Lifecycle & Rendering Tests', () => {
  let rtlRender: any;

  before(async () => {
    const rtl = await import('@testing-library/react');
    rtlRender = rtl.render;
  });

  beforeEach(() => {
    resetSpies();
  });

  const generateCandles = (count: number, startPrice = 100, startTime = 1700000000) => {
    return Array.from({ length: count }, (_, i) => ({
      time: startTime + i * 86400,
      open: startPrice + i * 0.5,
      high: startPrice + i * 0.5 + 2,
      low: startPrice + i * 0.5 - 2,
      close: startPrice + i * 0.5 + 1,
      volume: 1000,
    }));
  };

  const renderChart = (props: any) => {
    return rtlRender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(Chart, {
          resistances: [],
          supports: [],
          fvgs: [],
          signals: [],
          activeFormation: 'CASCADE',
          ...props,
        })
      )
    );
  };

  test('1. Initial Mount: creates chart, sets data and positions visible range', async () => {
    const candles601 = generateCandles(601, 2000); // ETH
    const { unmount } = renderChart({
      coin: 'ETH',
      interval: '1d',
      candles: candles601,
    });

    assert.equal(chartSpies.createChartCalls.length, 1, 'createChart must be called once on mount');
    assert.equal(chartSpies.setDataCalls.length, 1, 'setData must be called once with initial candles');
    assert.equal(chartSpies.setDataCalls[0].length, 601);
    assert.equal(chartSpies.updateCalls.length, 0, 'update must NOT be called on initial mount');

    // Check visible logical range position: 601 candles -> totalBars = 601, from = 501, to = 613
    assert.ok(chartSpies.setVisibleLogicalRangeCalls.length >= 1, 'setVisibleLogicalRange must be called');
    const firstRange = chartSpies.setVisibleLogicalRangeCalls[0];
    assert.equal(firstRange.from, 501);
    assert.equal(firstRange.to, 613);

    unmount();
    assert.equal(chartSpies.removeCalls, 1, 'chart.remove() must be called on unmount');
    assert.equal(chartSpies.unsubscribeCalls, 1, 'unsubscribeVisibleLogicalRangeChange must be called');
  });

  test('2. Rapid Coin Switching (BTC -> ETH -> SOL): replaces data via setData and recalculates viewport without unmounting', async () => {
    const btcCandles = generateCandles(601, 75000);
    const ethCandles = generateCandles(601, 2500);
    const solCandles = generateCandles(601, 150);

    const { rerender, unmount } = renderChart({
      coin: 'BTC',
      interval: '1d',
      candles: btcCandles,
    });

    assert.equal(chartSpies.setDataCalls.length, 1);
    assert.equal(chartSpies.setDataCalls[0][0].close, 75001);

    // Switch BTC -> ETH
    rerender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(Chart, {
          coin: 'ETH',
          interval: '1d',
          candles: ethCandles,
          resistances: [],
          supports: [],
          fvgs: [],
          signals: [],
          activeFormation: 'CASCADE',
        })
      )
    );

    assert.equal(chartSpies.createChartCalls.length, 1, 'Chart instance should be reused, not recreated');
    assert.equal(chartSpies.setDataCalls.length, 2, 'setData must be called for ETH');
    assert.equal(chartSpies.setDataCalls[1][0].close, 2501, 'setData must receive ETH prices');
    assert.equal(chartSpies.updateCalls.length, 0, 'update must NOT be called for a coin switch');

    // Switch ETH -> SOL
    rerender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(Chart, {
          coin: 'SOL',
          interval: '1d',
          candles: solCandles,
          resistances: [],
          supports: [],
          fvgs: [],
          signals: [],
          activeFormation: 'CASCADE',
        })
      )
    );

    assert.equal(chartSpies.createChartCalls.length, 1, 'Chart instance preserved');
    assert.equal(chartSpies.setDataCalls.length, 3, 'setData must be called for SOL');
    assert.equal(chartSpies.setDataCalls[2][0].close, 151, 'setData must receive SOL prices');
    assert.equal(chartSpies.updateCalls.length, 0, 'update must NOT be called');

    unmount();
    assert.equal(chartSpies.removeCalls, 1);
  });

  test('3. Timeframe change (1d -> 1h): replaces data and recalculates viewport', async () => {
    const candles1d = generateCandles(601, 2500);
    const candles1h = generateCandles(500, 2550);

    const { rerender, unmount } = renderChart({
      coin: 'ETH',
      interval: '1d',
      candles: candles1d,
    });

    assert.equal(chartSpies.setDataCalls.length, 1);
    const initialRangesCount = chartSpies.setVisibleLogicalRangeCalls.length;

    rerender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(Chart, {
          coin: 'ETH',
          interval: '1h',
          candles: candles1h,
          resistances: [],
          supports: [],
          fvgs: [],
          signals: [],
          activeFormation: 'CASCADE',
        })
      )
    );

    assert.equal(chartSpies.setDataCalls.length, 2, 'setData called on interval change');
    assert.equal(chartSpies.updateCalls.length, 0);
    assert.ok(
      chartSpies.setVisibleLogicalRangeCalls.length > initialRangesCount,
      'Viewport recalculated for new interval'
    );

    unmount();
  });

  test('4. Small history listing (XTEN, 12 candles): calculates proper viewport (0 to 24)', async () => {
    const xtenCandles = generateCandles(12, 10);

    const { unmount } = renderChart({
      coin: 'XTEN',
      interval: '1d',
      candles: xtenCandles,
    });

    assert.equal(chartSpies.setDataCalls.length, 1);
    assert.equal(chartSpies.setDataCalls[0].length, 12);
    const range = chartSpies.setVisibleLogicalRangeCalls[0];
    assert.equal(range.from, 0);
    assert.equal(range.to, 24);

    unmount();
  });

  test('5. Full history reload for SAME coin (isLiveTick: false): calls setData but does NOT reset camera viewport', async () => {
    const initialCandles = generateCandles(601, 100);
    const { rerender, unmount } = renderChart({
      coin: 'SOL',
      interval: '1d',
      candles: initialCandles,
      isLiveTick: false,
    });

    assert.equal(chartSpies.setDataCalls.length, 1);
    const rangesCountBeforeReload = chartSpies.setVisibleLogicalRangeCalls.length;

    // Simulate full analysis refresh or reconnect reload: 601 candles with corrected prices
    const reloadedCandles = generateCandles(601, 105);
    rerender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(Chart, {
          coin: 'SOL',
          interval: '1d',
          candles: reloadedCandles,
          resistances: [],
          supports: [],
          fvgs: [],
          signals: [],
          activeFormation: 'CASCADE',
          isLiveTick: false,
        })
      )
    );

    assert.equal(chartSpies.setDataCalls.length, 2, 'Must call setData() to replace entire historical series');
    assert.equal(chartSpies.updateCalls.length, 0, 'Must NOT call update() on full history reload');
    assert.equal(
      chartSpies.setVisibleLogicalRangeCalls.length,
      rangesCountBeforeReload,
      'Must NOT call setVisibleLogicalRange again on reload (preserves user viewport)'
    );

    unmount();
  });

  test('6. Real-time WebSocket tick (isLiveTick: true): calls update() with zero setData() calls', async () => {
    const initialCandles = generateCandles(601, 100);
    const { rerender, unmount } = renderChart({
      coin: 'SOL',
      interval: '1d',
      candles: initialCandles,
      isLiveTick: false,
    });

    assert.equal(chartSpies.setDataCalls.length, 1);
    assert.equal(chartSpies.updateCalls.length, 0);

    // Live tick arrives via WebSocket
    const tickedCandles = [...initialCandles];
    tickedCandles[tickedCandles.length - 1] = {
      ...tickedCandles[tickedCandles.length - 1],
      close: 104.5,
    };

    rerender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(Chart, {
          coin: 'SOL',
          interval: '1d',
          candles: tickedCandles,
          resistances: [],
          supports: [],
          fvgs: [],
          signals: [],
          activeFormation: 'CASCADE',
          isLiveTick: true,
        })
      )
    );

    assert.equal(chartSpies.updateCalls.length, 1, 'Must call update() for real-time live tick');
    assert.equal(chartSpies.updateCalls[0].close, 104.5);
    assert.equal(chartSpies.setDataCalls.length, 1, 'Must NOT call setData() during live tick');

    unmount();
  });
});

describe('SidebarLevels.tsx Trendline Structural Context Tests (Phase 5.2)', () => {
  let rtlRender: any;

  before(async () => {
    const rtl = await import('@testing-library/react');
    rtlRender = rtl.render;
  });

  const baseProps = {
    resistances: [],
    supports: [],
    currentPrice: 2000.0,
    cascades: [],
    trendlines: [],
    fvgs: [],
    fvgConfluences: [],
  };

  test('1. Renders TIER_1_CONFLUENT badge and support metrics on Long Sweep signal', () => {
    const signal: any = {
      id: 'sweep-t1-1',
      coin: 'ETH',
      interval: '15m',
      category: 'sweep',
      title: 'Бичачий Sweep [2000]',
      direction: 'LONG',
      desc: 'Sweep of support level',
      price: 2000.0,
      time: 1700000000,
      confirmationStatus: 'CONFIRMED',
      structuralContext: {
        contextAvailable: true,
        htfAlignment: 'ALIGNED',
        hasSupportConfluence: true,
        confluentLineQ: 88.5,
        distanceToSupportAtr: 0.25,
        distanceToResistanceAtr: 3.1,
        nearestSupportQ: 88.5,
        nearestResistanceQ: 75.0,
        isCompression: false,
        compressionRatio: 1.1,
        isRetest: false,
        riskFlags: [],
        structuralTier: 'TIER_1_CONFLUENT',
      },
    };

    const { container } = rtlRender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(SidebarLevels, {
          ...baseProps,
          activeFormation: 'SWEEP',
          signals: [signal],
        })
      )
    );

    const text = container.textContent || '';
    assert.match(text, /Збіг/i, 'Must render Confluent (Збіг) badge');
    assert.match(text, /Підтримка Q:89/i, 'Must render support line quality rounded to integer');
    assert.match(text, /0\.3 ATR/i, 'Must render distance to support line');
    assert.match(text, /1h Збіг/i, 'Must render 1h HTF alignment indicator (1h Збіг)');
  });

  test('2. Renders TIER_3_WARNING badges (Against HTF and Compression)', () => {
    const signal: any = {
      id: 'sweep-t3-1',
      coin: 'BTC',
      interval: '15m',
      category: 'sweep',
      title: 'Бичачий Sweep проти тренду',
      direction: 'LONG',
      desc: 'Sweep under severe compression',
      price: 64000.0,
      time: 1700000000,
      confirmationStatus: 'POTENTIAL',
      structuralContext: {
        contextAvailable: true,
        htfAlignment: 'AGAINST_HTF',
        hasSupportConfluence: false,
        confluentLineQ: null,
        distanceToSupportAtr: 1.4,
        distanceToResistanceAtr: 0.8,
        nearestSupportQ: 70.0,
        nearestResistanceQ: 85.0,
        isCompression: true,
        compressionRatio: 0.52,
        isRetest: false,
        riskFlags: ['AGAINST_HTF', 'COMPRESSION'],
        structuralTier: 'TIER_3_WARNING',
      },
    };

    const { container } = rtlRender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(SidebarLevels, {
          ...baseProps,
          activeFormation: 'SWEEP',
          signals: [signal],
        })
      )
    );

    const text = container.textContent || '';
    assert.match(text, /Проти HTF/i, 'Must render Проти HTF warning badge');
    assert.match(text, /Стиснення/i, 'Must render Стиснення warning badge');
    assert.match(text, /Проти 1h/i, 'Must render Проти 1h status');
    assert.doesNotMatch(text, /Збіг/i, 'Must NOT render Збіг badge on Tier 3');
  });

  test('3. Renders TIER_2_STANDARD signal without warning badges or confluence badge', () => {
    const signal: any = {
      id: 'fvg-t2-1',
      coin: 'SOL',
      interval: '15m',
      category: 'fvg',
      title: 'Бичачий FVG',
      direction: 'LONG',
      desc: 'Normal FVG test',
      price: 150.0,
      time: 1700000000,
      structuralContext: {
        contextAvailable: true,
        htfAlignment: 'NEUTRAL',
        hasSupportConfluence: false,
        confluentLineQ: null,
        distanceToSupportAtr: 2.2,
        distanceToResistanceAtr: 1.8,
        nearestSupportQ: 74.0,
        nearestResistanceQ: 78.0,
        isCompression: false,
        compressionRatio: 0.95,
        isRetest: false,
        riskFlags: [],
        structuralTier: 'TIER_2_STANDARD',
      },
    };

    const { container } = rtlRender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(SidebarLevels, {
          ...baseProps,
          activeFormation: 'FVG',
          signals: [signal],
        })
      )
    );

    const text = container.textContent || '';
    assert.doesNotMatch(text, /Збіг/i, 'Must NOT render Confluent badge on standard Tier 2');
    assert.doesNotMatch(text, /Проти HTF/i, 'Must NOT render Against HTF badge');
    assert.doesNotMatch(text, /Стиснення/i, 'Must NOT render Compression badge');
    assert.match(text, /Підтримка: 2\.2 ATR/i, 'Must render plain support distance');
    assert.match(text, /Опір: 1\.8 ATR/i, 'Must render plain resistance distance');
  });

  test('4. Graceful fallback when contextAvailable is false', () => {
    const signal: any = {
      id: 'fvg-no-ctx',
      coin: 'PUMP',
      interval: '15m',
      category: 'fvg',
      title: 'Бичачий FVG без контексту',
      direction: 'LONG',
      desc: 'FVG test when HTF history is unavailable',
      price: 0.005,
      time: 1700000000,
      structuralContext: {
        contextAvailable: false,
        unavailableReason: 'INSUFFICIENT_CANDLES',
        htfAlignment: 'UNAVAILABLE',
        hasSupportConfluence: false,
        confluentLineQ: null,
        distanceToSupportAtr: null,
        distanceToResistanceAtr: null,
        nearestSupportQ: null,
        nearestResistanceQ: null,
        isCompression: false,
        compressionRatio: null,
        isRetest: false,
        riskFlags: [],
        structuralTier: 'TIER_2_STANDARD',
      },
    };

    const { container } = rtlRender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(SidebarLevels, {
          ...baseProps,
          activeFormation: 'SWEEP',
          signals: [signal],
        })
      )
    );

    const text = container.textContent || '';
    assert.doesNotMatch(text, /Збіг/i);
    assert.doesNotMatch(text, /Проти HTF/i);
    assert.doesNotMatch(text, /Стиснення/i);
    assert.doesNotMatch(text, /Підтримка/i, 'Should not render empty support distance row');
  });

  test('5. Backward compatibility with legacy signals lacking structuralContext', () => {
    const legacySignal: any = {
      id: 'legacy-sweep-1',
      coin: 'MET',
      interval: '15m',
      category: 'sweep',
      title: 'Legacy Sweep',
      direction: 'LONG',
      desc: 'Old signal format without structuralContext',
      price: 45.0,
      time: 1700000000,
      confirmationStatus: 'CONFIRMED',
      oiConfirmed: true,
      oiDeltaPct: -3.5,
    };

    const { container } = rtlRender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(SidebarLevels, {
          ...baseProps,
          activeFormation: 'SWEEP',
          signals: [legacySignal],
        })
      )
    );

    const text = container.textContent || '';
    assert.match(text, /Legacy Sweep/i, 'Must render legacy title cleanly');
    assert.match(text, /ПІДТВЕРДЖЕНО/i, 'Must render legacy status');
    assert.match(text, /-3\.500%/i, 'Must render legacy OI delta');
    assert.doesNotMatch(text, /Збіг/i);
    assert.doesNotMatch(text, /Проти HTF/i);
  });
});
