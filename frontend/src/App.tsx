import React, { useState, useEffect, useCallback, useRef } from 'react';
import { TopBar } from './components/TopBar';
import { FormationsBar } from './components/FormationsBar';
import { Chart } from './components/Chart';
import { SidebarLevels } from './components/SidebarLevels';
import { ScreenerModal } from './components/ScreenerModal';
import { AlertToast } from './components/AlertToast';
import { Timeframe, FormationFilter, AnalysisData, CoinMeta, ScreenerItem, LevelItem } from './types';

const API_BASE = 'http://localhost:8000';
const WS_BASE = 'ws://localhost:8000/ws';

export function App() {
  const [selectedCoin, setSelectedCoin] = useState<string>('ETH');
  const [timeframe, setTimeframe] = useState<Timeframe>('1D');
  const [activeFormation, setActiveFormation] = useState<FormationFilter>('CASCADE');
  
  // Multi-Timeframe Controls: by default only the active timeframe is enabled
  const [selectedTfs, setSelectedTfs] = useState<string[]>([timeframe.toLowerCase()]);
  const [minStrength, setMinStrength] = useState<number>(50);

  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [allCoins, setAllCoins] = useState<CoinMeta[]>([]);
  const [screenerData, setScreenerData] = useState<ScreenerItem[]>([]);
  
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isScreenerLoading, setIsScreenerLoading] = useState<boolean>(false);
  const [isScreenerOpen, setIsScreenerOpen] = useState<boolean>(false);
  const [wsStatus, setWsStatus] = useState<'connected' | 'reconnecting' | 'disconnected'>('disconnected');

  // AbortController ref to cancel obsolete in-flight analysis requests
  const abortControllerRef = useRef<AbortController | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<any>(null);
  const selectedCoinRef = useRef(selectedCoin);
  const timeframeRef = useRef(timeframe);
  const prevSubRef = useRef<{ coin: string; interval: string }>({ coin: '', interval: '' });

  selectedCoinRef.current = selectedCoin;
  timeframeRef.current = timeframe;

  // 1. Fetch Coins List on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/coins`)
      .then((res) => res.json())
      .then((data) => {
        if (data.success && data.coins) {
          setAllCoins(data.coins);
        }
      })
      .catch((err) => console.error('Error fetching coins:', err));
  }, []);

  // 2. Fetch Screener Signals (runs on mount and on a background timer, NOT blocking the chart)
  const fetchScreener = useCallback(() => {
    setIsScreenerLoading(true);
    fetch(`${API_BASE}/api/screener?top_n=20&interval=5m`)
      .then((res) => res.json())
      .then((data) => {
        if (data.success && data.results) {
          setScreenerData(data.results);
        }
      })
      .catch((err) => console.error('Error fetching screener:', err))
      .finally(() => setIsScreenerLoading(false));
  }, []);

  useEffect(() => {
    fetchScreener();
    const interval = setInterval(fetchScreener, 30000); // refresh screener every 30s in background
    return () => clearInterval(interval);
  }, [fetchScreener]);

  // 3. Fetch Single Coin Analysis & Candles with AbortController for instant responsiveness
  const fetchAnalysis = useCallback((coinToFetch: string, tfToFetch: string) => {
    // Cancel previous in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsLoading(true);

    const cleanTf = tfToFetch.toLowerCase();
    fetch(`${API_BASE}/api/analysis?coin=${coinToFetch}&interval=${cleanTf}`, {
      signal: controller.signal,
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.success && data.data) {
          setAnalysis(data.data);
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          console.error('Error fetching analysis:', err);
        }
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, []);

  // 4. WebSocket Manager for Real-Time Hyperliquid Ticks & Instant Sweeps
  const connectWebSocket = useCallback(() => {
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    try {
      const ws = new WebSocket(WS_BASE);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsStatus('connected');
        // Subscribe to current coin & interval immediately on connect
        ws.send(
          JSON.stringify({
            action: 'subscribe',
            coin: selectedCoinRef.current,
            interval: timeframeRef.current.toLowerCase(),
          })
        );
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'ws_status') {
            setWsStatus(data.status === 'connected' ? 'connected' : 'reconnecting');
          } else if (data.type === 'candle_tick') {
            const currentCoin = selectedCoinRef.current.toUpperCase();
            const currentTf = timeframeRef.current.toLowerCase();

            if (data.coin?.toUpperCase() === currentCoin && data.interval?.toLowerCase() === currentTf) {
              setAnalysis((prev) => {
                if (!prev) return prev;
                // Guard: Do not apply tick to stale coin or timeframe
                if (
                  prev.coin?.toUpperCase() !== currentCoin ||
                  prev.interval?.toLowerCase() !== currentTf
                ) {
                  return prev;
                }

                const updatedCandles = [...prev.candles];
                const newCandle = data.candle;

                if (updatedCandles.length > 0) {
                  const lastIdx = updatedCandles.length - 1;
                  if (updatedCandles[lastIdx].time === newCandle.time) {
                    updatedCandles[lastIdx] = newCandle;
                  } else if (newCandle.time > updatedCandles[lastIdx].time) {
                    updatedCandles.push(newCandle);
                    if (updatedCandles.length > 300) updatedCandles.shift();
                  }
                }

                let updatedSignals = prev.signals || [];
                let updatedSweeps = prev.liquidity?.sweeps || [];

                // Live sweep detected in real time!
                if (data.sweep) {
                  const sw = data.sweep;
                  const alreadyExists = updatedSweeps.some(
                    (s) => s.levelPrice === sw.levelPrice && Math.abs(s.time - sw.time) < 60
                  );
                  if (!alreadyExists) {
                    updatedSweeps = [sw, ...updatedSweeps].slice(0, 3);
                    const sweepSignal = {
                      id: `live-sweep-${sw.levelPrice}-${sw.time}`,
                      coin: data.coin,
                      interval: data.interval,
                      category: 'sweep' as const,
                      title: sw.formation,
                      direction: sw.direction,
                      desc: sw.desc,
                      price: sw.levelPrice,
                      time: sw.time,
                    };
                    updatedSignals = [sweepSignal, ...updatedSignals];
                  }
                }

                return {
                  ...prev,
                  currentPrice: data.currentPrice,
                  candles: updatedCandles,
                  signals: updatedSignals,
                  liquidity: {
                    ...prev.liquidity,
                    sweeps: updatedSweeps,
                    pools: prev.liquidity?.pools || [],
                    trendlines: prev.liquidity?.trendlines || [],
                  },
                };
              });
            }
          }
        } catch (err) {
          console.error('Error handling WS message:', err);
        }
      };

      ws.onclose = () => {
        setWsStatus('reconnecting');
        wsRef.current = null;
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, 2000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch (err) {
      setWsStatus('disconnected');
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000);
    }
  }, []);

  // Connect WebSocket on component mount
  useEffect(() => {
    connectWebSocket();
    return () => {
      clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connectWebSocket]);

  // Trigger analysis when selectedCoin or timeframe changes + switch WS subscription
  useEffect(() => {
    fetchAnalysis(selectedCoin, timeframe);

    // Switch WebSocket subscription to the newly selected coin / timeframe
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      if (prevSubRef.current.coin && prevSubRef.current.interval) {
        wsRef.current.send(
          JSON.stringify({
            action: 'unsubscribe',
            coin: prevSubRef.current.coin,
            interval: prevSubRef.current.interval.toLowerCase(),
          })
        );
      }

      wsRef.current.send(
        JSON.stringify({
          action: 'subscribe',
          coin: selectedCoin,
          interval: timeframe.toLowerCase(),
        })
      );
    }
    prevSubRef.current = { coin: selectedCoin, interval: timeframe };

    // Gentle background sync every 60s for higher-level structure refresh (replaces 6s spam polling)
    const backgroundSync = setInterval(() => {
      fetchAnalysis(selectedCoin, timeframe);
    }, 60000);

    return () => clearInterval(backgroundSync);
  }, [selectedCoin, timeframe, fetchAnalysis]);

  const currentCoinMeta = allCoins.find((c) => c.name === selectedCoin);
  const currentPrice = analysis?.currentPrice || currentCoinMeta?.markPrice || 0;

  // Multi-Timeframe Level Filtering (Section 2.6)
  const { filteredResistances, filteredSupports } = React.useMemo(() => {
    if (!analysis) return { filteredResistances: [], filteredSupports: [] };

    if (analysis.multiTimeframeLevels) {
      const res: LevelItem[] = [];
      const sup: LevelItem[] = [];

      selectedTfs.forEach((tf) => {
        const tfData = analysis.multiTimeframeLevels?.[tf];
        if (!tfData) return;

        (tfData.resistances || []).forEach((r) => {
          const score = r.strength_score ?? 50;
          if (score >= minStrength) {
            res.push({ ...r, timeframe: tf });
          }
        });

        (tfData.supports || []).forEach((s) => {
          const score = s.strength_score ?? 50;
          if (score >= minStrength) {
            sup.push({ ...s, timeframe: tf });
          }
        });
      });

      res.sort((a, b) => a.price - b.price);
      sup.sort((a, b) => b.price - a.price);

      return { filteredResistances: res, filteredSupports: sup };
    }

    return {
      filteredResistances: analysis.levels.resistances || [],
      filteredSupports: analysis.levels.supports || [],
    };
  }, [analysis, selectedTfs, minStrength]);

  const handleToggleTf = (tf: string) => {
    setSelectedTfs((prev) =>
      prev.includes(tf) ? prev.filter((t) => t !== tf) : [...prev, tf]
    );
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-[#0b0e11] text-gray-200 overflow-hidden font-sans">
      {/* Top Header */}
      <TopBar
        coin={selectedCoin}
        price={currentPrice}
        timeframe={timeframe}
        onTimeframeChange={(newTf) => {
          setTimeframe(newTf);
          setSelectedTfs([newTf.toLowerCase()]);
        }}
        onOpenScreener={() => {
          setIsScreenerOpen(true);
          fetchScreener();
        }}
        onRefresh={() => fetchAnalysis(selectedCoin, timeframe)}
        isLoading={isLoading}
        wsStatus={wsStatus}
      />

      {/* Formations & Multi-Timeframe Filter Bar */}
      <FormationsBar
        active={activeFormation}
        onChange={setActiveFormation}
        selectedTfs={selectedTfs}
        onToggleTf={handleToggleTf}
        minStrength={minStrength}
        onMinStrengthChange={setMinStrength}
      />

      {/* Main Workspace (Chart + Right Sidebar) */}
      <div className="flex flex-1 overflow-hidden relative">
        <main className="flex-1 h-full relative">
          {analysis && analysis.candles && analysis.candles.length > 0 ? (
            <Chart
              candles={analysis.candles}
              resistances={filteredResistances}
              supports={filteredSupports}
              fvgs={analysis.fvgs}
              signals={analysis.signals}
              liquidity={analysis.liquidity}
              activeFormation={activeFormation}
              coin={selectedCoin}
              interval={timeframe}
            />
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center text-gray-500 text-xs gap-2">
              <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
              <span>Завантаження даних {selectedCoin} ({timeframe}) з Hyperliquid...</span>
            </div>
          )}
        </main>

        {/* Right Sidebar with Levels and Formations */}
        <SidebarLevels
          resistances={filteredResistances}
          supports={filteredSupports}
          signals={analysis?.signals || []}
          structure={analysis?.structure}
          openInterest={currentCoinMeta?.openInterest}
          fundingRate={currentCoinMeta?.fundingRate}
          activeFormation={activeFormation}
        />
      </div>

      {/* Screener Modal / Drawer */}
      <ScreenerModal
        isOpen={isScreenerOpen}
        onClose={() => setIsScreenerOpen(false)}
        screenerData={screenerData}
        allCoins={allCoins}
        selectedCoin={selectedCoin}
        onSelectCoin={(coin) => {
          setSelectedCoin(coin);
          setIsScreenerOpen(false);
        }}
        isLoading={isScreenerLoading}
      />

      {/* Live Alert Toast in Bottom-Right Corner */}
      {analysis?.signals && (
        <AlertToast
          signals={analysis.signals}
          coin={selectedCoin}
          onSwitchCoin={(c) => setSelectedCoin(c)}
        />
      )}
    </div>
  );
}

export default App;
