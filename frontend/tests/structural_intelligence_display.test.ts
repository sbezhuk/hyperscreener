import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ZonesPrimitive } from '../src/components/ZonesPrimitive';
import { TrendlineItem } from '../src/types';

test('Frontend Structural Intelligence Rendering Verification', async (t) => {
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
        timeToCoordinate: (t: number) => 100 + (t - 1700000000) * 0.1,
      },
      candleSeries: {
        priceToCoordinate: (p: number) => 600 - (p - 100) * 4,
      },
    };
  };

  await t.test('1. Renders Q: 85 and [COMPRESSION] badges independently on the canvas', () => {
    const primitive = new ZonesPrimitive();
    const { timeScale, candleSeries } = createMockScaleAndSeries();
    drawCalls = [];

    primitive.attached({
      chart: { timeScale: () => timeScale },
      series: candleSeries,
      requestUpdate: () => {},
    } as any);

    const tl: TrendlineItem = {
      id: 'tl-15m-res-1',
      timeframe: '15m',
      direction: 'DESCENDING',
      line_type: 'resistance_trendline',
      label: 'Наклонка (Опір)',
      start_point: { time: 1700000100, price: 150 },
      end_point: { time: 1700000300, price: 140 },
      slope: -0.05,
      touch_count: 3,
      strength: 84.5,
      structural_quality: 84.5,
      structuralQuality: 84.5,
      interaction_state: 'COMPRESSION',
      interactionState: 'COMPRESSION',
      status: 'ACTIVE',
      last_updated: 1700000500,
      type: 'resistance_trendline',
      p1: { time: 1700000100, price: 150 },
      p2: { time: 1700000300, price: 140 },
      score: 84.5,
      touches: 3,
    };

    primitive.updateData({
      trendlines: [tl],
      activeFormation: 'TRENDLINE',
      currentTimeframe: '15m',
    });

    const renderer = primitive.paneViews()[0].renderer();
    renderer.draw({
      useMediaCoordinateSpace: (cb: any) => {
        cb({ context: canvasContextMock, mediaSize: { width: 1000, height: 600 } });
      },
    });

    const labels = drawCalls.filter((c) => c.type === 'fillText').map((c) => c.args[0]);
    // Must contain Q: 85
    assert.ok(labels.some((l) => l.includes('Q: 85')), 'Must draw Q: 85 indicator');
    // Must contain [COMPRESSION]
    assert.ok(labels.some((l) => l.includes('[COMPRESSION]')), 'Must draw [COMPRESSION] state badge');
  });

  await t.test('2. Timeframe switching does not leak state or Q across timeframes', () => {
    const primitive = new ZonesPrimitive();
    const { timeScale, candleSeries } = createMockScaleAndSeries();
    drawCalls = [];

    primitive.attached({
      chart: { timeScale: () => timeScale },
      series: candleSeries,
      requestUpdate: () => {},
    } as any);

    const tl15m: TrendlineItem = {
      timeframe: '15m',
      direction: 'DESCENDING',
      line_type: 'resistance_trendline',
      label: '15M-TL',
      start_point: { time: 1700000100, price: 150 },
      end_point: { time: 1700000300, price: 140 },
      slope: -0.05,
      touch_count: 3,
      strength: 92,
      structuralQuality: 92,
      interactionState: 'BREAKOUT',
      status: 'BROKEN',
      last_updated: 1700000500,
      type: 'resistance_trendline',
      p1: { time: 1700000100, price: 150 },
      p2: { time: 1700000300, price: 140 },
    };

    const tl1h: TrendlineItem = {
      timeframe: '1h',
      direction: 'ASCENDING',
      line_type: 'support_trendline',
      label: '1H-TL',
      start_point: { time: 1700000050, price: 120 },
      end_point: { time: 1700000250, price: 135 },
      slope: 0.075,
      touch_count: 2,
      strength: 71,
      structuralQuality: 71,
      interactionState: 'APPROACHING',
      status: 'ACTIVE',
      last_updated: 1700000500,
      type: 'support_trendline',
      p1: { time: 1700000050, price: 120 },
      p2: { time: 1700000250, price: 135 },
    };

    // User is on 1h chart -> only 1H line should be drawn
    primitive.updateData({
      trendlines: [tl15m, tl1h],
      activeFormation: 'TRENDLINE',
      currentTimeframe: '1h',
    });

    const renderer = primitive.paneViews()[0].renderer();
    renderer.draw({
      useMediaCoordinateSpace: (cb: any) => {
        cb({ context: canvasContextMock, mediaSize: { width: 1000, height: 600 } });
      },
    });

    const labels = drawCalls.filter((c) => c.type === 'fillText').map((c) => c.args[0]);
    assert.ok(labels.some((l) => l.includes('Q: 71')), '1h chart must render Q: 71');
    assert.ok(labels.some((l) => l.includes('[APPROACHING]')), '1h chart must render [APPROACHING]');
    assert.ok(!labels.some((l) => l.includes('Q: 92')), '1h chart MUST NOT render 15m Q: 92');
    assert.ok(!labels.some((l) => l.includes('[BREAKOUT]')), '1h chart MUST NOT render 15m [BREAKOUT]');
  });

  await t.test('3. Renders AGAINST HTF structural risk warning badge on chart canvas', () => {
    const primitive = new ZonesPrimitive();
    const { timeScale, candleSeries } = createMockScaleAndSeries();
    drawCalls = [];

    primitive.attached({
      chart: { timeScale: () => timeScale },
      series: candleSeries,
      requestUpdate: () => {},
    } as any);

    const tlAgainstHtf: TrendlineItem = {
      id: 'tl-15m-sup-against',
      timeframe: '15m',
      direction: 'ASCENDING',
      line_type: 'support_trendline',
      label: 'Наклонка (Підтримка)',
      start_point: { time: 1700000100, price: 100 },
      end_point: { time: 1700000300, price: 120 },
      slope: 0.1,
      touch_count: 3,
      strength: 88,
      structuralQuality: 88,
      interactionState: 'TESTING',
      htfContext: 'AGAINST_HTF',
      structuralRiskFlags: ['AGAINST_HTF'],
      status: 'ACTIVE',
      last_updated: 1700000500,
      type: 'support_trendline',
      p1: { time: 1700000100, price: 100 },
      p2: { time: 1700000300, price: 120 },
    };

    primitive.updateData({
      trendlines: [tlAgainstHtf],
      activeFormation: 'TRENDLINE',
      currentTimeframe: '15m',
    });

    const renderer = primitive.paneViews()[0].renderer();
    renderer.draw({
      useMediaCoordinateSpace: (cb: any) => {
        cb({ context: canvasContextMock, mediaSize: { width: 1000, height: 600 } });
      },
    });

    const labels = drawCalls.filter((c) => c.type === 'fillText').map((c) => c.args[0]);
    assert.ok(labels.some((l) => l.includes('Q: 88')), 'Must render Q: 88');
    assert.ok(labels.some((l) => l.includes('[TESTING]')), 'Must render [TESTING]');
    assert.ok(labels.some((l) => l.includes('⚠️ AGAINST HTF')), 'Must render ⚠️ AGAINST HTF warning badge');
  });
});
