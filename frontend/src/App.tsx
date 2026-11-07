import React, { useState, useEffect, useCallback, useRef } from 'react';
import { TopBar } from './components/TopBar';
import { FormationsBar } from './components/FormationsBar';
import { Chart } from './components/Chart';
import { SidebarLevels } from './components/SidebarLevels';
import { ScreenerModal } from './components/ScreenerModal';
import { AlertToast } from './components/AlertToast';
import { Timeframe, FormationFilter, AnalysisData, CoinMeta, ScreenerItem, LevelItem, FVGItem, FVGConfluenceItem, Candle, ConnectionState, WSConnectionDetails } from './types';

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
  const [isLoadingEarlier, setIsLoadingEarlier] = useState<boolean>(false);
  const [isScreenerLoading, setIsScreenerLoading] = useState<boolean>(false);
  const [isScreenerOpen, setIsScreenerOpen] = useState<boolean>(false);
  const [wsStatus, setWsStatus] = useState<ConnectionState>('disconnected');
  const [wsDetails, setWsDetails] = useState<WSConnectionDetails>({ state: 'disconnected' });
  const isManualDisconnectRef = useRef<boolean>(false);
  const clientRetryAttemptRef = useRef<number>(0);

  // Client-side cache for instant timeframe switching: key -> AnalysisData
  const analysisCacheRef = useRef<Map<string, { data: AnalysisData; timestamp: number }>>(new Map());
  // Track exhausted history for lazy loading: key -> boolean
  const hasMoreHistoryRef = useRef<Map<string, boolean>>(new Map());

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

  // 2. Fetch Screener Signals (runs in background with an initial delay so chart loads first)
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
    // Delay first screener scan by 2s so initial chart analysis gets full bandwidth and zero rate limits
    const initialTimer = setTimeout(() => {
      fetchScreener();
    }, 2000);
    const interval = setInterval(fetchScreener, 60000); // refresh screener every 60s in background
    return () => {
      clearTimeout(initialTimer);
      clearInterval(interval);
    };
  }, [fetchScreener]);

  // 3. Fetch Single Coin Analysis & Candles with AbortController for instant responsiveness
  const fetchAnalysis = useCallback((coinToFetch: string, tfToFetch: string, isSilent = false) => {
    // Cancel previous in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const cleanTf = tfToFetch.toLowerCase();
    const cacheKey = `${coinToFetch.toUpperCase()}:${cleanTf}`;
    const cachedEntry = analysisCacheRef.current.get(cacheKey);
    const now = Date.now();

    // Check if we have fresh cached data (< 60 seconds old)
    if (cachedEntry) {
      setAnalysis(cachedEntry.data);
      if (now - cachedEntry.timestamp < 60000) {
        setIsLoading(false);
        return;
      }
      // Stale cache: immediately display it to user so there's zero UI freeze, then revalidate in background
      setIsLoading(false);
    } else if (!isSilent) {
      setIsLoading(true);
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Fast-path: If opening without cache, quickly fetch raw candles first so the chart renders in <500ms
    if (!cachedEntry) {
      fetch(`${API_BASE}/api/candles?coin=${coinToFetch}&interval=${cleanTf}&limit=600`, {
        signal: controller.signal,
      })
        .then((res) => res.json())
        .then((candleData) => {
          if (candleData.success && candleData.candles && candleData.candles.length > 0) {
            setAnalysis((prev) => {
              // Only apply if full analysis hasn't arrived yet and context is still matching
              if (
                coinToFetch.toUpperCase() !== selectedCoinRef.current.toUpperCase() ||
                cleanTf !== timeframeRef.current.toLowerCase()
              ) {
                return prev;
              }
              // If full analysis already arrived (not a fast-path stub), don't overwrite it
              if (
                prev &&
                prev.coin?.toUpperCase() === coinToFetch.toUpperCase() &&
                prev.interval?.toLowerCase() === cleanTf &&
                !prev.isFastPath
              ) {
                return prev;
              }
              const lastCandle = candleData.candles[candleData.candles.length - 1];
              return {
                isFastPath: true,
                coin: coinToFetch,
                interval: cleanTf,
                currentPrice: lastCandle.close,
                candles: candleData.candles,
                levels: { currentPrice: lastCandle.close, resistances: [], supports: [], cascades: [] },
                multiTimeframeLevels: {},
                fvgs: [],
                multiTimeframeFvgs: {},
                fvgConfluences: [],
                liquidity: { sweeps: [], pools: [], trendlines: [] },
                structure: {
                  trend: 'NEUTRAL',
                  summary: 'Аналіз структури ринку...',
                  events: [],
                  recentHigh: lastCandle.high,
                  recentLow: lastCandle.low,
                },
                signals: [],
              };
            });
            setIsLoading(false);
          }
        })
        .catch(() => {});
    }

    fetch(`${API_BASE}/api/analysis?coin=${coinToFetch}&interval=${cleanTf}`, {
      signal: controller.signal,
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.success && data.data) {
          // Double check request is still relevant to current selection
          if (
            coinToFetch.toUpperCase() === selectedCoinRef.current.toUpperCase() &&
            cleanTf === timeframeRef.current.toLowerCase()
          ) {
            setAnalysis(data.data);
          }
          // Store in client-side cache
          analysisCacheRef.current.set(cacheKey, {
            data: data.data,
            timestamp: Date.now(),
          });
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          console.error('Error fetching analysis:', err);
        }
      })
      .finally(() => {
        if (
          coinToFetch.toUpperCase() === selectedCoinRef.current.toUpperCase() &&
          cleanTf === timeframeRef.current.toLowerCase()
        ) {
          setIsLoading(false);
        }
      });
  }, []);

  // 3.1 Lazy Load Earlier Historical Candles (pagination when scrolling left)
  const handleLoadEarlier = useCallback(() => {
    const currentCoin = selectedCoinRef.current.toUpperCase();
    const currentTf = timeframeRef.current.toLowerCase();
    const paginationKey = `${currentCoin}:${currentTf}`;

    if (hasMoreHistoryRef.current.get(paginationKey) === false) {
      return; // Already reached the beginning of history
    }

    if (isLoadingEarlier || !analysis || !analysis.candles || analysis.candles.length === 0) {
      return;
    }

    const oldestCandle = analysis.candles[0];
    if (!oldestCandle) return;

    setIsLoadingEarlier(true);
    fetch(
      `${API_BASE}/api/candles?coin=${currentCoin}&interval=${currentTf}&limit=500&before=${oldestCandle.time}`
    )
      .then((res) => res.json())
      .then((resData) => {
        if (resData.success && Array.isArray(resData.candles)) {
          const olderCandles: Candle[] = resData.candles;
          // Filter out candles with timestamps >= oldestCandle.time to ensure strict chronological prepend
          const strictlyOlder = olderCandles.filter((c) => c.time < oldestCandle.time);

          if (strictlyOlder.length === 0) {
            hasMoreHistoryRef.current.set(paginationKey, false);
          } else {
            setAnalysis((prev) => {
              if (!prev || prev.coin?.toUpperCase() !== currentCoin || prev.interval?.toLowerCase() !== currentTf) {
                return prev;
              }
              
              // Merge, deduplicate by time, and sort strictly ascending
              const candleMap = new Map<number, Candle>();
              for (const c of strictlyOlder) {
                candleMap.set(c.time, c);
              }
              for (const c of prev.candles) {
                candleMap.set(c.time, c);
              }
              const combinedCandles = Array.from(candleMap.values()).sort((a, b) => a.time - b.time);
              const updatedAnalysis = { ...prev, candles: combinedCandles };

              // Update cache with extended candle range
              const cacheKey = `${currentCoin}:${currentTf}`;
              const existingCache = analysisCacheRef.current.get(cacheKey);
              if (existingCache) {
                analysisCacheRef.current.set(cacheKey, {
                  ...existingCache,
                  data: updatedAnalysis,
                });
              }

              return updatedAnalysis;
            });
          }
        }
      })
      .catch((err) => {
        console.error('Error lazy-loading earlier candles:', err);
      })
      .finally(() => {
        setIsLoadingEarlier(false);
      });
  }, [analysis, isLoadingEarlier]);

  // Non-blocking Exponential Backoff calculation for Client WebSocket (1s, 2s, 4s... capped at 30s) + jitter
  const calculateClientBackoff = useCallback((attempt: number): number => {
    const initial = 1000;
    const max = 30000;
    const nominal = Math.min(max, initial * Math.pow(2, attempt));
    const jitter = Math.random() * nominal * 0.25;
    return Math.min(max, nominal + jitter);
  }, []);

  // 4. WebSocket Manager for Real-Time Hyperliquid Ticks & Instant Sweeps
  const connectWebSocket = useCallback(() => {
    if (isManualDisconnectRef.current) {
      return;
    }
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
        clientRetryAttemptRef.current = 0;
        setWsStatus('connected');
        setWsDetails({ state: 'connected' });
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
            const serverState: ConnectionState = data.status || 'connected';
            setWsStatus(serverState);
            setWsDetails({
              state: serverState,
              attempt: data.attempt,
              nextRetryDelay: data.next_retry_delay,
              reason: data.reason,
              isManual: data.is_manual,
            });
            if (data.is_manual) {
              isManualDisconnectRef.current = true;
            }
          } else if (data.type === 'candle_tick') {
            const currentCoin = selectedCoinRef.current.toUpperCase();
            const currentTf = timeframeRef.current.toLowerCase();

            if (data.coin?.toUpperCase() === currentCoin && data.interval?.toLowerCase() === currentTf) {
              setAnalysis((prev) => {
                // Do not apply live tick if historical analysis or candles have not loaded yet!
                if (!prev || !prev.candles || prev.candles.length === 0) return prev;
                // Guard: Do not apply tick to stale coin or timeframe
                if (
                  prev.coin?.toUpperCase() !== currentCoin ||
                  prev.interval?.toLowerCase() !== currentTf
                ) {
                  return prev;
                }

                const updatedCandles = [...prev.candles];
                const newCandle = data.candle;

                const lastIdx = updatedCandles.length - 1;
                if (updatedCandles[lastIdx].time === newCandle.time) {
                  updatedCandles[lastIdx] = newCandle;
                } else if (newCandle.time > updatedCandles[lastIdx].time) {
                  updatedCandles.push(newCandle);
                }

                // Ensure strict ascending order by time without duplicates
                const candleMap = new Map<number, Candle>();
                for (const c of updatedCandles) {
                  candleMap.set(c.time, c);
                }
                const sortedCandles = Array.from(candleMap.values()).sort((a, b) => a.time - b.time);

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
                  candles: sortedCandles,
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
        wsRef.current = null;
        if (isManualDisconnectRef.current) {
          setWsStatus('disconnected');
          setWsDetails({ state: 'disconnected', isManual: true, reason: 'Відключено вручну користувачем' });
          return;
        }

        const nextAttempt = clientRetryAttemptRef.current + 1;
        clientRetryAttemptRef.current = nextAttempt;
        const delayMs = calculateClientBackoff(nextAttempt - 1);
        const nextState: ConnectionState = nextAttempt >= 12 ? 'failed' : 'reconnecting';

        setWsStatus(nextState);
        setWsDetails({
          state: nextState,
          attempt: nextAttempt,
          nextRetryDelay: Math.round(delayMs / 1000),
          reason: 'З’єднання розірвано. Автоматичний реконект...',
        });

        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, delayMs);
      };

      ws.onerror = () => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
      };
    } catch (err) {
      if (isManualDisconnectRef.current) {
        setWsStatus('disconnected');
        setWsDetails({ state: 'disconnected', isManual: true });
        return;
      }
      const nextAttempt = clientRetryAttemptRef.current + 1;
      clientRetryAttemptRef.current = nextAttempt;
      const delayMs = calculateClientBackoff(nextAttempt - 1);
      const nextState: ConnectionState = nextAttempt >= 12 ? 'failed' : 'reconnecting';
      setWsStatus(nextState);
      setWsDetails({
        state: nextState,
        attempt: nextAttempt,
        nextRetryDelay: Math.round(delayMs / 1000),
        reason: 'Помилка ініціалізації WebSocket. Повтор...',
      });
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = setTimeout(connectWebSocket, delayMs);
    }
  }, [calculateClientBackoff]);

  const handleToggleWS = useCallback(() => {
    if (wsStatus === 'connected') {
      // User manual disconnect
      isManualDisconnectRef.current = true;
      clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        try {
          wsRef.current.send(JSON.stringify({ action: 'disconnect' }));
        } catch {
          // ignore
        }
        wsRef.current.close();
      }
      wsRef.current = null;
      setWsStatus('disconnected');
      setWsDetails({ state: 'disconnected', isManual: true, reason: 'Відключено вручну користувачем' });
    } else {
      // User manual reconnect
      isManualDisconnectRef.current = false;
      clientRetryAttemptRef.current = 0;
      setWsStatus('reconnecting');
      setWsDetails({ state: 'reconnecting', attempt: 1, reason: 'Підключення вручну...' });
      clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action: 'reconnect' }));
      } else {
        connectWebSocket();
      }
    }
  }, [wsStatus, connectWebSocket]);

  // Connect WebSocket on component mount
  useEffect(() => {
    connectWebSocket();
    return () => {
      clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        // Prevent close() from triggering during CONNECTING in React StrictMode
        const activeWs = wsRef.current;
        wsRef.current = null;
        if (activeWs.readyState === WebSocket.OPEN) {
          activeWs.close();
        } else if (activeWs.readyState === WebSocket.CONNECTING) {
          activeWs.onopen = () => {
            activeWs.close();
          };
        }
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

  // Compute filtered FVGs across selected timeframes
  const filteredFvgs = React.useMemo(() => {
    if (!analysis) return [];

    let candidates: FVGItem[] = [];

    if (analysis.multiTimeframeFvgs && Object.keys(analysis.multiTimeframeFvgs).length > 0) {
      selectedTfs.forEach((tf) => {
        const tfClean = tf.toLowerCase();
        const list = analysis.multiTimeframeFvgs?.[tfClean] || [];
        candidates = candidates.concat(list);
      });
    } else {
      candidates = analysis.fvgs || [];
    }

    return candidates.filter((f) => {
      // Exclude fully mitigated or invalid ones, keeping active bullish and bearish FVGs
      const status = f.mitigation_status || (f.status === 'mitigated' ? 'FULLY MITIGATED' : 'FRESH');
      if (status === 'FULLY MITIGATED') return false;

      const score = f.strength_score ?? 70;
      return score >= minStrength;
    });
  }, [analysis, selectedTfs, minStrength]);

  const handleToggleTf = (tf: string) => {
    setSelectedTfs((prev) =>
      prev.includes(tf) ? prev.filter((t) => t !== tf) : [...prev, tf]
    );
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-slate-100 dark:bg-[#0b0e11] text-slate-900 dark:text-gray-200 overflow-hidden font-sans transition-colors">
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
        wsDetails={wsDetails}
        onToggleWS={handleToggleWS}
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
            <>
              <Chart
                candles={analysis.candles}
                resistances={filteredResistances}
                supports={filteredSupports}
                fvgs={filteredFvgs}
                signals={analysis.signals}
                liquidity={analysis.liquidity}
                activeFormation={activeFormation}
                coin={selectedCoin}
                interval={timeframe}
                onLoadEarlier={handleLoadEarlier}
                isLoadingEarlier={isLoadingEarlier}
              />
              {/* Overlay Loader during timeframe or coin switch */}
              {isLoading && (
                <div className="absolute inset-0 bg-white/60 dark:bg-[#0b0e11]/60 backdrop-blur-[2px] flex flex-col items-center justify-center text-slate-700 dark:text-gray-300 text-xs gap-2.5 z-40 transition-all pointer-events-none">
                  <div className="w-6 h-6 border-2 border-emerald-500 dark:border-emerald-400 border-t-transparent rounded-full animate-spin" />
                  <span className="font-medium bg-white/95 dark:bg-[#15191e]/90 px-3 py-1 rounded-full border border-slate-200 dark:border-[#2b313a] shadow-sm">
                    Оновлення даних {selectedCoin} ({timeframe})...
                  </span>
                </div>
              )}
            </>
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center text-slate-500 dark:text-gray-400 text-xs gap-3">
              <div className="w-7 h-7 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
              <span className="font-medium">Завантаження графіка {selectedCoin} ({timeframe}) з Hyperliquid...</span>
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
