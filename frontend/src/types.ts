export type Timeframe = '1m' | '5m' | '15m' | '1h' | '4h' | '1D';

export type FormationFilter = 'NONE' | 'CASCADE' | 'SWEEP' | 'TRENDLINE' | 'FVG';

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LevelItem {
  price: number;
  top: number;
  bottom: number;
  touches: number;
  distPct: number;
  firstTime?: number;
  latestTime?: number;
  strength: number;
  // New fields (populated by the comprehensive algorithm):
  zone_id?: string;
  type?: 'support' | 'resistance';
  upper_price?: number;
  lower_price?: number;
  center_price?: number;
  strength_score?: number;
  touches_count?: number;
  average_bounce_atr?: number;
  volume_confirmation?: number;
  timeframe?: string;
  first_detected_at?: number;
  last_tested_at?: number;
  status?: 'active' | 'weakening' | 'broken' | 'retested';
  is_htf?: boolean;
}

export interface FVGItem {
  type: 'bullish' | 'bearish';
  top: number;
  bottom: number;
  mid: number;
  gapPct: number;
  startTime: number;
  endTime: number;
  status: 'mitigated' | 'unmitigated';
}

export interface SignalItem {
  id: string;
  coin: string;
  interval: string;
  category: 'sweep' | 'cascade' | 'trendline' | 'fvg';
  title: string;
  direction: 'LONG' | 'SHORT' | 'NEUTRAL';
  desc: string;
  price: number;
  distPct?: number;
  time: number;
}

export interface AnalysisData {
  coin: string;
  interval: string;
  currentPrice: number;
  candles: Candle[];
  levels: {
    currentPrice: number;
    resistances: LevelItem[];
    supports: LevelItem[];
    cascades: Array<{
      type: string;
      levels: number[];
      desc: string;
      distPct: number;
    }>;
  };
  fvgs: FVGItem[];
  liquidity: {
    pools: Array<{
      type: string;
      label: string;
      price: number;
      touches?: number;
    }>;
    sweeps: Array<{
      type: string;
      formation: string;
      levelPrice: number;
      sweepPrice: number;
      touches: number;
      direction: 'LONG' | 'SHORT';
      time: number;
      desc: string;
    }>;
    trendlines: Array<{
      type: string;
      label: string;
      p1: { time: number; price: number };
      p2: { time: number; price: number };
    }>;
  };
  structure: {
    trend: 'BULLISH' | 'BEARISH' | 'EXPANDING' | 'CONSOLIDATING' | 'NEUTRAL';
    summary: string;
    events: Array<{
      type: string;
      name: string;
      level: number;
      desc: string;
    }>;
    recentHigh: number;
    recentLow: number;
  };
  signals: SignalItem[];
}

export interface CoinMeta {
  name: string;
  markPrice: number;
  volume24h: number;
  change24h: number;
  openInterest: number;
  fundingRate: number;
  szDecimals: number;
}

export interface ScreenerItem {
  coin: string;
  currentPrice: number;
  trend: string;
  signals: SignalItem[];
  signalsCount: number;
  resistancesCount: number;
  supportsCount: number;
}
