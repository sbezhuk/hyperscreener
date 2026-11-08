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

export type DrawingToolType =
  | 'cursor'
  | 'trendline'
  | 'ray'
  | 'horizontal'
  | 'horizontal_ray'
  | 'rectangle'
  | 'fibonacci'
  | 'text'
  | 'ruler'
  | 'brush'
  | 'eraser';

export interface ChartDrawingPoint {
  time: number;
  price: number;
}

export interface ChartDrawing {
  id: string;
  type: DrawingToolType | string;
  coin: string;
  timeframe?: string;
  points: ChartDrawingPoint[];
  text?: string;
  color?: string;
  lineWidth?: number;
  lineStyle?: number; // 0: Solid, 1: Dotted, 2: Dashed
  fillColor?: string;
  fillOpacity?: number;
  properties?: Record<string, any>;
  createdAt: number;
  updatedAt: number;
}

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
  is_pivot?: boolean;
  pivot_label?: 'PP' | 'R1' | 'R2' | 'R3' | 'S1' | 'S2' | 'S3' | string;
  // SMC Smart Money Fields:
  smc_type?: 'ORDER_BLOCK' | 'BREAKER_BLOCK' | 'LIQUIDITY_POOL' | 'STRUCTURE_ORIGIN' | string;
  smc_label?: string;
  is_mitigated?: boolean;
  has_fvg?: boolean;
  caused_bos?: boolean;
  swept_liquidity?: boolean;
  zone_location?: 'Premium' | 'Discount' | 'Equilibrium';
  vol_ratio?: number;
  displacement_atr?: number;
  strength_category?: 'Weak' | 'Moderate' | 'Strong' | 'Very Strong';
}

export interface PivotPointsData {
  period: string;
  period_key?: string;
  first_time?: number;
  last_time?: number;
  high: number;
  low: number;
  close: number;
  pp: number;
  r1: number;
  r2: number;
  r3: number;
  s1: number;
  s2: number;
  s3: number;
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

export interface StructuralContext {
  contextAvailable: boolean;
  context_available?: boolean;
  unavailableReason?: string | null;
  unavailable_reason?: string | null;
  htfAlignment: 'ALIGNED' | 'AGAINST_HTF' | 'NEUTRAL' | 'UNAVAILABLE';
  htf_alignment?: 'ALIGNED' | 'AGAINST_HTF' | 'NEUTRAL' | 'UNAVAILABLE';
  hasSupportConfluence: boolean;
  has_support_confluence?: boolean;
  confluentLineQ?: number | null;
  confluent_line_q?: number | null;
  distanceToSupportAtr?: number | null;
  distance_to_support_atr?: number | null;
  distanceToResistanceAtr?: number | null;
  distance_to_resistance_atr?: number | null;
  nearestSupportQ?: number | null;
  nearest_support_q?: number | null;
  nearestResistanceQ?: number | null;
  nearest_resistance_q?: number | null;
  isCompression: boolean;
  is_compression?: boolean;
  compressionRatio?: number | null;
  compression_ratio?: number | null;
  isRetest: boolean;
  is_retest?: boolean;
  riskFlags: string[];
  risk_flags?: string[];
  structuralTier: 'TIER_1_CONFLUENT' | 'TIER_2_STANDARD' | 'TIER_3_WARNING';
  structural_tier?: 'TIER_1_CONFLUENT' | 'TIER_2_STANDARD' | 'TIER_3_WARNING';
}

export interface ConfluenceFactor {
  category: 'structure' | 'level' | 'sweep' | 'fvg' | 'trendline' | 'oi' | string;
  title: string;
  desc: string;
  weight: number;
}

export interface TradeSetup {
  coin: string;
  interval: string;
  action: 'LOOK_FOR_LONG' | 'LOOK_FOR_SHORT' | 'WAIT' | string;
  direction: 'LONG' | 'SHORT' | 'NEUTRAL';
  recommendation_title: string;
  status_label: string;
  badge_color: 'green' | 'red' | 'gray' | string;
  entry_price: number | null;
  entry_range: [number, number] | null;
  stop_loss: number | null;
  take_profit: number | null;
  targets?: number[];
  risk_reward: number | null;
  risk_reward_formatted: string | null;
  risk_pct: number | null;
  reward_pct: number | null;
  confluence_score: number;
  confluence_tier: 'HIGH' | 'MEDIUM' | 'SPECULATIVE' | 'NONE' | string;
  confluence_factors: ConfluenceFactor[];
  primary_trigger?: string;
  summary_comment: string;
  long_potential?: {
    score: number;
    rr: number | null;
    rejection_reason?: string;
  };
  short_potential?: {
    score: number;
    rr: number | null;
    rejection_reason?: string;
  };
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
  badge_color?: string;
  confirmationStatus?: 'CONFIRMED' | 'UNCONFIRMED' | 'POTENTIAL';
  statusLabel?: string;
  status_label?: string;
  oiConfirmed?: boolean;
  oi_confirmed?: boolean;
  oiDeltaPct?: number | null;
  oi_delta_pct?: number | null;
  oiDelta?: number | null;
  oi_delta?: number | null;
  oiReason?: string;
  oi_reason?: string;
  oiReasonDesc?: string;
  strength?: number;

