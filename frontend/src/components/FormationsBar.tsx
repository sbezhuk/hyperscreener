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

  const mtfList = ['1m', '5m', '15m', '1h', '4h', '1d'];
  const strengthOptions = [
    { value: 0, label: 'Всі (0+)' },
    { value: 50, label: '50+' },
    { value: 70, label: '70+' },
    { value: 80, label: '80+' },
  ];

  return (
    <div className="min-h-10 px-4 py-1.5 bg-[#0b0e11] border-b border-[#1e2329] flex items-center justify-between gap-4 select-none text-xs overflow-x-auto no-scrollbar">
      {/* Left: Formation selector */}
      <div className="flex items-center gap-1.5 flex-nowrap flex-shrink-0">
        <span className="text-gray-500 font-medium text-[11px] mr-1 whitespace-nowrap">Формація:</span>
        {tabs.map((tab) => {
          const isSelected = active === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onChange(tab.id)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-all duration-150 cursor-pointer ${
                isSelected
                  ? 'bg-emerald-950/60 text-[#0ecb81] border border-emerald-500/50 shadow-sm'
                  : 'bg-[#15191e] text-gray-400 border border-[#23272e] hover:text-gray-200 hover:bg-[#1e2329]'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Right / Center: MTF Overlay & Strength Filter Controls */}
      <div className="flex items-center gap-3 flex-nowrap flex-shrink-0 border-l border-[#1e2329] pl-3 ml-auto">
        {/* Timeframe Checkboxes / Pills */}
        <div className="flex items-center gap-1">
          <span className="text-gray-500 font-medium text-[11px] mr-1 whitespace-nowrap">Рівні TF:</span>
          {mtfList.map((tf) => {
            const isEnabled = selectedTfs.includes(tf);
            const label = tf.replace('h', 'H').replace('d', 'D');
            return (
              <button
                key={tf}
                onClick={() => onToggleTf(tf)}
                title={`Показати/приховати рівні таймфрейму ${label}`}
                className={`px-1.5 py-0.5 rounded text-[11px] font-mono font-medium transition-all cursor-pointer ${
                  isEnabled
                    ? 'bg-blue-600/20 text-blue-300 border border-blue-500/60 shadow-sm font-semibold'
                    : 'bg-[#15191e] text-gray-500 border border-[#23272e] hover:text-gray-400 opacity-60'
                }`}
              >
                {isEnabled ? `✓${label}` : label}
              </button>
            );
          })}
        </div>

        {/* Strength Score Filter */}
        <div className="flex items-center gap-1 pl-2 border-l border-[#1e2329]">
          <span className="text-gray-500 font-medium text-[11px] mr-0.5 whitespace-nowrap">Сила:</span>
          {strengthOptions.map((opt) => {
            const isSelected = minStrength === opt.value;
            return (
              <button
                key={opt.value}
                onClick={() => onMinStrengthChange(opt.value)}
                className={`px-1.5 py-0.5 rounded text-[11px] font-mono font-medium transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-emerald-950/60 text-[#0ecb81] border border-emerald-500/50'
                    : 'bg-[#15191e] text-gray-400 border border-[#23272e] hover:text-gray-300'
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
