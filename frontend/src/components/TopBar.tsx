import React from 'react';
import { Timeframe } from '../types';
import { ArrowLeft, RefreshCw, Zap } from 'lucide-react';

interface TopBarProps {
  coin: string;
  price: number;
  timeframe: Timeframe;
  onTimeframeChange: (tf: Timeframe) => void;
  onOpenScreener: () => void;
  onRefresh: () => void;
  isLoading: boolean;
  wsStatus?: 'connected' | 'reconnecting' | 'disconnected';
}

export const TopBar: React.FC<TopBarProps> = ({
  coin,
  price,
  timeframe,
  onTimeframeChange,
  onOpenScreener,
  onRefresh,
  isLoading,
  wsStatus = 'connected',
}) => {
  const timeframes: Timeframe[] = ['1m', '5m', '15m', '1h', '4h', '1D'];

  return (
    <header className="h-14 px-4 bg-[#0e1114] border-b border-[#1e2329] flex items-center justify-between select-none">
      {/* Left: Back / Screener button and Coin Info */}
      <div className="flex items-center gap-4">
        <button
          onClick={onOpenScreener}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white px-2.5 py-1.5 rounded bg-[#15191e] border border-[#23272e] hover:border-gray-500 transition"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span className="font-medium">Скрінер монет</span>
        </button>

        <div className="flex items-baseline gap-2.5">
          <span className="text-xl font-bold tracking-tight text-white font-mono">{coin}</span>
          <span className="text-xs text-gray-400 font-medium hidden sm:inline">
            USDT perpetual · Hyperliquid
          </span>
          <div
            className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded font-mono font-medium transition ${
              wsStatus === 'connected'
                ? 'text-emerald-400 bg-emerald-500/10'
                : wsStatus === 'reconnecting'
                ? 'text-amber-400 bg-amber-500/10'
                : 'text-red-400 bg-red-500/10'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                wsStatus === 'connected'
                  ? 'bg-[#0ecb81] animate-pulse'
                  : wsStatus === 'reconnecting'
                  ? 'bg-amber-400 animate-ping'
                  : 'bg-red-500'
              }`}
            />
            <span>
              {wsStatus === 'connected'
                ? 'WS LIVE'
                : wsStatus === 'reconnecting'
                ? 'RECONNECTING'
                : 'OFFLINE'}
            </span>
          </div>
        </div>

        {/* Current Price */}
        <div className="ml-2 font-mono text-xl font-semibold text-[#0ecb81]">
          {price > 0 ? (price < 1 ? price.toFixed(5) : price < 50 ? price.toFixed(3) : price.toFixed(2)) : '---'}
        </div>
      </div>

      {/* Right: Timeframe Selector & Actions */}
      <div className="flex items-center gap-2">
        <div className="flex items-center bg-[#15191e] border border-[#23272e] rounded p-0.5">
          {timeframes.map((tf) => (
            <button
              key={tf}
              onClick={() => onTimeframeChange(tf)}
              className={`px-2.5 py-1 text-xs font-semibold rounded transition ${
                timeframe === tf
                  ? 'bg-[#2b313a] text-white shadow-sm'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>

        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="p-1.5 rounded bg-[#15191e] border border-[#23272e] hover:bg-[#1e2329] text-gray-400 hover:text-white transition disabled:opacity-50"
          title="Оновити дані"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-emerald-400' : ''}`} />
        </button>
      </div>
    </header>
  );
};
