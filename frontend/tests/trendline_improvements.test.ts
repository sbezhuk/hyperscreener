import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ZonesPrimitive } from '../src/components/ZonesPrimitive';
import { TrendlineItem, RegressionChannelItem } from '../src/types';

test('Frontend Trendline Improvements & Linear Regression Channel Tests', async (t) => {
  let drawCalls: Array<{ type: string; args: any[] }> = [];

  const canvasContextMock = {
    font: '',
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 1,
    lineDash: [] as number[],
    textBaseline: 'alphabetic',
    textAlign: 'start',
    measureText: (text: string) => ({ width: text.length * 6.5 }),
    beginPath: () => drawCalls.push({ type: 'beginPath', args: [] }),
    moveTo: (x: number, y: number) => drawCalls.push({ type: 'moveTo', args: [x, y] }),
    lineTo: (x: number, y: number) => drawCalls.push({ type: 'lineTo', args: [x, y] }),
    stroke: () => drawCalls.push({ type: 'stroke', args: [] }),
    fill: () => drawCalls.push({ type: 'fill', args: [] }),
    closePath: () => drawCalls.push({ type: 'closePath', args: [] }),
    arc: (x: number, y: number, r: number, sa: number, ea: number) =>
      drawCalls.push({ type: 'arc', args: [x, y, r, sa, ea] }),
    rect: (x: number, y: number, w: number, h: number) =>
      drawCalls.push({ type: 'rect', args: [x, y, w, h] }),
    fillRect: (x: number, y: number, w: number, h: number) =>
      drawCalls.push({ type: 'fillRect', args: [x, y, w, h] }),
    strokeRect: (x: number, y: number, w: number, h: number) =>
      drawCalls.push({ type: 'strokeRect', args: [x, y, w, h] }),
    fillText: (text: string, x: number, y: number) =>
      drawCalls.push({ type: 'fillText', args: [text, x, y] }),
    setLineDash: (segments: number[]) => {
      canvasContextMock.lineDash = segments;
      drawCalls.push({ type: 'setLineDash', args: [segments] });
    },
    roundRect: (x: number, y: number, w: number, h: number, r: number) =>
      drawCalls.push({ type: 'roundRect', args: [x, y, w, h, r] }),
  };

  const createMockScaleAndSeries = () => {
    return {
      timeScale: {
        timeToCoordinate: (timeVal: number) => 100 + (timeVal - 1700000000) * 0.1,
      },
      candleSeries: {
        priceToCoordinate: (p: number) => 600 - (p - 100) * 4,
      },
    };
  };

  await t.test('1. Renders Linear Regression Channel when formation is TRENDLINE', () => {
    const primitive = new ZonesPrimitive();
    const { timeScale, candleSeries } = createMockScaleAndSeries();
    drawCalls = [];

    primitive.attached({
      chart: { timeScale: () => timeScale },
      series: candleSeries,
      requestUpdate: () => {},
    } as any);

    const regChan: RegressionChannelItem = {
      id: 'regchan-5m-1700000100-1700000500',
      timeframe: '5m',
      slope: 0.25,
      intercept: 100.0,
      r_squared: 0.88,
      rSquared: 0.88,
      std_dev: 1.5,
      stdDev: 1.5,
      num_std: 2.0,
      direction: 'ASCENDING',
      sample_size: 50,
      channel_position_pct: 65.0,
      start_time: 1700000100,
      end_time: 1700000500,
      middle: {
        p1: { time: 1700000100, price: 100.0 },
        p2: { time: 1700000500, price: 110.0 },
      },
      upper: {
        p1: { time: 1700000100, price: 103.0 },
        p2: { time: 1700000500, price: 113.0 },
      },
      lower: {
        p1: { time: 1700000100, price: 97.0 },
        p2: { time: 1700000500, price: 107.0 },
      },
    };

    primitive.updateData({
      activeFormation: 'TRENDLINE',
      currentTimeframe: '5m',
      regressionChannel: regChan,
      trendlines: [],
    });

    const paneView = primitive.paneViews()[0];
    const renderer = paneView.renderer();
    renderer.draw({
      useMediaCoordinateSpace: (cb: any) =>
        cb({ context: canvasContextMock, mediaSize: { width: 1000, height: 600 } }),
    });

    // Verify fillText called with regression channel badge
    const fillTexts = drawCalls.filter((c) => c.type === 'fillText').map((c) => c.args[0]);
    const regBadge = fillTexts.find((t) => t.includes('Канал регресії'));
    assert.ok(regBadge, `Expected 'Канал регресії' badge in fillText calls, got: ${fillTexts.join(', ')}`);
    assert.ok(regBadge.includes('R²: 0.88'));
    assert.ok(regBadge.includes('k: +0.25'));
  });

  await t.test('2. Renders 3+ touch confirmed trendline label', () => {
    const primitive = new ZonesPrimitive();
    const { timeScale, candleSeries } = createMockScaleAndSeries();
    drawCalls = [];

    primitive.attached({
      chart: { timeScale: () => timeScale },
      series: candleSeries,
      requestUpdate: () => {},
    } as any);

    const tl: TrendlineItem = {
      id: 'tl-5m-res-3touch',
      timeframe: '5m',
      direction: 'DESCENDING',
      line_type: 'resistance_trendline',
      label: 'Наклонка (Опір)',
      timeframe_label: 'Наклонка (Опір) [5m] (x3 Підтверджена)',
      start_point: { time: 1700000100, price: 150 },
      end_point: { time: 1700000300, price: 140 },
      slope: -0.05,
      touch_count: 3,
      is_confirmed: true,
      strength: 92,
      status: 'ACTIVE',
      last_updated: 1700000400,
      type: 'resistance_trendline',
      p1: { time: 1700000100, price: 150 },
      p2: { time: 1700000300, price: 140 },
      interaction_state: 'TESTING',
    };

    primitive.updateData({
      activeFormation: 'TRENDLINE',
      currentTimeframe: '5m',
      trendlines: [tl],
    });

    const paneView = primitive.paneViews()[0];
    const renderer = paneView.renderer();
    renderer.draw({
      useMediaCoordinateSpace: (cb: any) =>
        cb({ context: canvasContextMock, mediaSize: { width: 1000, height: 600 } }),
    });

    const fillTexts = drawCalls.filter((c) => c.type === 'fillText').map((c) => c.args[0]);
    const tlLabel = fillTexts.find((t) => t.includes('Підтверджена'));
    assert.ok(tlLabel, `Expected 'Підтверджена' in labels, got: ${fillTexts.join(', ')}`);
  });
});
