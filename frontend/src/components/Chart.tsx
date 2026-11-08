import React, { useState, useEffect, useRef, useCallback } from 'react';
import { createChart, IChartApi, ISeriesApi, LineStyle, SeriesMarker, CrosshairMode } from 'lightweight-charts';
import {
  Candle,
  LevelItem,
  FVGItem,
  SignalItem,
  FormationFilter,
  AnalysisData,
  DrawingToolType,
  ChartDrawing,
  ChartDrawingPoint,
  getAssetPricePrecision,
} from '../types';
import { ZonesPrimitive } from './ZonesPrimitive';
import { DrawingsPrimitive } from './DrawingsPrimitive';
import { DrawingToolbar } from './DrawingToolbar';
import { loadCoinDrawings, saveCoinDrawings } from '../utils/storage';
import { useTheme } from '../context/ThemeContext';

function distanceToSegment(px: number, py: number, x1: number, y1: number, x2: number, y2: number): number {
  const l2 = (x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1);
  if (l2 === 0) return Math.hypot(px - x1, py - y1);
  let t = ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (x1 + t * (x2 - x1)), py - (y1 + t * (y2 - y1)));
}

function findDrawingAtCoords(
  chart: IChartApi | null,
  series: ISeriesApi<'Candlestick'> | null,
  pixelX: number,
  pixelY: number,
  allDrawings: ChartDrawing[]
): { drawing: ChartDrawing; handleIndex?: number } | null {
  if (!chart || !series) return null;
  const timeScale = chart.timeScale();

  for (let i = allDrawings.length - 1; i >= 0; i--) {
    const d = allDrawings[i];
    const coords = (d.points || []).map((p) => {
      const x = (timeScale as any).timeToCoordinate ? (timeScale as any).timeToCoordinate(p.time as any) : null;
      const y = (series as any).priceToCoordinate ? (series as any).priceToCoordinate(p.price) : null;
      return { x, y };
    });

    // Check handles first
    for (let hi = 0; hi < coords.length; hi++) {
      const cp = coords[hi];
      if (cp.x !== null && cp.y !== null) {
        if (Math.hypot(pixelX - cp.x, pixelY - cp.y) <= 10) {
          return { drawing: d, handleIndex: hi };
        }
      }
    }

    // Check drawing body
    if (d.type === 'horizontal') {
      const cp = coords[0];
      if (cp && cp.y !== null && Math.abs(pixelY - cp.y) <= 8) {
        return { drawing: d };
      }
    } else if (d.type === 'horizontal_ray') {
      const cp = coords[0];
      if (cp && cp.x !== null && cp.y !== null && pixelX >= cp.x - 8 && Math.abs(pixelY - cp.y) <= 8) {
        return { drawing: d };
      }
    } else if (d.type === 'trendline' || d.type === 'ruler') {
      if (coords.length >= 2 && coords[0].x !== null && coords[0].y !== null && coords[1].x !== null && coords[1].y !== null) {
        const dist = distanceToSegment(pixelX, pixelY, coords[0].x, coords[0].y, coords[1].x, coords[1].y);
        if (dist <= 8) {
          return { drawing: d };
        }
      }
    } else if (d.type === 'ray') {
      if (coords.length >= 2 && coords[0].x !== null && coords[0].y !== null && coords[1].x !== null && coords[1].y !== null) {
        const dx = coords[1].x - coords[0].x;
        const dy = coords[1].y - coords[0].y;
        const extX = coords[0].x + dx * 100;
        const extY = coords[0].y + dy * 100;
        const dist = distanceToSegment(pixelX, pixelY, coords[0].x, coords[0].y, extX, extY);
        if (dist <= 8) {
          return { drawing: d };
        }
      }
    } else if (d.type === 'rectangle') {
      if (coords.length >= 2 && coords[0].x !== null && coords[0].y !== null && coords[1].x !== null && coords[1].y !== null) {
        const minX = Math.min(coords[0].x, coords[1].x) - 6;
        const maxX = Math.max(coords[0].x, coords[1].x) + 6;
        const minY = Math.min(coords[0].y, coords[1].y) - 6;
        const maxY = Math.max(coords[0].y, coords[1].y) + 6;
        if (pixelX >= minX && pixelX <= maxX && pixelY >= minY && pixelY <= maxY) {
          return { drawing: d };
        }
      }
    } else if (d.type === 'fibonacci') {
      if (coords.length >= 2 && coords[0].x !== null && coords[0].y !== null && coords[1].x !== null && coords[1].y !== null) {
        const minY = Math.min(coords[0].y, coords[1].y) - 6;
        const maxY = Math.max(coords[0].y, coords[1].y) + 6;
        const minX = Math.min(coords[0].x, coords[1].x) - 10;
        if (pixelX >= minX && pixelY >= minY && pixelY <= maxY) {
          return { drawing: d };
        }
      }
    } else if (d.type === 'text') {
      if (coords[0] && coords[0].x !== null && coords[0].y !== null) {
        if (Math.hypot(pixelX - coords[0].x, pixelY - coords[0].y) <= 30) {
          return { drawing: d };
        }
      }
    } else if (d.type === 'brush') {
      if (coords.length >= 2) {
        for (let j = 0; j < coords.length - 1; j++) {
          const p1 = coords[j];
          const p2 = coords[j + 1];
          if (p1.x !== null && p1.y !== null && p2.x !== null && p2.y !== null) {
            if (distanceToSegment(pixelX, pixelY, p1.x, p1.y, p2.x, p2.y) <= 10) {
              return { drawing: d };
            }
          }
        }
      }
    }
  }

  return null;
}

