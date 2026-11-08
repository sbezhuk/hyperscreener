import React, { useEffect, useRef } from 'react';
import { Timeframe } from '../types';
import { useTheme } from '../context/ThemeContext';

interface TradingViewWidgetProps {
  coin: string;
  timeframe: Timeframe;
}

declare global {
  interface Window {
    TradingView?: any;
  }
}

function mapTimeframeToTvInterval(tf: Timeframe): string {
  const clean = tf.trim().toLowerCase();
  if (clean === '1m') return '1';
  if (clean === '5m') return '5';
  if (clean === '15m') return '15';
  if (clean === '1h') return '60';
  if (clean === '4h') return '240';
  if (clean === '1d' || clean === 'd') return 'D';
  return '60';
}

export const TradingViewWidget: React.FC<TradingViewWidgetProps> = ({ coin, timeframe }) => {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const containerRef = useRef<HTMLDivElement>(null);
  const containerId = useRef(`tradingview_${Math.random().toString(36).substring(2, 9)}`).current;

  useEffect(() => {
    let isCancelled = false;

    const loadScriptAndInit = () => {
      if (window.TradingView) {
        initWidget();
        return;
      }

      const existingScript = document.getElementById('tradingview-widget-script');
      if (!existingScript) {
        const script = document.createElement('script');
        script.id = 'tradingview-widget-script';
        script.src = 'https://s3.tradingview.com/tv.js';
        script.type = 'text/javascript';
        script.async = true;
        script.onload = () => {
          if (!isCancelled) {
            initWidget();
          }
        };
        document.head.appendChild(script);
      } else {
        existingScript.addEventListener('load', () => {
          if (!isCancelled) {
            initWidget();
          }
        });
      }
    };

    const initWidget = () => {
      if (!containerRef.current || !window.TradingView) return;

      // Clean old container content
      containerRef.current.innerHTML = `<div id="${containerId}" style="width:100%;height:100%;"></div>`;

      const cleanCoin = coin.toUpperCase().trim();
      // Try BINANCE perpetual / spot format or CRYPTO fallback
      const symbol = `BINANCE:${cleanCoin}USDT`;

      new window.TradingView.widget({
        autosize: true,
        symbol: symbol,
        interval: mapTimeframeToTvInterval(timeframe),
        timezone: 'Etc/UTC',
        theme: isDark ? 'dark' : 'light',
        style: '1',
        locale: 'uk',
        toolbar_bg: isDark ? '#0e1114' : '#f8fafc',
        enable_publishing: false,
        hide_top_toolbar: false,
        hide_side_toolbar: false, // Displays the native TradingView left drawing toolbar!
        allow_symbol_change: true,
        save_image: true,
        container_id: containerId,
        studies: [],
        disabled_features: ['use_localstorage_for_settings'],
        enabled_features: ['study_templates'],
      });
    };

    loadScriptAndInit();

    return () => {
      isCancelled = true;
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
    };
  }, [coin, timeframe, isDark, containerId]);

  return (
    <div className="relative w-full h-full min-h-0 min-w-0 bg-[#0e1114] overflow-hidden">
      <div ref={containerRef} className="w-full h-full" />
    </div>
  );
};
