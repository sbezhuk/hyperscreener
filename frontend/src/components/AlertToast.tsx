import React, { useEffect, useState, useRef } from 'react';
import { SignalItem } from '../types';
import { Bell, ChevronUp, ChevronDown, Minimize2 } from 'lucide-react';

interface AlertToastProps {
  signals: SignalItem[];
  coin: string;
  onSwitchCoin?: (coin: string) => void;
  onOpenAlert?: (coin: string, interval: string, timestamp: number, category?: string) => void;
}

export const AlertToast: React.FC<AlertToastProps> = ({ signals, coin, onSwitchCoin, onOpenAlert }) => {
  const [activeAlert, setActiveAlert] = useState<SignalItem | null>(null);
  const [isMinimized, setIsMinimized] = useState<boolean>(true);
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [isHovered, setIsHovered] = useState<boolean>(false);
  
  const lastSignalKeyRef = useRef<string | null>(null);
  const autoCollapseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (signals && signals.length > 0) {
      const latest = signals[0];
      const key = `${latest.coin}_${latest.interval}_${latest.time}_${latest.title}`;

      // Check if this is a newly arrived signal
      if (lastSignalKeyRef.current !== key) {
        lastSignalKeyRef.current = key;
        setActiveAlert(latest);

        // Display pill preview for new signals and start auto-collapse timer
        setIsMinimized(false);
        setIsExpanded(false);

        if (autoCollapseTimerRef.current) {
          clearTimeout(autoCollapseTimerRef.current);
        }
        autoCollapseTimerRef.current = setTimeout(() => {
          setIsMinimized(true);
        }, 6000);
      }
    } else {
      setActiveAlert(null);
    }

    return () => {
      if (autoCollapseTimerRef.current) {
        clearTimeout(autoCollapseTimerRef.current);
      }
    };
  }, [signals]);

  // Pause auto-collapse timer while hovered
  useEffect(() => {
    if (isHovered && autoCollapseTimerRef.current) {
      clearTimeout(autoCollapseTimerRef.current);
    }
  }, [isHovered]);

  if (!activeAlert) return null;

  const handleOpenChart = () => {
    if (onOpenAlert) {
      onOpenAlert(activeAlert.coin, activeAlert.interval, activeAlert.time, activeAlert.category);
    } else if (onSwitchCoin) {
      onSwitchCoin(activeAlert.coin);
    }
    // Tuck away after navigation so it doesn't block chart view
    setIsExpanded(false);
    setIsMinimized(true);
  };

  const formattedInterval =
    activeAlert.interval?.toLowerCase() === '4h'
      ? '4H'
      : activeAlert.interval?.toLowerCase() === '1h'
      ? '1H'
      : activeAlert.interval?.toLowerCase() === '1d'
      ? '1D'
      : activeAlert.interval;

  return (
    <div className="fixed bottom-3 left-3 sm:left-4 z-40 max-w-sm select-none font-sans transition-all duration-200">
      {/* 1. Minimized Mode: Subtle floating bell pill (always accessible, cannot be closed) */}
      {isMinimized && (
        <button
          onClick={() => {
            setIsMinimized(false);
            setIsExpanded(false);
          }}
          className="group flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/90 dark:bg-[#15191e]/90 backdrop-blur-md border border-slate-300 dark:border-[#2b313a] shadow-lg hover:border-emerald-500/60 dark:hover:border-emerald-500/60 transition-all cursor-pointer text-xs"
          title="Показати сповіщення про формацію"
        >
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                activeAlert.direction === 'LONG' ? 'bg-[#0ecb81]' : 'bg-[#f6465d]'
              }`}
            />
          </span>
          <Bell className="w-3 h-3 text-slate-500 dark:text-gray-400 group-hover:text-emerald-500 transition-colors" />
          <span className="font-mono text-[11px] font-bold text-slate-800 dark:text-gray-200">
            {activeAlert.coin} {formattedInterval}
          </span>
          <ChevronUp className="w-3 h-3 text-slate-400 group-hover:text-slate-600 dark:group-hover:text-gray-300 ml-0.5" />
        </button>
      )}

      {/* 2. Compact Single-Line Mode: Unobtrusive preview banner */}
      {!isMinimized && !isExpanded && (
        <div
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/95 dark:bg-[#15191e]/95 backdrop-blur-md border border-slate-300 dark:border-[#2b313a] shadow-xl text-xs transition-all animate-in fade-in slide-in-from-bottom-2 duration-200"
        >
          <span className="relative flex h-2 w-2 flex-shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                activeAlert.direction === 'LONG' ? 'bg-[#0ecb81]' : 'bg-[#f6465d]'
              }`}
            />
          </span>
          <span className="font-mono font-bold text-slate-900 dark:text-white text-[11px] flex-shrink-0">
            {activeAlert.coin} {formattedInterval}
          </span>
          <span className="text-slate-300 dark:text-gray-600">·</span>
          <span
            className="text-slate-700 dark:text-gray-300 font-medium text-[11px] truncate max-w-[170px] sm:max-w-[230px] cursor-pointer hover:text-emerald-500 dark:hover:text-emerald-400 transition"
            title="Клікніть щоб переглянути повний опис"
            onClick={() => setIsExpanded(true)}
          >
            {activeAlert.title}
          </span>
          <button
            onClick={handleOpenChart}
            className="text-emerald-600 dark:text-[#0ecb81] hover:underline font-semibold text-[11px] whitespace-nowrap ml-1 cursor-pointer flex-shrink-0"
            title="Відкрити точку формації на графіку"
          >
            Графік →
          </button>
          <div className="flex items-center gap-0.5 ml-1 pl-1 border-l border-slate-200 dark:border-[#2b313a] flex-shrink-0 text-slate-400 dark:text-gray-500">
            <button
              onClick={() => setIsExpanded(true)}
              className="p-1 rounded hover:bg-slate-100 dark:hover:bg-[#23272e] hover:text-slate-700 dark:hover:text-gray-200 transition cursor-pointer"
              title="Розгорнути деталі"
            >
              <ChevronUp className="w-3 h-3" />
            </button>
            <button
              onClick={() => setIsMinimized(true)}
              className="p-1 rounded hover:bg-slate-100 dark:hover:bg-[#23272e] hover:text-slate-700 dark:hover:text-gray-200 transition cursor-pointer"
              title="Згорнути в значок"
            >
              <Minimize2 className="w-3 h-3" />
            </button>
          </div>
        </div>
      )}

      {/* 3. Detailed Card Mode: On explicit user demand */}
      {!isMinimized && isExpanded && (
        <div
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
          className="w-80 max-w-[calc(100vw-2rem)] bg-white dark:bg-[#15191e] border border-slate-200 dark:border-[#2b313a] rounded-xl shadow-2xl p-3 flex flex-col gap-1.5 transition-all animate-in fade-in zoom-in-95 duration-200"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-bold text-slate-900 dark:text-white font-mono">
              <span
                className={`w-2 h-2 rounded-full ${
                  activeAlert.direction === 'LONG' ? 'bg-[#0ecb81]' : 'bg-[#f6465d]'
                } animate-ping`}
              />
              <span>
                {activeAlert.coin} {formattedInterval}
              </span>
              <span className="text-[10px] text-slate-400 font-sans font-normal ml-1">Сповіщення</span>
            </div>
            <div className="flex items-center gap-1 text-slate-400 dark:text-gray-500">
              <button
                onClick={() => {
                  setIsExpanded(false);
                  setIsMinimized(true);
                }}
                className="p-1 rounded hover:bg-slate-100 dark:hover:bg-[#23272e] hover:text-slate-700 dark:hover:text-gray-200 transition cursor-pointer"
                title="Згорнути в значок"
              >
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div className="text-xs font-bold text-slate-900 dark:text-white leading-snug">
            {activeAlert.title}
          </div>

          <div className="text-[11px] text-slate-600 dark:text-gray-400 leading-relaxed font-sans">
            {activeAlert.desc}
          </div>

          <div className="flex items-center justify-between mt-1 pt-1.5 border-t border-slate-200 dark:border-[#1e2329] text-[11px]">
            <span className="text-slate-500 dark:text-gray-400 font-mono text-[10px]">
              Ціна: <span className="font-semibold text-slate-700 dark:text-gray-200">{activeAlert.price}</span>
            </span>
            <button
              onClick={handleOpenChart}
              className="inline-flex items-center gap-1 text-emerald-600 dark:text-[#0ecb81] hover:underline font-semibold cursor-pointer text-xs"
            >
              <span>Відкрити графік</span>
              <span>→</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
