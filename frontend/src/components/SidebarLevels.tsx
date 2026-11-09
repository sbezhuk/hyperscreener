import React, { useState } from 'react';
import { LevelItem, SignalItem, AnalysisData, FormationFilter, OIData, formatOiDeltaPct, PivotPointsData, TradeSetup } from '../types';
import { Activity, BarChart2, X, TrendingUp, TrendingDown, Target, Shield, CheckCircle2, AlertCircle, Compass, ChevronDown, ChevronUp, Copy, Check, Sparkles } from 'lucide-react';

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
  onlyConfirmedOi?: boolean;
  onClose?: () => void;
  pivotPoints?: PivotPointsData;
  tradeSetup?: TradeSetup;
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
  onlyConfirmedOi = false,
  onClose,
  pivotPoints,
  tradeSetup,
}) => {
  const filteredSignals = signals.filter((sig) => {
    if (activeFormation === 'NONE') return false;
    if (activeFormation === 'CASCADE') return sig.category === 'cascade';
    if (activeFormation === 'SWEEP') {
      if (sig.category !== 'sweep') return false;
      if (onlyConfirmedOi && sig.confirmationStatus !== 'CONFIRMED' && !sig.oiConfirmed) {
        return false;
      }
      return true;
    }
    if (activeFormation === 'TRENDLINE') return sig.category === 'trendline';
    if (activeFormation === 'FVG') return sig.category === 'fvg';
    return false;
  });

  const allLevelsCount = resistances.length + supports.length;
  const [isDetailsOpen, setIsDetailsOpen] = useState(true);
  const [isCopied, setIsCopied] = useState(false);

  const handleCopySetup = () => {
    if (!tradeSetup || tradeSetup.entry_price === null) return;
    const text = `${tradeSetup.coin} [${tradeSetup.direction}]
Вхід: $${tradeSetup.entry_price} (${tradeSetup.entry_range ? `${tradeSetup.entry_range[0]} - ${tradeSetup.entry_range[1]}` : 'маркет'})
Stop Loss: $${tradeSetup.stop_loss} (-${tradeSetup.risk_pct}%)
Take Profit: $${tradeSetup.take_profit} (+${tradeSetup.reward_pct}%)
Risk/Reward: 1:${tradeSetup.risk_reward?.toFixed(1)}
Тригер: ${tradeSetup.primary_trigger || 'Конфлюенс формацій'}`;
    navigator.clipboard.writeText(text);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  return (
    <aside className="w-full h-full border-l border-slate-200 dark:border-[#1e2329] bg-white dark:bg-[#0e1114] flex flex-col select-none text-xs transition-colors overflow-hidden">
      
      {/* Sidebar Header with Close Button */}
      {onClose && (
        <div className="p-2.5 sm:p-3 border-b border-slate-200 dark:border-[#1e2329] flex items-center justify-between bg-slate-100 dark:bg-[#15191e] flex-shrink-0">
          <span className="font-semibold text-slate-800 dark:text-gray-200 text-xs uppercase tracking-wider">
            Рівні та формації
          </span>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-200 dark:hover:bg-[#1e2329] text-slate-500 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white transition cursor-pointer"
            title="Закрити панель"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Unified Scrollable Container for All Sidebar Content */}
      <div className="flex-1 overflow-y-auto overscroll-contain divide-y divide-slate-200 dark:divide-[#1e2329]">
        {/* 0. SUMMARY TRADE SIGNAL & SETUP (RR >= 1:3) */}
        {tradeSetup && (
          <div className="p-3 bg-gradient-to-b from-slate-50 to-white dark:from-[#13171d] dark:to-[#0e1114]">
            {/* Header row */}
            <div className="flex items-center justify-between mb-2">
              <span className="text-slate-500 dark:text-gray-400 font-semibold flex items-center gap-1.5 uppercase text-[11px] tracking-wider whitespace-nowrap">
                <Compass className="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400 flex-shrink-0" />
                ТОРГОВИЙ СИГНАЛ
              </span>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-bold whitespace-nowrap ${
                    tradeSetup.confluence_score >= 70
                      ? 'bg-indigo-500/15 text-indigo-700 dark:text-indigo-400 border border-indigo-500/30'
                      : 'bg-slate-200 dark:bg-[#1f242d] text-slate-600 dark:text-gray-400'
                  }`}
                  title="Оцінка конфлюенсу формацій"
                >
                  ЗБІГ {tradeSetup.confluence_score}%
                </span>
                <button
                  onClick={() => setIsDetailsOpen(!isDetailsOpen)}
                  className="p-1 rounded hover:bg-slate-200 dark:hover:bg-[#1f242d] text-slate-400 hover:text-slate-600 dark:hover:text-gray-200 transition"
                  title={isDetailsOpen ? "Згорнути деталі" : "Розгорнути деталі"}
                >
                  {isDetailsOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>

            {/* Main Action Banner */}
            <div
              className={`p-2.5 rounded-lg border transition-all ${
                tradeSetup.direction === 'LONG'
                  ? 'bg-emerald-500/[0.04] dark:bg-emerald-950/20 border-emerald-300/80 dark:border-emerald-500/30 shadow-xs'
                  : tradeSetup.direction === 'SHORT'
                  ? 'bg-rose-500/[0.04] dark:bg-rose-950/20 border-rose-300/80 dark:border-rose-500/30 shadow-xs'
                  : 'bg-slate-50 dark:bg-[#14181f] border-slate-200 dark:border-[#222832]'
              }`}
            >
              {/* Status Header: Row 1 = Direction Badge + RR Badge; Row 2 = Full Trigger Description */}
              <div className="pb-2 border-b border-slate-200/60 dark:border-[#202632] space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={`px-2 py-0.5 rounded-md text-xs font-black tracking-wider uppercase flex items-center gap-1.5 flex-shrink-0 ${
                      tradeSetup.direction === 'LONG'
                        ? 'bg-emerald-500/15 text-emerald-700 dark:text-[#0ecb81] border border-emerald-500/30'
                        : tradeSetup.direction === 'SHORT'
                        ? 'bg-rose-500/15 text-rose-700 dark:text-[#f6465d] border border-rose-500/30'
                        : 'bg-slate-200 dark:bg-[#1e2329] text-slate-600 dark:text-gray-400'
                    }`}
                  >
                    {tradeSetup.direction === 'LONG' ? (
                      <TrendingUp className="w-3.5 h-3.5 flex-shrink-0" />
                    ) : tradeSetup.direction === 'SHORT' ? (
                      <TrendingDown className="w-3.5 h-3.5 flex-shrink-0" />
                    ) : (
                      <AlertCircle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
                    )}
                    {tradeSetup.direction === 'LONG' ? 'LONG' : tradeSetup.direction === 'SHORT' ? 'SHORT' : 'WAIT'}
                  </span>

                  {tradeSetup.risk_reward && (
                    <div className="flex items-center gap-1 flex-shrink-0 whitespace-nowrap">
                      <span className="text-[10px] text-slate-400 font-mono font-medium">RR</span>
                      <span className="text-xs font-mono font-black text-emerald-600 dark:text-[#0ecb81] bg-emerald-500/15 px-2 py-0.5 rounded border border-emerald-500/30 whitespace-nowrap">
                        1 : {tradeSetup.risk_reward.toFixed(1)}
                      </span>
                    </div>
                  )}
                </div>

                {(tradeSetup.primary_trigger || tradeSetup.status_label) && (
                  <div className="text-[11px] font-medium text-slate-700 dark:text-gray-300 leading-snug">
                    {tradeSetup.primary_trigger || tradeSetup.status_label}
                  </div>
                )}
              </div>

              {/* Active Setup Body */}
              {tradeSetup.entry_price !== null && tradeSetup.stop_loss !== null && tradeSetup.take_profit !== null ? (
                <div className="pt-2 space-y-2">
                  {/* Risk vs Reward Proportion Visual Bar */}
                  <div className="space-y-1">
                    <div className="flex justify-between items-center text-[9px] font-mono">
                      <span className="text-rose-500 font-semibold whitespace-nowrap">РИЗИК 1.0R ({tradeSetup.risk_pct}%)</span>
                      <span className="text-[#0ecb81] font-bold whitespace-nowrap">ТЕЙК {tradeSetup.risk_reward?.toFixed(1)}R (+{tradeSetup.reward_pct}%)</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full overflow-hidden flex bg-slate-200 dark:bg-[#1a1f26]">
                      <div 
                        style={{ width: `${Math.max(12, Math.min(28, (1 / (1 + (tradeSetup.risk_reward || 3))) * 100))}%` }} 
                        className="bg-rose-500 h-full"
                        title={`Ризик: ${tradeSetup.risk_pct}%`}
                      />
                      <div 
                        style={{ width: `${100 - Math.max(12, Math.min(28, (1 / (1 + (tradeSetup.risk_reward || 3))) * 100))}%` }} 
                        className="bg-emerald-500 h-full"
                        title={`Потенціал: +${tradeSetup.reward_pct}% (1:${tradeSetup.risk_reward?.toFixed(1)})`}
                      />
                    </div>
                  </div>

                  {/* Primary Entry Card with full range */}
                  <div className="bg-white dark:bg-[#101419] p-2 rounded-lg border border-slate-200/90 dark:border-[#222832] flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="w-6 h-6 rounded-md bg-blue-500/10 text-blue-500 flex items-center justify-center font-bold flex-shrink-0">
                        <Target className="w-3.5 h-3.5" />
                      </div>
                      <div className="min-w-0">
                        <span className="text-[9px] text-slate-400 dark:text-gray-500 uppercase font-bold tracking-wider block whitespace-nowrap">
                          Вхід (Entry)
                        </span>
                        <span className="text-xs sm:text-sm font-mono font-bold text-slate-900 dark:text-white truncate block">
                          ${tradeSetup.entry_price}
                        </span>
                      </div>
                    </div>
                    {tradeSetup.entry_range && (
                      <div className="text-right flex-shrink-0">
                        <span className="text-[9px] text-slate-400 dark:text-gray-500 uppercase block whitespace-nowrap">Діапазон</span>
                        <span className="text-[10px] font-mono font-medium text-slate-700 dark:text-gray-300 bg-slate-100 dark:bg-[#181d24] px-1.5 py-0.5 rounded border border-slate-200 dark:border-[#252b36] whitespace-nowrap inline-block">
                          {tradeSetup.entry_range[0]} — {tradeSetup.entry_range[1]}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* SL and TP 2-Columns Grid */}
                  <div className="grid grid-cols-2 gap-1.5 font-mono">
                    {/* Stop Loss Card */}
                    <div className="bg-white dark:bg-[#101419] p-2 rounded-lg border border-rose-200/80 dark:border-rose-900/40 flex flex-col justify-between overflow-hidden">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[9px] text-rose-500 font-sans font-bold flex items-center gap-1 whitespace-nowrap">
                          <Shield className="w-3 h-3 text-rose-500 flex-shrink-0" /> СТОП (SL)
                        </span>
                        <span className="text-[9px] px-1 py-0.2 rounded font-bold bg-rose-500/15 text-[#f6465d] whitespace-nowrap">
                          -{tradeSetup.risk_pct}%
                        </span>
                      </div>
                      <div className="text-xs font-bold text-[#f6465d] mt-1 truncate" title={`$${tradeSetup.stop_loss}`}>
                        ${tradeSetup.stop_loss}
                      </div>
                    </div>

                    {/* Take Profit Card */}
                    <div className="bg-white dark:bg-[#101419] p-2 rounded-lg border border-emerald-200/80 dark:border-emerald-900/40 flex flex-col justify-between overflow-hidden">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[9px] text-emerald-500 font-sans font-bold flex items-center gap-1 whitespace-nowrap">
                          <CheckCircle2 className="w-3 h-3 text-emerald-500 flex-shrink-0" /> ТЕЙК (TP)
                        </span>
                        <span className="text-[9px] px-1 py-0.2 rounded font-bold bg-emerald-500/15 text-[#0ecb81] whitespace-nowrap">
                          +{tradeSetup.reward_pct}%
                        </span>
                      </div>
                      <div className="text-xs font-bold text-[#0ecb81] mt-1 truncate" title={`$${tradeSetup.take_profit}`}>
                        ${tradeSetup.take_profit}
                      </div>
                    </div>
                  </div>

                  {/* Confluence Badges - Clean Pills */}
                  {isDetailsOpen && tradeSetup.confluence_factors && tradeSetup.confluence_factors.length > 0 && (
                    <div className="space-y-1 pt-0.5">
                      <div className="text-[10px] text-slate-500 dark:text-gray-400 font-medium flex items-center gap-1">
                        <Sparkles className="w-3 h-3 text-indigo-500 dark:text-indigo-400" />
                        <span>Підтверджено формаціями:</span>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {tradeSetup.confluence_factors.map((f, idx) => (
                          <span
                            key={idx}
                            className="px-2 py-0.5 rounded-full text-[9px] bg-white dark:bg-[#161a20] text-slate-700 dark:text-gray-300 border border-slate-200 dark:border-[#232832] flex items-center gap-1 shadow-2xs"
                            title={f.desc}
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            {f.title}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Narrative Insight */}
                  {isDetailsOpen && tradeSetup.summary_comment && (
                    <div className="text-[10px] text-slate-600 dark:text-gray-300 leading-relaxed bg-white/70 dark:bg-[#11151b] p-2 rounded-lg border border-slate-200/70 dark:border-[#1e242d]">
                      💡 <span className="font-normal">{tradeSetup.summary_comment}</span>
                    </div>
                  )}

                  {/* Quick Copy Button */}
                  <button
                    onClick={handleCopySetup}
                    className={`w-full py-1.5 rounded-md text-[10px] font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer ${
                      isCopied
                        ? 'bg-emerald-500 text-white shadow-xs'
                        : 'bg-white dark:bg-[#161a20] text-slate-700 dark:text-gray-300 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-[#262c37] hover:bg-slate-50 dark:hover:bg-[#1a2028]'
                    }`}
                  >
                    {isCopied ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-white" />
                        <span>Параметри скопійовано!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3 text-slate-400" />
                        <span>Скопіювати параметри угоди</span>
                      </>
                    )}
                  </button>
                </div>
              ) : (
                /* When in WAIT mode */
                <div className="pt-2 text-[11px] text-slate-600 dark:text-gray-400 leading-snug space-y-1.5">
                  <div className="flex items-center justify-between text-[10px] font-mono">
                    <span className="text-slate-400">Потенціал Long:</span>
                    <span className={tradeSetup.long_potential?.rr && tradeSetup.long_potential.rr >= 3.0 ? 'text-[#0ecb81] font-bold' : 'text-slate-400'}>
                      {tradeSetup.long_potential?.rr ? `RR 1:${tradeSetup.long_potential.rr.toFixed(1)}` : 'Немає запасу'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[10px] font-mono">
                    <span className="text-slate-400">Потенціал Short:</span>
                    <span className={tradeSetup.short_potential?.rr && tradeSetup.short_potential.rr >= 3.0 ? 'text-[#f6465d] font-bold' : 'text-slate-400'}>
                      {tradeSetup.short_potential?.rr ? `RR 1:${tradeSetup.short_potential.rr.toFixed(1)}` : 'Немає запасу'}
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-500 dark:text-gray-400 italic bg-white/50 dark:bg-[#101419] p-1.5 rounded border border-slate-200/60 dark:border-[#1e2329]">
                    {tradeSetup.summary_comment}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      
      {/* 1. Market Structure & Trend Header */}
      {structure && (
        <div className="p-3 bg-slate-50/40 dark:bg-[#12161d]/30">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-500 dark:text-gray-400 font-semibold flex items-center gap-1.5 uppercase text-[11px] tracking-wider whitespace-nowrap">
              <Activity className="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400 flex-shrink-0" />
              СТРУКТУРА ТА ТРЕНД
            </span>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider flex items-center gap-1 flex-shrink-0 ${
                structure.trend === 'BULLISH'
                  ? 'bg-emerald-500/15 text-emerald-600 dark:text-[#0ecb81] border border-emerald-500/30'
                  : structure.trend === 'BEARISH'
                  ? 'bg-rose-500/15 text-rose-600 dark:text-[#f6465d] border border-rose-500/30'
                  : 'bg-amber-500/15 text-amber-600 dark:text-yellow-400 border border-amber-500/30'
              }`}
            >
              {structure.trend === 'BULLISH' && <TrendingUp className="w-3 h-3" />}
              {structure.trend === 'BEARISH' && <TrendingDown className="w-3 h-3" />}
              {structure.trend}
            </span>
          </div>

          <div className="bg-white dark:bg-[#151920] p-2.5 rounded-lg border border-slate-200/80 dark:border-[#20252e] flex items-center justify-between gap-2 shadow-2xs">
            <span className="text-slate-800 dark:text-gray-200 font-medium text-xs leading-snug">
              {structure.summary}
            </span>
            {fundingRate !== undefined && (
              <span 
                className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded flex-shrink-0 whitespace-nowrap ${
                  fundingRate >= 0 
                    ? 'text-emerald-600 dark:text-[#0ecb81] bg-emerald-500/10 border border-emerald-500/20' 
                    : 'text-rose-600 dark:text-[#f6465d] bg-rose-500/10 border border-rose-500/20'
                }`}
                title="Funding Rate (ставка фінансування)"
              >
                Фінансування: {(fundingRate * 100).toFixed(4)}%
              </span>
            )}
          </div>
        </div>
      )}

      {/* 2. Open Interest (OI) Delta & Breakout Confirmation */}
      <div className="p-3 bg-slate-50/20 dark:bg-[#12161d]/20 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-slate-500 dark:text-gray-400 font-semibold flex items-center gap-1.5 uppercase text-[11px] tracking-wider whitespace-nowrap">
            <BarChart2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
            ДЕТЕКЦІЯ OI DELTA
          </span>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-bold flex-shrink-0 ${
              oiData?.oi_status === 'INCREASING'
                ? 'bg-emerald-500/15 text-[#0ecb81] border border-emerald-500/30'
                : oiData?.oi_status === 'DECREASING'
                ? 'bg-rose-500/15 text-[#f6465d] border border-rose-500/30'
                : 'bg-slate-200 dark:bg-[#1e2329] text-slate-500 dark:text-gray-400'
            }`}
          >
            {oiData?.oi_status || 'NEUTRAL'}
          </span>
        </div>

        {/* Current OI & Volatility card */}
        <div className="bg-white dark:bg-[#151920] p-2 rounded-lg border border-slate-200/80 dark:border-[#20252e] space-y-1.5 text-[11px]">
          <div className="flex justify-between items-baseline">
            <span className="text-slate-400 dark:text-gray-500 text-[10px]">Базовий OI:</span>
            <div className="text-right">
              <span className="text-slate-900 dark:text-gray-100 font-mono font-bold">
                {oiData?.current_oi !== null && oiData?.current_oi !== undefined
                  ? oiData.current_oi.toLocaleString(undefined, { maximumFractionDigits: 1 })
                  : openInterest !== undefined
                  ? openInterest.toLocaleString(undefined, { maximumFractionDigits: 1 })
                  : '---'}
              </span>
              <span className="text-[10px] text-slate-400 font-sans ml-1">
                {oiData?.coin || ''}
              </span>
              {oiData?.current_oi_usd && (
                <span className="text-[10px] text-slate-400 dark:text-gray-500 font-mono ml-1.5">
                  (${oiData.current_oi_usd >= 1e9
                    ? `${(oiData.current_oi_usd / 1e9).toFixed(2)}B`
                    : `${(oiData.current_oi_usd / 1e6).toFixed(2)}M`})
                </span>
              )}
            </div>
          </div>

          <div className="flex justify-between items-center text-[10px] text-slate-400 dark:text-gray-500 pt-1 border-t border-slate-100 dark:border-[#1e2329]">
            <span>Поріг чутливості θ:</span>
            <span className={`font-mono font-medium ${oiData?.volatility_info?.is_adaptive ? 'text-emerald-500' : 'text-slate-400'}`}>
              ±{(oiData?.volatility_threshold_pct ?? 0.25).toFixed(2)}%
              {oiData?.volatility_info?.is_adaptive ? ' (адапт.)' : ' (фікс.)'}
            </span>
          </div>
        </div>

        {/* Multi-Interval Delta Grid: 1m, 5m, 15m, 1h */}
        <div className="grid grid-cols-4 gap-1.5 font-mono text-[10px]">
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
              ? 'text-slate-400 bg-slate-100 dark:bg-[#171b21] border-slate-200 dark:border-[#222730]'
              : isInc
              ? 'text-[#0ecb81] bg-emerald-500/10 border-emerald-500/25 font-bold'
              : isDec
              ? 'text-[#f6465d] bg-rose-500/10 border-rose-500/25 font-bold'
              : 'text-slate-600 dark:text-gray-300 bg-slate-100 dark:bg-[#171b21] border-slate-200 dark:border-[#222730]';

            return (
              <div key={intv} className={`p-1.5 rounded-md border flex flex-col items-center justify-center ${colorClass}`}>
                <span className="text-[9px] text-slate-400 dark:text-gray-500 font-sans uppercase font-semibold">{intv}</span>
                <span className="text-[11px] mt-0.5 whitespace-nowrap">
                  {isGap ? (
                    'GAP'
                  ) : isNoHist || d?.delta_pct === null || d?.delta_pct === undefined ? (
                    d?.actual_duration_seconds && d?.interval_seconds && d.actual_duration_seconds > 60 ? (
                      <span
                        className="text-[9px] font-normal"
                        title={`Накопичення історії: ${Math.round(d.actual_duration_seconds / 60)}хв з ${Math.round(d.interval_seconds / 60)}хв`}
                      >
                        {Math.round(d.actual_duration_seconds / 60)}/{Math.round(d.interval_seconds / 60)}m
                      </span>
                    ) : (
                      '...'
                    )
                  ) : (
                    formatOiDeltaPct(d.delta_pct)
                  )}
                </span>
              </div>
            );
          })}
        </div>

        {/* Level Breakout / Interaction Analysis Card */}
        {oiData?.breakout_signals && oiData.breakout_signals.length > 0 ? (
          <div className="space-y-1.5">
            {oiData.breakout_signals.slice(0, 2).map((sig) => (
              <div
                key={sig.level_id}
                className={`p-2 rounded-lg border text-[11px] ${
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
                      className={`text-[9px] px-1.5 py-0.2 rounded font-sans font-bold ${
                        sig.direction === 'UP'
                          ? 'bg-emerald-500/20 text-[#0ecb81]'
                          : 'bg-rose-500/20 text-[#f6465d]'
                      }`}
                    >
                      {sig.direction === 'UP' ? 'LONG' : 'SHORT'}
                    </span>
                    <span className="text-[10px] truncate">{sig.status}</span>
                  </div>
                  <span
                    className={`font-mono text-[10px] font-bold ${
                      sig.oi_delta_pct && sig.oi_delta_pct > 0
                        ? 'text-[#0ecb81]'
                        : sig.oi_delta_pct && sig.oi_delta_pct < 0
                        ? 'text-[#f6465d]'
                        : 'text-slate-500 dark:text-gray-400'
                    }`}
                  >
                    {formatOiDeltaPct(sig.oi_delta_pct)}
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
          <div className="text-[10px] text-slate-400 dark:text-gray-500 italic py-1 px-2 rounded bg-slate-100/60 dark:bg-[#14181e] border border-slate-200/50 dark:border-[#1d222b]">
            Ціна поза зоною пробою / тестування ключових рівнів.
          </div>
        )}
      </div>

      {/* 3. Found Formations Section */}
      <div className="p-3">
        <div className="flex items-center justify-between text-slate-500 dark:text-gray-400 text-[11px] font-semibold tracking-wider uppercase mb-2">
          <span className="flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-amber-500" />
            ЗНАЙДЕНІ ФОРМАЦІЇ · {filteredSignals.length}
          </span>
        </div>

        {filteredSignals.length === 0 ? (
          <p className="text-slate-400 dark:text-gray-500 text-[11px] leading-relaxed py-2 text-center bg-slate-50/50 dark:bg-[#14181e] rounded-lg border border-slate-200/60 dark:border-[#1e2329]">
            Для поточної монети формацій не виявлено.
          </p>
        ) : (
          <div className="space-y-2 max-h-56 overflow-y-auto pr-0.5">
            {filteredSignals.map((sig) => {
              const isLong = sig.direction === 'LONG';
              const isShort = sig.direction === 'SHORT';

              return (
                <div
                  key={sig.id}
                  onClick={() => onSelectSignal?.(sig)}
                  className="p-2.5 rounded-lg bg-white dark:bg-[#14181f] border border-slate-200/90 dark:border-[#222731] hover:border-indigo-400 dark:hover:border-indigo-500 cursor-pointer transition shadow-2xs space-y-1.5"
                >
                  {/* Formation Header: Title + Direction Badge */}
                  <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
                    <span className="text-slate-900 dark:text-gray-100 font-semibold text-xs leading-snug">
                      {sig.title}
                    </span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[9px] font-bold tracking-wider uppercase flex-shrink-0 ${
                        isLong
                          ? 'bg-emerald-500/15 text-emerald-600 dark:text-[#0ecb81] border border-emerald-500/30'
                          : isShort
                          ? 'bg-rose-500/15 text-rose-600 dark:text-[#f6465d] border border-rose-500/30'
                          : 'bg-slate-200 dark:bg-[#1e2329] text-slate-600 dark:text-gray-400'
                      }`}
                    >
                      {sig.direction}
                    </span>
                  </div>

                  {/* Badges / Meta row */}
                  <div className="flex flex-wrap items-center gap-1">
                    {sig.category === 'trendline' && (
                      <>
                        <span className="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-slate-100 dark:bg-[#1a2028] text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-[#262c37]">
                          Q: {Math.round(sig.structural_quality ?? sig.structuralQuality ?? sig.strength ?? 50)}
                        </span>
                        {(sig.is_confirmed || sig.isConfirmed || (sig.touch_count ?? sig.touchCount ?? 0) >= 3) && (
                          <span className="px-1 py-0.2 rounded text-[8px] font-bold bg-indigo-500/15 text-indigo-400 border border-indigo-500/30">
                            x3+ Підтверджена
                          </span>
                        )}
                        {(sig.signal_type || sig.signalType) ? (
                          <span className="px-1 py-0.2 rounded text-[8px] font-bold bg-emerald-500/15 text-[#0ecb81] border border-emerald-500/30">
                            {(sig.signal_type === 'BOUNCE' || sig.signalType === 'BOUNCE') ? 'ВІДСКОК' : 'АКТИВНА'}
                          </span>
                        ) : (
                          <span
                            className={`px-1 py-0.2 rounded text-[8px] font-bold whitespace-nowrap flex-shrink-0 ${
                              sig.interaction_state === 'BREAKOUT' || sig.interactionState === 'BREAKOUT'
                                ? 'bg-rose-500/20 text-[#f6465d] border border-rose-500/30'
                                : sig.interaction_state === 'RETEST' || sig.interactionState === 'RETEST'
                                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                                : sig.interaction_state === 'COMPRESSION' || sig.interactionState === 'COMPRESSION'
                                ? 'bg-amber-500/20 text-amber-500 border border-amber-500/30'
                                : sig.interaction_state === 'TESTING' || sig.interactionState === 'TESTING'
                                ? 'bg-yellow-500/20 text-yellow-500 border border-yellow-500/30'
                                : sig.interaction_state === 'REJECTED' || sig.interactionState === 'REJECTED'
                                ? 'bg-emerald-500/20 text-[#0ecb81] border border-emerald-500/30'
                                : 'bg-slate-500/20 text-slate-400 border border-slate-500/30'
                            }`}
                          >
                            {(() => {
                              const state = sig.interaction_state || sig.interactionState || 'ACTIVE';
                              const stateMap: Record<string, string> = {
                                BREAKOUT: 'ПРОБІЙ',
                                RETEST: 'РЕТЕСТ',
                                COMPRESSION: 'СТИCНЕННЯ',
                                TESTING: 'ТЕСТ',
                                REJECTED: 'ВІДХИЛЕНО',
                                APPROACHING: 'НАБЛИЖЕННЯ',
                                STALE: 'ЗАСТАРІЛА',
                                ACTIVE: 'АКТИВНА',
                              };
                              return stateMap[state] || state;
                            })()}
                          </span>
                        )}
                        {(sig.htf_context || sig.htfContext) && (sig.htf_context !== 'UNAVAILABLE' && sig.htfContext !== 'UNAVAILABLE') && (
                          <span
                            className={`px-1 py-0.2 rounded text-[8px] font-bold whitespace-nowrap flex-shrink-0 ${
                              (sig.htf_context === 'AGAINST_HTF' || sig.htfContext === 'AGAINST_HTF')
                                ? 'bg-rose-500/20 text-[#f6465d] border border-rose-500/30'
                                : (sig.htf_context === 'ALIGNED' || sig.htfContext === 'ALIGNED')
                                ? 'bg-emerald-500/20 text-[#0ecb81] border border-emerald-500/30'
                                : 'bg-slate-500/20 text-slate-400 border border-slate-500/30'
                            }`}
                          >
                            {(sig.htf_context === 'AGAINST_HTF' || sig.htfContext === 'AGAINST_HTF')
                              ? '⚠️ ПРОТИ HTF'
                              : (sig.htf_context === 'ALIGNED' || sig.htfContext === 'ALIGNED')
                              ? 'HTF: ЗБІГ'
                              : 'HTF: НЕЙТР.'}
                          </span>
                        )}
                      </>
                    )}

                    {sig.category === 'sweep' && sig.confirmationStatus && (
                      <span className="px-1.5 py-0.2 rounded text-[8px] font-bold bg-emerald-500/15 text-[#0ecb81] border border-emerald-500/30">
                        {sig.confirmationStatus === 'CONFIRMED' ? 'ПІДТВЕРДЖЕНО' : 'ПОТЕНЦІЙНИЙ'}
                      </span>
                    )}

                    {/* FVG specific status pill */}
                    {sig.category === 'fvg' && (
                      <span className="px-1.5 py-0.2 rounded text-[8px] font-bold bg-amber-500/15 text-amber-500 border border-amber-500/30">
                        Дисбаланс FVG
                      </span>
                    )}

                    {/* Phase 5.2: Structural Context Tier / Warning Badges */}
                    {(() => {
                      const ctx = sig.structuralContext || sig.structural_context;
                      if (!ctx || (!ctx.contextAvailable && !ctx.context_available)) return null;
                      const isTier1 = ctx.structuralTier === 'TIER_1_CONFLUENT' || ctx.structural_tier === 'TIER_1_CONFLUENT' || ctx.hasSupportConfluence || ctx.has_support_confluence;
                      const flags = ctx.riskFlags || ctx.risk_flags || [];
                      const isAgainstHtf = flags.includes('AGAINST_HTF') || ctx.htfAlignment === 'AGAINST_HTF' || ctx.htf_alignment === 'AGAINST_HTF';
                      const isComp = flags.includes('COMPRESSION') || ctx.isCompression || ctx.is_compression;

                      return (
                        <>
                          {isTier1 && (
                            <span className="px-1 py-0.2 rounded text-[8px] font-bold bg-emerald-500/15 text-[#0ecb81] border border-emerald-500/30 whitespace-nowrap flex-shrink-0">
                              🛡️ Збіг
                            </span>
                          )}
                          {isAgainstHtf && (
                            <span className="px-1 py-0.2 rounded text-[8px] font-bold bg-rose-500/20 text-[#f6465d] border border-rose-500/30 whitespace-nowrap flex-shrink-0">
                              ⚠️ Проти HTF
                            </span>
                          )}
                          {isComp && (
                            <span className="px-1 py-0.2 rounded text-[8px] font-bold bg-amber-500/20 text-amber-500 border border-amber-500/30 whitespace-nowrap flex-shrink-0">
                              ⚡ Стиснення
                            </span>
                          )}
                        </>
                      );
                    })()}
                  </div>

                  {sig.category === 'sweep' && sig.oiDeltaPct !== undefined && sig.oiDeltaPct !== null && (
                    <div className="flex items-center justify-between text-[10px] font-mono py-0.5 px-1 bg-slate-100 dark:bg-[#1a1f26] rounded">
                      <span className="text-slate-400 dark:text-gray-500">Зміна Open Interest:</span>
                      <span className={`font-bold ${sig.oiDeltaPct < 0 ? 'text-[#0ecb81]' : sig.oiDeltaPct > 0 ? 'text-[#f6465d]' : 'text-slate-400'}`}>
                        {formatOiDeltaPct(sig.oiDeltaPct)}
                      </span>
                    </div>
                  )}

                  {/* Phase 5.2: Enriched Structural Context row for Non-Trendline Signals */}
                  {sig.category !== 'trendline' && (() => {
                    const ctx = sig.structuralContext || sig.structural_context;
                    if (!ctx || (!ctx.contextAvailable && !ctx.context_available)) return null;
                    const hasSup = ctx.hasSupportConfluence || ctx.has_support_confluence;
                    const supDist = ctx.distanceToSupportAtr ?? ctx.distance_to_support_atr;
                    const resDist = ctx.distanceToResistanceAtr ?? ctx.distance_to_resistance_atr;
                    const supQ = ctx.confluentLineQ ?? ctx.confluent_line_q ?? ctx.nearestSupportQ ?? ctx.nearest_support_q;
                    const htf = ctx.htfAlignment ?? ctx.htf_alignment;

                    if ((supDist === null || supDist === undefined) && (resDist === null || resDist === undefined) && (!htf || htf === 'UNAVAILABLE')) {
                      return null;
                    }

                    return (
                      <div className="flex items-center justify-between text-[10px] font-mono py-0.5 px-1 bg-slate-100 dark:bg-[#1a1f26] rounded text-slate-500 dark:text-gray-400">
                        <div className="flex items-center gap-1.5 truncate">
                          {hasSup ? (
                            <span className="text-[#0ecb81] font-semibold">
                              Підтримка Q:{Math.round(supQ ?? 80)} ({supDist !== null && supDist !== undefined ? supDist.toFixed(1) : '0.0'} ATR)
                            </span>
                          ) : supDist !== null && supDist !== undefined ? (
                            <span>Підтримка: {supDist.toFixed(1)} ATR</span>
                          ) : null}
                          {resDist !== null && resDist !== undefined && (
                            <span>Опір: {resDist.toFixed(1)} ATR</span>
                          )}
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {htf === 'ALIGNED' && (
                            <span className="text-[#0ecb81] text-[9px] font-bold">1h Збіг</span>
                          )}
                          {htf === 'AGAINST_HTF' && (
                            <span className="text-[#f6465d] text-[9px] font-bold">Проти 1h</span>
                          )}
                        </div>
                      </div>
                    );
                  })()}

                  {/* Formation Details / Description */}
                  {sig.desc && (
                    <div className="text-[10px] text-slate-600 dark:text-gray-300 bg-slate-50 dark:bg-[#101318] p-1.5 rounded border border-slate-100 dark:border-[#1c212a] leading-relaxed">
                      {sig.desc}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 4. Lines & Zones on Chart Section */}
      <div className="p-3 flex flex-col space-y-3">
        {/* Smart Money Concepts (SMC) Summary Card */}
        <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-[#12161d] border border-slate-200/80 dark:border-[#1e2329] text-[11px] shadow-2xs">
          <div className="flex items-center justify-between font-semibold text-slate-700 dark:text-gray-300 mb-2">
            <span className="flex items-center gap-1.5 text-xs">
              <span className="w-2 h-2 rounded-full bg-blue-500" />
              SMART MONEY (SMC) РІВНІ
            </span>
            <span className="text-[10px] text-slate-400 dark:text-gray-500 font-mono">
              Найближчі пули
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 font-mono">
            {/* Supply (Resistance) Card */}
            <div className="bg-white dark:bg-[#161a22] p-2 rounded-lg border border-rose-200/80 dark:border-rose-900/40 flex flex-col justify-between space-y-1">
              <div className="flex items-center justify-between text-[9px]">
                <span className="font-bold text-rose-600 dark:text-rose-400 uppercase tracking-wider font-sans">
                  OB SUPPLY
                </span>
                {resistances[0] && (
                  <span className="font-bold text-[#f6465d]">
                    +{resistances[0].distPct?.toFixed(1)}%
                  </span>
                )}
              </div>
              <div className="text-xs sm:text-sm font-bold text-slate-900 dark:text-white truncate">
                {resistances[0] ? `$${resistances[0].price}` : '—'}
              </div>
              <div className="flex items-center gap-1 flex-wrap text-[8px] pt-0.5">
                {resistances[0] ? (
                  <>
                    <span className="text-slate-400 dark:text-gray-500 font-sans">
                      Сила {Math.round(resistances[0].strength_score || 80)}
                    </span>
                    {resistances[0].has_fvg && (
                      <span className="px-1 py-0.2 rounded bg-amber-500/15 text-amber-500 font-bold">FVG</span>
                    )}
                    {resistances[0].swept_liquidity && (
                      <span className="px-1 py-0.2 rounded bg-purple-500/15 text-purple-400 font-bold">SWEEP</span>
                    )}
                  </>
                ) : (
                  <span className="text-slate-400 text-[9px] font-sans">Немає вище</span>
                )}
              </div>
            </div>

            {/* Demand (Support) Card */}
            <div className="bg-white dark:bg-[#161a22] p-2 rounded-lg border border-emerald-200/80 dark:border-emerald-900/40 flex flex-col justify-between space-y-1">
              <div className="flex items-center justify-between text-[9px]">
                <span className="font-bold text-emerald-600 dark:text-[#0ecb81] uppercase tracking-wider font-sans">
                  OB DEMAND
                </span>
                {supports[0] && (
                  <span className="font-bold text-[#0ecb81]">
                    {supports[0].distPct?.toFixed(1)}%
                  </span>
                )}
              </div>
              <div className="text-xs sm:text-sm font-bold text-slate-900 dark:text-white truncate">
                {supports[0] ? `$${supports[0].price}` : '—'}
              </div>
              <div className="flex items-center gap-1 flex-wrap text-[8px] pt-0.5">
                {supports[0] ? (
                  <>
                    <span className="text-slate-400 dark:text-gray-500 font-sans">
                      Сила {Math.round(supports[0].strength_score || 80)}
                    </span>
                    {supports[0].has_fvg && (
                      <span className="px-1 py-0.2 rounded bg-amber-500/15 text-amber-500 font-bold">FVG</span>
                    )}
                    {supports[0].swept_liquidity && (
                      <span className="px-1 py-0.2 rounded bg-purple-500/15 text-purple-400 font-bold">SWEEP</span>
                    )}
                  </>
                ) : (
                  <span className="text-slate-400 text-[9px] font-sans">Немає нижче</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* 5. Levels List with Zero Truncation */}
        <div>
          <div className="text-slate-500 dark:text-gray-400 text-[11px] font-semibold tracking-wider uppercase mb-2 flex items-center justify-between">
            <span>ЗОНИ ТА РІВНІ · {allLevelsCount}</span>
            <span className="text-[10px] text-slate-400 font-normal lowercase">ціна / діапазон / сила</span>
          </div>

          <div className="space-y-1.5 font-mono">
            {/* Resistances (Red Dots) */}
            {resistances.map((r, idx) => (
              <div
                key={`r-${idx}`}
                className="p-2 rounded-lg bg-white dark:bg-[#13171e] border border-slate-200/80 dark:border-[#1e2329] hover:border-slate-300 dark:hover:border-gray-600 transition space-y-1 shadow-2xs"
              >
                {/* Row 1: Badges & Label on Left, Distance % on Right */}
                <div className="flex items-center justify-between gap-1.5">
                  <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                    <span className="w-2 h-2 rounded-full flex-shrink-0 bg-[#f6465d]" />
                    <span className="font-semibold text-xs font-sans text-slate-800 dark:text-gray-100 whitespace-nowrap">
                      {r.smc_label || (r.smc_type === 'BREAKER_BLOCK' ? 'Breaker' : 'Опір')}
                    </span>
                    {r.timeframe && (
                      <span className="px-1 py-0.2 rounded bg-blue-500/15 text-blue-500 dark:text-blue-300 text-[9px] font-bold">
                        {r.timeframe.toUpperCase()}
                      </span>
                    )}
                    {r.has_fvg && (
                      <span className="px-1 py-0.2 rounded bg-amber-500/15 text-amber-500 text-[8px] font-bold" title="Fair Value Gap Imbalance">
                        FVG
                      </span>
                    )}
                    {r.swept_liquidity && (
                      <span className="px-1 py-0.2 rounded bg-purple-500/15 text-purple-400 text-[8px] font-bold" title="Зняття ліквідності (Sweep)">
                        SWEEP
                      </span>
                    )}
                    {r.zone_location && (
                      <span className={`px-1 py-0.2 rounded text-[8px] font-bold ${r.zone_location === 'Premium' ? 'bg-indigo-500/15 text-indigo-400' : 'bg-teal-500/15 text-teal-400'}`}>
                        {r.zone_location === 'Premium' ? 'PREM' : 'DISC'}
                      </span>
                    )}
                    {r.status && r.status !== 'active' && (
                      <span className="text-[8px] font-bold px-1 py-0.2 rounded bg-blue-500/15 text-blue-400">
                        {r.status === 'retested' ? 'Ретест' : 'Ослабл'}
                      </span>
                    )}
                  </div>
                  <span className="font-bold text-xs flex-shrink-0 text-[#f6465d] whitespace-nowrap">
                    {r.distPct >= 0 ? `+${r.distPct.toFixed(2)}%` : `${r.distPct.toFixed(2)}%`}
                  </span>
                </div>

                {/* Row 2: Price and Range on Left, Strength Progress Bar on Right */}
                <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-100 dark:border-[#191e25]">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="font-bold text-slate-900 dark:text-white whitespace-nowrap">
                      ${r.price}
                    </span>
                    {r.bottom && r.top && (
                      <span className="text-[10px] text-slate-400 dark:text-gray-500 truncate" title={`Діапазон зони: ${r.bottom} — ${r.top}`}>
                        ({r.bottom} — {r.top})
                      </span>
                    )}
                    {r.touches > 1 && (
                      <span className="text-[10px] text-slate-400 dark:text-gray-500 font-sans flex-shrink-0">
                        x{r.touches}
                      </span>
                    )}
                  </div>

                  {r.strength_score !== undefined && (
                    <div className="flex items-center gap-1 flex-shrink-0 text-[10px] text-slate-400">
                      <span className="w-10 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700/60 overflow-hidden flex">
                        <span 
                          className="h-full bg-rose-500/80 rounded-full" 
                          style={{ width: `${Math.min(100, Math.round(r.strength_score))}%` }} 
                        />
                      </span>
                      <span className="font-semibold">{Math.round(r.strength_score)}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Supports (Green Dots) */}
            {supports.map((s, idx) => (
              <div
                key={`s-${idx}`}
                className="p-2 rounded-lg bg-white dark:bg-[#13171e] border border-slate-200/80 dark:border-[#1e2329] hover:border-slate-300 dark:hover:border-gray-600 transition space-y-1 shadow-2xs"
              >
                {/* Row 1: Badges & Label on Left, Distance % on Right */}
                <div className="flex items-center justify-between gap-1.5">
                  <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                    <span className="w-2 h-2 rounded-full flex-shrink-0 bg-[#0ecb81]" />
                    <span className="font-semibold text-xs font-sans text-slate-800 dark:text-gray-100 whitespace-nowrap">
                      {s.smc_label || (s.smc_type === 'BREAKER_BLOCK' ? 'Breaker' : 'Підтримка')}
                    </span>
                    {s.timeframe && (
                      <span className="px-1 py-0.2 rounded bg-blue-500/15 text-blue-500 dark:text-blue-300 text-[9px] font-bold">
                        {s.timeframe.toUpperCase()}
                      </span>
                    )}
                    {s.has_fvg && (
                      <span className="px-1 py-0.2 rounded bg-amber-500/15 text-amber-500 text-[8px] font-bold" title="Fair Value Gap Imbalance">
                        FVG
                      </span>
                    )}
                    {s.swept_liquidity && (
                      <span className="px-1 py-0.2 rounded bg-purple-500/15 text-purple-400 text-[8px] font-bold" title="Зняття ліквідності (Sweep)">
                        SWEEP
                      </span>
                    )}
                    {s.zone_location && (
                      <span className={`px-1 py-0.2 rounded text-[8px] font-bold ${s.zone_location === 'Discount' ? 'bg-teal-500/15 text-teal-400' : 'bg-indigo-500/15 text-indigo-400'}`}>
                        {s.zone_location === 'Discount' ? 'DISC' : 'PREM'}
                      </span>
                    )}
                    {s.status && s.status !== 'active' && (
                      <span className="text-[8px] font-bold px-1 py-0.2 rounded bg-blue-500/15 text-blue-400">
                        {s.status === 'retested' ? 'Ретест' : 'Ослабл'}
                      </span>
                    )}
                  </div>
                  <span className="font-bold text-xs flex-shrink-0 text-[#0ecb81] whitespace-nowrap">
                    {s.distPct >= 0 ? `+${s.distPct.toFixed(2)}%` : `${s.distPct.toFixed(2)}%`}
                  </span>
                </div>

                {/* Row 2: Price and Range on Left, Strength Progress Bar on Right */}
                <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-100 dark:border-[#191e25]">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="font-bold text-slate-900 dark:text-white whitespace-nowrap">
                      ${s.price}
                    </span>
                    {s.bottom && s.top && (
                      <span className="text-[10px] text-slate-400 dark:text-gray-500 truncate" title={`Діапазон зони: ${s.bottom} — ${s.top}`}>
                        ({s.bottom} — {s.top})
                      </span>
                    )}
                    {s.touches > 1 && (
                      <span className="text-[10px] text-slate-400 dark:text-gray-500 font-sans flex-shrink-0">
                        x{s.touches}
                      </span>
                    )}
                  </div>

                  {s.strength_score !== undefined && (
                    <div className="flex items-center gap-1 flex-shrink-0 text-[10px] text-slate-400">
                      <span className="w-10 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700/60 overflow-hidden flex">
                        <span 
                          className="h-full bg-emerald-500/80 rounded-full" 
                          style={{ width: `${Math.min(100, Math.round(s.strength_score))}%` }} 
                        />
                      </span>
                      <span className="font-semibold">{Math.round(s.strength_score)}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {allLevelsCount === 0 && (
              <div className="text-slate-400 dark:text-gray-600 text-center py-4 bg-slate-50/50 dark:bg-[#14181e] rounded-lg border border-slate-200/60 dark:border-[#1e2329]">
                Зон не виявлено
              </div>
            )}
          </div>
        </div>
      </div>
      </div>

      {/* Bottom Explanatory Help */}
      <div className="p-2.5 border-t border-slate-200 dark:border-[#1e2329] text-[10px] text-slate-400 dark:text-gray-500 leading-tight bg-slate-50/70 dark:bg-[#0b0e11]/50">
        Мульти-таймфреймові рівні: кожен таймфрейм розраховується незалежно та має власний колір і статус.
      </div>
    </aside>
  );
};
