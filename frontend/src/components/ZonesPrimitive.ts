import {
  ISeriesPrimitive,
  SeriesAttachedParameter,
  ISeriesPrimitivePaneView,
  ISeriesPrimitivePaneRenderer,
  Time,
} from 'lightweight-charts';
import { LevelItem, FVGItem, FVGConfluenceItem, FormationFilter, LiquiditySweepItem, TrendlineItem } from '../types';

export interface ZonesPrimitiveData {
  resistances?: LevelItem[];
  supports?: LevelItem[];
  fvgs?: FVGItem[];
  fvgConfluences?: FVGConfluenceItem[];
  trendlines?: TrendlineItem[];
  sweeps?: Array<LiquiditySweepItem>;
  activeFormation: FormationFilter;
  theme?: 'dark' | 'light';
  currentTimeframe?: string;
}

// Helper: draws a sleek pill badge with high contrast that never bleeds into candles
function drawBadge(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  color: string,
  align: 'left' | 'right' = 'left',
  theme: 'dark' | 'light' = 'dark'
) {
  ctx.font = 'bold 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace';
  const metrics = ctx.measureText(text);
  const textWidth = metrics.width;
  const paddingX = 6;
  const badgeHeight = 16;
  const badgeWidth = textWidth + paddingX * 2;

  const badgeX = align === 'right' ? x - badgeWidth : x;
  const badgeY = y - badgeHeight / 2;

  // Background container
  ctx.fillStyle = theme === 'light' ? 'rgba(255, 255, 255, 0.94)' : 'rgba(11, 14, 17, 0.92)';
  ctx.beginPath();
  if (ctx.roundRect) {
    ctx.roundRect(badgeX, badgeY, badgeWidth, badgeHeight, 3);
  } else {
    ctx.rect(badgeX, badgeY, badgeWidth, badgeHeight);
  }
  ctx.fill();

  // Fine boundary border
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.stroke();

  // Text
  ctx.fillStyle = color;
  ctx.textBaseline = 'middle';
  ctx.fillText(text, badgeX + paddingX, badgeY + badgeHeight / 2);
}

export class ZonesPrimitive implements ISeriesPrimitive<Time> {
  private _chart: any = null;
  private _series: any = null;
  private _requestUpdate: (() => void) | null = null;
  private _data: ZonesPrimitiveData = {
    resistances: [],
    supports: [],
    fvgs: [],
    trendlines: [],
    sweeps: [],
    activeFormation: 'CASCADE',
  };

  private _paneView: ISeriesPrimitivePaneView;

  constructor() {
    const renderer: ISeriesPrimitivePaneRenderer = {
      draw: (target: any) => {
        if (!this._chart || !this._series) return;
        try {
          target.useMediaCoordinateSpace(({ context: ctx, mediaSize }: any) => {
            this._draw(ctx, mediaSize.width, mediaSize.height);
          });
        } catch (err) {
          console.warn('Error in ZonesPrimitive draw:', err);
        }
      },
    };

    this._paneView = {
      zOrder: () => 'normal',
      renderer: () => renderer,
    };
  }

  attached(param: SeriesAttachedParameter<Time, any>): void {
    this._chart = param.chart;
    this._series = param.series;
    this._requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }

