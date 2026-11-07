import React, { useEffect, useState } from 'react';
import { SignalItem } from '../types';
import { Bell, X } from 'lucide-react';

interface AlertToastProps {
  signals: SignalItem[];
  coin: string;
  onSwitchCoin?: (coin: string) => void;
}

export const AlertToast: React.FC<AlertToastProps> = ({ signals, coin, onSwitchCoin }) => {
  const [activeAlert, setActiveAlert] = useState<SignalItem | null>(null);

  useEffect(() => {
    if (signals.length > 0) {
      // Show the latest signal
      setActiveAlert(signals[0]);
      const timer = setTimeout(() => {
        // keep it or fade after 12s
      }, 12000);
      return () => clearTimeout(timer);
    }
  }, [signals]);

  if (!activeAlert) return null;

  return (
    <div className="fixed bottom-5 right-5 z-40 max-w-xs w-full bg-white dark:bg-[#15191e] border border-slate-200 dark:border-[#2b313a] rounded-lg shadow-2xl p-3 flex flex-col gap-1.5 select-none animate-in fade-in slide-in-from-bottom-3 duration-300 transition-colors">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-bold text-slate-900 dark:text-white font-mono">
          <span
            className={`w-2 h-2 rounded-full ${
              activeAlert.direction === 'LONG' ? 'bg-[#0ecb81]' : 'bg-[#f6465d]'
            } animate-ping`}
          />
          <span>
            {activeAlert.coin} {activeAlert.interval}
          </span>
        </div>
        <button
          onClick={() => setActiveAlert(null)}
          className="text-slate-400 dark:text-gray-500 hover:text-slate-800 dark:hover:text-white p-0.5 rounded transition"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="text-xs font-semibold text-slate-800 dark:text-gray-200">{activeAlert.title}</div>
      <div className="text-[11px] text-slate-600 dark:text-gray-400 line-clamp-2 leading-tight">
        {activeAlert.desc}
      </div>

      <div className="flex items-center justify-between mt-1 pt-1 border-t border-slate-200 dark:border-[#1e2329] text-[10px]">
        <span className="text-slate-500 dark:text-gray-500 font-mono">Ціна: {activeAlert.price}</span>
        <button
          onClick={() => onSwitchCoin?.(activeAlert.coin)}
          className="text-emerald-600 dark:text-emerald-400 hover:underline font-medium"
        >
          Відкрити графік →
        </button>
      </div>
    </div>
  );
};
