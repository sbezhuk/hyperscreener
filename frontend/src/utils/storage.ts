import { Timeframe, normalizeTimeframe, FormationFilter, ChartDrawing, ChartDrawingPoint } from '../types';

export const STORAGE_KEYS = {
  SELECTED_COIN: 'hyperscreener:selected_coin',
  SELECTED_TIMEFRAME: 'hyperscreener:selected_timeframe',
  ACTIVE_FORMATION: 'hyperscreener:active_formation',
  SELECTED_TFS: 'hyperscreener:selected_tfs',
  MIN_STRENGTH: 'hyperscreener:min_strength',
  ONLY_CONFIRMED_OI: 'hyperscreener:only_confirmed_oi',
  CHART_MODE: 'hyperscreener:chart_mode',
  DRAWINGS_PREFIX: 'hyperscreener:drawings:',
} as const;

export const VALID_FORMATIONS: readonly FormationFilter[] = [
  'NONE',
  'CASCADE',
  'SWEEP',
  'TRENDLINE',
  'FVG',
] as const;

export function isValidFormation(val: any): val is FormationFilter {
  return typeof val === 'string' && (VALID_FORMATIONS as readonly string[]).includes(val.toUpperCase());
}

/**
 * Safe localStorage wrapper that gracefully handles SSR, disabled storage,
 * and quota limits.
 */
export function safeGetItem(key: string): string | null {
  if (typeof window === 'undefined' || !window.localStorage) {
    return null;
  }
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function safeSetItem(key: string, value: string): void {
  if (typeof window === 'undefined' || !window.localStorage) {
    return;
  }
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Graceful fallback for private browsing / quota errors
  }
}

export function safeRemoveItem(key: string): void {
  if (typeof window === 'undefined' || !window.localStorage) {
    return;
  }
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Ignore
  }
}

/**
 * Reads query params from current window.location.search
 */
function getQueryParams(): URLSearchParams | null {
  if (typeof window === 'undefined' || !window.location || !window.location.search) {
    return null;
  }
  try {
    return new URLSearchParams(window.location.search);
  } catch {
    return null;
  }
}

/**
 * Updates URL search query parameters without causing a page reload.
 */
export function syncUrlState(params: {
  coin?: string;
  timeframe?: string;
  formation?: FormationFilter;
}): void {
  if (typeof window === 'undefined' || !window.history || !window.location) {
    return;
  }
  try {
    const url = new URL(window.location.href);
    if (params.coin) {
      url.searchParams.set('coin', params.coin.toUpperCase().trim());
    }
    if (params.timeframe) {
      url.searchParams.set('interval', params.timeframe.toLowerCase().trim());
    }
    if (params.formation) {
      url.searchParams.set('formation', params.formation);
    }
    window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
  } catch {
    // Ignore
  }
}

/**
 * Resolves initial active coin from URL search params -> localStorage -> default ('ETH').
 */
export function getInitialCoin(defaultCoin = 'ETH'): string {
  const query = getQueryParams();
  if (query) {
    const fromUrl = query.get('coin') || query.get('symbol');
    if (fromUrl && fromUrl.trim().length > 0) {
      return fromUrl.toUpperCase().trim();
    }
  }

  const fromStorage = safeGetItem(STORAGE_KEYS.SELECTED_COIN);
  if (fromStorage && fromStorage.trim().length > 0) {
    return fromStorage.toUpperCase().trim();
  }

  return defaultCoin;
}

export function saveSelectedCoin(coin: string): void {
  const clean = coin.toUpperCase().trim();
  safeSetItem(STORAGE_KEYS.SELECTED_COIN, clean);
}

/**
 * Resolves initial timeframe from URL search params -> localStorage -> default ('1D').
 */
export function getInitialTimeframe(defaultTf: Timeframe = '1D'): Timeframe {
  const query = getQueryParams();
  if (query) {
    const fromUrl = query.get('interval') || query.get('tf') || query.get('timeframe');
    if (fromUrl && fromUrl.trim().length > 0) {
      return normalizeTimeframe(fromUrl);
    }
  }

  const fromStorage = safeGetItem(STORAGE_KEYS.SELECTED_TIMEFRAME);
  if (fromStorage && fromStorage.trim().length > 0) {
    return normalizeTimeframe(fromStorage);
  }

  return defaultTf;
}

export function saveSelectedTimeframe(tf: Timeframe): void {
  safeSetItem(STORAGE_KEYS.SELECTED_TIMEFRAME, tf);
}

/**
 * Resolves initial active formation from URL search params -> localStorage -> default ('CASCADE').
 */
export function getInitialFormation(defaultFormation: FormationFilter = 'CASCADE'): FormationFilter {
  const query = getQueryParams();
  if (query) {
    const fromUrl = query.get('formation');
    if (fromUrl && isValidFormation(fromUrl.toUpperCase())) {
      return fromUrl.toUpperCase() as FormationFilter;
    }
  }

  const fromStorage = safeGetItem(STORAGE_KEYS.ACTIVE_FORMATION);
  if (fromStorage && isValidFormation(fromStorage.toUpperCase())) {
    return fromStorage.toUpperCase() as FormationFilter;
  }

  return defaultFormation;
}

