import React, { useEffect, useRef } from 'react';
import { createChart, IChartApi, ISeriesApi, LineStyle, SeriesMarker } from 'lightweight-charts';
import { Candle, LevelItem, FVGItem, SignalItem, FormationFilter, AnalysisData } from '../types';
import { ZonesPrimitive } from './ZonesPrimitive';

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
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const zonesPrimitiveRef = useRef<ZonesPrimitive | null>(null);
  const priceLinesRef = useRef<any[]>([]);

  const prevContextRef = useRef<{ coin: string; interval: string }>({ coin: '', interval: '' });

  // 1. Initialize Chart & Attach ZonesPrimitive directly to Candle Series
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#0b0e11' },
        textColor: '#848e9c',
        fontSize: 11,
        fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      },
      grid: {
        vertLines: { color: 'rgba(30, 35, 41, 0.25)' },
        horzLines: { color: 'rgba(30, 35, 41, 0.25)' },
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: '#474d57',
          width: 1,
          style: LineStyle.Dashed,
        },
        horzLine: {
          color: '#474d57',
          width: 1,
          style: LineStyle.Dashed,
        },
      },
      timeScale: {
        borderColor: '#1e2329',
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: '#1e2329',
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
    });

    const zonesPrimitive = new ZonesPrimitive();
    candleSeries.attachPrimitive(zonesPrimitive as any);

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    zonesPrimitiveRef.current = zonesPrimitive;

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  const prevCandlesLenRef = useRef<number>(0);
  // True after the first successful setData() for the current context.
  // Reset to false whenever coin/interval changes so a fresh setData() is always called first.
  const initializedRef = useRef<boolean>(false);

  // 2. Update Candles Data & preserve user scroll/zoom position!
  useEffect(() => {
    if (!candleSeriesRef.current || !chartRef.current || candles.length === 0) return;

    const isContextChanged =
      prevContextRef.current.coin !== coin ||
      prevContextRef.current.interval !== (interval || '');

    const mappedCandles = candles.map((c) => ({
      time: c.time as any,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    // Always do a full setData() when:
    // 1. The coin or interval changed (new context)
    // 2. We have never successfully loaded data for this context yet (initializedRef is false)
    // 3. A big batch arrived (not a single WS tick)
    const isBigBatch = initializedRef.current && Math.abs(candles.length - prevCandlesLenRef.current) > 1;

    if (isContextChanged || !initializedRef.current || isBigBatch) {
      if (isContextChanged) {
        // Reset state for the new context BEFORE calling setData
        initializedRef.current = false;
        prevCandlesLenRef.current = 0;
        prevContextRef.current = { coin, interval: interval || '' };
      }

      try {
        candleSeriesRef.current.setData(mappedCandles);
        chartRef.current.timeScale().fitContent();
        // Mark as initialized ONLY after successful setData
        initializedRef.current = true;
        prevCandlesLenRef.current = candles.length;
      } catch (err) {
        console.error('Error in candleSeries.setData:', err);
        // Do NOT set initializedRef = true so the next render retries setData
      }
      return;
    }

    // Incremental real-time update — single candle tick from WebSocket
    const lastCandle = candles[candles.length - 1];
    try {
      candleSeriesRef.current.update({
        time: lastCandle.time as any,
        open: lastCandle.open,
        high: lastCandle.high,
        low: lastCandle.low,
        close: lastCandle.close,
      });
      prevCandlesLenRef.current = candles.length;
    } catch (err) {
      // LightweightCharts threw (e.g. time regression) — fallback to full reload
      console.warn('candle.update() failed, falling back to setData:', err);
      initializedRef.current = false; // force full reload on next render
    }
  }, [candles, coin, interval]);

  // 3. Update Zones, Trendlines & Sweeps in Native Primitive
  useEffect(() => {
    if (!zonesPrimitiveRef.current) return;

    zonesPrimitiveRef.current.updateData({
      resistances,
      supports,
      fvgs,
      trendlines: liquidity?.trendlines || [],
      sweeps: liquidity?.sweeps || [],
      activeFormation,
    });
  }, [resistances, supports, fvgs, liquidity, activeFormation]);

  // 4. Update Candlestick Markers (Unified style, no middle lines)
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    // Clean any old price lines
    priceLinesRef.current.forEach((line) => {
      try {
        candleSeriesRef.current?.removePriceLine(line);
      } catch (e) {}
    });
    priceLinesRef.current = [];

    // Clean candlestick markers: NO massive text blobs over candles!
    const rawMarkers: SeriesMarker<any>[] = [];

    // SWEEP markers (crisp arrows on triggering wicks without text pollution)
    if (activeFormation === 'SWEEP' && liquidity?.sweeps) {
      liquidity.sweeps.forEach((sw) => {
        rawMarkers.push({
          time: sw.time as any,
          position: sw.direction === 'SHORT' ? 'aboveBar' : 'belowBar',
          color: sw.direction === 'SHORT' ? '#f6465d' : '#0ecb81',
          shape: sw.direction === 'SHORT' ? 'arrowDown' : 'arrowUp',
          text: '', // Clean arrow only!
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
            text: '', // Clean arrow only!
          });
        }
      });
    }

    // Sort strictly in ascending order by time
    rawMarkers.sort((a, b) => Number(a.time) - Number(b.time));

    // Deduplicate by time to prevent collisions
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
    <div className="relative w-full h-full flex flex-col bg-[#0b0e11] overflow-hidden">
      <div ref={chartContainerRef} className="w-full flex-1" />

      <div className="absolute bottom-2 left-3 flex items-center gap-1.5 opacity-60 text-xs font-mono select-none pointer-events-none z-20">
        <span className="bg-[#1e2329] px-1.5 py-0.5 rounded text-[10px] text-gray-400 font-bold">17</span>
        <span className="text-gray-500 text-[11px]">TradingView Lightweight Engine · Hyperliquid</span>
      </div>
    </div>
  );
};