  // Trendline Structural Intelligence (Phase 1, 2, 4)
  structural_quality?: number;
  structuralQuality?: number;
  interaction_state?: string;
  interactionState?: string;
  touch_count?: number;
  touchCount?: number;
  distance_to_line_atr?: number;
  distanceToLineAtr?: number;
  compression_ratio?: number;
  compressionRatio?: number;
  htf_context?: 'ALIGNED' | 'AGAINST_HTF' | 'NEUTRAL' | 'UNAVAILABLE';
  htfContext?: 'ALIGNED' | 'AGAINST_HTF' | 'NEUTRAL' | 'UNAVAILABLE';
  structural_risk_flags?: string[];
  structuralRiskFlags?: string[];

  // Phase 5.2: Enriched Structural Context
  structuralContext?: StructuralContext;
  structural_context?: StructuralContext;

  // Trendline Improved Signals (Breakout & Retest, Bounce, OI)
  signal_type?: 'BREAKOUT' | 'BOUNCE' | 'APPROACH' | 'CHANNEL_BREAKOUT' | 'CHANNEL_FALSE_BREAKOUT' | 'CHANNEL_TEST' | string;
  signalType?: 'BREAKOUT' | 'BOUNCE' | 'APPROACH' | 'CHANNEL_BREAKOUT' | 'CHANNEL_FALSE_BREAKOUT' | 'CHANNEL_TEST' | string;
  is_retest?: boolean;
  isRetest?: boolean;
  is_confirmed?: boolean;
  isConfirmed?: boolean;
  target_price?: number;
  targetPrice?: number;
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

export interface TrendlineItem {
  id?: string;
  timeframe: string;
  direction: 'ASCENDING' | 'DESCENDING' | 'UP' | 'DOWN' | 'LONG' | 'SHORT';
  line_type: string;
  start_point: { time: number; price: number; index?: number };
  end_point: { time: number; price: number; index?: number };
  slope: number;
  touch_count: number;
  strength: number;
  status: 'ACTIVE' | 'BROKEN' | 'FORMING' | 'STALE';
  last_updated: number;
  type: string;
  label: string;
  timeframe_label?: string;
  p1: { time: number; price: number };
  p2: { time: number; price: number };
  score?: number;
  touches?: number;

  // Trendline Structural Intelligence
  structural_quality?: number;
  structuralQuality?: number;
  structural_quality_components?: {
    anchor_prominence: number;
    spacing_regularity: number;
    ray_precision: number;
    void_integrity: number;
  };
  structuralQualityComponents?: {
    anchor_prominence: number;
    spacing_regularity: number;
    ray_precision: number;
    void_integrity: number;
  };
  interaction_state?: 'APPROACHING' | 'TESTING' | 'REJECTED' | 'COMPRESSION' | 'BREAKOUT' | 'RETEST' | 'STALE' | string;
  interactionState?: 'APPROACHING' | 'TESTING' | 'REJECTED' | 'COMPRESSION' | 'BREAKOUT' | 'RETEST' | 'STALE' | string;
  interaction_state_since?: number;
  interactionStateSince?: number;
  previous_interaction_state?: string;
  previousInteractionState?: string;
  touchCount?: number;
  last_confirmed_touch?: number;
  lastConfirmedTouch?: number;
  touch_spacing_bars?: number;
  touchSpacingBars?: number;
  distance_to_line_atr?: number;
  distanceToLineAtr?: number;
  compression_ratio?: number;
  compressionRatio?: number;
  arrival_velocity?: number;
  arrivalVelocity?: number;

  // Phase 4: HTF Structural Context & Risk Flags
  htf_context?: 'ALIGNED' | 'AGAINST_HTF' | 'NEUTRAL' | 'UNAVAILABLE';
  htfContext?: 'ALIGNED' | 'AGAINST_HTF' | 'NEUTRAL' | 'UNAVAILABLE';
  structural_risk_flags?: string[];
  structuralRiskFlags?: string[];

