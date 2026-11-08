import React from 'react';
import { Timeframe, ConnectionState, WSConnectionDetails, OIData, formatOiDeltaPct } from '../types';
import { ArrowLeft, RefreshCw, Sun, Moon, Laptop, Power, Play, RefreshCcw, TrendingUp, TrendingDown, Minus, SlidersHorizontal } from 'lucide-react';
import { useTheme, ThemePreference } from '../context/ThemeContext';

interface TopBarProps {
  coin: string;
  price: number;
  timeframe: Timeframe;
  onTimeframeChange: (tf: Timeframe) => void;
  onOpenScreener: () => void;
  onRefresh: () => void;
  isLoading: boolean;
  wsStatus?: ConnectionState;
  wsDetails?: WSConnectionDetails;
  onToggleWS?: () => void;
  oiData?: OIData;
  onToggleSidebar?: () => void;
  isSidebarOpen?: boolean;
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
  wsDetails,
  onToggleWS,
  oiData,
  onToggleSidebar,
  isSidebarOpen,
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
    <header className="w-full max-w-full bg-white dark:bg-[#0e1114] border-b border-slate-200 dark:border-[#1e2329] select-none transition-colors no-scrollbar overflow-x-hidden">
      {/* Main TopBar Container: single sleek row on sm+, 2 adaptive rows on mobile */}
      <div className="px-2 sm:px-4 py-2 sm:py-0 sm:h-14 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        {/* Row 1 on mobile / Left group on desktop */}
        <div className="flex items-center justify-between sm:justify-start gap-2 sm:gap-3 min-w-0 w-full sm:w-auto">
          {/* Back to Screener */}
          <button
            onClick={onOpenScreener}
            className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white px-2 sm:px-2.5 py-1.5 rounded bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] hover:border-slate-400 dark:hover:border-gray-500 transition flex-shrink-0"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span className="font-medium hidden sm:inline">Скрінер монет</span>
            <span className="font-medium sm:hidden">Скрінер</span>
          </button>

          {/* Coin Symbol, Live Connection Status Pill, and Real-time Price */}
          <div className="flex items-center gap-2 sm:gap-2.5 flex-shrink-0">
            <span className="text-lg sm:text-xl font-bold tracking-tight text-slate-900 dark:text-white font-mono leading-none">
              {coin}
            </span>
            <span className="text-xs text-slate-500 dark:text-gray-400 font-medium hidden 2xl:inline">
              USDT безстроковий · Hyperliquid
            </span>
            <button
              onClick={onToggleWS}
              title={
                wsStatus === 'connected'
                  ? 'З’єднання активне (Hyperliquid WS). Клікніть, щоб зупинити/відключити'
                  : wsStatus === 'reconnecting'
                  ? `Відновлення підключення (спроба ${wsDetails?.attempt || 1}, очікування ${wsDetails?.nextRetryDelay || 0}s). Клікніть для негайного реконекту`
                  : wsStatus === 'failed'
                  ? 'Підключення не вдалося. Клікніть, щоб повторити спробу'
                  : 'Відключено вручну. Клікніть, щоб відновити підключення'
              }
              className={`group inline-flex items-center gap-1.5 text-[10px] px-2 py-0.5 rounded-full font-mono font-medium transition cursor-pointer hover:opacity-90 active:scale-95 flex-shrink-0 ${
                wsStatus === 'connected'
                  ? 'text-emerald-600 dark:text-[#0ecb81] bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 shadow-[0_0_8px_rgba(14,203,129,0.12)]'
                  : wsStatus === 'reconnecting'
                  ? 'text-amber-600 dark:text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 shadow-[0_0_8px_rgba(245,158,11,0.12)]'
                  : wsStatus === 'failed'
                  ? 'text-rose-600 dark:text-rose-400 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 shadow-[0_0_8px_rgba(244,63,94,0.12)]'
                  : 'text-slate-500 dark:text-gray-400 bg-slate-500/10 hover:bg-slate-500/20 border border-slate-500/30'
              }`}
            >
              <span className="relative flex h-1.5 w-1.5">
                {wsStatus === 'connected' && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                )}
                {wsStatus === 'reconnecting' && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                )}
                <span
                  className={`relative inline-flex rounded-full h-1.5 w-1.5 ${
                    wsStatus === 'connected'
                      ? 'bg-[#0ecb81]'
                      : wsStatus === 'reconnecting'
                      ? 'bg-amber-400'
                      : wsStatus === 'failed'
                      ? 'bg-rose-500'
                      : 'bg-slate-400'
                  }`}
                />
              </span>
              <span className="font-semibold tracking-wide">
                {wsStatus === 'connected'
                  ? 'НАЖИВО'
                  : wsStatus === 'reconnecting'
                  ? `ВІДНОВЛЕННЯ ${wsDetails?.attempt ? `#${wsDetails.attempt}` : ''}`
                  : wsStatus === 'failed'
                  ? 'ПОМИЛКА'
                  : 'ОФЛАЙН'}
              </span>
              {wsStatus === 'connected' ? (
                <Power className="w-2.5 h-2.5 ml-0.5 text-rose-500 dark:text-rose-400 transition-colors group-hover:text-rose-600 dark:group-hover:text-rose-300" />
              ) : wsStatus === 'reconnecting' ? (
                <RefreshCcw className="w-2.5 h-2.5 animate-spin ml-0.5" />
              ) : (
                <Play className="w-2.5 h-2.5 opacity-70 group-hover:opacity-100 ml-0.5 text-emerald-500" />
              )}
            </button>

            {/* Separator */}
            <span className="h-4 w-px bg-slate-200 dark:bg-[#23272e]" />

            {/* Current Price */}
            <div className="font-mono text-base sm:text-xl font-bold text-[#0ecb81] tracking-tight leading-none flex-shrink-0">
              {price > 0 ? (price < 1 ? price.toFixed(5) : price < 50 ? price.toFixed(3) : price.toFixed(2)) : '---'}
            </div>
          </div>

          {/* Real-time Open Interest Delta Badge (2xl+ screens only to avoid header crowding on laptops) */}
          {oiData && oiData.current_oi !== null && (
            <div
              title={`Hyperliquid OI: ${oiData.current_oi.toLocaleString()} ${coin} (${oiData.current_oi_usd ? '$' + (oiData.current_oi_usd >= 1e9 ? (oiData.current_oi_usd / 1e9).toFixed(2) + 'B' : oiData.current_oi_usd >= 1e6 ? (oiData.current_oi_usd / 1e6).toFixed(2) + 'M' : (oiData.current_oi_usd / 1e3).toFixed(1) + 'K') : ''}) | 1m: ${formatOiDeltaPct(oiData.deltas?.['1m']?.delta_pct)} | 5m: ${formatOiDeltaPct(oiData.deltas?.['5m']?.delta_pct)} | 15m: ${formatOiDeltaPct(oiData.deltas?.['15m']?.delta_pct)} | 1h: ${formatOiDeltaPct(oiData.deltas?.['1h']?.delta_pct)}`}
              className="hidden 2xl:flex items-center gap-2 px-2.5 py-1 rounded bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] text-xs font-mono ml-2 select-none flex-shrink-0"
            >
              <span className="text-slate-400 dark:text-gray-500 font-sans text-[11px] font-medium">OI:</span>
              <span className="text-slate-800 dark:text-gray-200 font-semibold">
                {oiData.current_oi >= 1_000_000
                  ? `${(oiData.current_oi / 1_000_000).toFixed(2)}M`
                  : oiData.current_oi >= 1_000
                  ? `${(oiData.current_oi / 1_000).toFixed(1)}K`
                  : oiData.current_oi.toFixed(1)}{' '}
                <span className="text-[10px] text-slate-400 font-sans">{coin}</span>
              </span>

              {oiData.current_oi_usd && (
                <span className="text-[10px] text-slate-500 dark:text-gray-400 font-sans">
                  (${oiData.current_oi_usd >= 1e9
                    ? `${(oiData.current_oi_usd / 1e9).toFixed(2)}B`
                    : oiData.current_oi_usd >= 1e6
                    ? `${(oiData.current_oi_usd / 1e6).toFixed(2)}M`
                    : `${(oiData.current_oi_usd / 1e3).toFixed(1)}K`})
                </span>
              )}

              {(() => {
                const d5 = oiData.deltas?.['5m'];
                const pct = d5?.delta_pct ?? 0;
                const isGap = d5?.status === 'GAP_DETECTED';
                const isNoHist = d5?.status === 'INSUFFICIENT_HISTORY';
                const isInc = pct > (oiData.volatility_threshold_pct || 0.25);
                const isDec = pct < -(oiData.volatility_threshold_pct || 0.25);
                return (
                  <span
                    className={`flex items-center gap-0.5 text-[11px] font-bold px-1.5 py-0.5 rounded ${
                      isGap
                        ? 'text-amber-500 bg-amber-500/10'
                        : isNoHist
                        ? 'text-slate-400 bg-slate-500/10'
                        : isInc
                        ? 'text-[#0ecb81] bg-emerald-500/10'
                        : isDec
                        ? 'text-[#f6465d] bg-rose-500/10'
                        : 'text-slate-500 dark:text-gray-400 bg-slate-500/10'
                    }`}
                  >
                    {isGap ? (
                      'GAP'
                    ) : isNoHist || d5?.delta_pct === null || d5?.delta_pct === undefined ? (
                      '...'
                    ) : (
                      <>
                        {isInc ? (
                          <TrendingUp className="w-3 h-3" />
                        ) : isDec ? (
                          <TrendingDown className="w-3 h-3" />
                        ) : (
                          <Minus className="w-3 h-3" />
                        )}
                        {formatOiDeltaPct(d5.delta_pct)} (5m)
                      </>
                    )}
                  </span>
                );
              })()}
            </div>
          )}

          {/* Mobile Right Action Icons (Theme, Sidebar, Refresh) */}
          <div className="flex sm:hidden items-center gap-1.5 flex-shrink-0">
            {/* Mobile Theme Toggle Button */}
            <button
              onClick={handleToggleTheme}
              className="p-1.5 rounded bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] text-slate-700 dark:text-gray-300 hover:text-slate-900 dark:hover:text-white transition"
              title={getThemeTitle()}
            >
              {getThemeIcon()}
            </button>

            {/* Mobile Sidebar Toggle Button */}
            {onToggleSidebar && (
              <button
                onClick={onToggleSidebar}
                className={`p-1.5 rounded border transition flex items-center justify-center cursor-pointer ${
                  isSidebarOpen
                    ? 'bg-emerald-500/15 text-[#0ecb81] border-emerald-500/40'
                    : 'bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] text-slate-700 dark:text-gray-300 hover:text-slate-900 dark:hover:text-white'
                }`}
                title="Рівні та формації"
              >
                <SlidersHorizontal className="w-3.5 h-3.5" />
              </button>
            )}

            {/* Refresh button */}
            <button
              onClick={onRefresh}
              disabled={isLoading}
              className="p-1.5 rounded bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] hover:bg-slate-200 dark:hover:bg-[#1e2329] text-slate-600 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white transition disabled:opacity-50"
              title="Оновити дані"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-emerald-500 dark:text-emerald-400' : ''}`} />
            </button>
          </div>
        </div>

        {/* Desktop Controls (Right side on sm+) */}
        <div className="hidden sm:flex items-center gap-2 flex-shrink-0">
          {/* Compact Theme Toggle Button (1-click cycle on screens < 2xl) */}
          <div className="2xl:hidden flex items-center bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] rounded p-0.5">
            <button
              onClick={handleToggleTheme}
              className="p-1.5 rounded text-slate-700 dark:text-gray-300 hover:text-slate-900 dark:hover:text-white transition"
              title={getThemeTitle()}
            >
              {getThemeIcon()}
            </button>
          </div>

          {/* Expanded Theme Mode Switcher on 2xl+ monitors (Light / Dark / Auto) */}
          <div className="hidden 2xl:flex items-center bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] rounded p-0.5 text-xs">
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
              <span className="text-[11px]">Світла</span>
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
              <span className="text-[11px]">Темна</span>
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
              <span className="text-[11px]">Авто</span>
            </button>
          </div>

          {/* Desktop Timeframe selector */}
          <div className="flex items-center bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] rounded p-0.5">
            {timeframes.map((tf) => {
              const isSelected = timeframe.toLowerCase() === tf.toLowerCase();
              const label = tf.toLowerCase() === '1h' ? '1H' : tf.toLowerCase() === '4h' ? '4H' : tf;
              return (
                <button
                  key={tf}
                  onClick={() => onTimeframeChange(tf)}
                  className={`px-1.5 sm:px-2 py-0.5 sm:py-1 text-[11px] sm:text-xs font-semibold rounded transition cursor-pointer ${
                    isSelected
                      ? 'bg-white dark:bg-[#2b313a] text-slate-900 dark:text-white shadow-sm'
                      : 'text-slate-500 dark:text-gray-400 hover:text-slate-900 dark:hover:text-gray-200'
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>

          {/* Sidebar Toggle Button (Desktop & Tablet) */}
          {onToggleSidebar && (
            <button
              onClick={onToggleSidebar}
              className={`p-1.5 rounded border transition flex items-center gap-1 cursor-pointer ${
                isSidebarOpen
                  ? 'bg-emerald-500/15 text-[#0ecb81] border-emerald-500/40'
                  : 'bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] text-slate-700 dark:text-gray-300 hover:text-slate-900 dark:hover:text-white'
              }`}
              title={isSidebarOpen ? 'Приховати рівні та формації' : 'Показати рівні та формації'}
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
            </button>
          )}

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

        {/* Mobile Row 2: Full-width responsive Timeframe bar (< sm) */}
        <div className="sm:hidden grid grid-cols-6 gap-1 w-full bg-slate-100 dark:bg-[#15191e] border border-slate-300 dark:border-[#23272e] rounded p-0.5">
          {timeframes.map((tf) => {
            const isSelected = timeframe.toLowerCase() === tf.toLowerCase();
            const label = tf.toLowerCase() === '1h' ? '1H' : tf.toLowerCase() === '4h' ? '4H' : tf;
            return (
              <button
                key={tf}
                onClick={() => onTimeframeChange(tf)}
                className={`py-1 text-center text-xs font-semibold rounded transition cursor-pointer ${
                  isSelected
                    ? 'bg-white dark:bg-[#2b313a] text-slate-900 dark:text-white shadow-sm'
                    : 'text-slate-500 dark:text-gray-400 hover:text-slate-900 dark:hover:text-gray-200'
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
};
