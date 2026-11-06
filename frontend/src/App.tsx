import React, { useState, useEffect, useCallback, useRef } from 'react';
import { TopBar } from './components/TopBar';
import { FormationsBar } from './components/FormationsBar';
import { Chart } from './components/Chart';
import { SidebarLevels } from './components/SidebarLevels';
import { ScreenerModal } from './components/ScreenerModal';
import { AlertToast } from './components/AlertToast';
import { Timeframe, FormationFilter, AnalysisData, CoinMeta, ScreenerItem } from './types';

const API_BASE = 'http://localhost:8000';

export function App() {
  const [selectedCoin, setSelectedCoin] = useState<string>('ETH');
  const [timeframe, setTimeframe] = useState<Timeframe>('1D');
  const [activeFormation, setActiveFormation] = useState<FormationFilter>('CASCADE');
  
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [allCoins, setAllCoins] = useState<CoinMeta[]>([]);
  const [screenerData, setScreenerData] = useState<ScreenerItem[]>([]);
  
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isScreenerLoading, setIsScreenerLoading] = useState<boolean>(false);
  const [isScreenerOpen, setIsScreenerOpen] = useState<boolean>(false);

  // AbortController ref to cancel obsolete in-flight analysis requests
  const abortControllerRef = useRef<AbortController | null>(null);

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

  // Trigger analysis when selectedCoin or timeframe changes
  useEffect(() => {
    fetchAnalysis(selectedCoin, timeframe);
    const interval = setInterval(() => {
      fetchAnalysis(selectedCoin, timeframe);
    }, 6000); // refresh candle data every 6 seconds
    return () => clearInterval(interval);
  }, [selectedCoin, timeframe, fetchAnalysis]);

  const currentCoinMeta = allCoins.find((c) => c.name === selectedCoin);
  const currentPrice = analysis?.currentPrice || currentCoinMeta?.markPrice || 0;

  return (
    <div className="flex flex-col h-screen w-screen bg-[#0b0e11] text-gray-200 overflow-hidden font-sans">
      {/* Top Header */}
      <TopBar
        coin={selectedCoin}
        price={currentPrice}
        timeframe={timeframe}
        onTimeframeChange={(newTf) => {
          setTimeframe(newTf);
        }}
        onOpenScreener={() => {
          setIsScreenerOpen(true);
          fetchScreener();
        }}
        onRefresh={() => fetchAnalysis(selectedCoin, timeframe)}
        isLoading={isLoading}
      />

      {/* Formations Filter Bar */}
      <FormationsBar active={activeFormation} onChange={setActiveFormation} />

      {/* Main Workspace (Chart + Right Sidebar) */}
      <div className="flex flex-1 overflow-hidden relative">
        <main className="flex-1 h-full relative">
          {analysis && analysis.candles && analysis.candles.length > 0 ? (
            <Chart
              candles={analysis.candles}
              resistances={analysis.levels.resistances}
              supports={analysis.levels.supports}
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
          resistances={analysis?.levels.resistances || []}
          supports={analysis?.levels.supports || []}
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