  // 3-Touch Confirmation Rule
  is_confirmed?: boolean;
  isConfirmed?: boolean;
  confirmation_status?: 'CONFIRMED' | 'FORMING' | string;
  confirmationStatus?: 'CONFIRMED' | 'FORMING' | string;
  touches_rule?: string;
}

export interface RegressionChannelItem {
  id: string;
  timeframe: string;
  slope: number;
  intercept: number;
  r_squared: number;
  rSquared?: number;
  std_dev: number;
  stdDev?: number;
  num_std: number;
  numStd?: number;
  direction: 'ASCENDING' | 'DESCENDING' | 'FLAT';
  sample_size: number;
  channel_position_pct: number;
  channelPositionPct?: number;
  start_time: number;
  end_time: number;
  middle: {
    p1: { time: number; price: number };
    p2: { time: number; price: number };
  };
  upper?: {
    p1: { time: number; price: number };
    p2: { time: number; price: number };
  };
  lower?: {
    p1: { time: number; price: number };
    p2: { time: number; price: number };
  };
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
    pivot_points?: PivotPointsData;
  };
  multiTimeframeLevels?: Record<string, { resistances: LevelItem[]; supports: LevelItem[]; pivot_points?: PivotPointsData }>;
  fvgs: FVGItem[];
  multiTimeframeFvgs?: Record<string, FVGItem[]>;
  fvgConfluences?: FVGConfluenceItem[];
  trendlines?: TrendlineItem[];
  multiTimeframeTrendlines?: Record<string, TrendlineItem[]>;
  regressionChannel?: RegressionChannelItem | null;
  regression_channel?: RegressionChannelItem | null;
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
      confirmationStatus?: 'CONFIRMED' | 'UNCONFIRMED' | 'POTENTIAL';
      statusLabel?: string;
      oiConfirmed?: boolean;
      oiDeltaPct?: number | null;
      oiDelta?: number | null;
      oiReason?: string;
      oiReasonDesc?: string;
    }>;
    trendlines: TrendlineItem[];
    regressionChannel?: RegressionChannelItem | null;
    regression_channel?: RegressionChannelItem | null;
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
  tradeSetup?: TradeSetup;
  trade_setup?: TradeSetup;
  summarySignal?: TradeSetup;
}

export type LiquiditySweepItem = AnalysisData['liquidity']['sweeps'][number];

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
  tradeSetup?: TradeSetup;
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

/**
 * Calculates optimal price precision and minMove step for Lightweight Charts
 * based on price magnitude and actual candle decimal places.
 */
export function getAssetPricePrecision(
  candles?: { open: number; high: number; low: number; close: number }[] | null,
  currentPrice?: number
): { precision: number; minMove: number } {
  let samplePrice = currentPrice && currentPrice > 0 ? currentPrice : 0;
  let maxDecimalsFromData = 0;

  if (candles && candles.length > 0) {
    const sample = candles.slice(-50);
    if (!samplePrice) {
      samplePrice = sample[sample.length - 1]?.close || 0;
    }
    for (const c of sample) {
      for (const val of [c.close, c.open, c.high, c.low]) {
        if (typeof val === 'number' && !isNaN(val) && val > 0) {
          const s = Number(val.toPrecision(12)).toString();
          const dot = s.indexOf('.');
          if (dot !== -1) {
            const dec = s.length - dot - 1;
            if (dec > maxDecimalsFromData && dec <= 8) {
              maxDecimalsFromData = dec;
            }
          }
        }
      }
    }
  }

  // Baseline precision based on price magnitude
  let baselinePrecision = 2;
  if (samplePrice >= 10000) baselinePrecision = 1;
  else if (samplePrice >= 1000) baselinePrecision = 2;
  else if (samplePrice >= 100) baselinePrecision = 2;
  else if (samplePrice >= 10) baselinePrecision = 3;
  else if (samplePrice >= 1) baselinePrecision = 4;
  else if (samplePrice >= 0.1) baselinePrecision = 5;
  else if (samplePrice >= 0.01) baselinePrecision = 6;
  else if (samplePrice >= 0.001) baselinePrecision = 7;
  else if (samplePrice > 0) baselinePrecision = 8;

  const precision = Math.min(8, Math.max(baselinePrecision, maxDecimalsFromData));
  const minMove = Number(Math.pow(10, -precision).toFixed(precision));

  return { precision, minMove };
}

/**
 * Formats asset price with precision tailored to asset magnitude.
 * Avoids truncating significant decimals for coins like $1.3412 or $0.00365.
 */
export function formatPrice(price: number | null | undefined, maxDecimals?: number): string {
  if (price === null || price === undefined || Number.isNaN(price) || price <= 0) {
    return '---';
  }
  if (maxDecimals !== undefined) {
    return price.toFixed(maxDecimals);
  }
  if (price >= 10000) return price.toFixed(1);
  if (price >= 1000) return price.toFixed(2);
  if (price >= 100) return price.toFixed(2);
  if (price >= 10) return price.toFixed(3);
  if (price >= 1) return price.toFixed(4);
  if (price >= 0.1) return price.toFixed(5);
  if (price >= 0.01) return price.toFixed(6);
  if (price >= 0.001) return price.toFixed(6);
  return price.toFixed(8);
}

