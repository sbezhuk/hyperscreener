import {
  ISeriesPrimitive,
  SeriesAttachedParameter,
  ISeriesPrimitivePaneView,
  ISeriesPrimitivePaneRenderer,
  Time,
} from 'lightweight-charts';
import { LevelItem, FVGItem, FormationFilter } from '../types';

export interface ZonesPrimitiveData {
  resistances?: LevelItem[];
  supports?: LevelItem[];
  fvgs?: FVGItem[];
  trendlines?: Array<{
    type: string;
    label: string;
    p1: { time: number; price: number };
    p2: { time: number; price: number };
  }>;
  sweeps?: Array<{
    type: string;
    formation: string;
    levelPrice: number;
    sweepPrice: number;
    touches: number;
    direction: 'LONG' | 'SHORT';
    time: number;
    desc: string;
  }>;
  activeFormation: FormationFilter;
}

// Helper: draws a sleek dark pill badge with high contrast that never bleeds into candles
function drawBadge(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  color: string,
  align: 'left' | 'right' = 'left'
) {
  ctx.font = 'bold 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace';
  const metrics = ctx.measureText(text);
  const textWidth = metrics.width;
  const paddingX = 6;
  const badgeHeight = 16;
  const badgeWidth = textWidth + paddingX * 2;

  const badgeX = align === 'right' ? x - badgeWidth : x;
  const badgeY = y - badgeHeight / 2;

  // Dark background container
  ctx.fillStyle = 'rgba(11, 14, 17, 0.92)';
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
      trendlines: data.trendlines || [],
      sweeps: data.sweeps || [],
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

    const timeScale = this._chart.timeScale();
    const candleSeries = this._series;
    const maxRightX = width - 4;

    // 1. Draw Clean FVG Zones
    if (activeFormation === 'FVG') {
      fvgs.forEach((f) => {
        const yTop = candleSeries.priceToCoordinate(f.top);
        const yBottom = candleSeries.priceToCoordinate(f.bottom);
        if (yTop === null || yBottom === null) return;

        let xStart = timeScale.timeToCoordinate(f.startTime as any);
        if (xStart === null || xStart < 0) xStart = 0;

        const boxWidth = Math.max(maxRightX - xStart, 20);
        const boxHeight = Math.max(Math.abs(yBottom - yTop), 4);
        const minY = Math.min(yTop, yBottom);

        const isBull = f.type === 'bullish';
        const fillCol = isBull ? 'rgba(14, 203, 129, 0.12)' : 'rgba(246, 70, 93, 0.12)';
        const borderCol = isBull ? 'rgba(14, 203, 129, 0.65)' : 'rgba(246, 70, 93, 0.65)';

        // Clean rectangle
        ctx.fillStyle = fillCol;
        ctx.fillRect(xStart, minY, boxWidth, boxHeight);

        ctx.strokeStyle = borderCol;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 3]);
        ctx.strokeRect(xStart, minY, boxWidth, boxHeight);
        ctx.setLineDash([]);

        // Badge anchored cleanly at the right
        const badgeText = `${isBull ? '▲ BULL' : '▼ BEAR'} FVG`;
        drawBadge(ctx, badgeText, maxRightX - 8, minY + boxHeight / 2, borderCol, 'right');
      });
      return;
    }

    // 2. Draw Trendlines (Наклонки)
    if (activeFormation === 'TRENDLINE') {
      trendlines.forEach((tl) => {
        const x1 = timeScale.timeToCoordinate(tl.p1.time as any);
        const y1 = candleSeries.priceToCoordinate(tl.p1.price);
        const x2 = timeScale.timeToCoordinate(tl.p2.time as any);
        const y2 = candleSeries.priceToCoordinate(tl.p2.price);

        if (x1 === null || y1 === null || x2 === null || y2 === null) return;
        if (x2 <= x1) return;

        const isSupport = tl.type.includes('support');
        const color = isSupport ? '#0ecb81' : '#f6465d';

        const slope = (y2 - y1) / (x2 - x1);
        const extendX = maxRightX;
        const extendY = y2 + slope * (extendX - x2);

        // Ray line
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        ctx.setLineDash([5, 4]);
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

        // Badge at right ray end
        drawBadge(ctx, tl.label, maxRightX - 10, extendY, color, 'right');
      });
      return;
    }

    // 3. Draw False Breakout / Sweep Levels (Pristine, No Collisions)
    if (activeFormation === 'SWEEP') {
      sweeps.forEach((sw) => {
        const yLevel = candleSeries.priceToCoordinate(sw.levelPrice);
        const ySweep = candleSeries.priceToCoordinate(sw.sweepPrice);
        const xCandle = timeScale.timeToCoordinate(sw.time as any);

        if (yLevel === null) return;

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

        // Subtle vertical wick sweep marker on the triggering candle
        if (xCandle !== null && ySweep !== null) {
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(xCandle, yLevel);
          ctx.lineTo(xCandle, ySweep);
          ctx.stroke();
        }

        // Sleek badge on the right edge with dark background (NEVER touches candles)
        const badgeLabel = `ХИБНИЙ ПРОБІЙ ${sw.levelPrice} (${sw.direction})`;
        drawBadge(ctx, badgeLabel, maxRightX - 8, yLevel, color, 'right');
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
        drawBadge(ctx, badgeText, maxRightX - 8, minY + boxHeight / 2, 'rgba(246, 70, 93, 0.95)', 'right');
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
        drawBadge(ctx, badgeText, maxRightX - 8, minY + boxHeight / 2, 'rgba(14, 203, 129, 0.95)', 'right');
      });
    }
  }
}
