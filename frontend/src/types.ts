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
  fvg_id?: string;
  symbol?: string;
  timeframe?: string;
  type: 'bullish' | 'bearish' | 'BULLISH' | 'BEARISH';
  upper_price?: number;
  lower_price?: number;
  midpoint_price?: number;
  gap_size?: number;
  gap_size_atr?: number;
  strength_score?: number;
  strength_category?: 'Weak' | 'Moderate' | 'Strong' | 'Very Strong';
  mitigation_percent?: number;
  wick_penetration_percent?: number;
  close_penetration_percent?: number;
  mitigation_status?: 'FRESH' | 'PARTIALLY MITIGATED' | '50% MITIGATED' | 'FULLY MITIGATED' | 'INVERTED' | 'INVALIDATED';
  inversion_status?: string;
  inversion_timestamp?: number;
  inversion_price?: number;
  ifvg_type?: string;
  creation_timestamp?: number;
  last_tested_timestamp?: number;
  ce_reached?: boolean;
  ce_first_time?: number;
  ce_close_after?: number;
  first_candle_id?: number;
  impulse_candle_id?: number;
  third_candle_id?: number;
  volume_confirmation?: boolean;
  market_structure_confirmation?: boolean;
  // Compatibility fields
  top: number;
  bottom: number;
  mid: number;
  gapPct: number;
  startTime: number;
  endTime: number;
  status: 'mitigated' | 'unmitigated' | string;
}

export interface FVGConfluenceItem {
  confluence_id: string;
  type: 'BULLISH' | 'BEARISH' | string;
  upper_price: number;
  lower_price: number;
  midpoint_price: number;
  timeframes: string[];
  timeframe_count: number;
  confluence_score: number;
  fvg_ids: string[];
  desc: string;
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
  isFastPath?: boolean;
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
  multiTimeframeLevels?: Record<string, { resistances: LevelItem[]; supports: LevelItem[] }>;
  fvgs: FVGItem[];
  multiTimeframeFvgs?: Record<string, FVGItem[]>;
  fvgConfluences?: FVGConfluenceItem[];
  liquidity: {
    pools: Array<{
      type: string;
      label: string;
      price: number;
      touches?: number;
    }>;
    sweeps: Array<{
      id?: string;
      type: string;
      subType?: string;
      formation: string;
      levelPrice: number;
      sweepPrice: number;
      touches?: number;
      levelStrength?: number;
      volumeRatio?: number;
      direction: 'LONG' | 'SHORT';
      time: number;
      breakoutTime?: number;
      confirmationTime?: number;
      desc: string;
      isLive?: boolean;
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
