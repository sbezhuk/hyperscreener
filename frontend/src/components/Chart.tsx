import React, { useEffect, useRef } from 'react';
import { createChart, IChartApi, ISeriesApi, LineStyle, SeriesMarker, CrosshairMode } from 'lightweight-charts';
import { Candle, LevelItem, FVGItem, SignalItem, FormationFilter, AnalysisData } from '../types';
import { ZonesPrimitive } from './ZonesPrimitive';
import { useTheme } from '../context/ThemeContext';

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
}) => {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const zonesPrimitiveRef = useRef<ZonesPrimitive | null>(null);
  const priceLinesRef = useRef<any[]>([]);

  const onLoadEarlierRef = useRef(onLoadEarlier);
  onLoadEarlierRef.current = onLoadEarlier;
  const isLoadingEarlierRef = useRef(isLoadingEarlier);
  isLoadingEarlierRef.current = isLoadingEarlier;

  const prevContextRef = useRef<{ coin: string; interval: string }>({ coin: '', interval: '' });
  const prevNavTokenRef = useRef<number | null>(null);
  // Track user interaction (drag / scroll) so pagination only triggers on deliberate scrolling into the past
  const userHasScrolledHistoryRef = useRef<boolean>(false);

  // 1. Initialize Chart & Attach ZonesPrimitive directly to Candle Series
  useEffect(() => {
    if (!chartContainerRef.current) return;

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
    });

    const zonesPrimitive = new ZonesPrimitive();
    candleSeries.attachPrimitive(zonesPrimitive as any);

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    zonesPrimitiveRef.current = zonesPrimitive;

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
      lastSetDataSeriesRef.current = null;
      initializedRef.current = false;
      prevContextRef.current = { coin: '', interval: '' };
      prevNavTokenRef.current = null;
      prevCandlesLenRef.current = 0;
      prevFirstCandleTimeRef.current = 0;
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
  const initializedRef = useRef<boolean>(false);

  // 2. Update Candles Data & preserve user scroll/zoom position!
  useEffect(() => {
    if (!candleSeriesRef.current || !chartRef.current || candles.length === 0) return;

    const isSeriesChanged = lastSetDataSeriesRef.current !== candleSeriesRef.current;
    const isContextChanged =
      prevContextRef.current.coin !== coin ||
      prevContextRef.current.interval.toLowerCase() !== (interval || '').toLowerCase();
    const isNewNavigation =
      navigationToken != null && navigationToken !== prevNavTokenRef.current;

    const firstCandleTime = candles[0]?.time || 0;
    const isPrependedEarlier =
      !isSeriesChanged &&
      initializedRef.current &&
      !isContextChanged &&
      !isNewNavigation &&
      prevFirstCandleTimeRef.current !== 0 &&
      firstCandleTime < prevFirstCandleTimeRef.current;

    // Deduplicate and strictly sort ascending to prevent assertion error in lightweight-charts
    const uniqueMap = new Map<number, Candle>();
    for (const c of candles) {
      if (typeof c.time === 'number' && !isNaN(c.time)) {
        uniqueMap.set(c.time, c);
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

      prevContextRef.current = { coin, interval: interval || '' };
    } else {
      // Real-time tick or poll update for the current coin/timeframe:
      // If only the latest bar updated, call update() for speed and zero jitter!
      if (
        mappedCandles.length === prevCandlesLenRef.current &&
        firstCandleTime === prevFirstCandleTimeRef.current
      ) {
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
        try {
          candleSeriesRef.current.setData(mappedCandles);
          lastSetDataSeriesRef.current = candleSeriesRef.current;
        } catch (err) {
          console.warn('Safely caught periodic setData error:', err);
        }
      }
    }

    prevCandlesLenRef.current = mappedCandles.length;
    prevFirstCandleTimeRef.current = mappedCandles[0]?.time ? Number(mappedCandles[0].time) : 0;
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
      activeFormation,
      theme: isDark ? 'dark' : 'light',
    });
  }, [resistances, supports, fvgs, liquidity, activeFormation, isDark]);

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
    <div className="relative w-full h-full flex flex-col bg-[#0b0e11] dark:bg-[#0b0e11] bg-white overflow-hidden transition-colors">
      <div ref={chartContainerRef} className="w-full flex-1 min-h-0 min-w-0" />

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
