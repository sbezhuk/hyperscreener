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
}

export const FormationsBar: React.FC<FormationsBarProps> = ({
  active,
  onChange,
  selectedTfs,
  onToggleTf,
  minStrength,
  onMinStrengthChange,
}) => {
  const tabs: { id: FormationFilter; label: string }[] = [
    { id: 'NONE', label: 'Без формацій' },
    { id: 'CASCADE', label: 'Пробій (каскад / рівні)' },
    { id: 'SWEEP', label: 'Відскік / хибний пробій' },
    { id: 'TRENDLINE', label: 'Наклонки' },
    { id: 'FVG', label: 'FVG (Імбаланс)' },
  ];

  const mtfList = ['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d'];
  const strengthOptions = [
    { value: 0, label: 'Всі (0+)' },
    { value: 50, label: '50+' },
    { value: 70, label: '70+' },
    { value: 80, label: '80+' },
  ];

  return (
    <div className="min-h-10 px-4 py-1.5 bg-slate-50 dark:bg-[#0b0e11] border-b border-slate-200 dark:border-[#1e2329] flex items-center justify-between gap-4 select-none text-xs overflow-x-auto no-scrollbar transition-colors">
      {/* Left: Formation selector */}
      <div className="flex items-center gap-1.5 flex-nowrap flex-shrink-0">
        <span className="text-slate-500 dark:text-gray-500 font-medium text-[11px] mr-1 whitespace-nowrap">Формація:</span>
        {tabs.map((tab) => {
          const isSelected = active === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onChange(tab.id)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-all duration-150 cursor-pointer ${
                isSelected
                  ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-[#0ecb81] border border-emerald-400 dark:border-emerald-500/50 shadow-sm'
                  : 'bg-white dark:bg-[#15191e] text-slate-600 dark:text-gray-400 border border-slate-300 dark:border-[#23272e] hover:text-slate-900 dark:hover:text-gray-200 hover:bg-slate-100 dark:hover:bg-[#1e2329]'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Right: Multi-Timeframe Matrix & Strength Filter */}
      <div className="flex items-center gap-3 flex-nowrap flex-shrink-0 border-l border-slate-200 dark:border-[#1e2329] pl-3 ml-auto">
        {/* MTF Badges */}
        <div className="flex items-center gap-1">
          <span className="text-slate-500 dark:text-gray-500 font-medium text-[11px] mr-1 whitespace-nowrap">MTF:</span>
          {mtfList.map((tf) => {
            const isChecked = selectedTfs.includes(tf);
            return (
              <button
                key={tf}
                onClick={() => onToggleTf(tf)}
                className={`px-1.5 py-0.5 rounded text-[11px] font-mono font-semibold transition cursor-pointer ${
                  isChecked
                    ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/50 shadow-sm'
                    : 'bg-white dark:bg-[#15191e] text-slate-400 dark:text-gray-500 border border-slate-300 dark:border-[#23272e] hover:text-slate-600 dark:hover:text-gray-400 opacity-70'
                }`}
                title={`Фільтрувати рівні за ТФ ${tf}`}
              >
                {tf.toUpperCase()}
              </button>
            );
          })}
        </div>

        {/* Strength Filter */}
        <div className="flex items-center gap-1 pl-2 border-l border-slate-200 dark:border-[#1e2329]">
          <span className="text-slate-500 dark:text-gray-500 font-medium text-[11px] mr-1 whitespace-nowrap">Сила:</span>
          {strengthOptions.map((opt) => {
            const isSelected = minStrength === opt.value;
            return (
              <button
                key={opt.value}
                onClick={() => onMinStrengthChange(opt.value)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition cursor-pointer ${
                  isSelected
                    ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-[#0ecb81] border border-emerald-400 dark:border-emerald-500/50'
                    : 'bg-white dark:bg-[#15191e] text-slate-600 dark:text-gray-400 border border-slate-300 dark:border-[#23272e] hover:text-slate-900 dark:hover:text-gray-300'
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
