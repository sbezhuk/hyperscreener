import React from 'react';
import { FormationFilter } from '../types';

interface FormationsBarProps {
  active: FormationFilter;
  onChange: (filter: FormationFilter) => void;
  // Multi-Timeframe Controls
  selectedTfs: string[];
  onToggleTf: (tf: string) => void;
  minStrength: number;
  onMinStrengthChange: (score: number) => void;
  // Open Interest False Breakout Filter
  onlyConfirmedOi?: boolean;
  onToggleConfirmedOi?: () => void;
}

export const FormationsBar: React.FC<FormationsBarProps> = ({
  active,
  onChange,
  selectedTfs,
  onToggleTf,
  minStrength,
  onMinStrengthChange,
  onlyConfirmedOi = false,
  onToggleConfirmedOi,
}) => {
  const tabs: { id: FormationFilter; label: string; shortLabel: string }[] = [
    { id: 'NONE', label: 'Без формацій', shortLabel: 'Без ф-цій' },
    { id: 'CASCADE', label: 'Рівні (підтримка / опір)', shortLabel: 'Рівні' },
    { id: 'SWEEP', label: 'Відскік / хибний пробій', shortLabel: 'Хибний пробій' },
    { id: 'TRENDLINE', label: 'Наклонки', shortLabel: 'Наклонки' },
    { id: 'FVG', label: 'FVG (Імбаланс)', shortLabel: 'FVG' },
  ];

  const mtfList = ['1m', '5m', '15m', '1h', '4h', '1d'];
  const strengthOptions = [
    { value: 0, label: 'Всі (0+)' },
    { value: 50, label: '50+' },
    { value: 70, label: '70+' },
    { value: 80, label: '80+' },
  ];

  const showMtf = active === 'CASCADE' || active === 'FVG';
  const showStrength = active === 'CASCADE' || active === 'FVG';
  const showOi = active === 'SWEEP' && Boolean(onToggleConfirmedOi);
  const hasControls = showMtf || showStrength || showOi;

  return (
    <div className="w-full max-w-full px-2 sm:px-4 py-1.5 bg-slate-50 dark:bg-[#0b0e11] border-b border-slate-200 dark:border-[#1e2329] flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 select-none text-xs transition-colors no-scrollbar overflow-x-hidden">
      {/* Left: Formation selector */}
      <div className="flex flex-wrap items-center gap-1 sm:gap-1.5">
        <span className="text-slate-500 dark:text-gray-500 font-medium text-[11px] mr-0.5 sm:mr-1 whitespace-nowrap">Формація:</span>
        {tabs.map((tab) => {
          const isSelected = active === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onChange(tab.id)}
              className={`px-2 sm:px-2.5 py-0.5 sm:py-1 rounded-full text-[11px] sm:text-xs font-medium whitespace-nowrap transition-all duration-150 cursor-pointer ${isSelected
                  ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-[#0ecb81] border border-emerald-400 dark:border-emerald-500/50 shadow-sm'
                  : 'bg-white dark:bg-[#15191e] text-slate-600 dark:text-gray-400 border border-slate-300 dark:border-[#23272e] hover:text-slate-900 dark:hover:text-gray-200 hover:bg-slate-100 dark:hover:bg-[#1e2329]'
                }`}
            >
              {tab.id === 'CASCADE' ? (
                <>
                  Рівні<span className="hidden xl:inline"> (підтримка / опір)</span>
                </>
              ) : tab.id === 'SWEEP' ? (
                <>
                  <span className="hidden xl:inline">Відскік / </span>хибний пробій
                </>
              ) : tab.id === 'FVG' ? (
                <>
                  FVG<span className="hidden xl:inline"> (Імбаланс)</span>
                </>
              ) : (
                tab.label
              )}
            </button>
          );
        })}
      </div>

      {/* Right: Sub-controls dynamically tailored to the active formation */}
      {hasControls && (
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 lg:border-l lg:border-slate-200 lg:dark:border-[#1e2329] lg:pl-3">
          {/* MTF Badges (Relevant for CASCADE & FVG) */}
          {showMtf && (
            <div className="flex items-center gap-1">
              <span className="text-slate-500 dark:text-gray-500 font-medium text-[11px] mr-1 whitespace-nowrap">MTF:</span>
              {mtfList.map((tf) => {
                const isChecked = selectedTfs.includes(tf);
                return (
                  <button
                    key={tf}
                    onClick={() => onToggleTf(tf)}
                    className={`px-1.5 py-0.5 rounded text-[11px] font-mono font-semibold transition cursor-pointer ${isChecked
                        ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/50 shadow-sm'
                        : 'bg-white dark:bg-[#15191e] text-slate-400 dark:text-gray-500 border border-slate-300 dark:border-[#23272e] hover:text-slate-600 dark:hover:text-gray-400 opacity-70'
                      }`}
                    title={active === 'FVG' ? `Фільтрувати FVG за ТФ ${tf}` : `Фільтрувати рівні за ТФ ${tf}`}
                  >
                    {tf.toUpperCase()}
                  </button>
                );
              })}
            </div>
          )}

          {/* Strength Filter (Relevant for CASCADE & FVG) */}
          {showStrength && (
            <div className={`flex items-center gap-1 ${showMtf ? 'pl-2 border-l border-slate-200 dark:border-[#1e2329]' : ''}`}>
              <span className="text-slate-500 dark:text-gray-500 font-medium text-[11px] mr-1 whitespace-nowrap">Сила:</span>
              {strengthOptions.map((opt) => {
                const isSelected = minStrength === opt.value;
                return (
                  <button
                    key={opt.value}
                    onClick={() => onMinStrengthChange(opt.value)}
                    className={`px-2 py-0.5 rounded text-[11px] font-medium transition cursor-pointer ${isSelected
                        ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-[#0ecb81] border border-emerald-400 dark:border-emerald-500/50'
                        : 'bg-white dark:bg-[#15191e] text-slate-600 dark:text-gray-400 border border-slate-300 dark:border-[#23272e] hover:text-slate-900 dark:hover:text-gray-300'
                      }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          )}

          {/* OI Confirmation Toggle for False Breakout (Relevant only for SWEEP) */}
          {showOi && (
            <div className={`flex items-center gap-1.5 ${showMtf || showStrength ? 'pl-2 border-l border-slate-200 dark:border-[#1e2329]' : ''}`}>
              <button
                onClick={onToggleConfirmedOi}
                className={`px-2.5 py-0.5 rounded text-[11px] font-medium transition cursor-pointer flex items-center gap-1.5 ${
                  onlyConfirmedOi
                    ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/50 shadow-sm font-semibold'
                    : 'bg-white dark:bg-[#15191e] text-slate-500 dark:text-gray-400 border border-slate-300 dark:border-[#23272e] hover:text-slate-700 dark:hover:text-gray-300'
                }`}
                title="Фільтрувати тільки формації, підтверджені скороченням Open Interest"
              >
                <span className={`w-2 h-2 rounded-full ${onlyConfirmedOi ? 'bg-emerald-500' : 'bg-slate-400 dark:bg-gray-600'}`} />
                <span className="hidden sm:inline">Тільки підтверджені OI</span>
                <span className="sm:hidden">Підтв. OI</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
