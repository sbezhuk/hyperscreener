import React from 'react';
import { Timeframe } from '../types';
import { ArrowLeft, RefreshCw, Sun, Moon, Laptop } from 'lucide-react';
import { useTheme, ThemePreference } from '../context/ThemeContext';

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
  const { themePreference, resolvedTheme, setThemePreference } = useTheme();
  const timeframes: Timeframe[] = ['1m', '5m', '15m', '1h', '4h', '1D'];

  const themeCycle: ThemePreference[] = ['auto', 'light', 'dark'];
  const handleToggleTheme = () => {
    const currentIndex = themeCycle.indexOf(themePreference);
    const nextTheme = themeCycle[(currentIndex + 1) % themeCycle.length];
    setThemePreference(nextTheme);
  };

  const getThemeIcon = () => {
    if (themePreference === 'auto') {
      return <Laptop className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />;
    }
    if (themePreference === 'light') {
      return <Sun className="w-4 h-4 text-amber-500" />;
    }
    return <Moon className="w-4 h-4 text-blue-400" />;
  };

  const getThemeTitle = () => {
    if (themePreference === 'auto') {
      return `Тема: Авто (системна: ${resolvedTheme === 'dark' ? 'темна' : 'світла'}). Клікніть щоб змінити на світлу`;
    }
    if (themePreference === 'light') {
      return 'Тема: Світла. Клікніть щоб змінити на темну';
    }
    return 'Тема: Темна. Клікніть щоб змінити на авто (системну)';
  };

  return (
    <header className="h-14 px-4 bg-white dark:bg-[#0e1114] border-b border-slate-200 dark:border-[#1e2329] flex items-center justify-between select-none transition-colors">
      {/* Left: Back / Screener button and Coin Info */}
      <div className="flex items-center gap-4">
        <button
          onClick={onOpenScreener}
          className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white px-2.5 py-1.5 rounded bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] hover:border-slate-400 dark:hover:border-gray-500 transition"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span className="font-medium">Скрінер монет</span>
        </button>

        <div className="flex items-baseline gap-2.5">
          <span className="text-xl font-bold tracking-tight text-slate-900 dark:text-white font-mono">{coin}</span>
          <span className="text-xs text-slate-500 dark:text-gray-400 font-medium hidden sm:inline">
            USDT perpetual · Hyperliquid
          </span>
          <div
            className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded font-mono font-medium transition ${
              wsStatus === 'connected'
                ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'
                : wsStatus === 'reconnecting'
                ? 'text-amber-600 dark:text-amber-400 bg-amber-500/10'
                : 'text-rose-600 dark:text-red-400 bg-red-500/10'
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

      {/* Right: Theme Selector, Timeframe Selector & Actions */}
      <div className="flex items-center gap-2">
        {/* Theme Mode Switcher */}
        <div className="flex items-center bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] rounded p-0.5 text-xs">
          <button
            onClick={() => setThemePreference('light')}
            className={`px-2 py-1 rounded flex items-center gap-1 font-medium transition ${
              themePreference === 'light'
                ? 'bg-white dark:bg-[#2b313a] text-slate-900 dark:text-white shadow-sm'
                : 'text-slate-500 dark:text-gray-400 hover:text-slate-900 dark:hover:text-gray-200'
            }`}
            title="Світла тема"
          >
            <Sun className="w-3.5 h-3.5 text-amber-500" />
            <span className="hidden md:inline text-[11px]">Світла</span>
          </button>

          <button
            onClick={() => setThemePreference('dark')}
            className={`px-2 py-1 rounded flex items-center gap-1 font-medium transition ${
              themePreference === 'dark'
                ? 'bg-white dark:bg-[#2b313a] text-slate-900 dark:text-white shadow-sm'
                : 'text-slate-500 dark:text-gray-400 hover:text-slate-900 dark:hover:text-gray-200'
            }`}
            title="Темна тема"
          >
            <Moon className="w-3.5 h-3.5 text-blue-400" />
            <span className="hidden md:inline text-[11px]">Темна</span>
          </button>

          <button
            onClick={() => setThemePreference('auto')}
            className={`px-2 py-1 rounded flex items-center gap-1 font-medium transition ${
              themePreference === 'auto'
                ? 'bg-white dark:bg-[#2b313a] text-slate-900 dark:text-white shadow-sm'
                : 'text-slate-500 dark:text-gray-400 hover:text-slate-900 dark:hover:text-gray-200'
            }`}
            title={getThemeTitle()}
          >
            <Laptop className="w-3.5 h-3.5 text-emerald-500 dark:text-emerald-400" />
            <span className="hidden md:inline text-[11px]">Авто</span>
          </button>
        </div>

        {/* Timeframe selector */}
        <div className="flex items-center bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] rounded p-0.5">
          {timeframes.map((tf) => (
            <button
              key={tf}
              onClick={() => onTimeframeChange(tf)}
              className={`px-2.5 py-1 text-xs font-semibold rounded transition ${
                timeframe === tf
                  ? 'bg-white dark:bg-[#2b313a] text-slate-900 dark:text-white shadow-sm'
                  : 'text-slate-500 dark:text-gray-400 hover:text-slate-900 dark:hover:text-gray-200'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>

        {/* Refresh button */}
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="p-1.5 rounded bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] hover:bg-slate-200 dark:hover:bg-[#1e2329] text-slate-600 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white transition disabled:opacity-50"
          title="Оновити дані"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-emerald-500 dark:text-emerald-400' : ''}`} />
        </button>
      </div>
    </header>
  );
};
