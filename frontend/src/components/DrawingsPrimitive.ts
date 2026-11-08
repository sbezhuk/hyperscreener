import {
  ISeriesPrimitive,
  SeriesAttachedParameter,
  ISeriesPrimitivePaneView,
  ISeriesPrimitivePaneRenderer,
  Time,
} from 'lightweight-charts';
import { ChartDrawing, ChartDrawingPoint, Candle } from '../types';

export interface DrawingsPrimitiveData {
  drawings: ChartDrawing[];
  activeDrawing?: ChartDrawing | null;
  selectedDrawingId?: string | null;
  hoverDrawingId?: string | null;
  theme?: 'dark' | 'light';
  candles?: Candle[];
}

const FIB_LEVELS = [
  { level: 0.0, label: '0.0', color: '#787b86' },
  { level: 0.236, label: '0.236', color: '#f23645' },
  { level: 0.382, label: '0.382', color: '#ff9800' },
  { level: 0.5, label: '0.5', color: '#4caf50' },
  { level: 0.618, label: '0.618', color: '#089981' },
  { level: 0.786, label: '0.786', color: '#00bcd4' },
  { level: 1.0, label: '1.0', color: '#787b86' },
];

export class DrawingsPrimitive implements ISeriesPrimitive<Time> {
  private _chart: any = null;
  private _series: any = null;
  private _requestUpdate: (() => void) | null = null;
  private _data: DrawingsPrimitiveData = {
    drawings: [],
    activeDrawing: null,
    selectedDrawingId: null,
    hoverDrawingId: null,
    theme: 'dark',
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
          console.warn('Error in DrawingsPrimitive draw:', err);
        }
      },
    };

    this._paneView = {
      zOrder: () => 'top',
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

  updateData(data: Partial<DrawingsPrimitiveData>): void {
    this._data = { ...this._data, ...data };
    if (this._requestUpdate) {
      this._requestUpdate();
    }
  }

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    return [this._paneView];
  }

  private _getPointCoords(p: ChartDrawingPoint): { x: number | null; y: number | null } {
    if (!this._chart || !this._series) return { x: null, y: null };
    const timeScale = this._chart.timeScale();
    let x = (timeScale as any).timeToCoordinate ? (timeScale as any).timeToCoordinate(p.time as any) : null;
    const y = this._series.priceToCoordinate(p.price);

    // Support stretching infinitely into the future or past beyond loaded candles
    if (x === null && this._data.candles && this._data.candles.length > 0) {
      const candles = this._data.candles;
      const last = candles[candles.length - 1];
      const first = candles[0];
      if (p.time >= last.time) {
        const prev = candles[Math.max(0, candles.length - 2)];
        const dt = last.time - prev.time || 60;
        const futureLogical = candles.length - 1 + (p.time - last.time) / dt;
        if ((timeScale as any).logicalToCoordinate) {
          x = (timeScale as any).logicalToCoordinate(futureLogical);
        }
      } else if (p.time <= first.time) {
        const next = candles[1] || first;
        const dt = next.time - first.time || 60;
        const pastLogical = (p.time - first.time) / dt;
        if ((timeScale as any).logicalToCoordinate) {
          x = (timeScale as any).logicalToCoordinate(pastLogical);
        }
      }
    }

    return { x, y };
  }

  private _draw(ctx: CanvasRenderingContext2D, width: number, height: number): void {
    if (!this._chart || !this._series) return;

    const allDrawings = [...this._data.drawings];
    if (this._data.activeDrawing) {
      allDrawings.push(this._data.activeDrawing);
    }

    if (allDrawings.length === 0) return;

    ctx.save();

    for (const d of allDrawings) {
      const isSelected = d.id === this._data.selectedDrawingId;
      const isHovered = d.id === this._data.hoverDrawingId;
      this._drawSingleDrawing(ctx, d, isSelected, isHovered, width, height);
    }

    ctx.restore();
  }

  private _drawSingleDrawing(
    ctx: CanvasRenderingContext2D,
    d: ChartDrawing,
    isSelected: boolean,
    isHovered: boolean,
    width: number,
    height: number
  ): void {
    const points = d.points || [];
    if (points.length === 0) return;

    const baseColor = d.color || '#2962ff';
    const lineWidth = (d.lineWidth || 2) + (isHovered && !isSelected ? 1 : 0);
    const lineStyle = d.lineStyle ?? 0; // 0: solid, 1: dotted, 2: dashed

    ctx.save();
    ctx.strokeStyle = baseColor;
    ctx.lineWidth = lineWidth;

    if (lineStyle === 1) {
      ctx.setLineDash([3, 3]);
    } else if (lineStyle === 2) {
      ctx.setLineDash([6, 4]);
    } else {
      ctx.setLineDash([]);
    }

    const coords = points.map((p) => this._getPointCoords(p));

    switch (d.type) {
      case 'trendline': {
        if (coords.length < 2) break;
        const p1 = coords[0];
        const p2 = coords[1];
        if (p1.x === null || p1.y === null || p2.x === null || p2.y === null) break;

        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();

        if (isSelected) {
          this._drawHandle(ctx, p1.x, p1.y, baseColor);
          this._drawHandle(ctx, p2.x, p2.y, baseColor);
        }
        break;
      }

      case 'ray': {
        if (coords.length < 2) break;
        const p1 = coords[0];
        const p2 = coords[1];
        if (p1.x === null || p1.y === null || p2.x === null || p2.y === null) break;

        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        let endX = p2.x;
        let endY = p2.y;

        if (Math.abs(dx) > 0.0001) {
          const targetX = dx > 0 ? width + 50 : -50;
          const slope = dy / dx;
          endX = targetX;
          endY = p1.y + slope * (targetX - p1.x);
        } else {
          endY = dy > 0 ? height + 50 : -50;
        }

        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(endX, endY);
        ctx.stroke();

        if (isSelected) {
          this._drawHandle(ctx, p1.x, p1.y, baseColor);
          this._drawHandle(ctx, p2.x, p2.y, baseColor);
        }
        break;
      }

      case 'horizontal': {
        const p1 = coords[0];
        if (p1.y === null) break;

        ctx.beginPath();
        ctx.moveTo(0, p1.y);
        ctx.lineTo(width, p1.y);
        ctx.stroke();

        this._drawPriceBadge(ctx, points[0].price, width - 4, p1.y, baseColor);

        if (isSelected) {
          const midX = p1.x !== null ? p1.x : width / 2;
          this._drawHandle(ctx, midX, p1.y, baseColor);
        }
        break;
      }

      case 'horizontal_ray': {
        const p1 = coords[0];
        if (p1.x === null || p1.y === null) break;

        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(width, p1.y);
        ctx.stroke();

        this._drawPriceBadge(ctx, points[0].price, width - 4, p1.y, baseColor);

        if (isSelected) {
          this._drawHandle(ctx, p1.x, p1.y, baseColor);
        }
        break;
      }

      case 'rectangle': {
        if (coords.length < 2) break;
        const p1 = coords[0];
        const p2 = coords[1];
        if (p1.x === null || p1.y === null || p2.x === null || p2.y === null) break;

        const left = Math.min(p1.x, p2.x);
        const top = Math.min(p1.y, p2.y);
        const rectW = Math.abs(p2.x - p1.x);
        const rectH = Math.abs(p2.y - p1.y);

        ctx.fillStyle = d.fillColor || `${baseColor}22`;
        ctx.fillRect(left, top, rectW, rectH);

        ctx.beginPath();
        ctx.strokeRect(left, top, rectW, rectH);

        if (isSelected) {
          this._drawHandle(ctx, p1.x, p1.y, baseColor);
          this._drawHandle(ctx, p2.x, p2.y, baseColor);
          this._drawHandle(ctx, p1.x, p2.y, baseColor);
          this._drawHandle(ctx, p2.x, p1.y, baseColor);
        }
        break;
      }

      case 'fibonacci': {
        if (coords.length < 2) break;
        const p1 = coords[0];
        const p2 = coords[1];
        if (p1.x === null || p1.y === null || p2.x === null || p2.y === null) break;

        const price1 = points[0].price;
        const price2 = points[1].price;
        const priceDiff = price2 - price1;

        const leftX = Math.min(p1.x, p2.x);
        const rightX = Math.max(width, Math.max(p1.x, p2.x));

        // Draw Fibonacci Levels
        for (const fib of FIB_LEVELS) {
          const targetPrice = price1 + priceDiff * fib.level;
          const y = this._series.priceToCoordinate(targetPrice);
          if (y === null) continue;

          ctx.strokeStyle = fib.color;
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 2]);

          ctx.beginPath();
          ctx.moveTo(leftX, y);
          ctx.lineTo(rightX, y);
          ctx.stroke();

          // Label
          ctx.font = '10px monospace';
          ctx.fillStyle = fib.color;
          ctx.fillText(`${fib.label} ($${targetPrice.toFixed(2)})`, leftX + 6, y - 3);
        }

        // Draw main diagonal
        ctx.strokeStyle = baseColor;
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 2]);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();

        if (isSelected) {
          this._drawHandle(ctx, p1.x, p1.y, baseColor);
          this._drawHandle(ctx, p2.x, p2.y, baseColor);
        }
        break;
      }

      case 'text': {
        const p1 = coords[0];
        if (p1.x === null || p1.y === null) break;
        const text = d.text || 'Текст';

        ctx.font = 'bold 12px Inter, sans-serif';
        const metrics = ctx.measureText(text);
        const padX = 8;
        const padY = 5;
        const boxW = metrics.width + padX * 2;
        const boxH = 22;

        ctx.fillStyle = this._data.theme === 'light' ? '#ffffff' : '#1e222d';
        ctx.strokeStyle = baseColor;
        ctx.lineWidth = isSelected ? 2 : 1;
        ctx.setLineDash([]);

        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(p1.x, p1.y - boxH / 2, boxW, boxH, 4);
        } else {
          ctx.rect(p1.x, p1.y - boxH / 2, boxW, boxH);
        }
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = this._data.theme === 'light' ? '#131722' : '#d1d4dc';
        ctx.textBaseline = 'middle';
        ctx.fillText(text, p1.x + padX, p1.y);

        if (isSelected) {
          this._drawHandle(ctx, p1.x, p1.y, baseColor);
        }
        break;
      }

      case 'ruler': {
        if (coords.length < 2) break;
        const p1 = coords[0];
        const p2 = coords[1];
        if (p1.x === null || p1.y === null || p2.x === null || p2.y === null) break;

        const left = Math.min(p1.x, p2.x);
        const top = Math.min(p1.y, p2.y);
        const rectW = Math.abs(p2.x - p1.x);
        const rectH = Math.abs(p2.y - p1.y);

        const price1 = points[0].price;
        const price2 = points[1].price;
        const deltaPrice = price2 - price1;
        const deltaPct = price1 !== 0 ? (deltaPrice / price1) * 100 : 0;
        const isUp = deltaPrice >= 0;

        const boxColor = isUp ? '#0ecb81' : '#f6465d';
        ctx.fillStyle = `${boxColor}22`;
        ctx.fillRect(left, top, rectW, rectH);

        ctx.strokeStyle = boxColor;
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.strokeRect(left, top, rectW, rectH);

        // Arrow from start to end
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();

        // Info pill in middle
        const midX = (p1.x + p2.x) / 2;
        const midY = (p1.y + p2.y) / 2;
        const infoText = `${isUp ? '+' : ''}${deltaPrice.toFixed(2)} (${isUp ? '+' : ''}${deltaPct.toFixed(2)}%)`;

        ctx.font = 'bold 11px monospace';
        const infoMetrics = ctx.measureText(infoText);
        const infoW = infoMetrics.width + 12;
        const infoH = 20;

        ctx.fillStyle = this._data.theme === 'light' ? 'rgba(255,255,255,0.92)' : 'rgba(20,24,32,0.92)';
        ctx.strokeStyle = boxColor;
        ctx.lineWidth = 1;
        ctx.setLineDash([]);
        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(midX - infoW / 2, midY - infoH / 2, infoW, infoH, 4);
        } else {
          ctx.rect(midX - infoW / 2, midY - infoH / 2, infoW, infoH);
        }
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = boxColor;
        ctx.textBaseline = 'middle';
        ctx.textAlign = 'center';
        ctx.fillText(infoText, midX, midY);
        ctx.textAlign = 'left';

        if (isSelected) {
          this._drawHandle(ctx, p1.x, p1.y, boxColor);
          this._drawHandle(ctx, p2.x, p2.y, boxColor);
        }
        break;
      }

      case 'brush': {
        if (coords.length < 2) break;
        ctx.beginPath();
        let started = false;
        for (const pt of coords) {
          if (pt.x === null || pt.y === null) continue;
          if (!started) {
            ctx.moveTo(pt.x, pt.y);
            started = true;
          } else {
            ctx.lineTo(pt.x, pt.y);
          }
        }
        ctx.stroke();
        break;
      }

      case 'long_position':
      case 'short_position': {
        if (coords.length < 3) break;
        const c0 = coords[0]; // Entry
        const c1 = coords[1]; // TP
        const c2 = coords[2]; // SL
        if (c0.x === null || c0.y === null || c1.y === null || c2.y === null) break;

        const xStart = c0.x;
        const xEnd = c1.x !== null ? c1.x : (c2.x !== null ? c2.x : xStart + 150);
        const left = Math.min(xStart, xEnd);
        const right = Math.max(xStart, xEnd);
        const boxWidth = Math.max(20, right - left);
        const xMid = left + boxWidth / 2;

        const yEntry = c0.y;
        const yTP = c1.y;
        const ySL = c2.y;

        const entryPrice = points[0].price;
        const tpPrice = points[1].price;
        const slPrice = points[2].price;

        const risk = Math.abs(entryPrice - slPrice);
        const reward = Math.abs(tpPrice - entryPrice);
        const rr = risk > 0 ? (reward / risk).toFixed(2) : '0.00';

        const tpPct = entryPrice > 0 ? ((Math.abs(tpPrice - entryPrice) / entryPrice) * 100).toFixed(2) : '0.00';
        const slPct = entryPrice > 0 ? ((Math.abs(slPrice - entryPrice) / entryPrice) * 100).toFixed(2) : '0.00';

        const isLong = d.type === 'long_position';
        const tpColor = '#0ecb81';
        const slColor = '#f6465d';

        // 1. Draw Profit (TP) Box
        const tpTop = Math.min(yEntry, yTP);
        const tpH = Math.max(1, Math.abs(yEntry - yTP));
        ctx.fillStyle = 'rgba(14, 203, 129, 0.22)';
        ctx.fillRect(left, tpTop, boxWidth, tpH);
        ctx.strokeStyle = tpColor;
        ctx.lineWidth = 1.2;
        ctx.setLineDash([]);
        ctx.strokeRect(left, tpTop, boxWidth, tpH);

        // 2. Draw Loss (SL) Box
        const slTop = Math.min(yEntry, ySL);
        const slH = Math.max(1, Math.abs(yEntry - ySL));
        ctx.fillStyle = 'rgba(246, 70, 93, 0.22)';
        ctx.fillRect(left, slTop, boxWidth, slH);
        ctx.strokeStyle = slColor;
        ctx.lineWidth = 1.2;
        ctx.strokeRect(left, slTop, boxWidth, slH);

        // 3. Draw Entry separator line
        ctx.beginPath();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.moveTo(left, yEntry);
        ctx.lineTo(right, yEntry);
        ctx.stroke();
        ctx.setLineDash([]);

        // 4. Render sleek TradingView-styled stats badges
        const fmt = (p: number) => (p >= 1000 ? p.toFixed(2) : p >= 1 ? p.toFixed(4) : p.toFixed(6));

        const badgeLeft = left + 14;

        // TP Badge
        const tpBadgeY = isLong ? tpTop + 4 : tpTop + tpH - 22;
        this._drawPositionBadge(ctx, `Ціль: $${fmt(tpPrice)} (+${tpPct}%)`, badgeLeft, tpBadgeY, tpColor, 'left');

        // SL Badge
        const slBadgeY = isLong ? slTop + slH - 22 : slTop + 4;
        this._drawPositionBadge(ctx, `Стоп: $${fmt(slPrice)} (-${slPct}%)`, badgeLeft, slBadgeY, slColor, 'left');

        // Center / Entry R:R Badge
        const entryBadgeY = yEntry - 9;
        this._drawPositionBadge(ctx, `Вхід: $${fmt(entryPrice)} | Р/П: 1:${rr}`, badgeLeft, entryBadgeY, '#3b82f6', 'left');

        // 5. Handles when selected
        if (isSelected) {
          // Left handle (move position)
          this._drawHandle(ctx, left, yEntry, '#3b82f6');
          // TP handle
          this._drawHandle(ctx, xMid, yTP, tpColor);
          // SL handle
          this._drawHandle(ctx, xMid, ySL, slColor);
          // Right edge handle (time duration)
          this._drawHandle(ctx, right, yEntry, '#ffffff');
        }
        break;
      }
    }

    ctx.restore();
  }

  private _drawPositionBadge(
    ctx: CanvasRenderingContext2D,
    text: string,
    x: number,
    y: number,
    color: string,
    anchor: 'top' | 'bottom' | 'center' | 'left'
  ): void {
    ctx.save();
    ctx.font = 'bold 10px monospace';
    const textWidth = ctx.measureText(text).width;
    const badgeW = textWidth + 12;
    const badgeH = 18;
    let badgeX = x - badgeW / 2;
    let badgeY = y - badgeH / 2;
    if (anchor === 'left') {
      badgeX = x;
      badgeY = y;
    } else if (anchor === 'top') {
      badgeY = y - badgeH - 2;
    } else if (anchor === 'bottom') {
      badgeY = y + 2;
    }

    ctx.fillStyle = this._data.theme === 'light' ? 'rgba(255, 255, 255, 0.94)' : 'rgba(19, 23, 34, 0.94)';
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 4);
    } else {
      ctx.rect(badgeX, badgeY, badgeW, badgeH);
    }
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = color;
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    ctx.fillText(text, badgeX + 6, badgeY + badgeH / 2);
    ctx.restore();
  }

  private _drawHandle(ctx: CanvasRenderingContext2D, x: number, y: number, color: string): void {
    ctx.save();
    ctx.fillStyle = '#ffffff';
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.setLineDash([]);

    ctx.beginPath();
    ctx.arc(x, y, 4.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  private _drawPriceBadge(
    ctx: CanvasRenderingContext2D,
    price: number,
    x: number,
    y: number,
    color: string
  ): void {
    ctx.save();
    const text = `$${price.toFixed(2)}`;
    ctx.font = 'bold 10px monospace';
    const textWidth = ctx.measureText(text).width;
    const badgeW = textWidth + 10;
    const badgeH = 16;
    const badgeX = x - badgeW;
    const badgeY = y - badgeH / 2;

    ctx.fillStyle = color;
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 3);
    } else {
      ctx.rect(badgeX, badgeY, badgeW, badgeH);
    }
    ctx.fill();

    ctx.fillStyle = '#ffffff';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, badgeX + 5, badgeY + badgeH / 2);
    ctx.restore();
  }
}