  updateData(data: ZonesPrimitiveData): void {
    this._data = {
      ...this._data,
      ...data,
      resistances: data.resistances || [],
      supports: data.supports || [],
      fvgs: data.fvgs || [],
      fvgConfluences: data.fvgConfluences || [],
      trendlines: data.trendlines || [],
      sweeps: data.sweeps || [],
      theme: data.theme || 'dark',
    };
    if (this._requestUpdate) {
      this._requestUpdate();
    }
  }

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    return [this._paneView];
  }

  private _draw(ctx: CanvasRenderingContext2D, width: number, height: number): void {
    const activeFormation = this._data.activeFormation;
    if (activeFormation === 'NONE') return;

    const resistances = this._data.resistances || [];
    const supports = this._data.supports || [];
    const fvgs = this._data.fvgs || [];
    const trendlines = this._data.trendlines || [];
    const sweeps = this._data.sweeps || [];
    const theme = this._data.theme || 'dark';

    const timeScale = this._chart.timeScale();
    const candleSeries = this._series;
    const maxRightX = width - 4;

    // 1. Draw Clean FVG Zones (Only Bullish and Bearish FVGs)
    if (activeFormation === 'FVG') {
      fvgs.forEach((f) => {
        const topPrice = f.upper_price ?? f.top;
        const bottomPrice = f.lower_price ?? f.bottom;

        const yTop = candleSeries.priceToCoordinate(topPrice);
        const yBottom = candleSeries.priceToCoordinate(bottomPrice);
        if (yTop === null || yBottom === null) return;

        const fvgStartTime = f.creation_timestamp ?? f.startTime;
        let xStart = timeScale.timeToCoordinate(fvgStartTime as any);
        if (xStart === null || xStart < 0) xStart = 0;

        const boxWidth = Math.max(maxRightX - xStart, 25);
        const boxHeight = Math.max(Math.abs(yBottom - yTop), 4);
        const minY = Math.min(yTop, yBottom);

        const isBull = f.type.toLowerCase() === 'bullish';
        const fillCol = isBull ? 'rgba(14, 203, 129, 0.14)' : 'rgba(246, 70, 93, 0.14)';
        const borderCol = isBull ? 'rgba(14, 203, 129, 0.75)' : 'rgba(246, 70, 93, 0.75)';

        // Zone rectangle
        ctx.fillStyle = fillCol;
        ctx.fillRect(xStart, minY, boxWidth, boxHeight);

        ctx.strokeStyle = borderCol;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 3]);
        ctx.strokeRect(xStart, minY, boxWidth, boxHeight);
        ctx.setLineDash([]);

        // Badge: Bullish / Bearish FVG
        const badgeText = isBull ? '▲ BULL FVG' : '▼ BEAR FVG';
        drawBadge(ctx, badgeText, maxRightX - 8, minY + boxHeight / 2, borderCol, 'right', theme);
      });
      return;
    }

    // 2. Draw Trendlines (Наклонки) - Strictly per timeframe
    if (activeFormation === 'TRENDLINE') {
      const currentTf = this._data.currentTimeframe?.toLowerCase();

      trendlines.forEach((tl) => {
        // Enforce strict timeframe independence on canvas
        if (currentTf && tl.timeframe && tl.timeframe.toLowerCase() !== currentTf) {
          return;
        }

        const pt1 = tl.start_point || tl.p1;
        const pt2 = tl.end_point || tl.p2;
        if (!pt1 || !pt2) return;

        const x1 = timeScale.timeToCoordinate(pt1.time as any);
        const y1 = candleSeries.priceToCoordinate(pt1.price);
        const x2 = timeScale.timeToCoordinate(pt2.time as any);
        const y2 = candleSeries.priceToCoordinate(pt2.price);

        if (x1 === null || y1 === null || x2 === null || y2 === null) return;
        if (x2 <= x1) return;

        const tlType = tl.line_type || tl.type || '';
        const isSupport = tlType.includes('support') || tl.direction === 'ASCENDING' || tl.direction === 'LONG';
        const isBroken = tl.status === 'BROKEN';
        const isForming = tl.status === 'FORMING';

        const baseColor = isSupport ? '#0ecb81' : '#f6465d';
        const color = isBroken ? (isSupport ? 'rgba(14, 203, 129, 0.45)' : 'rgba(246, 70, 93, 0.45)') : baseColor;

        const slope = (y2 - y1) / (x2 - x1);
        const extendX = maxRightX;
        const extendY = y2 + slope * (extendX - x2);

        // Solid ray line between anchors
        ctx.strokeStyle = color;
        ctx.lineWidth = isBroken ? 1.5 : 2;
        if (isBroken) {
          ctx.setLineDash([4, 4]);
        } else {
          ctx.setLineDash([]);
        }
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        // Projected extension ray to the right
        ctx.setLineDash(isBroken ? [3, 4] : [5, 4]);
        ctx.beginPath();
        ctx.moveTo(x2, y2);
        ctx.lineTo(extendX, extendY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Pivot anchors
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(x1, y1, 3.5, 0, Math.PI * 2);
        ctx.arc(x2, y2, 3.5, 0, Math.PI * 2);
        ctx.fill();

        // 1. Structural Quality (Q) - Neutral styling without directional bias
        const qVal = tl.structuralQuality ?? tl.structural_quality ?? Math.round(tl.strength ?? 50);
        const qText = `Q: ${Math.round(qVal)}`;
        const qColor = theme === 'dark' ? '#cbd5e1' : '#475569';

        // 2. Market Interaction State
        const rawState = tl.interactionState || tl.interaction_state;
        const stateLabel = rawState || (isBroken ? 'BREAKOUT' : (isForming ? 'FORMING' : 'ACTIVE'));

        let stateColor = '#94a3b8';
        if (stateLabel === 'BREAKOUT' || isBroken) {
          stateColor = '#f6465d';
        } else if (stateLabel === 'RETEST') {
          stateColor = '#3b82f6';
        } else if (stateLabel === 'COMPRESSION') {
          stateColor = '#f59e0b';
        } else if (stateLabel === 'TESTING') {
          stateColor = '#eab308';
        } else if (stateLabel === 'REJECTED') {
          stateColor = '#10b981';
        } else if (stateLabel === 'APPROACHING') {
          stateColor = '#94a3b8';
        } else if (stateLabel === 'STALE') {
          stateColor = '#64748b';
        }

        // Display label: includes line label, timeframe, and state badge
        let displayLabel = tl.timeframe_label || tl.label || 'Наклонка';
        if (isBroken || stateLabel === 'BREAKOUT') {
          displayLabel += ' [Пробита]';
        } else if (isForming || stateLabel === 'FORMING') {
          displayLabel += ' [Формується]';
        } else if (stateLabel && stateLabel !== 'ACTIVE') {
          displayLabel += ` [${stateLabel}]`;
        }

        // Measure badge widths to layout badges adjacent to each other from right to left
        ctx.font = 'bold 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace';
        const qWidth = ctx.measureText(qText).width + 12;

        let rightOffset = maxRightX - 8;

        // 1. Draw Q badge at rightmost edge
        drawBadge(ctx, qText, rightOffset, extendY, qColor, 'right', theme);
        rightOffset -= (qWidth + 4);

        // 2. Draw Market Interaction State badge
        const stateWidth = ctx.measureText(displayLabel).width + 12;
        drawBadge(ctx, displayLabel, rightOffset, extendY, stateColor, 'right', theme);
        rightOffset -= (stateWidth + 4);

        // 3. Phase 4: Structural Risk Warning (e.g. AGAINST HTF)
        const riskFlags = tl.structuralRiskFlags || tl.structural_risk_flags || [];
        const isAgainstHtf = riskFlags.includes('AGAINST_HTF') || tl.htfContext === 'AGAINST_HTF' || tl.htf_context === 'AGAINST_HTF';
        if (isAgainstHtf) {
          const warningLabel = '⚠️ AGAINST HTF';
          drawBadge(ctx, warningLabel, rightOffset, extendY, '#ef4444', 'right', theme);
        }
      });
      return;
    }

    // 3. Draw False Breakout / Sweep Levels (Pristine, No Collisions)
    if (activeFormation === 'SWEEP') {
      // Filter out visual collisions: if two sweeps are within 18px on the Y axis, keep only the most significant one
      interface VisualSweep {
        sw: typeof sweeps[0];
        yLevel: number;
        ySweep: number | null;
        ySL: number | null;
        slPrice: number;
        xBreakout: number | null;
        xCandle: number | null;
        score: number;
      }

      const visualItems: VisualSweep[] = [];
      sweeps.forEach((sw) => {
        const yLevel = candleSeries.priceToCoordinate(sw.levelPrice);
        if (yLevel === null) return;
        const ySweep = candleSeries.priceToCoordinate(sw.sweepPrice);
        const xBreakout = sw.breakoutTime ? timeScale.timeToCoordinate(sw.breakoutTime as any) : null;
        const xConfirm = sw.confirmationTime ? timeScale.timeToCoordinate(sw.confirmationTime as any) : timeScale.timeToCoordinate(sw.time as any);
        const xCandle = xConfirm ?? xBreakout;

        // Calculate safe Stop-Loss price with protective buffer (0.25x sweep depth or min 0.18% price)
        const isLong = sw.direction === 'LONG';
        const sweepDist = Math.abs(sw.sweepPrice - sw.levelPrice);
        const buffer = Math.max(sweepDist * 0.25, sw.sweepPrice * 0.0018);
        const slPrice = isLong
          ? Number((sw.sweepPrice - buffer).toFixed(sw.sweepPrice > 10 ? 2 : 4))
          : Number((sw.sweepPrice + buffer).toFixed(sw.sweepPrice > 10 ? 2 : 4));
        const ySL = candleSeries.priceToCoordinate(slPrice);

        // Importance score for collision resolution
        const strength = sw.levelStrength ?? 50;
        const touches = sw.touches ?? 1;
        const recency = sw.time;
        const score = strength * 2 + touches * 10 + recency * 0.0001;

        visualItems.push({
          sw,
          yLevel,
          ySweep,
          ySL,
          slPrice,
          xBreakout,
          xCandle,
          score,
        });
      });

      // Sort by importance descending
      visualItems.sort((a, b) => b.score - a.score);

      // Select items without visual collision (min 20px badge vertical gap)
      const nonColliding: VisualSweep[] = [];
      const minPixelGap = 20;

      for (const item of visualItems) {
        const hasCollision = nonColliding.some(
          (chosen) => Math.abs(chosen.yLevel - item.yLevel) < minPixelGap
        );
        if (!hasCollision) {
          nonColliding.push(item);
        }
      }

      // Draw non-colliding breakouts
      nonColliding.forEach(({ sw, yLevel, ySweep, ySL, slPrice, xBreakout, xCandle }) => {
        const isLong = sw.direction === 'LONG';
        const color = isLong ? '#0ecb81' : '#f6465d';

        // Draw horizontal swept level line across the chart
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 3]);
        ctx.beginPath();
        ctx.moveTo(0, yLevel);
        ctx.lineTo(maxRightX, yLevel);
        ctx.stroke();
        ctx.setLineDash([]);

        // Elegant Sweep Box & Safe Stop-Loss indicator (with protective buffer above/below wick)
        const x1 = xBreakout !== null ? xBreakout : xCandle;
        const x2 = xCandle !== null ? xCandle : xBreakout;
        if (x1 !== null && x2 !== null && ySweep !== null) {
          const minX = Math.min(x1, x2) - 10;
          const maxX = Math.max(x1, x2) + 10;
          const boxTop = Math.min(yLevel, ySweep);
          const boxBottom = Math.max(yLevel, ySweep);
          const boxH = Math.max(boxBottom - boxTop, 3);
          const centerX = (minX + maxX) / 2;

          // 1. Shaded Liquidity Sweep Zone (penetration area)
          ctx.fillStyle = isLong ? 'rgba(14, 203, 129, 0.12)' : 'rgba(246, 70, 93, 0.12)';
          ctx.fillRect(minX, boxTop, maxX - minX, boxH);

          // 2. Subtle dashed perimeter of the sweep zone
          ctx.strokeStyle = isLong ? 'rgba(14, 203, 129, 0.45)' : 'rgba(246, 70, 93, 0.45)';
          ctx.lineWidth = 1;
          ctx.setLineDash([3, 2]);
          ctx.strokeRect(minX, boxTop, maxX - minX, boxH);
          ctx.setLineDash([]);

          // 3. Peak wick indicator (subtle mark at the exact candle extreme)
          ctx.strokeStyle = isLong ? 'rgba(14, 203, 129, 0.5)' : 'rgba(246, 70, 93, 0.5)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(minX + 2, ySweep);
          ctx.lineTo(maxX - 2, ySweep);
          ctx.stroke();

          // 4. Safe Stop-Loss Level with Protective Buffer (NEVER flush to the wick)
          // Ensures at least a 12-16px visual safety margin and an algorithmic price buffer
          const safeYSL = ySL !== null
            ? (isLong ? Math.max(ySL, ySweep + 14) : Math.min(ySL, ySweep - 14))
            : (isLong ? ySweep + 14 : ySweep - 14);

          // Dotted connector from wick peak to safe SL level showing the protective buffer
          ctx.strokeStyle = isLong ? 'rgba(14, 203, 129, 0.6)' : 'rgba(246, 70, 93, 0.6)';
          ctx.lineWidth = 1;
          ctx.setLineDash([2, 2]);
          ctx.beginPath();
          ctx.moveTo(centerX, ySweep);
          ctx.lineTo(centerX, safeYSL);
          ctx.stroke();
          ctx.setLineDash([]);

          // Horizontal Stop-Loss bar at safe buffer distance
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(minX - 4, safeYSL);
          ctx.lineTo(maxX + 4, safeYSL);
          ctx.stroke();

          // 5. Sleek "SL {price}" pill badge placed cleanly at the buffered Stop-Loss bar
          const slText = `SL ${slPrice}`;
          ctx.font = 'bold 9px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace';
          const textWidth = ctx.measureText(slText).width;
          const pillW = textWidth + 8;
          const pillH = 14;
          const pillX = centerX - pillW / 2;
          const pillY = isLong ? safeYSL + 2 : safeYSL - pillH - 2;

          ctx.fillStyle = theme === 'dark' ? 'rgba(15, 20, 25, 0.95)' : 'rgba(255, 255, 255, 0.95)';
          ctx.strokeStyle = color;
          ctx.lineWidth = 1;
          ctx.beginPath();
          if (typeof ctx.roundRect === 'function') {
            ctx.roundRect(pillX, pillY, pillW, pillH, 3);
          } else {
            ctx.rect(pillX, pillY, pillW, pillH);
          }
          ctx.fill();
          ctx.stroke();

          ctx.fillStyle = color;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(slText, pillX + pillW / 2, pillY + pillH / 2);
          ctx.textAlign = 'left';
        }

        // Sleek badge on the right edge with dark background
        const typeTag = sw.subType === 'two_candle_reversal' ? ' [2C]' : '';
        const oiTag = sw.oiDeltaPct !== undefined && sw.oiDeltaPct !== null
          ? ` [OI ${sw.oiDeltaPct > 0 ? '+' : ''}${sw.oiDeltaPct.toFixed(2)}%]`
          : '';
        const statusTag = sw.confirmationStatus === 'CONFIRMED'
          ? '✓ '
          : sw.confirmationStatus === 'POTENTIAL'
          ? '⌛ '
          : '⚠ ';
        const badgeLabel = `${statusTag}ХИБНИЙ ПРОБІЙ ${sw.levelPrice} (${sw.direction})${typeTag}${oiTag}`;
        drawBadge(ctx, badgeLabel, maxRightX - 8, yLevel, color, 'right', theme);
      });
      return;
    }

    // 4. Draw Cascade / Support & Resistance Zones
    if (activeFormation === 'CASCADE') {
      // Helper: resolve fill opacity from strength_score (0-100) → 0.06..0.18
      const fillOpacity = (score?: number) => {
        const s = score ?? 50;
        return 0.06 + (Math.min(s, 100) / 100) * 0.12;
      };

      // Draw Resistances (ALWAYS RED)
      resistances.forEach((r) => {
        if (!r.price || r.touches < 1) return;

        const yTop = candleSeries.priceToCoordinate(r.top);
        const yBottom = candleSeries.priceToCoordinate(r.bottom);
        if (yTop === null || yBottom === null) return;

        let xStart = r.firstTime ? (timeScale.timeToCoordinate(r.firstTime as any) as number | null) : 0;
        if (xStart === null || xStart < 0) xStart = 0;

        const boxWidth = Math.max(maxRightX - xStart, 20);
        const boxHeight = Math.max(Math.abs(yBottom - yTop), 3);
        const minY = Math.min(yTop, yBottom);

        const isWeakening = r.status === 'weakening';
        const opacity = fillOpacity(r.strength_score);

        // Fill - Red
        ctx.fillStyle = `rgba(246, 70, 93, ${opacity})`;
        ctx.fillRect(xStart, minY, boxWidth, boxHeight);

        // Border - Red
        const borderAlpha = r.touches >= 3 ? 0.75 : 0.45;
        ctx.strokeStyle = `rgba(246, 70, 93, ${borderAlpha})`;
        ctx.setLineDash([]);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(xStart, minY);
        ctx.lineTo(maxRightX, minY);
        ctx.moveTo(xStart, minY + boxHeight);
        ctx.lineTo(maxRightX, minY + boxHeight);
        ctx.stroke();

        // Badge text: clean ОПІР with timeframe, touches and score anchored cleanly at the right edge
        const sc = r.strength_score !== undefined ? Math.round(r.strength_score) : undefined;
        const retestPart = r.status === 'retested' ? ' [ДЗЕРКАЛЬНИЙ]' : '';
        const tfBadge = r.timeframe ? ` [${r.timeframe.replace('h', 'H').replace('d', 'D')}]` : '';
        const badgeText = `ОПІР${tfBadge} x${r.touches}${sc !== undefined ? ` S:${sc}` : ''}${retestPart}`;
        drawBadge(ctx, badgeText, maxRightX - 8, minY + boxHeight / 2, 'rgba(246, 70, 93, 0.95)', 'right', theme);
      });

      // Draw Supports (ALWAYS GREEN)
      supports.forEach((s) => {
        if (!s.price || s.touches < 1) return;

        const yTop = candleSeries.priceToCoordinate(s.top);
        const yBottom = candleSeries.priceToCoordinate(s.bottom);
        if (yTop === null || yBottom === null) return;

        let xStart = s.firstTime ? (timeScale.timeToCoordinate(s.firstTime as any) as number | null) : 0;
        if (xStart === null || xStart < 0) xStart = 0;

        const boxWidth = Math.max(maxRightX - xStart, 20);
        const boxHeight = Math.max(Math.abs(yBottom - yTop), 3);
        const minY = Math.min(yTop, yBottom);

        const isWeakening = s.status === 'weakening';
        const opacity = fillOpacity(s.strength_score);

        // Fill - Green
        ctx.fillStyle = `rgba(14, 203, 129, ${opacity})`;
        ctx.fillRect(xStart, minY, boxWidth, boxHeight);

        // Border - Green
        const borderAlpha = s.touches >= 3 ? 0.75 : 0.45;
        ctx.strokeStyle = `rgba(14, 203, 129, ${borderAlpha})`;
        ctx.setLineDash([]);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(xStart, minY);
        ctx.lineTo(maxRightX, minY);
        ctx.moveTo(xStart, minY + boxHeight);
        ctx.lineTo(maxRightX, minY + boxHeight);
        ctx.stroke();

        // Badge text: clean ПІДТРИМКА with timeframe, touches and score anchored cleanly at the right edge
        const sc = s.strength_score !== undefined ? Math.round(s.strength_score) : undefined;
        const retestPart = s.status === 'retested' ? ' [ДЗЕРКАЛЬНИЙ]' : '';
        const tfBadge = s.timeframe ? ` [${s.timeframe.replace('h', 'H').replace('d', 'D')}]` : '';
        const badgeText = `ПІДТРИМКА${tfBadge} x${s.touches}${sc !== undefined ? ` S:${sc}` : ''}${retestPart}`;
        drawBadge(ctx, badgeText, maxRightX - 8, minY + boxHeight / 2, 'rgba(14, 203, 129, 0.95)', 'right', theme);
      });
    }
  }
}
