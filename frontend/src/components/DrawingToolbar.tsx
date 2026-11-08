import React, { useState, useRef, useEffect } from 'react';
import { Trash2, GripVertical } from 'lucide-react';
import { DrawingToolType, ChartDrawing } from '../types';

interface DrawingToolbarProps {
  activeTool: DrawingToolType;
  onSelectTool: (tool: DrawingToolType) => void;
  selectedDrawing?: ChartDrawing | null;
  onUpdateDrawing?: (updated: Partial<ChartDrawing>, drawingId?: string) => void;
  onDeleteSelectedDrawing?: (drawingId?: string) => void;
  onClearAllDrawings?: () => void;
  drawingsCount: number;
}

const PRESET_COLORS = [
  { name: 'Синій', value: '#2962ff' },
  { name: 'Зелений', value: '#0ecb81' },
  { name: 'Червоний', value: '#f6465d' },
  { name: 'Помаранчевий', value: '#ff9800' },
  { name: 'Фіолетовий', value: '#ab47bc' },
  { name: 'Білий', value: '#ffffff' },
];

const PRESET_WIDTHS = [1, 2, 3, 4];

// Native TradingView SVG Icons matching the official TradingView drawing sidebar
const TvIcons = {
  Crosshair: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="#00f2fe" strokeWidth="1.6">
      <line x1="14" y1="3" x2="14" y2="9" />
      <line x1="14" y1="19" x2="14" y2="25" />
      <line x1="3" y1="14" x2="9" y2="14" />
      <line x1="19" y1="14" x2="25" y2="14" />
    </svg>
  ),
  TrendLine: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="7" cy="21" r="2.5" />
      <circle cx="21" cy="7" r="2.5" />
      <line x1="8.8" y1="19.2" x2="19.2" y2="8.8" />
    </svg>
  ),
  Fibonacci: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <line x1="4" y1="6" x2="19" y2="6" />
      <circle cx="21.5" cy="6" r="2" />
      <line x1="4" y1="11" x2="24" y2="11" />
      <line x1="4" y1="17" x2="24" y2="17" />
      <circle cx="6.5" cy="22" r="2" />
      <line x1="8.5" y1="22" x2="24" y2="22" />
    </svg>
  ),
  Patterns: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.4">
      <circle cx="6" cy="20" r="1.8" />
      <circle cx="11" cy="8" r="1.8" />
      <circle cx="16" cy="16" r="1.8" />
      <circle cx="22" cy="10" r="1.8" />
      <circle cx="22" cy="20" r="1.8" />
      <path d="M7.5 18.5L9.5 9.5L14.5 14.5L20.5 11" />
      <line x1="16" y1="18" x2="21" y2="20" />
      <line x1="11" y1="9.5" x2="16" y2="14.5" />
    </svg>
  ),
  Prediction: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="6" cy="7" r="2" />
      <line x1="8" y1="7" x2="24" y2="7" />
      <line x1="7" y1="9" x2="21" y2="19" strokeDasharray="2,2" />
      <circle cx="22" cy="14" r="2" />
      <line x1="4" y1="14" x2="20" y2="14" />
      <circle cx="6" cy="21" r="2" />
      <line x1="8" y1="21" x2="24" y2="21" />
    </svg>
  ),
  Brush: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M6 21c2.5-3 5-7 8.5-8.5 2-.8 3.5.5 3 2.5-.8 3-5 5-8 6-1.5.5-2.5.5-3.5 0z" />
      <path d="M17.5 12.5l3.5-3.5c1-1 2.5-1 3.5 0l-.5 3.5-3.5 3.5" />
    </svg>
  ),
  Text: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="currentColor">
      <path d="M7 6h14v3h-1.5c-.3-1.2-.8-1.5-2.5-1.5h-1.5v12.5c0 1.2.3 1.5 2 1.5V23h-7v-1.5c1.7 0 2-.3 2-1.5V7.5H11c-1.7 0-2.2.3-2.5 1.5H7V6z" />
    </svg>
  ),
  Smiley: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="14" cy="14" r="9" />
      <circle cx="11" cy="12" r="1" fill="currentColor" />
      <circle cx="17" cy="12" r="1" fill="currentColor" />
      <path d="M10 16c1 2 2.5 2.5 4 2.5s3-.5 4-2.5" />
    </svg>
  ),
  Ruler: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M7 21L21 7l3 3L10 24z" />
      <line x1="18.5" y1="9.5" x2="16.5" y2="11.5" />
      <line x1="15.5" y1="12.5" x2="14" y2="14" />
      <line x1="12.5" y1="15.5" x2="10.5" y2="17.5" />
    </svg>
  ),
  Zoom: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="13" cy="13" r="6.5" />
      <line x1="18" y1="18" x2="23" y2="23" />
      <line x1="13" y1="10" x2="13" y2="16" />
      <line x1="10" y1="13" x2="16" y2="13" />
    </svg>
  ),
  Magnet: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 8v6a6 6 0 0012 0V8" />
      <line x1="8" y1="11" x2="11" y2="11" />
      <line x1="17" y1="11" x2="20" y2="11" />
      <path d="M8 8h3v3H8zM17 8h3v3h-3z" />
    </svg>
  ),
  LockMode: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M7 20l1-5L17 6l4 4-9 9-5 1z" />
      <rect x="15" y="16" width="7" height="6" rx="1" />
      <path d="M17 16v-2a1.5 1.5 0 013 0v2" />
    </svg>
  ),
  Eye: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 14s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" />
      <circle cx="14" cy="14" r="3" />
    </svg>
  ),
  LongPosition: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none">
      <rect x="4" y="5" width="20" height="9" fill="#0ecb81" fillOpacity="0.4" stroke="#0ecb81" strokeWidth="1.2" rx="1" />
      <rect x="4" y="14" width="20" height="9" fill="#f6465d" fillOpacity="0.4" stroke="#f6465d" strokeWidth="1.2" rx="1" />
      <line x1="4" y1="14" x2="24" y2="14" stroke="#ffffff" strokeWidth="1.5" />
      <polygon points="14,7 10.5,11.5 17.5,11.5" fill="#0ecb81" />
    </svg>
  ),
  ShortPosition: () => (
    <svg viewBox="0 0 28 28" width="18" height="18" fill="none">
      <rect x="4" y="5" width="20" height="9" fill="#f6465d" fillOpacity="0.4" stroke="#f6465d" strokeWidth="1.2" rx="1" />
      <rect x="4" y="14" width="20" height="9" fill="#0ecb81" fillOpacity="0.4" stroke="#0ecb81" strokeWidth="1.2" rx="1" />
      <line x1="4" y1="14" x2="24" y2="14" stroke="#ffffff" strokeWidth="1.5" />
      <polygon points="14,21 10.5,16.5 17.5,16.5" fill="#0ecb81" />
    </svg>
  ),
};