interface ChartProps {
  candles: Candle[];
  resistances: LevelItem[];
  supports: LevelItem[];
  fvgs: FVGItem[];
  signals: SignalItem[];
  liquidity?: AnalysisData['liquidity'];
  activeFormation: FormationFilter;
  coin: string;
  interval?: string;
  targetTimestamp?: number | null;
  navigationToken?: number | null;
  onLoadEarlier?: () => void;
  isLoadingEarlier?: boolean;
  isLiveTick?: boolean;
}

export const Chart: React.FC<ChartProps> = ({
  candles,
  resistances,
  supports,
  fvgs,
  signals,
  liquidity,
  activeFormation,
  coin,
  interval,
  targetTimestamp,
  navigationToken,
  onLoadEarlier,
  isLoadingEarlier = false,
  isLiveTick = false,
}) => {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const zonesPrimitiveRef = useRef<ZonesPrimitive | null>(null);
  const drawingsPrimitiveRef = useRef<DrawingsPrimitive | null>(null);
  const priceLinesRef = useRef<any[]>([]);

  // TradingView Drawing Tools State
  const [activeTool, setActiveTool] = useState<DrawingToolType>('cursor');
  const [drawings, setDrawings] = useState<ChartDrawing[]>(() => loadCoinDrawings(coin));
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const [activeDrawing, setActiveDrawing] = useState<ChartDrawing | null>(null);
  const isDraggingHandleRef = useRef<{ drawingId: string; pointIndex: number } | null>(null);

  const activeToolRef = useRef(activeTool);
  activeToolRef.current = activeTool;
  const drawingsRef = useRef(drawings);
  drawingsRef.current = drawings;
  const activeDrawingRef = useRef(activeDrawing);
  activeDrawingRef.current = activeDrawing;

  // Sync drawings per-coin
  useEffect(() => {
    const loaded = loadCoinDrawings(coin);
    setDrawings(loaded);
    setSelectedDrawingId(null);
    setActiveDrawing(null);
  }, [coin]);

  // Sync drawings with the DrawingsPrimitive renderer
  useEffect(() => {
    if (drawingsPrimitiveRef.current) {
      drawingsPrimitiveRef.current.updateData({
        drawings,
        activeDrawing,
        selectedDrawingId,
        theme: isDark ? 'dark' : 'light',
      });
    }
  }, [drawings, activeDrawing, selectedDrawingId, isDark]);

  const onLoadEarlierRef = useRef(onLoadEarlier);
  onLoadEarlierRef.current = onLoadEarlier;
  const isLoadingEarlierRef = useRef(isLoadingEarlier);
  isLoadingEarlierRef.current = isLoadingEarlier;

  const prevContextRef = useRef<{ coin: string; interval: string }>({ coin: '', interval: '' });
  const prevNavTokenRef = useRef<number | null>(null);
  const currentPrecisionRef = useRef<{ precision: number; minMove: number }>({ precision: 2, minMove: 0.01 });
  // Track user interaction (drag / scroll) so pagination only triggers on deliberate scrolling into the past
  const userHasScrolledHistoryRef = useRef<boolean>(false);

  // Keyboard navigation & deletion listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setActiveTool('cursor');
        setActiveDrawing(null);
        setSelectedDrawingId(null);
        chartRef.current?.applyOptions({ handleScroll: true, handleScale: true });
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (selectedDrawingId) {
          const updated = drawingsRef.current.filter((d) => d.id !== selectedDrawingId);
          setDrawings(updated);
          saveCoinDrawings(coin, updated);
          setSelectedDrawingId(null);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedDrawingId, coin]);

  const getPointFromMouseEvent = useCallback(
    (e: React.MouseEvent<HTMLDivElement> | MouseEvent): ChartDrawingPoint | null => {
      if (!chartRef.current || !candleSeriesRef.current || !chartContainerRef.current) return null;
      const rect = chartContainerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const timeScale = chartRef.current.timeScale();
      const rawTime = (timeScale as any).coordinateToTime ? (timeScale as any).coordinateToTime(x) : null;
      const price = (candleSeriesRef.current as any).coordinateToPrice
        ? (candleSeriesRef.current as any).coordinateToPrice(y)
        : null;

      if (price === null || isNaN(price)) return null;

      let resolvedTime: number | null = null;
      if (rawTime !== null && !isNaN(Number(rawTime))) {
        resolvedTime = Number(rawTime);
      } else if ((timeScale as any).coordinateToLogical) {
        const logical = (timeScale as any).coordinateToLogical(x);
        if (logical !== null && candles && candles.length > 0) {
          const idx = Math.round(logical);
          if (idx >= 0 && idx < candles.length) {
            resolvedTime = candles[idx].time;
          } else if (idx >= candles.length) {
            const last = candles[candles.length - 1];
            const prev = candles[Math.max(0, candles.length - 2)];
            const dt = last.time - prev.time || 60;
            resolvedTime = last.time + (idx - (candles.length - 1)) * dt;
          } else {
            const first = candles[0];
            const next = candles[1] || first;
            const dt = next.time - first.time || 60;
            resolvedTime = first.time + idx * dt;
          }
        }
      }

      if (resolvedTime === null) {
        resolvedTime = candles.length > 0 ? candles[candles.length - 1].time : Math.floor(Date.now() / 1000);
      }

      return { time: resolvedTime, price };
    },
    [candles]
  );

  const handleSelectTool = useCallback((tool: DrawingToolType) => {
    setActiveTool(tool);
    if (tool !== 'cursor') {
      setSelectedDrawingId(null);
      chartRef.current?.applyOptions({ handleScroll: false, handleScale: false });
    } else {
      chartRef.current?.applyOptions({ handleScroll: true, handleScale: true });
    }
  }, []);

  const handleContainerMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      // Double safety: ignore clicks inside the drawing toolbars to prevent deselecting active drawings
      const target = e.target as HTMLElement | null;
      if (target && target.closest('[data-toolbar="drawing"]')) {
        return;
      }

      if (!chartRef.current || !candleSeriesRef.current || !chartContainerRef.current) return;
      const rect = chartContainerRef.current.getBoundingClientRect();
      const pixelX = e.clientX - rect.left;
      const pixelY = e.clientY - rect.top;

      if (activeToolRef.current === 'cursor') {
        const hit = findDrawingAtCoords(chartRef.current, candleSeriesRef.current, pixelX, pixelY, drawingsRef.current);
        if (hit) {
          setSelectedDrawingId(hit.drawing.id);
          if (hit.handleIndex !== undefined) {
            isDraggingHandleRef.current = { drawingId: hit.drawing.id, pointIndex: hit.handleIndex };
            chartRef.current.applyOptions({ handleScroll: false, handleScale: false });
          }
        } else {
          setSelectedDrawingId(null);
        }
        return;
      }

      // Drawing mode:
      const pt = getPointFromMouseEvent(e);
      if (!pt) return;

      const tool = activeToolRef.current;
      const now = Date.now();

      if (tool === 'horizontal') {
        const newDrawing: ChartDrawing = {
          id: `draw-${now}`,
          type: 'horizontal',
          coin: coin.toUpperCase(),
          timeframe: interval,
          points: [pt],
          color: '#2962ff',
          lineWidth: 2,
          createdAt: now,
          updatedAt: now,
        };
        const updated = [...drawingsRef.current, newDrawing];
        setDrawings(updated);
        saveCoinDrawings(coin, updated);
        setSelectedDrawingId(newDrawing.id);
        setActiveTool('cursor');
        chartRef.current.applyOptions({ handleScroll: true, handleScale: true });
        return;
      }

      if (tool === 'horizontal_ray') {
        const newDrawing: ChartDrawing = {
          id: `draw-${now}`,
          type: 'horizontal_ray',
          coin: coin.toUpperCase(),
          timeframe: interval,
          points: [pt],
          color: '#2962ff',
          lineWidth: 2,
          createdAt: now,
          updatedAt: now,
        };
        const updated = [...drawingsRef.current, newDrawing];
        setDrawings(updated);
        saveCoinDrawings(coin, updated);
        setSelectedDrawingId(newDrawing.id);
        setActiveTool('cursor');
        chartRef.current.applyOptions({ handleScroll: true, handleScale: true });
        return;
      }

      if (tool === 'text') {
        const textContent = window.prompt('Введіть текст примітки:', 'Зона інтересу') || 'Нотатка';
        const newDrawing: ChartDrawing = {
          id: `draw-${now}`,
          type: 'text',
          coin: coin.toUpperCase(),
          timeframe: interval,
          points: [pt],
          text: textContent,
          color: '#2962ff',
          lineWidth: 2,
          createdAt: now,
          updatedAt: now,
        };
        const updated = [...drawingsRef.current, newDrawing];
        setDrawings(updated);
        saveCoinDrawings(coin, updated);
        setSelectedDrawingId(newDrawing.id);
        setActiveTool('cursor');
        chartRef.current.applyOptions({ handleScroll: true, handleScale: true });
        return;
      }

      if (tool === 'brush') {
        const newDrawing: ChartDrawing = {
          id: `draw-${now}`,
          type: 'brush',
          coin: coin.toUpperCase(),
          timeframe: interval,
          points: [pt],
          color: '#2962ff',
          lineWidth: 2,
          createdAt: now,
          updatedAt: now,
        };
        setActiveDrawing(newDrawing);
        return;
      }

      // 2-point tools (trendline, ray, rectangle, fibonacci, ruler)
      const newDrawing: ChartDrawing = {
        id: `draw-${now}`,
        type: tool,
        coin: coin.toUpperCase(),
        timeframe: interval,
        points: [pt, pt],
        color: tool === 'ruler' ? '#0ecb81' : '#2962ff',
        lineWidth: 2,
        createdAt: now,
        updatedAt: now,
      };
      setActiveDrawing(newDrawing);
    },
    [coin, interval, getPointFromMouseEvent]
  );

  const handleContainerMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (isDraggingHandleRef.current) {
        const pt = getPointFromMouseEvent(e);
        if (!pt) return;
        const { drawingId, pointIndex } = isDraggingHandleRef.current;
        const updated = drawingsRef.current.map((d) => {
          if (d.id !== drawingId) return d;
          const nextPoints = [...d.points];
          nextPoints[pointIndex] = pt;
          return { ...d, points: nextPoints, updatedAt: Date.now() };
        });
        setDrawings(updated);
        if (drawingsPrimitiveRef.current) {
          drawingsPrimitiveRef.current.updateData({ drawings: updated });
        }
        return;
      }

      if (activeDrawingRef.current) {
        const pt = getPointFromMouseEvent(e);
        if (!pt) return;
        const cur = activeDrawingRef.current;

        if (cur.type === 'brush') {
          const nextPoints = [...cur.points, pt];
          const updated = { ...cur, points: nextPoints };
          setActiveDrawing(updated);
          if (drawingsPrimitiveRef.current) {
            drawingsPrimitiveRef.current.updateData({ activeDrawing: updated });
          }
        } else {
          // 2-point tool: update point 2
          const nextPoints = [cur.points[0], pt];
          const updated = { ...cur, points: nextPoints };
          setActiveDrawing(updated);
          if (drawingsPrimitiveRef.current) {
            drawingsPrimitiveRef.current.updateData({ activeDrawing: updated });
          }
        }
      }
    },
    [getPointFromMouseEvent]
  );

  const handleContainerMouseUp = useCallback(() => {
    if (isDraggingHandleRef.current) {
      saveCoinDrawings(coin, drawingsRef.current);
      isDraggingHandleRef.current = null;
      chartRef.current?.applyOptions({ handleScroll: true, handleScale: true });
      return;
    }

    if (activeDrawingRef.current) {
      const cur = activeDrawingRef.current;
      const updated = [...drawingsRef.current, cur];
      setDrawings(updated);
      saveCoinDrawings(coin, updated);
      setSelectedDrawingId(cur.id);
      setActiveDrawing(null);
      setActiveTool('cursor');
      chartRef.current?.applyOptions({ handleScroll: true, handleScale: true });
    }
  }, [coin]);

  const handleUpdateSelectedDrawing = useCallback(
    (props: Partial<ChartDrawing>, targetId?: string) => {
      const idToUpdate = targetId || selectedDrawingId;
      if (!idToUpdate) return;
      const updated = drawingsRef.current.map((d) =>
        d.id === idToUpdate ? { ...d, ...props, updatedAt: Date.now() } : d
      );
      setDrawings(updated);
      saveCoinDrawings(coin, updated);
      if (drawingsPrimitiveRef.current) {
        drawingsPrimitiveRef.current.updateData({ drawings: updated });
      }
    },
    [selectedDrawingId, coin]
  );

  const handleDeleteSelectedDrawing = useCallback(
    (targetId?: string) => {
      const idToDelete = targetId || selectedDrawingId;
      if (!idToDelete) return;
      const updated = drawingsRef.current.filter((d) => d.id !== idToDelete);
      setDrawings(updated);
      saveCoinDrawings(coin, updated);
      setSelectedDrawingId(null);
      if (drawingsPrimitiveRef.current) {
        drawingsPrimitiveRef.current.updateData({ drawings: updated, selectedDrawingId: null });
      }
    },
    [selectedDrawingId, coin]
  );

  const handleClearAllDrawings = useCallback(() => {
    setDrawings([]);
    saveCoinDrawings(coin, []);
    setSelectedDrawingId(null);
    setActiveDrawing(null);
  }, [coin]);

  // 1. Initialize Chart & Attach ZonesPrimitive directly to Candle Series
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const initialPrecision = getAssetPricePrecision(candles);
    currentPrecisionRef.current = initialPrecision;

    const chart = createChart(chartContainerRef.current, {
      autoSize: true,
      layout: {
        background: { color: isDark ? '#0b0e11' : '#ffffff' },
        textColor: isDark ? '#848e9c' : '#475569',
        fontSize: 11,
        fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      },
      grid: {
        vertLines: { color: isDark ? 'rgba(30, 35, 41, 0.25)' : 'rgba(226, 232, 240, 0.8)' },
        horzLines: { color: isDark ? 'rgba(30, 35, 41, 0.25)' : 'rgba(226, 232, 240, 0.8)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: isDark ? '#474d57' : '#94a3b8',
          width: 1,
          style: LineStyle.Dashed,
          labelVisible: true,
        },
        horzLine: {
          color: isDark ? '#474d57' : '#94a3b8',
          width: 1,
          style: LineStyle.Dashed,
          labelVisible: true,
        },
      },
      timeScale: {
        borderColor: isDark ? '#1e2329' : '#e2e8f0',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 12,
        shiftVisibleRangeOnNewBar: true,
      },
      rightPriceScale: {
        borderColor: isDark ? '#1e2329' : '#e2e8f0',
        scaleMargins: {
          top: 0.12,
          bottom: 0.15,
        },
      },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#0ecb81',
      downColor: '#f6465d',
      borderVisible: false,
      wickUpColor: '#0ecb81',
      wickDownColor: '#f6465d',
      priceFormat: {
        type: 'price',
        precision: initialPrecision.precision,
        minMove: initialPrecision.minMove,
      },
    });

    const zonesPrimitive = new ZonesPrimitive();
    candleSeries.attachPrimitive(zonesPrimitive as any);

    const drawingsPrimitive = new DrawingsPrimitive();
    candleSeries.attachPrimitive(drawingsPrimitive as any);

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    zonesPrimitiveRef.current = zonesPrimitive;
    drawingsPrimitiveRef.current = drawingsPrimitive;

    // Subscribe to visible range changes for lazy pagination when scrolling left
    const handleLogicalRangeChange = (newRange: any) => {
      if (!newRange || !candleSeriesRef.current || !onLoadEarlierRef.current) return;
      if (isLoadingEarlierRef.current) return;

      const barsInfo = candleSeriesRef.current.barsInLogicalRange(newRange);
      // Trigger pagination only when user explicitly scrolled back towards older history
      if (barsInfo && barsInfo.barsAfter > 30) {
        userHasScrolledHistoryRef.current = true;
      }

      if (userHasScrolledHistoryRef.current && barsInfo && barsInfo.barsBefore < 40) {
        onLoadEarlierRef.current();
      }
    };

    chart.timeScale().subscribeVisibleLogicalRangeChange(handleLogicalRangeChange);

    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleLogicalRangeChange);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      zonesPrimitiveRef.current = null;
      drawingsPrimitiveRef.current = null;
      lastSetDataSeriesRef.current = null;
      initializedRef.current = false;
      prevContextRef.current = { coin: '', interval: '' };
      prevNavTokenRef.current = null;
      prevCandlesLenRef.current = 0;
      prevFirstCandleTimeRef.current = 0;
      prevLastCandleTimeRef.current = 0;
      userHasScrolledHistoryRef.current = false;
      priceLinesRef.current = [];
    };
  }, []);

  // Update chart layout theme dynamically
  useEffect(() => {
    if (!chartRef.current) return;
    chartRef.current.applyOptions({
      layout: {
        background: { color: isDark ? '#0b0e11' : '#ffffff' },
        textColor: isDark ? '#848e9c' : '#475569',
      },
      grid: {
        vertLines: { color: isDark ? 'rgba(30, 35, 41, 0.25)' : 'rgba(226, 232, 240, 0.8)' },
        horzLines: { color: isDark ? 'rgba(30, 35, 41, 0.25)' : 'rgba(226, 232, 240, 0.8)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: isDark ? '#474d57' : '#94a3b8',
          labelVisible: true,
        },
        horzLine: {
          color: isDark ? '#474d57' : '#94a3b8',
          labelVisible: true,
        },
      },
      timeScale: {
        borderColor: isDark ? '#1e2329' : '#e2e8f0',
      },
      rightPriceScale: {
        borderColor: isDark ? '#1e2329' : '#e2e8f0',
      },
    });
  }, [isDark]);

  const lastSetDataSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const prevCandlesLenRef = useRef<number>(0);
  const prevFirstCandleTimeRef = useRef<number>(0);
  const prevLastCandleTimeRef = useRef<number>(0);
  const initializedRef = useRef<boolean>(false);

  // 2. Update Candles Data & preserve user scroll/zoom position!
  useEffect(() => {
    if (!candleSeriesRef.current || !chartRef.current || !candles || candles.length === 0) return;

    const isSeriesChanged = lastSetDataSeriesRef.current !== candleSeriesRef.current;
    const isContextChanged =
      prevContextRef.current.coin.toUpperCase() !== coin.toUpperCase() ||
      prevContextRef.current.interval.toLowerCase() !== (interval || '').toLowerCase();
    const isNewNavigation =
      navigationToken != null && navigationToken !== prevNavTokenRef.current;

    // Deduplicate and strictly sort ascending to prevent assertion error in lightweight-charts
    const uniqueMap = new Map<number, Candle>();
    for (const c of candles) {
      const rawTime = Number(c.time);
      if (!isNaN(rawTime) && rawTime > 0) {
        const timeSec = rawTime > 1e11 ? Math.floor(rawTime / 1000) : rawTime;
        uniqueMap.set(timeSec, { ...c, time: timeSec });
      }
    }
    const sanitizedCandles = Array.from(uniqueMap.values()).sort((a, b) => Number(a.time) - Number(b.time));

    const mappedCandles = sanitizedCandles.map((c) => ({
      time: c.time as any,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    if (mappedCandles.length === 0) return;

    // Ensure series price precision matches the coin magnitude and candle decimals
    const priceFormatOpts = getAssetPricePrecision(mappedCandles);
    if (
      isSeriesChanged ||
      priceFormatOpts.precision !== currentPrecisionRef.current.precision ||
      priceFormatOpts.minMove !== currentPrecisionRef.current.minMove
    ) {
      currentPrecisionRef.current = priceFormatOpts;
      candleSeriesRef.current.applyOptions({
        priceFormat: {
          type: 'price',
          precision: priceFormatOpts.precision,
          minMove: priceFormatOpts.minMove,
        },
      });
    }

    const firstCandleTime = Number(mappedCandles[0].time);
    const lastCandleTime = Number(mappedCandles[mappedCandles.length - 1].time);

    const isPrependedEarlier =
      !isSeriesChanged &&
      initializedRef.current &&
      !isContextChanged &&
      !isNewNavigation &&
      prevFirstCandleTimeRef.current !== 0 &&
      firstCandleTime < prevFirstCandleTimeRef.current;

    if (isPrependedEarlier) {
      // User scrolled left into history: save logical range, update data, restore offset so candle under cursor stays still
      const currentRange = chartRef.current.timeScale().getVisibleLogicalRange();
      const addedBars = mappedCandles.length - prevCandlesLenRef.current;

      try {
        candleSeriesRef.current.setData(mappedCandles);
        lastSetDataSeriesRef.current = candleSeriesRef.current;
      } catch (err) {
        console.warn('Safely caught setData error during pagination:', err);
      }

      if (currentRange && addedBars > 0) {
        chartRef.current.timeScale().setVisibleLogicalRange({
          from: currentRange.from + addedBars,
          to: currentRange.to + addedBars,
        });
      }
    } else if (isSeriesChanged || isContextChanged || isNewNavigation || !initializedRef.current) {
      // First load, fresh chart series, new coin / timeframe, OR explicit alert navigation:
      try {
        candleSeriesRef.current.setData(mappedCandles);
        lastSetDataSeriesRef.current = candleSeriesRef.current;
      } catch (err) {
        console.error('Error setting candle data:', err);
      }
      initializedRef.current = true;
      userHasScrolledHistoryRef.current = false;
      if (isNewNavigation) {
        prevNavTokenRef.current = navigationToken;
      }

      const totalBars = mappedCandles.length;
      let fromIndex = Math.max(0, totalBars - 100);
      let toIndex = totalBars + 12;

      // Position relative to targetTimestamp if specified
      if (targetTimestamp && totalBars > 0) {
        const targetSec = targetTimestamp > 1e11 ? Math.floor(targetTimestamp / 1000) : targetTimestamp;
        let targetIdx = -1;
        let minDiff = Infinity;

        for (let i = 0; i < mappedCandles.length; i++) {
          const cTime = Number(mappedCandles[i].time);
          const diff = Math.abs(cTime - targetSec);
          if (diff < minDiff) {
            minDiff = diff;
            targetIdx = i;
          }
        }

        if (targetIdx !== -1) {
          // Provide ~30 bars of historical context before the alert signal
          const contextBefore = Math.min(30, targetIdx);
          fromIndex = Math.max(0, targetIdx - contextBefore);
          
          // Ensure current live candle and right offset margin are displayed
          toIndex = totalBars + 12;

          // Prevent extreme zoom out if alert is exceptionally distant (>350 bars)
          if (toIndex - fromIndex > 350) {
            toIndex = Math.min(totalBars + 12, targetIdx + 120);
          }
        }
      }

      chartRef.current.timeScale().setVisibleLogicalRange({
        from: fromIndex,
        to: toIndex,
      });

      // Re-affirm range on next animation frame in case container layout was settling
      requestAnimationFrame(() => {
        if (chartRef.current && !userHasScrolledHistoryRef.current) {
          chartRef.current.timeScale().setVisibleLogicalRange({
            from: fromIndex,
            to: toIndex,
          });
        }
      });

      prevContextRef.current = { coin: coin.toUpperCase(), interval: (interval || '').toLowerCase() };
    } else if (isLiveTick) {
      // Real-time live tick from WebSocket for the currently active coin & timeframe:
      // Update or append the latest candle with zero re-rendering overhead
      const lastCandle = mappedCandles[mappedCandles.length - 1];
      if (lastCandle) {
        try {
          candleSeriesRef.current.update(lastCandle);
        } catch (err) {
          candleSeriesRef.current.setData(mappedCandles);
          lastSetDataSeriesRef.current = candleSeriesRef.current;
        }
      }
    } else {
      // Full historical dataset replacement / reload for the SAME coin/timeframe:
      // (fast-path -> full analysis, manual refresh, 60s background sync, reconnect recovery)
      // Call setData() to update the complete history in place, WITHOUT jumping the camera viewport!
      try {
        candleSeriesRef.current.setData(mappedCandles);
        lastSetDataSeriesRef.current = candleSeriesRef.current;
      } catch (err) {
        console.warn('Safely caught periodic setData error:', err);
      }
    }

    prevCandlesLenRef.current = mappedCandles.length;
    prevFirstCandleTimeRef.current = firstCandleTime;
    prevLastCandleTimeRef.current = lastCandleTime;
  }, [candles, coin, interval, targetTimestamp, navigationToken]);

  // 3. Update Primitive Data (Zones & Drawings)
  useEffect(() => {
    if (!zonesPrimitiveRef.current) return;

    zonesPrimitiveRef.current.updateData({
      resistances,
      supports,
      fvgs,
      trendlines: liquidity?.trendlines || [],
      sweeps: liquidity?.sweeps || [],
      regressionChannel: liquidity?.regressionChannel || (liquidity as any)?.regression_channel || null,
      activeFormation,
      theme: isDark ? 'dark' : 'light',
      currentTimeframe: interval,
    });
  }, [resistances, supports, fvgs, liquidity, activeFormation, isDark, interval]);

  // 4. Update Candlestick Markers (Unified style, no middle lines)
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    // Clean any old price lines
    priceLinesRef.current.forEach((line) => {
      try {
        candleSeriesRef.current?.removePriceLine(line);
      } catch (e) { }
    });
    priceLinesRef.current = [];

    // Clean candlestick markers
    const rawMarkers: SeriesMarker<any>[] = [];

    // SWEEP / FALSE BREAKOUT markers
    if (activeFormation === 'SWEEP' && liquidity?.sweeps) {
      liquidity.sweeps.forEach((sw) => {
        // Confirmation marker
        const confirmTime = sw.confirmationTime || sw.time;
        rawMarkers.push({
          time: confirmTime as any,
          position: sw.direction === 'SHORT' ? 'aboveBar' : 'belowBar',
          color: sw.direction === 'SHORT' ? '#f6465d' : '#0ecb81',
          shape: sw.direction === 'SHORT' ? 'arrowDown' : 'arrowUp',
          text: sw.subType === 'two_candle_reversal' ? 'FB 2C' : 'FB',
        });
      });
    }

    // CASCADE markers
    if (activeFormation === 'CASCADE') {
      signals.forEach((sig) => {
        if (sig.category === 'cascade') {
          rawMarkers.push({
            time: sig.time as any,
            position: sig.direction === 'SHORT' ? 'aboveBar' : 'belowBar',
            color: sig.direction === 'SHORT' ? '#f6465d' : '#0ecb81',
            shape: sig.direction === 'SHORT' ? 'arrowDown' : 'arrowUp',
            text: '',
          });
        }
      });
    }

    rawMarkers.sort((a, b) => Number(a.time) - Number(b.time));

    const sortedMarkers: SeriesMarker<any>[] = [];
    const seenTimes = new Set<number>();
    for (const m of rawMarkers) {
      const t = Number(m.time);
      if (!seenTimes.has(t)) {
        seenTimes.add(t);
        sortedMarkers.push(m);
      }
    }

    try {
      candleSeriesRef.current.setMarkers(sortedMarkers);
    } catch (err) {
      console.warn('Safely caught setMarkers error:', err);
    }
  }, [resistances, supports, signals, liquidity, activeFormation]);

  return (
    <div
      className="relative w-full h-full flex flex-col bg-[#0b0e11] dark:bg-[#0b0e11] bg-white overflow-hidden transition-colors"
      onMouseDown={handleContainerMouseDown}
      onMouseMove={handleContainerMouseMove}
      onMouseUp={handleContainerMouseUp}
    >
      {/* TradingView Left Drawing Toolbar */}
      <DrawingToolbar
        activeTool={activeTool}
        onSelectTool={handleSelectTool}
        selectedDrawing={drawings.find((d) => d.id === selectedDrawingId) || null}
        onUpdateDrawing={handleUpdateSelectedDrawing}
        onDeleteSelectedDrawing={handleDeleteSelectedDrawing}
        onClearAllDrawings={handleClearAllDrawings}
        drawingsCount={drawings.length}
      />

      <div
        ref={chartContainerRef}
        className={`w-full flex-1 min-h-0 min-w-0 ${activeTool !== 'cursor' ? 'cursor-crosshair' : ''}`}
      />

      {/* Top indicator for loading earlier history */}
      {isLoadingEarlier && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-2 bg-white/90 dark:bg-[#15191e]/90 backdrop-blur border border-slate-200 dark:border-[#2b313a] text-slate-700 dark:text-gray-300 text-xs px-3 py-1.5 rounded-full shadow-lg z-30 transition-all pointer-events-none">
          <div className="w-3.5 h-3.5 border-2 border-emerald-500 dark:border-emerald-400 border-t-transparent rounded-full animate-spin" />
          <span>Довантаження історії...</span>
        </div>
      )}

      <div className="absolute bottom-2 left-3 flex items-center gap-1.5 opacity-60 text-xs font-mono select-none pointer-events-none z-20">
        <span className="bg-slate-200 dark:bg-[#1e2329] px-1.5 py-0.5 rounded text-[10px] text-slate-600 dark:text-gray-400 font-bold">17</span>
        <span className="text-slate-500 dark:text-gray-500 text-[11px]">TradingView Lightweight Engine · Hyperliquid</span>
      </div>
    </div>
  );
};
