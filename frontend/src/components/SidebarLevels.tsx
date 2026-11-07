import React from 'react';
import { LevelItem, SignalItem, AnalysisData, FormationFilter, OIData } from '../types';
import { Activity, BarChart2 } from 'lucide-react';

interface SidebarLevelsProps {
  resistances: LevelItem[];
  supports: LevelItem[];
  signals: SignalItem[];
  structure?: AnalysisData['structure'];
  openInterest?: number;
  fundingRate?: number;
  activeFormation: FormationFilter;
  onSelectSignal?: (sig: SignalItem) => void;
  oiData?: OIData;
}

export const SidebarLevels: React.FC<SidebarLevelsProps> = ({
  resistances,
  supports,
  signals,
  structure,
  openInterest,
  fundingRate,
  activeFormation,
  onSelectSignal,
  oiData,
}) => {
  const filteredSignals = signals.filter((sig) => {
    if (activeFormation === 'NONE') return false;
    if (activeFormation === 'CASCADE') return sig.category === 'cascade';
    if (activeFormation === 'SWEEP') return sig.category === 'sweep';
    if (activeFormation === 'TRENDLINE') return sig.category === 'trendline';
    if (activeFormation === 'FVG') return sig.category === 'fvg';
    return false;
  });

  const allLevelsCount = resistances.length + supports.length;

  return (
    <aside className="w-80 h-full border-l border-slate-200 dark:border-[#1e2329] bg-white dark:bg-[#0e1114] flex flex-col select-none text-xs transition-colors">
      
      {/* 1. Market Structure & Trend Header */}
      {structure && (
        <div className="p-3 border-b border-slate-200 dark:border-[#1e2329] bg-slate-50/70 dark:bg-[#15191e]/50 flex-shrink-0">
          <div className="flex items-center justify-between mb-1">
            <span className="text-slate-500 dark:text-gray-400 font-medium flex items-center gap-1.5 uppercase text-[11px] tracking-wider">
              <Activity className="w-3.5 h-3.5 text-blue-500 dark:text-blue-400" /> СТРУКТУРА ТА ТРЕНД
            </span>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                structure.trend === 'BULLISH'
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-[#0ecb81]'
                  : structure.trend === 'BEARISH'
                  ? 'bg-rose-500/10 text-[#f6465d]'
                  : 'bg-amber-500/10 text-amber-600 dark:text-yellow-400'
              }`}
            >
              {structure.trend}
            </span>
          </div>
          <div className="text-slate-700 dark:text-gray-300 font-medium text-[11px] mt-0.5">
            {structure.summary}
          </div>

          {(openInterest !== undefined || fundingRate !== undefined) && (
            <div className="mt-2 pt-2 border-t border-slate-200 dark:border-[#1e2329]/60 flex justify-between text-[11px] text-slate-500 dark:text-gray-400">
              {openInterest !== undefined && (
                <div>
                  <span className="text-slate-400 dark:text-gray-500">OI: </span>
                  <span className="text-slate-800 dark:text-gray-200 font-mono font-medium">{openInterest.toLocaleString(undefined, { maximumFractionDigits: 1 })}</span>
                </div>
              )}
              {fundingRate !== undefined && (
                <div>
                  <span className="text-slate-400 dark:text-gray-500">Funding: </span>
                  <span className={`font-mono font-medium ${fundingRate >= 0 ? 'text-[#0ecb81]' : 'text-[#f6465d]'}`}>
                    {(fundingRate * 100).toFixed(4)}%
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 2. Open Interest (OI) Delta & Breakout Confirmation */}
      <div className="p-3 border-b border-slate-200 dark:border-[#1e2329] bg-slate-50/50 dark:bg-[#15191e]/40 flex-shrink-0">
        <div className="flex items-center justify-between mb-2">
          <span className="text-slate-500 dark:text-gray-400 font-medium flex items-center gap-1.5 uppercase text-[11px] tracking-wider">
            <BarChart2 className="w-3.5 h-3.5 text-emerald-500" /> ДЕТЕКЦІЯ OI DELTA
          </span>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
              oiData?.oi_status === 'INCREASING'
                ? 'bg-emerald-500/10 text-[#0ecb81]'
                : oiData?.oi_status === 'DECREASING'
                ? 'bg-rose-500/10 text-[#f6465d]'
                : 'bg-slate-500/10 text-slate-500 dark:text-gray-400'
            }`}
          >
            {oiData?.oi_status || 'NEUTRAL'}
          </span>
        </div>

        {/* Current OI & Volatility threshold */}
        <div className="flex flex-col gap-0.5 mb-2 text-[11px]">
          <div className="flex justify-between items-baseline">
            <span className="text-slate-400 dark:text-gray-500">Базовий OI: </span>
            <span className="text-slate-800 dark:text-gray-100 font-mono font-bold">
              {oiData?.current_oi !== null && oiData?.current_oi !== undefined
                ? oiData.current_oi.toLocaleString(undefined, { maximumFractionDigits: 1 })
                : openInterest !== undefined
                ? openInterest.toLocaleString(undefined, { maximumFractionDigits: 1 })
                : '---'}{' '}
              <span className="text-[10px] text-slate-400 font-sans font-normal">{oiData?.coin || ''}</span>
            </span>
          </div>

          {oiData?.current_oi_usd && (
            <div className="flex justify-between items-baseline text-[10px]">
              <span className="text-slate-400 dark:text-gray-500">USD Notional: </span>
              <span className="text-slate-600 dark:text-gray-300 font-mono font-medium">
                ${oiData.current_oi_usd >= 1e9
                  ? `${(oiData.current_oi_usd / 1e9).toFixed(2)}B`
                  : `${(oiData.current_oi_usd / 1e6).toFixed(2)}M`}
              </span>
            </div>
          )}

          <div className="flex justify-between items-baseline text-[10px] text-slate-400 dark:text-gray-500 font-mono mt-0.5">
            <span>Поріг чутливості θ:</span>
            <span className={oiData?.volatility_info?.is_adaptive ? 'text-emerald-500' : 'text-slate-400'}>
              ±{(oiData?.volatility_threshold_pct ?? 0.25).toFixed(2)}%
              {oiData?.volatility_info?.is_adaptive ? ' (адапт.)' : ' (фікс.)'}
            </span>
          </div>
        </div>

        {/* Multi-Interval Delta Grid: 1m, 5m, 15m, 1h */}
        <div className="grid grid-cols-4 gap-1 mb-2 font-mono text-[10px]">
          {(['1m', '5m', '15m', '1h'] as const).map((intv) => {
            const d = oiData?.deltas?.[intv];
            const pct = d?.delta_pct ?? 0;
            const thresh = oiData?.volatility_threshold_pct ?? 0.25;
            const isGap = d?.status === 'GAP_DETECTED';
            const isNoHist = d?.status === 'INSUFFICIENT_HISTORY';
            const isInc = pct > thresh;
            const isDec = pct < -thresh;
            const colorClass = isGap
              ? 'text-amber-500 bg-amber-500/10 border-amber-500/20'
              : isNoHist
              ? 'text-slate-400 bg-slate-100 dark:bg-[#1e2329]/30 border-slate-200 dark:border-[#2b313a]'
              : isInc
              ? 'text-[#0ecb81] bg-emerald-500/10 border-emerald-500/20'
              : isDec
              ? 'text-[#f6465d] bg-rose-500/10 border-rose-500/20'
              : 'text-slate-500 dark:text-gray-400 bg-slate-100 dark:bg-[#1e2329]/50 border-slate-200 dark:border-[#2b313a]';

            return (
              <div key={intv} className={`p-1 rounded border flex flex-col items-center justify-center ${colorClass}`}>
                <span className="text-[9px] text-slate-400 dark:text-gray-500 font-sans">{intv}</span>
                <span className="font-bold">
                  {isGap ? (
                    'GAP'
                  ) : isNoHist ? (
                    '...'
                  ) : pct > 0 ? (
                    `+${pct.toFixed(1)}%`
                  ) : (
                    `${pct.toFixed(1)}%`
                  )}
                </span>
              </div>
            );
          })}
        </div>

        {/* Level Breakout / Interaction Analysis Card */}
        {oiData?.breakout_signals && oiData.breakout_signals.length > 0 ? (
          <div className="space-y-1.5 mt-2">
            {oiData.breakout_signals.slice(0, 2).map((sig) => (
              <div
                key={sig.level_id}
                className={`p-2 rounded border text-[11px] ${
                  sig.badge_color === 'green'
                    ? 'border-emerald-500/30 bg-emerald-500/5 text-emerald-800 dark:text-emerald-200'
                    : sig.badge_color === 'red'
                    ? 'border-rose-500/30 bg-rose-500/5 text-rose-800 dark:text-rose-200'
                    : sig.badge_color === 'amber'
                    ? 'border-amber-500/30 bg-amber-500/5 text-amber-800 dark:text-amber-200'
                    : 'border-slate-300 dark:border-gray-700 bg-slate-100/50 dark:bg-gray-800/30 text-slate-700 dark:text-gray-300'
                }`}
              >
                <div className="flex justify-between items-center font-bold mb-1">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`text-[9px] px-1 py-0.2 rounded font-sans font-bold ${
                        sig.direction === 'UP'
                          ? 'bg-emerald-500/20 text-[#0ecb81]'
                          : 'bg-rose-500/20 text-[#f6465d]'
                      }`}
                    >
                      {sig.direction === 'UP' ? 'LONG' : 'SHORT'}
                    </span>
                    <span className="text-[10px] truncate">{sig.status}</span>
                  </div>
                  <span className="font-mono text-[10px] font-bold">
                    {sig.oi_delta_pct > 0 ? `+${sig.oi_delta_pct.toFixed(2)}%` : `${sig.oi_delta_pct.toFixed(2)}%`}
                  </span>
                </div>
                <div className="text-[10px] leading-tight opacity-90">{sig.interpretation}</div>
                <div className="mt-1 pt-1 border-t border-current/10 flex justify-between text-[9px] opacity-75 font-mono">
                  <span>Рівень: {sig.level_price}</span>
                  <span>Час: {sig.duration_seconds.toFixed(0)}s</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[10px] text-slate-400 dark:text-gray-500 italic py-0.5">
            Ціна поза зоною пробою / тестування ключових рівнів.
          </div>
        )}
      </div>

      {/* 3. Found Formations Section */}
      <div className="p-3 border-b border-slate-200 dark:border-[#1e2329] flex-shrink-0">
        <div className="flex items-center justify-between text-slate-500 dark:text-gray-400 text-[11px] font-semibold tracking-wider uppercase mb-2">
          <span>ЗНАЙДЕНІ ФОРМАЦІЇ · {filteredSignals.length}</span>
        </div>

        {filteredSignals.length === 0 ? (
          <p className="text-slate-400 dark:text-gray-500 text-[11px] leading-relaxed py-1">
            Для цієї формації зараз немає сигналів, лише лінії на графіку.
          </p>
        ) : (
          <div className="space-y-1.5 max-h-44 overflow-y-auto pr-1">
            {filteredSignals.map((sig) => (
              <div
                key={sig.id}
                onClick={() => onSelectSignal?.(sig)}
                className="p-2 rounded bg-slate-50 dark:bg-[#15191e] border border-slate-200 dark:border-[#23272e] hover:border-slate-400 dark:hover:border-gray-500 cursor-pointer transition flex flex-col gap-1"
              >
                <div className="flex items-center justify-between">
                  <span className="text-slate-800 dark:text-gray-200 font-semibold text-[11px]">{sig.title}</span>
                  <span
                    className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                      sig.direction === 'LONG'
                        ? 'bg-emerald-500/20 text-[#0ecb81]'
                        : sig.direction === 'SHORT'
                        ? 'bg-rose-500/20 text-[#f6465d]'
                        : 'bg-gray-500/20 text-gray-400'
                    }`}
                  >
                    {sig.direction}
                  </span>
                </div>
                <div className="text-[10px] text-slate-500 dark:text-gray-400 leading-snug">{sig.desc}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 4. Lines & Zones on Chart Section */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col">
        <div className="text-slate-500 dark:text-gray-400 text-[11px] font-semibold tracking-wider uppercase mb-2">
          ЗОНИ ТА РІВНІ · {allLevelsCount}
        </div>

        <div className="space-y-1 font-mono">
          {/* Resistances (Red Dots) */}
          {resistances.map((r, idx) => (
            <div
              key={`r-${idx}`}
              className="flex items-center justify-between py-1 px-1.5 rounded hover:bg-slate-100 dark:hover:bg-[#15191e] transition text-[11px]"
            >
              <div className="flex items-center gap-1.5 text-slate-700 dark:text-gray-300 overflow-hidden">
                <span className="w-1.5 h-1.5 rounded-full bg-[#f6465d] flex-shrink-0" />
                {r.timeframe && (
                  <span className="px-1 py-0.2 rounded bg-blue-500/20 text-blue-500 dark:text-blue-300 text-[9px] font-bold flex-shrink-0">
                    {r.timeframe.replace('h', 'H').replace('d', 'D')}
                  </span>
                )}
                <span title={`Діапазон зони: ${r.bottom} - ${r.top}`} className="truncate">
                  Опір {r.price} {r.touches > 1 ? <span className="text-slate-400 dark:text-gray-500">x{r.touches}</span> : ''}
                </span>
                {/* strength_score progress bar */}
                {r.strength_score !== undefined && (
                  <span className="flex items-center gap-1 ml-1 flex-shrink-0">
                    <span
                      className="inline-block h-1.5 rounded-full bg-[#f6465d]/60"
                      style={{ width: `${Math.round(r.strength_score / 100 * 28)}px`, minWidth: '2px' }}
                    />
                    <span className="text-[9px] text-slate-400 dark:text-gray-500">{Math.round(r.strength_score)}</span>
                  </span>
                )}
                {/* status badge (skip 'active') */}
                {r.status && r.status !== 'active' && (
                  <span
                    className={`text-[9px] font-bold px-1 py-0.5 rounded flex-shrink-0 ${
                      r.status === 'retested'
                        ? 'bg-blue-500/15 text-blue-500 dark:text-blue-400'
                        : 'bg-amber-500/15 text-amber-600 dark:text-yellow-400'
                    }`}
                  >
                    {r.status === 'retested' ? 'Дзерк' : 'Ослабл'}
                  </span>
                )}
              </div>
              <span className="text-[#f6465d] font-semibold flex-shrink-0 ml-1">
                {r.distPct >= 0 ? `+${r.distPct.toFixed(2)}%` : `${r.distPct.toFixed(2)}%`}
              </span>
            </div>
          ))}

          {/* Supports (Green Dots) */}
          {supports.map((s, idx) => (
            <div
              key={`s-${idx}`}
              className="flex items-center justify-between py-1 px-1.5 rounded hover:bg-slate-100 dark:hover:bg-[#15191e] transition text-[11px]"
            >
              <div className="flex items-center gap-1.5 text-slate-700 dark:text-gray-300 overflow-hidden">
                <span className="w-1.5 h-1.5 rounded-full bg-[#0ecb81] flex-shrink-0" />
                {s.timeframe && (
                  <span className="px-1 py-0.2 rounded bg-blue-500/20 text-blue-500 dark:text-blue-300 text-[9px] font-bold flex-shrink-0">
                    {s.timeframe.replace('h', 'H').replace('d', 'D')}
                  </span>
                )}
                <span title={`Діапазон зони: ${s.bottom} - ${s.top}`} className="truncate">
                  Підтримка {s.price} {s.touches > 1 ? <span className="text-slate-400 dark:text-gray-500">x{s.touches}</span> : ''}
                </span>
                {/* strength_score progress bar */}
                {s.strength_score !== undefined && (
                  <span className="flex items-center gap-1 ml-1 flex-shrink-0">
                    <span
                      className="inline-block h-1.5 rounded-full bg-[#0ecb81]/60"
                      style={{ width: `${Math.round(s.strength_score / 100 * 28)}px`, minWidth: '2px' }}
                    />
                    <span className="text-[9px] text-slate-400 dark:text-gray-500">{Math.round(s.strength_score)}</span>
                  </span>
                )}
                {/* status badge (skip 'active') */}
                {s.status && s.status !== 'active' && (
                  <span
                    className={`text-[9px] font-bold px-1 py-0.5 rounded flex-shrink-0 ${
                      s.status === 'retested'
                        ? 'bg-blue-500/15 text-blue-500 dark:text-blue-400'
                        : 'bg-amber-500/15 text-amber-600 dark:text-yellow-400'
                    }`}
                  >
                    {s.status === 'retested' ? 'Дзерк' : 'Ослабл'}
                  </span>
                )}
              </div>
              <span className="text-[#0ecb81] font-semibold flex-shrink-0 ml-1">
                {s.distPct.toFixed(2)}%
              </span>
            </div>
          ))}

          {allLevelsCount === 0 && (
            <div className="text-slate-400 dark:text-gray-600 text-center py-4">Зон не виявлено</div>
          )}
        </div>
      </div>

      {/* Bottom Explanatory Help */}
      <div className="p-2.5 border-t border-slate-200 dark:border-[#1e2329] text-[10px] text-slate-400 dark:text-gray-500 leading-tight bg-slate-50/70 dark:bg-[#0b0e11]/50">
        Мульти-таймфреймові рівні: кожен таймфрейм розраховується незалежно та має власний колір і статус.
      </div>
    </aside>
  );
};