export function saveActiveFormation(formation: FormationFilter): void {
  safeSetItem(STORAGE_KEYS.ACTIVE_FORMATION, formation);
}

/**
 * Resolves initial selected multi-timeframe list (e.g. ['1d'] or ['15m', '1h']).
 */
export function getInitialSelectedTfs(currentTimeframe: string): string[] {
  const fromStorage = safeGetItem(STORAGE_KEYS.SELECTED_TFS);
  if (fromStorage) {
    try {
      const parsed = JSON.parse(fromStorage);
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed.map((s) => String(s).toLowerCase().trim());
      }
    } catch {
      // Ignore
    }
  }
  return [currentTimeframe.toLowerCase().trim()];
}

export function saveSelectedTfs(tfs: string[]): void {
  try {
    safeSetItem(STORAGE_KEYS.SELECTED_TFS, JSON.stringify(tfs));
  } catch {
    // Ignore
  }
}

/**
 * Resolves initial minimum strength threshold for levels & FVGs.
 */
export function getInitialMinStrength(defaultMin = 50): number {
  const fromStorage = safeGetItem(STORAGE_KEYS.MIN_STRENGTH);
  if (fromStorage !== null) {
    const parsed = Number(fromStorage);
    if (!isNaN(parsed) && parsed >= 0 && parsed <= 100) {
      return parsed;
    }
  }
  return defaultMin;
}

export function saveMinStrength(score: number): void {
  safeSetItem(STORAGE_KEYS.MIN_STRENGTH, String(score));
}

/**
 * Resolves initial confirmed OI filter toggle.
 */
export function getInitialConfirmedOi(defaultVal = false): boolean {
  const fromStorage = safeGetItem(STORAGE_KEYS.ONLY_CONFIRMED_OI);
  if (fromStorage !== null) {
    return fromStorage === 'true';
  }
  return defaultVal;
}

export function saveConfirmedOi(enabled: boolean): void {
  safeSetItem(STORAGE_KEYS.ONLY_CONFIRMED_OI, String(enabled));
}

/**
 * Resolves initial chart mode ('formations' | 'native_tv')
 */
export function getInitialChartMode(defaultMode: 'formations' | 'native_tv' = 'formations'): 'formations' | 'native_tv' {
  const query = getQueryParams();
  if (query) {
    const fromUrl = query.get('chart_mode') || query.get('mode');
    if (fromUrl === 'native_tv' || fromUrl === 'tv') {
      return 'native_tv';
    }
    if (fromUrl === 'formations') {
      return 'formations';
    }
  }

  const fromStorage = safeGetItem(STORAGE_KEYS.CHART_MODE);
  if (fromStorage === 'native_tv' || fromStorage === 'formations') {
    return fromStorage;
  }

  return defaultMode;
}

export function saveChartMode(mode: 'formations' | 'native_tv'): void {
  safeSetItem(STORAGE_KEYS.CHART_MODE, mode);
}

// -----------------------------------------------------------------------------
// TradingView Drawing Tools State Persistence Interface & Helpers
// -----------------------------------------------------------------------------

export type { ChartDrawing, ChartDrawingPoint };

/**
 * Returns saved drawings for the specified coin.
 */
export function loadCoinDrawings(coin: string): ChartDrawing[] {
  const clean = coin.toUpperCase().trim();
  const raw = safeGetItem(`${STORAGE_KEYS.DRAWINGS_PREFIX}${clean}`);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/**
 * Persists drawings for the specified coin to localStorage.
 */
export function saveCoinDrawings(coin: string, drawings: ChartDrawing[]): void {
  const clean = coin.toUpperCase().trim();
  try {
    safeSetItem(`${STORAGE_KEYS.DRAWINGS_PREFIX}${clean}`, JSON.stringify(drawings));
  } catch {
    // Ignore
  }
}

/**
 * Adds or updates a single drawing for a coin.
 */
export function saveDrawing(coin: string, drawing: ChartDrawing): void {
  const existing = loadCoinDrawings(coin);
  const idx = existing.findIndex((d) => d.id === drawing.id);
  let updated: ChartDrawing[];
  if (idx >= 0) {
    updated = existing.map((d, i) => (i === idx ? drawing : d));
  } else {
    updated = [...existing, drawing];
  }
  saveCoinDrawings(coin, updated);
}

/**
 * Removes a specific drawing by ID.
 */
export function removeDrawing(coin: string, drawingId: string): void {
  const existing = loadCoinDrawings(coin);
  const updated = existing.filter((d) => d.id !== drawingId);
  saveCoinDrawings(coin, updated);
}

/**
 * Clears saved drawings for the specified coin.
 */
export function clearCoinDrawings(coin: string): void {
  const clean = coin.toUpperCase().trim();
  safeRemoveItem(`${STORAGE_KEYS.DRAWINGS_PREFIX}${clean}`);
}
