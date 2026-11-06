import React from 'react';
import { LevelItem, SignalItem, AnalysisData, FormationFilter } from '../types';
import { TrendingUp, TrendingDown, Activity, Minus } from 'lucide-react';

interface SidebarLevelsProps {
  resistances: LevelItem[];
  supports: LevelItem[];
  signals: SignalItem[];
  structure?: AnalysisData['structure'];
  openInterest?: number;
  fundingRate?: number;
  activeFormation: FormationFilter;
  onSelectSignal?: (sig: SignalItem) => void;
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
    <aside className="w-80 h-full border-l border-[#1e2329] bg-[#0e1114] flex flex-col select-none text-xs">
      
      {/* 1. Market Structure & Trend Header */}
      {structure && (
        <div className="p-3 border-b border-[#1e2329] bg-[#15191e]/50">
          <div className="flex items-center justify-between mb-1">
            <span className="text-gray-400 font-medium flex items-center gap-1.5 uppercase text-[11px] tracking-wider">
              <Activity className="w-3.5 h-3.5 text-blue-400" /> СТРУКТУРА ТА ТРЕНД
            </span>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                structure.trend === 'BULLISH'
                  ? 'bg-emerald-500/10 text-[#0ecb81]'
                  : structure.trend === 'BEARISH'
                  ? 'bg-rose-500/10 text-[#f6465d]'
                  : 'bg-yellow-500/10 text-yellow-400'
              }`}
            >
              {structure.trend}
            </span>
          </div>
          <div className="text-gray-300 font-medium text-[11px] mt-0.5">
            {structure.summary}
          </div>

          {(openInterest !== undefined || fundingRate !== undefined) && (
            <div className="mt-2 pt-2 border-t border-[#1e2329]/60 flex justify-between text-[11px] text-gray-400">
              {openInterest !== undefined && (
                <div>
                  <span className="text-gray-500">OI: </span>
                  <span className="text-gray-200 font-mono font-medium">{openInterest.toLocaleString(undefined, { maximumFractionDigits: 1 })}</span>
                </div>
              )}
              {fundingRate !== undefined && (
                <div>
                  <span className="text-gray-500">Funding: </span>
                  <span className={`font-mono font-medium ${fundingRate >= 0 ? 'text-[#0ecb81]' : 'text-[#f6465d]'}`}>
                    {(fundingRate * 100).toFixed(4)}%
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 2. Found Formations Section */}
      <div className="p-3 border-b border-[#1e2329] flex-shrink-0">
        <div className="flex items-center justify-between text-gray-400 text-[11px] font-semibold tracking-wider uppercase mb-2">
          <span>ЗНАЙДЕНІ ФОРМАЦІЇ · {filteredSignals.length}</span>
        </div>

        {filteredSignals.length === 0 ? (
          <p className="text-gray-500 text-[11px] leading-relaxed py-1">
            Для цієї формації зараз немає сигналів, лише лінії на графіку.
          </p>
        ) : (
          <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
            {filteredSignals.map((sig) => (
              <div
                key={sig.id}
                onClick={() => onSelectSignal?.(sig)}
                className="p-2 rounded bg-[#15191e] border border-[#23272e] hover:border-gray-500 cursor-pointer transition flex flex-col gap-1"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-gray-200 text-[11px] flex items-center gap-1">
                    {sig.direction === 'LONG' ? (
                      <TrendingUp className="w-3 h-3 text-[#0ecb81]" />
                    ) : sig.direction === 'SHORT' ? (
                      <TrendingDown className="w-3 h-3 text-[#f6465d]" />
                    ) : (
                      <Minus className="w-3 h-3 text-yellow-400" />
                    )}
                    {sig.title}
                  </span>
                  <span
                    className={`text-[9px] font-bold px-1.5 py-0.2 rounded ${
                      sig.direction === 'LONG'
                        ? 'bg-emerald-500/20 text-[#0ecb81]'
                        : sig.direction === 'SHORT'
                        ? 'bg-rose-500/20 text-[#f6465d]'
                        : 'bg-yellow-500/20 text-yellow-400'
                    }`}
                  >
                    {sig.direction}
                  </span>
                </div>
                <div className="text-[10px] text-gray-400 leading-snug">{sig.desc}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 3. Lines & Zones on Chart Section */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col">
        <div className="text-gray-400 text-[11px] font-semibold tracking-wider uppercase mb-2">
          ЗОНИ ТА РІВНІ · {allLevelsCount}
        </div>

        <div className="space-y-1 font-mono">
          {/* Resistances (Red Dots) */}
          {resistances.map((r, idx) => (
            <div
              key={`r-${idx}`}
              className="flex items-center justify-between py-1 px-1.5 rounded hover:bg-[#15191e] transition text-[11px]"
            >
              <div className="flex items-center gap-2 text-gray-300">
                <span className="w-1.5 h-1.5 rounded-full bg-[#f6465d] flex-shrink-0" />
                <span title={`Діапазон зони: ${r.bottom} - ${r.top}`}>
                  Опір {r.price} {r.touches > 1 ? <span className="text-gray-500">x{r.touches}</span> : ''}
                </span>
                {/* strength_score progress bar */}
                {r.strength_score !== undefined && (
                  <span className="flex items-center gap-1 ml-1">
                    <span
                      className="inline-block h-1.5 rounded-full bg-[#f6465d]/60"
                      style={{ width: `${Math.round(r.strength_score / 100 * 32)}px`, minWidth: '2px' }}
                    />
                    <span className="text-[9px] text-gray-500">{Math.round(r.strength_score)}</span>
                  </span>
                )}
                {/* status badge (skip 'active') */}
                {r.status && r.status !== 'active' && (
                  <span
                    className={`text-[9px] font-bold px-1 py-0.5 rounded ${
                      r.status === 'retested'
                        ? 'bg-blue-500/15 text-blue-400'
                        : 'bg-yellow-500/15 text-yellow-400'
                    }`}
                  >
                    {r.status === 'retested' ? 'Дзеркальний' : 'Ослаблений'}
                  </span>
                )}
                {/* average bounce */}
                {r.average_bounce_atr !== undefined && r.average_bounce_atr > 0 && (
                  <span className="text-[9px] text-gray-500">~{r.average_bounce_atr.toFixed(1)}ATR</span>
                )}
              </div>
              <span className="text-[#f6465d] font-semibold">
                {r.distPct >= 0 ? `+${r.distPct.toFixed(2)}%` : `${r.distPct.toFixed(2)}%`}
              </span>
            </div>
          ))}

          {/* Supports (Green Dots) */}
          {supports.map((s, idx) => (
            <div
              key={`s-${idx}`}
              className="flex items-center justify-between py-1 px-1.5 rounded hover:bg-[#15191e] transition text-[11px]"
            >
              <div className="flex items-center gap-2 text-gray-300">
                <span className="w-1.5 h-1.5 rounded-full bg-[#0ecb81] flex-shrink-0" />
                <span title={`Діапазон зони: ${s.bottom} - ${s.top}`}>
                  Підтримка {s.price} {s.touches > 1 ? <span className="text-gray-500">x{s.touches}</span> : ''}
                </span>
                {/* strength_score progress bar */}
                {s.strength_score !== undefined && (
                  <span className="flex items-center gap-1 ml-1">
                    <span
                      className="inline-block h-1.5 rounded-full bg-[#0ecb81]/60"
                      style={{ width: `${Math.round(s.strength_score / 100 * 32)}px`, minWidth: '2px' }}
                    />
                    <span className="text-[9px] text-gray-500">{Math.round(s.strength_score)}</span>
                  </span>
                )}
                {/* status badge (skip 'active') */}
                {s.status && s.status !== 'active' && (
                  <span
                    className={`text-[9px] font-bold px-1 py-0.5 rounded ${
                      s.status === 'retested'
                        ? 'bg-blue-500/15 text-blue-400'
                        : 'bg-yellow-500/15 text-yellow-400'
                    }`}
                  >
                    {s.status === 'retested' ? 'Дзеркальний' : 'Ослаблений'}
                  </span>
                )}
                {/* average bounce */}
                {s.average_bounce_atr !== undefined && s.average_bounce_atr > 0 && (
                  <span className="text-[9px] text-gray-500">~{s.average_bounce_atr.toFixed(1)}ATR</span>
                )}
              </div>
              <span className="text-[#0ecb81] font-semibold">
                {s.distPct.toFixed(2)}%
              </span>
            </div>
          ))}

          {allLevelsCount === 0 && (
            <div className="text-gray-600 text-center py-4">Зон не виявлено</div>
          )}
        </div>
      </div>

      {/* Bottom Explanatory Help */}
      <div className="p-2.5 border-t border-[#1e2329] text-[10px] text-gray-500 leading-tight bg-[#0b0e11]/50">
        Формації шукаються за правилами: зони підтримки/опору формуються кластеризацією свінгів з урахуванням тіла та тіней свічок. Зони FVG виділяються кольоровими прямокутниками.
      </div>
    </aside>
  );
};
