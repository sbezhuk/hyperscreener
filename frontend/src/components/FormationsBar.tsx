import React from 'react';
import { FormationFilter } from '../types';

interface FormationsBarProps {
  active: FormationFilter;
  onChange: (filter: FormationFilter) => void;
}

export const FormationsBar: React.FC<FormationsBarProps> = ({ active, onChange }) => {
  const tabs: { id: FormationFilter; label: string }[] = [
    { id: 'NONE', label: 'Без формацій' },
    { id: 'CASCADE', label: 'Пробій (каскад)' },
    { id: 'SWEEP', label: 'Відскік / хибний пробій' },
    { id: 'TRENDLINE', label: 'Наклонки' },
    { id: 'FVG', label: 'FVG (Імбаланс)' },
  ];

  return (
    <div className="h-10 px-4 bg-[#0b0e11] border-b border-[#1e2329] flex items-center gap-3 select-none text-xs overflow-x-auto no-scrollbar">
      <span className="text-gray-500 font-medium text-[11px] whitespace-nowrap">Формація:</span>
      <div className="flex items-center gap-1.5 flex-nowrap">
        {tabs.map((tab) => {
          const isSelected = active === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onChange(tab.id)}
              className={`px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-all duration-150 cursor-pointer ${
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
    </div>
  );
};