export const DrawingToolbar: React.FC<DrawingToolbarProps> = ({
  activeTool,
  onSelectTool,
  selectedDrawing,
  onUpdateDrawing,
  onDeleteSelectedDrawing,
  onClearAllDrawings,
  drawingsCount,
}) => {
  const [isMagnetActive, setIsMagnetActive] = useState(false);
  const [isLockActive, setIsLockActive] = useState(false);

  // Position offset for the floating properties toolbar (user draggable)
  const [floatingOffset, setFloatingOffset] = useState<{ x: number; y: number }>({ x: 38, y: 0 });
  const isDraggingToolbarRef = useRef<{
    startX: number;
    startY: number;
    initX: number;
    initY: number;
    currentX: number;
    currentY: number;
  } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const dragRafRef = useRef<number | null>(null);

  const updateTransformRaf = (x: number, y: number) => {
    if (dragRafRef.current) cancelAnimationFrame(dragRafRef.current);
    dragRafRef.current = requestAnimationFrame(() => {
      if (panelRef.current) {
        panelRef.current.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      }
    });
  };

  const handleDragPointerDown = (e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    isDraggingToolbarRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initX: floatingOffset.x,
      initY: floatingOffset.y,
      currentX: floatingOffset.x,
      currentY: floatingOffset.y,
    };
  };

  const handleDragPointerMove = (e: React.PointerEvent) => {
    if (!isDraggingToolbarRef.current) return;
    e.stopPropagation();
    const dx = e.clientX - isDraggingToolbarRef.current.startX;
    const dy = e.clientY - isDraggingToolbarRef.current.startY;
    const nextX = isDraggingToolbarRef.current.initX + dx;
    const nextY = isDraggingToolbarRef.current.initY + dy;
    isDraggingToolbarRef.current.currentX = nextX;
    isDraggingToolbarRef.current.currentY = nextY;
    updateTransformRaf(nextX, nextY);
  };

  const handleDragPointerUp = (e: React.PointerEvent) => {
    if (dragRafRef.current) {
      cancelAnimationFrame(dragRafRef.current);
      dragRafRef.current = null;
    }
    if (isDraggingToolbarRef.current) {
      setFloatingOffset({
        x: isDraggingToolbarRef.current.currentX,
        y: isDraggingToolbarRef.current.currentY,
      });
      isDraggingToolbarRef.current = null;
    }
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }
  };

  const handleDragMouseDown = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    isDraggingToolbarRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initX: floatingOffset.x,
      initY: floatingOffset.y,
      currentX: floatingOffset.x,
      currentY: floatingOffset.y,
    };
  };

  useEffect(() => {
    const handleWindowMouseMove = (e: MouseEvent) => {
      if (!isDraggingToolbarRef.current) return;
      const dx = e.clientX - isDraggingToolbarRef.current.startX;
      const dy = e.clientY - isDraggingToolbarRef.current.startY;
      const nextX = isDraggingToolbarRef.current.initX + dx;
      const nextY = isDraggingToolbarRef.current.initY + dy;
      isDraggingToolbarRef.current.currentX = nextX;
      isDraggingToolbarRef.current.currentY = nextY;
      updateTransformRaf(nextX, nextY);
    };

    const handleWindowMouseUp = () => {
      if (dragRafRef.current) {
        cancelAnimationFrame(dragRafRef.current);
        dragRafRef.current = null;
      }
      if (isDraggingToolbarRef.current) {
        setFloatingOffset({
          x: isDraggingToolbarRef.current.currentX,
          y: isDraggingToolbarRef.current.currentY,
        });
        isDraggingToolbarRef.current = null;
      }
    };

    window.addEventListener('mousemove', handleWindowMouseMove, { capture: true });
    window.addEventListener('mouseup', handleWindowMouseUp, { capture: true });
    return () => {
      window.removeEventListener('mousemove', handleWindowMouseMove, { capture: true });
      window.removeEventListener('mouseup', handleWindowMouseUp, { capture: true });
    };
  }, []);

  // Position control inputs
  const [entryInput, setEntryInput] = useState('');
  const [tpInput, setTpInput] = useState('');
  const [slInput, setSlInput] = useState('');

  const isPosition = selectedDrawing?.type === 'long_position' || selectedDrawing?.type === 'short_position';

  useEffect(() => {
    if (isPosition && selectedDrawing && selectedDrawing.points && selectedDrawing.points.length >= 3) {
      setEntryInput(String(selectedDrawing.points[0]?.price ?? ''));
      setTpInput(String(selectedDrawing.points[1]?.price ?? ''));
      setSlInput(String(selectedDrawing.points[2]?.price ?? ''));
    }
  }, [
    isPosition,
    selectedDrawing?.id,
    selectedDrawing?.points?.[0]?.price,
    selectedDrawing?.points?.[1]?.price,
    selectedDrawing?.points?.[2]?.price,
  ]);

  const handlePriceChange = (pointIdx: number, valStr: string) => {
    if (pointIdx === 0) setEntryInput(valStr);
    if (pointIdx === 1) setTpInput(valStr);
    if (pointIdx === 2) setSlInput(valStr);

    const val = parseFloat(valStr);
    if (!isNaN(val) && val > 0 && selectedDrawing && selectedDrawing.points.length >= 3) {
      const nextPoints = [...selectedDrawing.points];
      nextPoints[pointIdx] = { ...nextPoints[pointIdx], price: val };
      onUpdateDrawing?.({ points: nextPoints }, selectedDrawing.id);
    }
  };

  const handleQuickRatio = (ratio: number) => {
    if (!selectedDrawing || selectedDrawing.points.length < 3) return;
    const entry = selectedDrawing.points[0].price;
    const sl = selectedDrawing.points[2].price;
    const isLong = selectedDrawing.type === 'long_position';
    const risk = Math.abs(entry - sl);
    const newTp = isLong ? entry + risk * ratio : entry - risk * ratio;
    const cleanTp = Number(newTp.toFixed(6));
    const nextPoints = [...selectedDrawing.points];
    nextPoints[1] = { ...nextPoints[1], price: cleanTp };
    setTpInput(String(cleanTp));
    onUpdateDrawing?.({ points: nextPoints }, selectedDrawing.id);
  };

  let positionRr = '0.00';
  let tpPct = '0.00';
  let slPct = '0.00';
  if (isPosition && selectedDrawing && selectedDrawing.points && selectedDrawing.points.length >= 3) {
    const entry = selectedDrawing.points[0]?.price ?? 0;
    const tp = selectedDrawing.points[1]?.price ?? 0;
    const sl = selectedDrawing.points[2]?.price ?? 0;
    const risk = Math.abs(entry - sl);
    const reward = Math.abs(tp - entry);
    positionRr = risk > 0 ? (reward / risk).toFixed(2) : '0.00';
    if (entry > 0) {
      tpPct = ((reward / entry) * 100).toFixed(2);
      slPct = ((risk / entry) * 100).toFixed(2);
    }
  }



  return (
    <div
      data-toolbar="drawing"
      className="absolute left-2 top-10 z-30 flex flex-col items-center select-none pointer-events-auto"
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Exact TradingView Left Toolbar Container */}
      <div className="flex flex-col items-center bg-[#131722]/95 dark:bg-[#131722]/95 backdrop-blur-md border border-[#2a2e39] rounded-sm shadow-2xl py-1 px-0.5 gap-0.5">
        {/* 1. Crosshair */}
        <button
          type="button"
          onClick={() => onSelectTool('cursor')}
          title="Курсор / Перехрестя (Crosshair)"
          className={`w-7 h-7 flex items-center justify-center rounded transition-all cursor-pointer ${
            activeTool === 'cursor' ? 'bg-[#2a2e39] text-white' : 'text-[#848e9c] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <TvIcons.Crosshair />
        </button>

        {/* 2. Trend Line Tools */}
        <button
          type="button"
          onClick={() => onSelectTool(activeTool === 'trendline' ? 'ray' : 'trendline')}
          title="Лінія тренду / Промінь (Trend Line)"
          className={`w-7 h-7 flex items-center justify-center rounded transition-all cursor-pointer ${
            activeTool === 'trendline' || activeTool === 'ray'
              ? 'bg-[#2962ff] text-white shadow-sm'
              : 'text-[#848e9c] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <TvIcons.TrendLine />
        </button>

        {/* 3. Gann & Fibonacci */}
        <button
          type="button"
          onClick={() => onSelectTool(activeTool === 'fibonacci' ? 'horizontal' : 'fibonacci')}
          title="Рівні Фібоначчі / Рівні (Fibonacci Retracement)"
          className={`w-7 h-7 flex items-center justify-center rounded transition-all cursor-pointer ${
            activeTool === 'fibonacci'
              ? 'bg-[#2962ff] text-white shadow-sm'
              : 'text-[#848e9c] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <TvIcons.Fibonacci />
        </button>

        {/* 4. Geometric Shapes / Rectangle */}
        <button
          type="button"
          onClick={() => onSelectTool('rectangle')}
          title="Геометричні фігури / Прямокутник (Rectangle)"
          className={`w-7 h-7 flex items-center justify-center rounded transition-all cursor-pointer ${
            activeTool === 'rectangle' ? 'bg-[#2962ff] text-white shadow-sm' : 'text-[#848e9c] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <TvIcons.Patterns />
        </button>

        {/* 5. Horizontal Line & Ray */}
        <button
          type="button"
          onClick={() => onSelectTool(activeTool === 'horizontal' ? 'horizontal_ray' : 'horizontal')}
          title="Горизонтальна лінія / Горизонтальний промінь (Horizontal Line)"
          className={`w-7 h-7 flex items-center justify-center rounded transition-all cursor-pointer ${
            activeTool === 'horizontal' || activeTool === 'horizontal_ray' ? 'bg-[#2962ff] text-white shadow-sm' : 'text-[#848e9c] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <TvIcons.Prediction />
        </button>

        {/* 5.1 Long Position (Довга позиція TP/SL) */}
        <button
          type="button"
          data-testid="tool-btn-long-position"
          onClick={() => onSelectTool('long_position')}
          title="Довга позиція / Long Position (TP & SL)"
          className={`w-7 h-7 flex items-center justify-center rounded transition-all cursor-pointer ${
            activeTool === 'long_position' ? 'bg-[#0ecb81]/30 text-white ring-1 ring-[#0ecb81]' : 'text-[#848e9c] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <TvIcons.LongPosition />
        </button>

        {/* 5.2 Short Position (Коротка позиція TP/SL) */}
        <button
          type="button"
          data-testid="tool-btn-short-position"
          onClick={() => onSelectTool('short_position')}
          title="Коротка позиція / Short Position (TP & SL)"
          className={`w-7 h-7 flex items-center justify-center rounded transition-all cursor-pointer ${
            activeTool === 'short_position' ? 'bg-[#f6465d]/30 text-white ring-1 ring-[#f6465d]' : 'text-[#848e9c] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <TvIcons.ShortPosition />
        </button>

        {/* 6. Brush */}
        <button
          type="button"
          onClick={() => onSelectTool('brush')}
          title="Пензель (Brush)"
          className={`w-7 h-7 flex items-center justify-center rounded transition-all cursor-pointer ${
            activeTool === 'brush' ? 'bg-[#2962ff] text-white shadow-sm' : 'text-[#848e9c] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <TvIcons.Brush />
        </button>

        {/* 7. Text Annotation */}
        <button
          type="button"
          onClick={() => onSelectTool('text')}
          title="Текст / Нотатка (Text)"
          className={`w-7 h-7 flex items-center justify-center rounded transition-all cursor-pointer ${
            activeTool === 'text' ? 'bg-[#2962ff] text-white shadow-sm' : 'text-[#848e9c] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <TvIcons.Text />
        </button>

        {/* 8. Emoji */}
        <button
          type="button"
          title="Значки / Смайлики (Icons)"
          className="w-7 h-7 flex items-center justify-center rounded text-[#848e9c] hover:text-white hover:bg-[#1e222d] transition cursor-pointer"
        >
          <TvIcons.Smiley />
        </button>

        {/* Separator */}
        <div className="w-5 h-[1px] bg-[#2a2e39] my-0.5" />

        {/* 9. Measure / Ruler */}
        <button
          type="button"
          onClick={() => onSelectTool('ruler')}
          title="Лінійка / Вимірювання (Measure Ruler)"
          className={`w-7 h-7 flex items-center justify-center rounded transition-all cursor-pointer ${
            activeTool === 'ruler' ? 'bg-[#0ecb81] text-white shadow-sm' : 'text-[#848e9c] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <TvIcons.Ruler />
        </button>

        {/* 10. Zoom */}
        <button
          type="button"
          title="Збільшити масштаб (Zoom In)"
          className="w-7 h-7 flex items-center justify-center rounded text-[#848e9c] hover:text-white hover:bg-[#1e222d] transition cursor-pointer"
        >
          <TvIcons.Zoom />
        </button>

        {/* Separator */}
        <div className="w-5 h-[1px] bg-[#2a2e39] my-0.5" />

        {/* 11. Magnet Mode */}
        <button
          type="button"
          onClick={() => setIsMagnetActive(!isMagnetActive)}
          title={isMagnetActive ? 'Режим магніту: Увімкнено' : 'Режим магніту: Вимкнено'}
          className={`w-7 h-7 flex items-center justify-center rounded transition-all cursor-pointer ${
            isMagnetActive ? 'bg-[#2962ff] text-white' : 'text-[#848e9c] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <TvIcons.Magnet />
        </button>

        {/* 12. Lock / Stay in Drawing Mode */}
        <button
          type="button"
          onClick={() => setIsLockActive(!isLockActive)}
          title={isLockActive ? 'Зафіксувати всі інструменти' : 'Залишатися в режимі малювання'}
          className={`w-7 h-7 flex items-center justify-center rounded transition-all cursor-pointer ${
            isLockActive ? 'bg-[#2962ff] text-white' : 'text-[#848e9c] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <TvIcons.LockMode />
        </button>

        {/* 13. Eye (Hide / Show) */}
        <button
          type="button"
          title="Приховати / Показати всі об'єкти малювання"
          className="w-7 h-7 flex items-center justify-center rounded text-[#848e9c] hover:text-white hover:bg-[#1e222d] transition cursor-pointer"
        >
          <TvIcons.Eye />
        </button>

        {/* 14. Clear All Drawings */}
        {drawingsCount > 0 && onClearAllDrawings && (
          <button
            type="button"
            onClick={() => {
              if (window.confirm('Видалити всі малюнки для цієї монети?')) {
                onClearAllDrawings();
              }
            }}
            title={`Очистити всі малюнки (${drawingsCount})`}
            className="w-7 h-7 flex items-center justify-center rounded text-rose-400 hover:text-white hover:bg-rose-950/50 transition cursor-pointer"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Floating Selected Drawing Properties Toolbar / Position Card */}
      {selectedDrawing && onUpdateDrawing && onDeleteSelectedDrawing && (
        <div
          ref={panelRef}
          data-testid="drawing-properties-panel"
          style={{
            transform: `translate3d(${floatingOffset.x}px, ${floatingOffset.y}px, 0)`,
            transition: 'none',
            willChange: 'transform',
          }}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          className={`absolute left-0 top-0 z-40 select-none touch-none ${
            isPosition
              ? 'w-80 bg-[#131722]/98 backdrop-blur-md border border-[#2a2e39] rounded-xl shadow-2xl p-3 flex flex-col gap-2.5'
              : 'flex items-center gap-1.5 bg-[#131722]/95 backdrop-blur-md border border-[#2a2e39] rounded shadow-2xl px-2.5 py-1.5'
          }`}
        >
          {/* Dedicated UI/UX for Long / Short Position: Beautiful Rectangular Card */}
          {isPosition ? (
            <div
              data-testid="position-properties-toolbar"
              className="flex flex-col gap-2.5 w-full select-none"
            >
              {/* Header: Drag Handle, Badge, Delete Button */}
              <div className="flex items-center justify-between pb-1.5 border-b border-[#262b36]">
                <div className="flex items-center gap-1.5">
                  <div
                    onPointerDown={handleDragPointerDown}
                    onPointerMove={handleDragPointerMove}
                    onPointerUp={handleDragPointerUp}
                    onPointerCancel={handleDragPointerUp}
                    onMouseDown={handleDragMouseDown}
                    title="Перетягнути форму"
                    className="flex items-center text-gray-500 hover:text-gray-300 cursor-grab active:cursor-grabbing p-0.5 touch-none"
                  >
                    <GripVertical className="w-3.5 h-3.5 pointer-events-none" />
                  </div>
                  <span
                    className={`text-[11px] font-mono font-bold uppercase px-2 py-0.5 rounded border tracking-wider ${
                      selectedDrawing.type === 'long_position'
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                        : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                    }`}
                  >
                    {selectedDrawing.type === 'long_position' ? 'LONG ПОЗИЦІЯ' : 'SHORT ПОЗИЦІЯ'}
                  </span>
                </div>

                <button
                  type="button"
                  data-testid="delete-drawing-btn"
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteSelectedDrawing(selectedDrawing.id);
                  }}
                  title="Видалити позицію (Delete / Backspace)"
                  className="p-1 rounded text-rose-500 hover:text-rose-400 hover:bg-rose-950/40 transition cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Input Rows: Entry, TP, SL */}
              <div className="flex flex-col gap-1.5">
                {/* Entry Price */}
                <div className="flex items-center justify-between bg-[#191d28]/70 border border-[#262b36] rounded-lg px-2.5 py-1.5 focus-within:border-blue-500 transition-colors">
                  <span className="text-[11px] font-medium text-gray-400">Вхід</span>
                  <input
                    type="number"
                    step="any"
                    data-testid="input-entry-price"
                    value={entryInput}
                    onChange={(e) => handlePriceChange(0, e.target.value)}
                    onMouseDown={(e) => e.stopPropagation()}
                    onKeyDown={(e) => e.stopPropagation()}
                    placeholder="0.00"
                    title="Ціна точки входу (Entry)"
                    className="w-32 bg-transparent text-white font-mono text-xs text-right focus:outline-none"
                  />
                </div>

                {/* TP Price */}
                <div className="flex items-center justify-between bg-[#191d28]/70 border border-[#262b36] rounded-lg px-2.5 py-1.5 focus-within:border-emerald-500 transition-colors">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[11px] font-bold text-emerald-400">TP</span>
                    <span className="text-[10px] text-emerald-500/80 font-mono">
                      (+{tpPct}%)
                    </span>
                  </div>
                  <input
                    type="number"
                    step="any"
                    data-testid="input-tp-price"
                    value={tpInput}
                    onChange={(e) => handlePriceChange(1, e.target.value)}
                    onMouseDown={(e) => e.stopPropagation()}
                    onKeyDown={(e) => e.stopPropagation()}
                    placeholder="0.00"
                    title="Ціна Take Profit (Ціль)"
                    className="w-32 bg-transparent text-emerald-400 font-mono text-xs text-right focus:outline-none"
                  />
                </div>

                {/* SL Price */}
                <div className="flex items-center justify-between bg-[#191d28]/70 border border-[#262b36] rounded-lg px-2.5 py-1.5 focus-within:border-rose-500 transition-colors">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[11px] font-bold text-rose-400">SL</span>
                    <span className="text-[10px] text-rose-500/80 font-mono">
                      (-{slPct}%)
                    </span>
                  </div>
                  <input
                    type="number"
                    step="any"
                    data-testid="input-sl-price"
                    value={slInput}
                    onChange={(e) => handlePriceChange(2, e.target.value)}
                    onMouseDown={(e) => e.stopPropagation()}
                    onKeyDown={(e) => e.stopPropagation()}
                    placeholder="0.00"
                    title="Ціна Stop Loss (Стоп)"
                    className="w-32 bg-transparent text-rose-400 font-mono text-xs text-right focus:outline-none"
                  />
                </div>
              </div>

              {/* Footer: R:R Ratio & Quick Presets */}
              <div className="pt-2 border-t border-[#262b36] flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] text-gray-400">Р/П:</span>
                  <span className="text-xs font-mono font-bold text-blue-400 bg-blue-500/10 border border-blue-500/25 px-1.5 py-0.5 rounded">
                    1:{positionRr}
                  </span>
                </div>

                <div className="flex items-center gap-1">
                  {[1.5, 2, 2.5, 3].map((r) => {
                    const isCurrent = positionRr === r.toFixed(2);
                    return (
                      <button
                        key={r}
                        type="button"
                        data-testid={`rr-ratio-${r}`}
                        onMouseDown={(e) => e.stopPropagation()}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleQuickRatio(r);
                        }}
                        title={`Встановити ціль зі співвідношенням 1:${r}`}
                        className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold transition-all cursor-pointer ${
                          isCurrent
                            ? 'bg-blue-600 text-white shadow-sm'
                            : 'bg-[#1e222d] text-gray-300 hover:bg-[#282f3d] hover:text-white border border-[#2a2e39]'
                        }`}
                      >
                        1:{r}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            /* Standard Drawings Toolbar (Trendlines, Rectangles, Fibonacci, etc.) */
            <>
              {/* Drag Handle */}
              <div
                onPointerDown={handleDragPointerDown}
                onPointerMove={handleDragPointerMove}
                onPointerUp={handleDragPointerUp}
                onPointerCancel={handleDragPointerUp}
                onMouseDown={handleDragMouseDown}
                title="Перетягнути панель"
                className="flex items-center text-gray-500 hover:text-gray-300 cursor-grab active:cursor-grabbing px-0.5 touch-none"
              >
                <GripVertical className="w-3.5 h-3.5 pointer-events-none" />
              </div>

              <span className="text-[10px] font-mono font-bold text-gray-400 uppercase select-none">
                {selectedDrawing.type}
              </span>

              <div className="w-[1px] h-4 bg-[#2a2e39]" />

              {/* Color Presets */}
              <div className="flex items-center gap-1">
                {PRESET_COLORS.map((c) => {
                  const isCurrent = (selectedDrawing.color || '#2962ff').toLowerCase() === c.value.toLowerCase();
                  return (
                    <button
                      key={c.value}
                      type="button"
                      data-testid={`color-btn-${c.value}`}
                      onMouseDown={(e) => e.stopPropagation()}
                      onClick={(e) => {
                        e.stopPropagation();
                        onUpdateDrawing({ color: c.value }, selectedDrawing.id);
                      }}
                      title={c.name}
                      style={{ backgroundColor: c.value }}
                      className={`w-4 h-4 rounded-full border border-white/20 transition-transform cursor-pointer ${
                        isCurrent ? 'scale-125 ring-2 ring-blue-500 ring-offset-1 ring-offset-[#131722]' : 'hover:scale-110 opacity-90 hover:opacity-100'
                      }`}
                    />
                  );
                })}
              </div>

              <div className="w-[1px] h-4 bg-[#2a2e39]" />

              {/* Line Width */}
              <div className="flex items-center gap-1">
                {PRESET_WIDTHS.map((w) => {
                  const isCurrent = (selectedDrawing.lineWidth || 2) === w;
                  return (
                    <button
                      key={w}
                      type="button"
                      data-testid={`width-btn-${w}`}
                      onMouseDown={(e) => e.stopPropagation()}
                      onClick={(e) => {
                        e.stopPropagation();
                        onUpdateDrawing({ lineWidth: w }, selectedDrawing.id);
                      }}
                      title={`Товщина: ${w}px`}
                      className={`w-5 h-5 flex items-center justify-center rounded text-[10px] font-bold cursor-pointer transition-colors ${
                        isCurrent
                          ? 'bg-blue-600 text-white shadow-sm'
                          : 'text-gray-400 hover:bg-[#202634] hover:text-gray-200'
                      }`}
                    >
                      {w}
                    </button>
                  );
                })}
              </div>

              <div className="w-[1px] h-4 bg-[#2a2e39]" />

              {/* Line Style (Solid / Dashed / Dotted) */}
              <button
                type="button"
                data-testid="style-toggle-btn"
                onMouseDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  const cur = selectedDrawing.lineStyle ?? 0;
                  const next = cur === 0 ? 2 : cur === 2 ? 1 : 0;
                  onUpdateDrawing({ lineStyle: next }, selectedDrawing.id);
                }}
                title="Змінити стиль лінії (Суцільна / Пунктирна / Точкова)"
                className="px-2 py-0.5 rounded text-[10px] font-medium text-gray-300 hover:bg-[#202634] hover:text-white transition-colors cursor-pointer"
              >
                {(selectedDrawing.lineStyle ?? 0) === 0 ? 'Суцільна' : selectedDrawing.lineStyle === 2 ? 'Пунктир' : 'Точки'}
              </button>

              {/* Optional Text editing for Text annotations */}
              {selectedDrawing.type === 'text' && (
                <>
                  <div className="w-[1px] h-4 bg-[#2a2e39]" />
                  <button
                    type="button"
                    onMouseDown={(e) => e.stopPropagation()}
                    onClick={(e) => {
                      e.stopPropagation();
                      const newText = window.prompt('Редагувати текст нотатки:', selectedDrawing.text || '');
                      if (newText !== null && newText.trim() !== '') {
                        onUpdateDrawing({ text: newText.trim() }, selectedDrawing.id);
                      }
                    }}
                    title="Змінити текст нотатки"
                    className="px-1.5 py-0.5 rounded text-[10px] font-medium text-blue-400 hover:bg-[#202634] cursor-pointer"
                  >
                    «{selectedDrawing.text || 'Нотатка'}»
                  </button>
                </>
              )}

              <div className="w-[1px] h-4 bg-[#2a2e39]" />

              {/* Delete Button */}
              <button
                type="button"
                data-testid="delete-drawing-btn"
                onMouseDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteSelectedDrawing(selectedDrawing.id);
                }}
                title="Видалити малюнок (Delete / Backspace)"
                className="p-1 rounded text-rose-500 hover:text-rose-400 hover:bg-rose-950/40 transition cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
};
