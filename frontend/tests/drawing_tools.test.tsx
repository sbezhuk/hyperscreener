import { test, describe, before } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { JSDOM } from 'jsdom';
import { DrawingToolbar } from '../src/components/DrawingToolbar';
import { DrawingsPrimitive } from '../src/components/DrawingsPrimitive';
import { ChartDrawing, DrawingToolType } from '../src/types';
import { saveCoinDrawings, loadCoinDrawings, clearCoinDrawings } from '../src/utils/storage';

// 1. Set up simulated DOM environment
const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost:3000',
});

global.window = dom.window as any;
global.document = dom.window.document as any;
global.HTMLElement = dom.window.HTMLElement as any;
global.HTMLDivElement = dom.window.HTMLDivElement as any;
global.localStorage = dom.window.localStorage as any;

describe('TradingView Drawing Tools & Primitives Verification', () => {
  let rtlRender: any;
  let rtlFireEvent: any;

  before(async () => {
    const rtl = await import('@testing-library/react');
    rtlRender = rtl.render;
    rtlFireEvent = rtl.fireEvent;
  });

  test('1. DrawingToolbar renders all 10 TradingView tools with localized titles', () => {
    let selectedTool: DrawingToolType = 'cursor';

    const { container } = rtlRender(
      React.createElement(DrawingToolbar, {
        activeTool: 'cursor',
        onSelectTool: (t) => {
          selectedTool = t;
        },
        drawingsCount: 0,
      })
    );

    // Verify presence of buttons by title
    const trendlineBtn = container.querySelector('button[title*="Лінія тренду"]');
    assert.ok(trendlineBtn, 'Trendline button must be present');

    const rayBtn = container.querySelector('button[title*="Промінь"]');
    assert.ok(rayBtn, 'Ray button must be present');

    const horzBtn = container.querySelector('button[title*="Горизонтальна лінія"]');
    assert.ok(horzBtn, 'Horizontal line button must be present');

    const horzRayBtn = container.querySelector('button[title*="Горизонтальний промінь"]');
    assert.ok(horzRayBtn, 'Horizontal ray button must be present');

    const rectBtn = container.querySelector('button[title*="Прямокутник"]');
    assert.ok(rectBtn, 'Rectangle button must be present');

    const fibBtn = container.querySelector('button[title*="Фібоначчі"]');
    assert.ok(fibBtn, 'Fibonacci button must be present');

    const textBtn = container.querySelector('button[title*="Текст"]');
    assert.ok(textBtn, 'Text button must be present');

    const rulerBtn = container.querySelector('button[title*="Лінійка"]');
    assert.ok(rulerBtn, 'Ruler button must be present');

    const brushBtn = container.querySelector('button[title*="Пензель"]');
    assert.ok(brushBtn, 'Brush button must be present');

    // Test tool selection
    rtlFireEvent.click(trendlineBtn);
    assert.equal(selectedTool, 'trendline', 'Clicking tool button must fire onSelectTool with trendline');
  });

  test('2. DrawingToolbar shows Clear All button when drawingsCount > 0', () => {
    let cleared = false;
    // Mock window.confirm
    global.window.confirm = () => true;

    const { container } = rtlRender(
      React.createElement(DrawingToolbar, {
        activeTool: 'cursor',
        onSelectTool: () => {},
        onClearAllDrawings: () => {
          cleared = true;
        },
        drawingsCount: 3,
      })
    );

    const clearBtn = container.querySelector('button[title*="Очистити всі малюнки (3)"]');
    assert.ok(clearBtn, 'Clear All button must be displayed when drawingsCount > 0');

    rtlFireEvent.click(clearBtn);
    assert.equal(cleared, true, 'Clicking clear button must fire onClearAllDrawings');
  });

  test('3. Floating properties bar renders when a drawing is selected', () => {
    let updatedProps: Partial<ChartDrawing> | null = null;
    let deleted = false;

    const sampleDrawing: ChartDrawing = {
      id: 'draw-rect-1',
      type: 'rectangle',
      coin: 'BTC',
      points: [
        { time: 1700000000, price: 65000 },
        { time: 1700003600, price: 67000 },
      ],
      color: '#2962ff',
      lineWidth: 2,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    const { container } = rtlRender(
      React.createElement(DrawingToolbar, {
        activeTool: 'cursor',
        onSelectTool: () => {},
        selectedDrawing: sampleDrawing,
        onUpdateDrawing: (up) => {
          updatedProps = up;
        },
        onDeleteSelectedDrawing: () => {
          deleted = true;
        },
        drawingsCount: 1,
      })
    );

    // Verify floating bar rendered
    const text = container.textContent || '';
    assert.match(text, /RECTANGLE/i, 'Must display drawing type tag');

    // Click color preset
    const greenColorBtn = container.querySelector('button[title="Зелений"]');
    assert.ok(greenColorBtn, 'Green color preset must be available');
    rtlFireEvent.click(greenColorBtn);
    assert.equal(updatedProps?.color, '#0ecb81', 'Must update drawing color to emerald');

    // Click line width 3
    const width3Btn = container.querySelector('button[title="Товщина: 3px"]');
    assert.ok(width3Btn, 'Width 3px button must be available');
    rtlFireEvent.click(width3Btn);
    assert.equal(updatedProps?.lineWidth, 3, 'Must update line width to 3');

    // Click delete
    const deleteBtn = container.querySelector('button[title*="Видалити"]');
    assert.ok(deleteBtn, 'Delete button must be available');
    rtlFireEvent.click(deleteBtn);
    assert.equal(deleted, true, 'Must fire onDeleteSelectedDrawing');
  });

  test('4. DrawingsPrimitive integrates with Chart lifecycle and updates state without errors', () => {
    const primitive = new DrawingsPrimitive();

    // Mock chart and series
    const mockChart = {
      timeScale: () => ({
        timeToCoordinate: (_t: any) => 120,
      }),
    };
    const mockSeries = {
      priceToCoordinate: (_p: any) => 80,
    };

    let updateRequested = false;
    primitive.attached({
      chart: mockChart as any,
      series: mockSeries as any,
      requestUpdate: () => {
        updateRequested = true;
      },
    });

    const mockDrawings: ChartDrawing[] = [
      {
        id: 'tl-1',
        type: 'trendline',
        coin: 'SOL',
        points: [
          { time: 1700000000, price: 150 },
          { time: 1700003600, price: 165 },
        ],
        color: '#0ecb81',
        lineWidth: 2,
        createdAt: 1700000000,
        updatedAt: 1700000000,
      },
      {
        id: 'fib-1',
        type: 'fibonacci',
        coin: 'SOL',
        points: [
          { time: 1700000000, price: 140 },
          { time: 1700003600, price: 170 },
        ],
        color: '#2962ff',
        lineWidth: 1,
        createdAt: 1700000000,
        updatedAt: 1700000000,
      },
      {
        id: 'hz-1',
        type: 'horizontal',
        coin: 'SOL',
        points: [{ time: 1700000000, price: 155 }],
        color: '#f6465d',
        lineWidth: 2,
        createdAt: 1700000000,
        updatedAt: 1700000000,
      },
    ];

    primitive.updateData({
      drawings: mockDrawings,
      selectedDrawingId: 'tl-1',
      theme: 'dark',
    });

    assert.equal(updateRequested, true, 'updateData must trigger requestUpdate on the chart');

    const views = primitive.paneViews();
    assert.equal(views.length, 1);
    assert.equal(views[0].zOrder(), 'top', 'DrawingsPrimitive must render on top of existing formations');

    // Verify draw execution on mock canvas
    const renderer = views[0].renderer();
    assert.ok(renderer, 'Renderer must exist');

    primitive.detached();
  });

  test('5. Per-coin drawings storage isolation', () => {
    clearCoinDrawings('BTC');
    clearCoinDrawings('ETH');

    const btcDrawings: ChartDrawing[] = [
      {
        id: 'btc-1',
        type: 'trendline',
        coin: 'BTC',
        points: [
          { time: 1, price: 60000 },
          { time: 2, price: 61000 },
        ],
        createdAt: 1,
        updatedAt: 1,
      },
    ];

    const ethDrawings: ChartDrawing[] = [
      {
        id: 'eth-1',
        type: 'rectangle',
        coin: 'ETH',
        points: [
          { time: 1, price: 3000 },
          { time: 2, price: 3200 },
        ],
        createdAt: 1,
        updatedAt: 1,
      },
    ];

    saveCoinDrawings('BTC', btcDrawings);
    saveCoinDrawings('ETH', ethDrawings);

    const loadedBtc = loadCoinDrawings('BTC');
    const loadedEth = loadCoinDrawings('ETH');

    assert.equal(loadedBtc.length, 1);
    assert.equal(loadedBtc[0].id, 'btc-1');
    assert.equal(loadedEth.length, 1);
    assert.equal(loadedEth[0].id, 'eth-1');
  });

  test('6. Floating properties panel stops mousedown propagation and supports style toggling', () => {
    let updatedProps: Partial<ChartDrawing> | null = null;
    let targetDrawingId: string | undefined = undefined;

    const sampleDrawing: ChartDrawing = {
      id: 'trend-1',
      type: 'trendline',
      coin: 'ETH',
      points: [
        { time: 1700000000, price: 3000 },
        { time: 1700003600, price: 3200 },
      ],
      color: '#2962ff',
      lineWidth: 2,
      lineStyle: 0,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    let parentReceivedMouseDown = false;
    const { container } = rtlRender(
      React.createElement(
        'div',
        {
          onMouseDown: () => {
            parentReceivedMouseDown = true;
          },
        },
        React.createElement(DrawingToolbar, {
          activeTool: 'cursor',
          onSelectTool: () => {},
          selectedDrawing: sampleDrawing,
          onUpdateDrawing: (up, id) => {
            updatedProps = up;
            targetDrawingId = id;
          },
          onDeleteSelectedDrawing: () => {},
          drawingsCount: 1,
        })
      )
    );

    const panel = container.querySelector('[data-testid="drawing-properties-panel"]');
    assert.ok(panel, 'Floating properties panel must be rendered');

    // Test mousedown event stops propagation in React synthetic event tree
    rtlFireEvent.mouseDown(panel);
    assert.equal(parentReceivedMouseDown, false, 'Panel must stop mousedown propagation to prevent canvas deselection');

    // Test style toggle button
    const styleBtn = container.querySelector('[data-testid="style-toggle-btn"]');
    assert.ok(styleBtn, 'Style toggle button must exist');
    rtlFireEvent.click(styleBtn);
    assert.equal(updatedProps?.lineStyle, 2, 'Clicking style toggle from Solid (0) must switch to Dashed (2)');
    assert.equal(targetDrawingId, 'trend-1', 'Must pass target drawing id to onUpdateDrawing');
  });

  test('7. Long & Short Position measurement tools with TP & SL calculation and R:R presets', () => {
    let selectedTool: DrawingToolType = 'cursor';
    let updatedProps: Partial<ChartDrawing> | null = null;
    let targetDrawingId: string | undefined = undefined;

    // Verify Long & Short tool buttons in toolbar
    const { container: toolbarContainer } = rtlRender(
      React.createElement(DrawingToolbar, {
        activeTool: 'cursor',
        onSelectTool: (t) => {
          selectedTool = t;
        },
        drawingsCount: 0,
      })
    );

    const longBtn = toolbarContainer.querySelector('[data-testid="tool-btn-long-position"]');
    assert.ok(longBtn, 'Long Position button must be rendered in toolbar');
    rtlFireEvent.click(longBtn);
    assert.equal(selectedTool, 'long_position');

    const shortBtn = toolbarContainer.querySelector('[data-testid="tool-btn-short-position"]');
    assert.ok(shortBtn, 'Short Position button must be rendered in toolbar');
    rtlFireEvent.click(shortBtn);
    assert.equal(selectedTool, 'short_position');

    // Verify Long Position properties toolbar: R:R ratio and quick 1:3 preset
    const longDrawing: ChartDrawing = {
      id: 'long-pos-1',
      type: 'long_position',
      coin: 'ETH',
      points: [
        { time: 1700000000, price: 3000 }, // Entry
        { time: 1700003600, price: 3300 }, // TP (+300)
        { time: 1700003600, price: 2900 }, // SL (-100, gives 3:1 R:R)
      ],
      color: '#0ecb81',
      lineWidth: 2,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    const { container: posContainer } = rtlRender(
      React.createElement(DrawingToolbar, {
        activeTool: 'cursor',
        onSelectTool: () => {},
        selectedDrawing: longDrawing,
        onUpdateDrawing: (up, id) => {
          updatedProps = up;
          targetDrawingId = id;
        },
        onDeleteSelectedDrawing: () => {},
        drawingsCount: 1,
      })
    );

    const text = posContainer.textContent || '';
    assert.match(text, /LONG/i, 'Must display LONG tag');
    assert.match(text, /Р\/П:\s*1:3\.00/i, 'Must display calculated 1:3.00 R:R ratio');

    // Verify presence of numeric input fields
    const entryInput = posContainer.querySelector('[data-testid="input-entry-price"]') as HTMLInputElement;
    const tpInput = posContainer.querySelector('[data-testid="input-tp-price"]') as HTMLInputElement;
    const slInput = posContainer.querySelector('[data-testid="input-sl-price"]') as HTMLInputElement;

    assert.ok(entryInput, 'Entry price input must be present');
    assert.ok(tpInput, 'TP price input must be present');
    assert.ok(slInput, 'SL price input must be present');
    assert.equal(entryInput.value, '3000');
    assert.equal(tpInput.value, '3300');
    assert.equal(slInput.value, '2900');

    // Test typing a new TP price (e.g. 3500)
    rtlFireEvent.change(tpInput, { target: { value: '3500' } });
    assert.ok(updatedProps?.points, 'Typing in TP input must trigger onUpdateDrawing');
    assert.equal(updatedProps.points[1].price, 3500);

    // Test typing a new SL price (e.g. 2800)
    rtlFireEvent.change(slInput, { target: { value: '2800' } });
    assert.equal(updatedProps.points[2].price, 2800);

    // Click 1:2 preset button: should set TP to 3000 + (100 * 2) = 3200
    const rr2Btn = posContainer.querySelector('[data-testid="rr-ratio-2"]');
    assert.ok(rr2Btn, '1:2 R:R preset button must exist');
    rtlFireEvent.click(rr2Btn);
    assert.ok(updatedProps?.points, 'Updated points must be provided');
    assert.equal(updatedProps.points[1].price, 3200, 'TP price must be updated to 3200 for 1:2 R:R ratio');
    assert.equal(targetDrawingId, 'long-pos-1');

    // Verify DrawingsPrimitive renders Long & Short position without throwing
    const primitive = new DrawingsPrimitive();
    const mockChart = {
      timeScale: () => ({ timeToCoordinate: () => 100 }),
    };
    const mockSeries = {
      priceToCoordinate: () => 150,
    };
    primitive.attached({
      chart: mockChart as any,
      series: mockSeries as any,
      requestUpdate: () => {},
    });

    primitive.updateData({
      drawings: [longDrawing],
      selectedDrawingId: 'long-pos-1',
      theme: 'dark',
    });

    const views = primitive.paneViews();
    assert.equal(views.length, 1);
    primitive.detached();
  });

  test('8. Stretching position into the future beyond candles and calculating future coordinates', () => {
    const primitive = new DrawingsPrimitive();
    let logicalCalculated = -1;

    const mockCandles: any[] = [
      { time: 1000, open: 100, high: 110, low: 90, close: 105 },
      { time: 1060, open: 105, high: 115, low: 100, close: 112 },
    ];

    const mockChart = {
      timeScale: () => ({
        timeToCoordinate: (t: number) => (t <= 1060 ? 100 : null), // future times return null in lightweight-charts
        logicalToCoordinate: (logical: number) => {
          logicalCalculated = logical;
          return 100 + (logical - 1) * 20; // 20px per bar
        },
      }),
    };
    const mockSeries = {
      priceToCoordinate: (p: number) => p * 2,
    };

    primitive.attached({
      chart: mockChart as any,
      series: mockSeries as any,
      requestUpdate: () => {},
    });

    // Position extending 10 bars (600s) into the future
    const futureDrawing: ChartDrawing = {
      id: 'pos-future-1',
      type: 'long_position',
      coin: 'ETH',
      points: [
        { time: 1060, price: 105 },
        { time: 1660, price: 120 }, // 10 bars in the future!
        { time: 1660, price: 95 },
      ],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    primitive.updateData({
      drawings: [futureDrawing],
      selectedDrawingId: 'pos-future-1',
      candles: mockCandles,
    });

    const views = primitive.paneViews();
    assert.equal(views.length, 1);
    const mockCtx = {
      save: () => {},
      restore: () => {},
      beginPath: () => {},
      stroke: () => {},
      fill: () => {},
      rect: () => {},
      fillRect: () => {},
      strokeRect: () => {},
      moveTo: () => {},
      lineTo: () => {},
      arc: () => {},
      measureText: () => ({ width: 40 }),
      fillText: () => {},
      setLineDash: () => {},
    };
    views[0].renderer().draw({
      useMediaCoordinateSpace: (cb: any) => cb({ context: mockCtx, mediaSize: { width: 800, height: 600 } }),
    });

    assert.ok(logicalCalculated > 1, 'Must compute future logical index for future timestamps');
    primitive.detached();
  });
});
