export type Timeframe = '1m' | '5m' | '15m' | '1h' | '4h' | '1D' | '1H' | '4H';

export function normalizeTimeframe(tf?: string): Timeframe {
  if (!tf) return '4h';
  const clean = tf.trim().toLowerCase();
  if (clean === '1m') return '1m';
  if (clean === '5m') return '5m';
  if (clean === '15m') return '15m';
  if (clean === '1h') return '1h';
  if (clean === '4h') return '4h';
  if (clean === '1d' || clean === 'd') return '1D';
  return '4h';
}

export type FormationFilter = 'NONE' | 'CASCADE' | 'SWEEP' | 'TRENDLINE' | 'FVG';

export type ConnectionState = 'connected' | 'reconnecting' | 'disconnected' | 'failed';

export interface WSConnectionDetails {
  state: ConnectionState;
  attempt?: number;
  nextRetryDelay?: number;
  reason?: string;
  isManual?: boolean;
}

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
  category: 'sweep' | 'cascade' | 'trendline' | 'fvg' | 'breakout_oi';
  title: string;
  direction: 'LONG' | 'SHORT' | 'NEUTRAL';
  desc: string;
  price: number;
  distPct?: number;
  time: number;
  scenario?: string;
  badgeColor?: string;
}

export interface OIDeltaItem {
  interval_seconds: number;
  current_oi: number | null;
  previous_oi: number | null;
  delta: number;
  delta_pct: number;
  status: 'OK' | 'STALE' | 'INSUFFICIENT_HISTORY' | 'GAP_DETECTED' | 'NO_DATA';
  is_valid: boolean;
  start_time: number | null;
  end_time: number | null;
  actual_duration_seconds: number;
}

export interface OILevelAnalysis {
  level_id: string;
  level_price: number;
  level_type: 'resistance' | 'support';
  current_price: number;
  test_start_price: number;
  breakout_price: number | null;
  test_start_time: number | null;
  current_time: number;
  duration_seconds: number;
  direction: 'UP' | 'DOWN';
  oi_delta: number;
  oi_delta_pct: number;
  threshold_pct: number;
  status: string;
  scenario: 'SCENARIO_A' | 'SCENARIO_B' | 'SCENARIO_C' | 'SCENARIO_D' | null;
  badge_color: 'green' | 'red' | 'gray' | 'amber' | 'blue';
  interpretation: string;
  is_breakout: boolean;
  in_test_zone: boolean;
  is_valid: boolean;
  is_new_event?: boolean;
  is_impulse?: boolean;
}

export interface OIData {
  coin: string;
  current_oi: number | null;
  current_oi_usd?: number | null;
  current_price: number | null;
  timestamp: number | null;
  is_stale: boolean;
  samples_count: number;
  deltas: {
    '1m': OIDeltaItem;
    '5m': OIDeltaItem;
    '15m': OIDeltaItem;
    '1h': OIDeltaItem;
  };
  volatility_threshold_pct: number;
  volatility_info?: {
    threshold_pct: number;
    is_adaptive: boolean;
    status: string;
    samples_count: number;
    desc: string;
  };
  oi_status: 'INCREASING' | 'DECREASING' | 'NEUTRAL' | 'COLLECTING' | 'STALE';
  oi_color: 'green' | 'red' | 'gray';
  level_analyses: OILevelAnalysis[];
  breakout_signals: OILevelAnalysis[];
}

export interface AnalysisData {
  isFastPath?: boolean;
  isLiveTick?: boolean;
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
  oi?: OIData;
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
  openInterest?: number;
  oiDelta5m?: number;
  oiDeltaPct5m?: number;
  oiStatus?: string;
  oiColor?: string;
  oiDeltaStatus5m?: string;
  oiThresholdPct?: number;
}

/**
 * Formats Open Interest percentage delta with 3 decimal places precision (e.g. +0.003%, -0.016%, +0.117%).
 * - Preserves exact positive/negative sign
 * - Does not collapse small non-zero numbers into zero
 * - Never substitutes null or undefined with 0.000%
 * - Returns 0.000% only if value truly equals 0 after 3-decimal rounding
 */
export function formatOiDeltaPct(pct: number | null | undefined): string {
  if (pct === null || pct === undefined || Number.isNaN(pct)) {
    return '...';
  }
  const formatted = pct.toFixed(3);
  if (formatted === '0.000' || formatted === '-0.000') {
    return '0.000%';
  }
  return pct > 0 ? `+${formatted}%` : `${formatted}%`;
}
