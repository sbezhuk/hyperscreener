import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { ZonesPrimitive } from '../src/components/ZonesPrimitive';

describe('Frontend Visual Audit & Rendering Verification', () => {
  let canvasContextMock: any;
  let drawCalls: { type: string; args: any[] }[];

  beforeEach(() => {
    drawCalls = [];
    canvasContextMock = {
      save: () => drawCalls.push({ type: 'save', args: [] }),
      restore: () => drawCalls.push({ type: 'restore', args: [] }),
      beginPath: () => drawCalls.push({ type: 'beginPath', args: [] }),
      moveTo: (x: number, y: number) => drawCalls.push({ type: 'moveTo', args: [x, y] }),
      lineTo: (x: number, y: number) => drawCalls.push({ type: 'lineTo', args: [x, y] }),
      stroke: () => drawCalls.push({ type: 'stroke', args: [] }),
      fill: () => drawCalls.push({ type: 'fill', args: [] }),
      arc: (x: number, y: number, r: number, sa: number, ea: number) =>
        drawCalls.push({ type: 'arc', args: [x, y, r, sa, ea] }),
      setLineDash: (dash: number[]) => drawCalls.push({ type: 'setLineDash', args: [dash] }),
      measureText: (text: string) => ({ width: text.length * 6 }),
      fillText: (text: string, x: number, y: number) => drawCalls.push({ type: 'fillText', args: [text, x, y] }),
      roundRect: (x: number, y: number, w: number, h: number, r: number) =>
        drawCalls.push({ type: 'roundRect', args: [x, y, w, h, r] }),
      font: '',
      fillStyle: '',
      strokeStyle: '',
      lineWidth: 1,
    };
  });

  function createMockSeriesAndScale() {
    // Simulated timeScale: time -> x coordinate (1 sec = 0.1 px, base 1700000000 -> 100)
    const timeScale = {
      timeToCoordinate: (t: number) => {
        if (!t) return null;
        return 100 + (t - 1700000000) * 0.1;
      },
    };
    // Simulated candleSeries: price -> y coordinate (linear mapping: price 100 -> 500, price 200 -> 100)
    const candleSeries = {
      priceToCoordinate: (p: number) => {
        if (p === null || p === undefined) return null;
        return 500 - (p - 100) * 4;
      },
    };
    return { timeScale, candleSeries };
  }

  test('1. Trendline anchors and ray extension are mathematically accurate', () => {
    const primitive = new ZonesPrimitive();
    const { timeScale, candleSeries } = createMockSeriesAndScale();

    primitive.attached({
      chart: { timeScale: () => timeScale },
      series: candleSeries,
      requestUpdate: () => {},
    } as any);

    const tl15m = {
      timeframe: '15m',
      direction: 'DESCENDING' as const,
      line_type: 'resistance_trendline',
      label: 'Наклонка (Опір)',
      start_point: { time: 1700000100, price: 150 }, // x1 = 110, y1 = 300
      end_point: { time: 1700000300, price: 140 },   // x2 = 130, y2 = 340
      slope: -0.05,
      touch_count: 3,
      strength: 85,
      status: 'ACTIVE' as const,
      last_updated: 1700000500,
      type: 'resistance_trendline',
      p1: { time: 1700000100, price: 150 },
      p2: { time: 1700000300, price: 140 },
    };

    primitive.updateData({
      trendlines: [tl15m],
      activeFormation: 'TRENDLINE',
      currentTimeframe: '15m',
    });

    const paneViews = primitive.paneViews();
    assert.equal(paneViews.length, 1);
    const renderer = paneViews[0].renderer();

    const targetMock = {
      useMediaCoordinateSpace: (cb: any) => {
        cb({ context: canvasContextMock, mediaSize: { width: 1000, height: 600 } });
      },
    };
    renderer.draw(targetMock);

    // Verify Anchor 1 and Anchor 2
    const expectedX1 = timeScale.timeToCoordinate(1700000100); // 110
    const expectedY1 = candleSeries.priceToCoordinate(150);     // 300
    const expectedX2 = timeScale.timeToCoordinate(1700000300); // 130
    const expectedY2 = candleSeries.priceToCoordinate(140);     // 340

    // Check line segment: moveTo(x1, y1), lineTo(x2, y2)
    const lineSegmentStart = drawCalls.find(
      (c) => c.type === 'moveTo' && Math.abs(c.args[0] - expectedX1!) < 1e-4 && Math.abs(c.args[1] - expectedY1!) < 1e-4
    );
    assert.ok(lineSegmentStart, 'Should moveTo starting anchor (x1, y1)');

    const lineSegmentEnd = drawCalls.find(
      (c) => c.type === 'lineTo' && Math.abs(c.args[0] - expectedX2!) < 1e-4 && Math.abs(c.args[1] - expectedY2!) < 1e-4
    );
    assert.ok(lineSegmentEnd, 'Should lineTo ending anchor (x2, y2)');

    // Check extension ray: slope = (340 - 300) / (130 - 110) = 40 / 20 = 2 px/px
    // maxRightX = width - 4 = 1000 - 4 = 996
    // extendX = 996, extendY = 340 + 2 * (996 - 130) = 340 + 1732 = 2072
    const expectedExtendX = 996;
    const expectedExtendY = 2072;
    const rayToRight = drawCalls.find(
      (c) => c.type === 'lineTo' && Math.abs(c.args[0] - expectedExtendX) < 1e-4 && Math.abs(c.args[1] - expectedExtendY) < 1e-4
    );
    assert.ok(rayToRight, 'Should extend ray colinearly to maxRightX');

    // Check anchor points: arc(x1, y1, 3.5), arc(x2, y2, 3.5)
    const arcCalls = drawCalls.filter((c) => c.type === 'arc');
    assert.equal(arcCalls.length, 2, 'Should draw exactly 2 anchor dots');
    assert.equal(arcCalls[0].args[0], expectedX1);
    assert.equal(arcCalls[1].args[0], expectedX2);
  });

  test('2. Timeframe Isolation: alien timeframes are never drawn on canvas', () => {
    const primitive = new ZonesPrimitive();
    const { timeScale, candleSeries } = createMockSeriesAndScale();

    primitive.attached({
      chart: { timeScale: () => timeScale },
      series: candleSeries,
      requestUpdate: () => {},
    } as any);

    const tl15m = {
      timeframe: '15m',
      direction: 'DESCENDING' as const,
      line_type: 'resistance_trendline',
      label: '15M LINE',
      start_point: { time: 1700000100, price: 150 },
      end_point: { time: 1700000300, price: 140 },
      slope: -0.05,
      touch_count: 3,
      strength: 85,
      status: 'ACTIVE' as const,
      last_updated: 1700000500,
      type: 'resistance_trendline',
      p1: { time: 1700000100, price: 150 },
      p2: { time: 1700000300, price: 140 },
    };

    const tl1h = {
      timeframe: '1h',
      direction: 'ASCENDING' as const,
      line_type: 'support_trendline',
      label: '1H LINE',
      start_point: { time: 1700000050, price: 120 },
      end_point: { time: 1700000250, price: 135 },
      slope: 0.075,
      touch_count: 4,
      strength: 90,
      status: 'ACTIVE' as const,
      last_updated: 1700000500,
      type: 'support_trendline',
      p1: { time: 1700000050, price: 120 },
      p2: { time: 1700000250, price: 135 },
    };

    // User is viewing 15m chart
    primitive.updateData({
      trendlines: [tl15m, tl1h],
      activeFormation: 'TRENDLINE',
      currentTimeframe: '15m',
    });

    const renderer = primitive.paneViews()[0].renderer();
    const targetMock = {
      useMediaCoordinateSpace: (cb: any) => {
        cb({ context: canvasContextMock, mediaSize: { width: 1000, height: 600 } });
      },
    };
    renderer.draw(targetMock);

    // Verify: 15m line label was drawn, 1H line label was NEVER drawn
    const drawnLabels = drawCalls.filter((c) => c.type === 'fillText').map((c) => c.args[0]);
    assert.ok(drawnLabels.some((l) => l.includes('15M LINE')), '15m line must be drawn');
    assert.ok(!drawnLabels.some((l) => l.includes('1H LINE')), '1h line MUST NOT be drawn on 15m chart');

    // Reset calls & switch user view to 1h chart
    drawCalls = [];
    primitive.updateData({
      trendlines: [tl15m, tl1h],
      activeFormation: 'TRENDLINE',
      currentTimeframe: '1h',
    });

    const renderer1h = primitive.paneViews()[0].renderer();
    renderer1h.draw(targetMock);

    const drawnLabels1h = drawCalls.filter((c) => c.type === 'fillText').map((c) => c.args[0]);
    assert.ok(drawnLabels1h.some((l) => l.includes('1H LINE')), '1h line must be drawn on 1h chart');
    assert.ok(!drawnLabels1h.some((l) => l.includes('15M LINE')), '15m line MUST NOT be drawn on 1h chart');
  });

  test('3. Broken Trendline visual status verification', () => {
    const primitive = new ZonesPrimitive();
    const { timeScale, candleSeries } = createMockSeriesAndScale();

    primitive.attached({
      chart: { timeScale: () => timeScale },
      series: candleSeries,
      requestUpdate: () => {},
    } as any);

    const brokenTl = {
      timeframe: '5m',
      direction: 'DESCENDING' as const,
      line_type: 'resistance_trendline',
      label: 'Наклонка (Опір)',
      start_point: { time: 1700000100, price: 150 },
      end_point: { time: 1700000300, price: 140 },
      slope: -0.05,
      touch_count: 2,
      strength: 40,
      status: 'BROKEN' as const,
      last_updated: 1700000500,
      type: 'resistance_trendline',
      p1: { time: 1700000100, price: 150 },
      p2: { time: 1700000300, price: 140 },
    };

    primitive.updateData({
      trendlines: [brokenTl],
      activeFormation: 'TRENDLINE',
      currentTimeframe: '5m',
    });

    const renderer = primitive.paneViews()[0].renderer();
    const targetMock = {
      useMediaCoordinateSpace: (cb: any) => {
        cb({ context: canvasContextMock, mediaSize: { width: 1000, height: 600 } });
      },
    };
    renderer.draw(targetMock);

    // Check dashed styling [4, 4] was applied for broken line
    const dashedCalls = drawCalls.filter(
      (c) => c.type === 'setLineDash' && Array.isArray(c.args[0]) && c.args[0][0] === 4
    );
    assert.ok(dashedCalls.length > 0, 'Broken trendline must be drawn dashed');

    // Check badge text contains [Пробита]
    const drawnLabels = drawCalls.filter((c) => c.type === 'fillText').map((c) => c.args[0]);
    assert.ok(drawnLabels.some((l) => l.includes('[Пробита]')), 'Broken line badge must display [Пробита]');
  });
});
