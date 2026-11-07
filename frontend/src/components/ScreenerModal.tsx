import React, { useState } from 'react';
import { ScreenerItem, CoinMeta } from '../types';
import { X, Search, Layers, Activity } from 'lucide-react';

interface ScreenerModalProps {
  isOpen: boolean;
  onClose: () => void;
  screenerData: ScreenerItem[];
  allCoins: CoinMeta[];
  selectedCoin: string;
  onSelectCoin: (coin: string) => void;
  isLoading: boolean;
}

export const ScreenerModal: React.FC<ScreenerModalProps> = ({
  isOpen,
  onClose,
  screenerData,
  allCoins,
  selectedCoin,
  onSelectCoin,
  isLoading,
}) => {
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'signals' | 'all'>('signals');

  if (!isOpen) return null;

  const filteredSignals = screenerData.filter((item) =>
    item.coin.toLowerCase().includes(search.toLowerCase())
  );

  const filteredAllCoins = allCoins.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 bg-black/50 dark:bg-black/60 backdrop-blur-sm flex justify-start select-none">
      <div className="w-full max-w-md h-full bg-white dark:bg-[#0e1114] border-r border-slate-200 dark:border-[#1e2329] flex flex-col shadow-2xl animate-in slide-in-from-left duration-200 transition-colors">
        
        {/* Header */}
        <div className="p-4 border-b border-slate-200 dark:border-[#1e2329] flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Layers className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
              Скрінер Hyperliquid
            </h2>
            <p className="text-xs text-slate-500 dark:text-gray-500 mt-0.5">Знайдені торгові формації та монети</p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-100 dark:hover:bg-[#1e2329] text-slate-400 dark:text-gray-400 hover:text-slate-800 dark:hover:text-white transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Search & Tabs */}
        <div className="p-3 border-b border-slate-200 dark:border-[#1e2329] space-y-2 bg-slate-50 dark:bg-[#12161b]">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 dark:text-gray-500 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Пошук монети (BTC, SOL, HYPE...)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 bg-white dark:bg-[#181d24] border border-slate-300 dark:border-[#23272e] rounded text-xs text-slate-900 dark:text-white focus:outline-none focus:border-emerald-500 font-mono shadow-sm placeholder-slate-400 dark:placeholder-gray-500"
            />
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab('signals')}
              className={`flex-1 py-1 rounded text-xs font-semibold transition cursor-pointer ${
                activeTab === 'signals'
                  ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-[#0ecb81] border border-emerald-400 dark:border-emerald-500/40 shadow-sm'
                  : 'bg-white dark:bg-[#181d24] text-slate-600 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-transparent'
              }`}
            >
              Активні формації ({filteredSignals.length})
            </button>
            <button
              onClick={() => setActiveTab('all')}
              className={`flex-1 py-1 rounded text-xs font-semibold transition cursor-pointer ${
                activeTab === 'all'
                  ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-[#0ecb81] border border-emerald-400 dark:border-emerald-500/40 shadow-sm'
                  : 'bg-white dark:bg-[#181d24] text-slate-600 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-transparent'
              }`}
            >
              Всі монети ({allCoins.length})
            </button>
          </div>
        </div>

        {/* List Content */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5 font-mono">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-48 text-slate-400 dark:text-gray-500 text-xs">
              <Activity className="w-6 h-6 animate-spin text-emerald-500 dark:text-emerald-400 mb-2" />
              Сканування ринку Hyperliquid...
            </div>
          ) : activeTab === 'signals' ? (
            filteredSignals.length === 0 ? (
              <div className="text-slate-400 dark:text-gray-500 text-center py-10 text-xs font-sans">
                Не знайдено сигналів за поточним фільтром.
              </div>
            ) : (
              filteredSignals.map((item) => {
                const isSelected = selectedCoin === item.coin;
                return (
                  <div
                    key={item.coin}
                    onClick={() => {
                      onSelectCoin(item.coin);
                      onClose();
                    }}
                    className={`p-2.5 rounded border transition cursor-pointer ${
                      isSelected
                        ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-500/60'
                        : 'bg-slate-50 dark:bg-[#15191e] border-slate-200 dark:border-[#23272e] hover:border-slate-400 dark:hover:border-gray-500'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">{item.coin}</span>
                        <span
                          className={`text-[9px] px-1.5 py-0.2 rounded font-sans font-bold ${
                            item.trend === 'BULLISH'
                              ? 'text-emerald-700 dark:text-[#0ecb81] bg-emerald-500/10'
                              : item.trend === 'BEARISH'
                              ? 'text-rose-700 dark:text-[#f6465d] bg-rose-500/10'
                              : 'text-amber-600 dark:text-yellow-400 bg-amber-500/10'
                          }`}
                        >
                          {item.trend}
                        </span>
                      </div>
                      <span className="text-xs font-semibold text-slate-700 dark:text-gray-300">
                        ${item.currentPrice < 1 ? item.currentPrice.toFixed(4) : item.currentPrice.toFixed(2)}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-gray-400 font-sans">
                      <div className="flex items-center gap-1.5">
                        <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{item.signalsCount} сетап(и)</span>
                        <span>·</span>
                        <span>{item.resistancesCount} опорів / {item.supportsCount} підтримок</span>
                      </div>
                    </div>

                    {/* First Signal Preview */}
                    {item.signals[0] && (
                      <div className="mt-1.5 text-[10px] text-slate-600 dark:text-gray-400 font-sans line-clamp-1 bg-white dark:bg-[#0b0e11] px-2 py-1 rounded border border-slate-200/80 dark:border-transparent">
                        <span className={item.signals[0].direction === 'LONG' ? 'text-emerald-600 dark:text-[#0ecb81]' : 'text-rose-600 dark:text-[#f6465d]'}>
                          [{item.signals[0].direction}]
                        </span>{' '}
                        {item.signals[0].title}: {item.signals[0].desc}
                      </div>
                    )}
                  </div>
                );
              })
            )
          ) : (
            filteredAllCoins.map((c) => {
              const isSelected = selectedCoin === c.name;
              return (
                <div
                  key={c.name}
                  onClick={() => {
                    onSelectCoin(c.name);
                    onClose();
                  }}
                  className={`p-2 rounded border transition cursor-pointer flex items-center justify-between ${
                    isSelected
                      ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-500/60'
                      : 'bg-slate-50 dark:bg-[#15191e] border-slate-200 dark:border-[#23272e] hover:border-slate-400 dark:hover:border-gray-500'
                  }`}
                >
                  <div>
                    <span className="font-bold text-slate-900 dark:text-white text-xs">{c.name}</span>
                    <span className="text-[10px] text-slate-400 dark:text-gray-500 ml-2 font-sans">
                      Vol: ${(c.volume24h / 1_000_000).toFixed(1)}M
                    </span>
                  </div>
                  <div className="text-right">
                    <div className="text-xs font-semibold text-slate-700 dark:text-gray-200">
                      ${c.markPrice < 1 ? c.markPrice.toFixed(4) : c.markPrice.toFixed(2)}
                    </div>
                    <div className={`text-[10px] font-sans ${c.change24h >= 0 ? 'text-[#0ecb81]' : 'text-[#f6465d]'}`}>
                      {c.change24h >= 0 ? `+${c.change24h}%` : `${c.change24h}%`}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
