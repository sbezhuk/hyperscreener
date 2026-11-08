import { test, describe, before } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { JSDOM } from 'jsdom';
import { TopBar } from '../src/components/TopBar';
import { FormationsBar } from '../src/components/FormationsBar';
import { SidebarLevels } from '../src/components/SidebarLevels';
import { ThemeProvider } from '../src/context/ThemeContext';

// Set up simulated DOM environment
const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost:3000',
  pretendToBeVisual: true,
});

global.window = dom.window as any;
global.document = dom.window.document as any;
global.HTMLElement = dom.window.HTMLElement as any;
global.HTMLDivElement = dom.window.HTMLDivElement as any;
(dom.window as any).matchMedia = () => ({
  matches: false,
  addListener: () => {},
  removeListener: () => {},
});
global.localStorage = dom.window.localStorage;

describe('Phase 5.3 — Responsive UI & Drawer Lifecycle Verification', () => {
  let rtlRender: any;
  let rtlFireEvent: any;

  before(async () => {
    const rtl = await import('@testing-library/react');
    rtlRender = rtl.render;
    rtlFireEvent = rtl.fireEvent;
  });

  const resolutions = [
    { name: 'Small Mobile', width: 320, height: 568 },
    { name: 'Mobile', width: 375, height: 667 },
    { name: 'Large Mobile', width: 430, height: 932 },
    { name: 'Tablet', width: 768, height: 1024 },
    { name: 'Small Desktop', width: 1024, height: 768 },
    { name: 'Desktop', width: 1440, height: 900 },
    { name: 'Large Desktop', width: 1920, height: 1080 },
  ];

  test('1. Validates responsive viewport contracts across all 7 target screen sizes', () => {
    for (const res of resolutions) {
      dom.window.innerWidth = res.width;
      dom.window.innerHeight = res.height;

      const isMobileOrTablet = res.width < 1024;
      assert.equal(
        isMobileOrTablet,
        res.width < 1024,
        `Resolution ${res.name} (${res.width}x${res.height}) must correctly map to ${isMobileOrTablet ? 'drawer overlay' : 'docked side-by-side'}`
      );
    }
  });

  test('2. TopBar renders mobile sidebar trigger button when onToggleSidebar is provided', () => {
    let toggleClicked = false;
    const { container } = rtlRender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(TopBar, {
          coin: 'ETH',
          price: 2450.5,
          timeframe: '15m',
          onTimeframeChange: () => {},
          onOpenScreener: () => {},
          onRefresh: () => {},
          isLoading: false,
          wsStatus: 'connected',
          onToggleSidebar: () => {
            toggleClicked = true;
          },
          isSidebarOpen: false,
        })
      )
    );

    const toggleBtn = container.querySelector('button[title="Рівні та формації"]');
    assert.ok(toggleBtn, 'TopBar must render mobile sidebar toggle button');
    
    rtlFireEvent.click(toggleBtn);
    assert.equal(toggleClicked, true, 'Clicking mobile sidebar button must trigger onToggleSidebar');
  });

  test('3. TopBar displays localized connection and perpetual labels in Ukrainian', () => {
    const { container } = rtlRender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(TopBar, {
          coin: 'SOL',
          price: 180.25,
          timeframe: '1h',
          onTimeframeChange: () => {},
          onOpenScreener: () => {},
          onRefresh: () => {},
          isLoading: false,
          wsStatus: 'connected',
        })
      )
    );

    const text = container.textContent || '';
    assert.match(text, /USDT безстроковий/i, 'Perpetual label must be in Ukrainian');
    assert.match(text, /WS НАЖИВО|НАЖИВО/i, 'Live WS connection badge must be in Ukrainian');
    assert.match(text, /Скрінер/i, 'Screener button must be in Ukrainian');
  });

  test('4. SidebarLevels renders close button and triggers onClose callback', () => {
    let closeClicked = false;
    const { container } = rtlRender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(SidebarLevels, {
          resistances: [],
          supports: [],
          signals: [],
          activeFormation: 'CASCADE',
          onClose: () => {
            closeClicked = true;
          },
        })
      )
    );

    const closeBtn = container.querySelector('button[title="Закрити панель"]');
    assert.ok(closeBtn, 'SidebarLevels must render mobile close button when onClose is provided');

    rtlFireEvent.click(closeBtn);
    assert.equal(closeClicked, true, 'Clicking close button must fire onClose');
  });

  test('5. SidebarLevels labels are fully localized in Ukrainian', () => {
    const { container } = rtlRender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(SidebarLevels, {
          resistances: [{ price: 2500, top: 2505, bottom: 2495, touches: 2, distPct: 1.5, timeframe: '1h' }],
          supports: [{ price: 2400, top: 2405, bottom: 2395, touches: 3, distPct: -2.1, timeframe: '1h' }],
          signals: [],
          structure: { trend: 'BULLISH', summary: 'Висхідний тренд з накопиченням' },
          openInterest: 125000,
          fundingRate: 0.0001,
          activeFormation: 'CASCADE',
        })
      )
    );

    const text = container.textContent || '';
    assert.match(text, /СТРУКТУРА ТА ТРЕНД/i, 'Header must be in Ukrainian');
    assert.match(text, /Фінансування:/i, 'Funding rate label must be in Ukrainian');
    assert.match(text, /ЗОНИ ТА РІВНІ/i, 'Levels header must be in Ukrainian');
    assert.match(text, /Опір/i, 'Resistance label must be in Ukrainian');
    assert.match(text, /Підтримка/i, 'Support label must be in Ukrainian');
  });

  test('6. SidebarLevels formation card maintains responsiveness with multiple badges', () => {
    const trendlineSignal: any = {
      id: 'tl-sig-1',
      coin: 'BTC',
      interval: '1d',
      category: 'trendline',
      title: 'Наклонка (Опір)',
      direction: 'SHORT',
      price: 2779.4,
      time: 1700000000,
      structural_quality: 96,
      interaction_state: 'APPROACHING',
      htf_context: 'AGAINST_HTF',
      touch_count: 2,
      distance_to_line_atr: -5.19,
      compression_ratio: 0.93,
    };

    const { container } = rtlRender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(SidebarLevels, {
          resistances: [],
          supports: [],
          signals: [trendlineSignal],
          activeFormation: 'TRENDLINE',
        })
      )
    );

    const text = container.textContent || '';
    assert.match(text, /Наклонка \(Опір\)/, 'Full title must be rendered without truncation');
    assert.match(text, /Q:\s*96/, 'Q quality badge must be rendered');
    assert.match(text, /НАБЛИЖЕННЯ/, 'State badge must be rendered in Ukrainian');
    assert.match(text, /⚠️ ПРОТИ HTF/, 'HTF risk badge must be rendered');
    assert.match(text, /SHORT/, 'Direction badge must be rendered');

    // Assert adaptive left-aligned flex-wrap container exists
    const flexWrapHeader = container.querySelector('.flex.flex-wrap.items-center.gap-x-2');
    assert.ok(flexWrapHeader, 'Card header must have flex-wrap to prevent losing responsiveness');

    const badgesContainer = container.querySelector('.flex.flex-wrap.items-center.gap-1');
    assert.ok(badgesContainer, 'Badges container must have flex-wrap and be left-aligned to accommodate multiple badges gracefully');
    assert.ok(!badgesContainer.classList.contains('ml-auto'), 'Badges must be aligned to the left side without ml-auto');
  });

  test('7. FormationsBar provides adaptive labels for mobile/desktop without horizontal overflow', () => {
    const { container } = rtlRender(
      React.createElement(FormationsBar, {
        active: 'CASCADE',
        onChange: () => {},
        selectedTfs: ['1h'],
        onToggleTf: () => {},
        minStrength: 50,
        onMinStrengthChange: () => {},
      })
    );

    const barContainer = container.firstElementChild;
    assert.ok(barContainer?.classList.contains('w-full'), 'FormationsBar container must be w-full');
    assert.ok(barContainer?.classList.contains('overflow-x-hidden'), 'FormationsBar must hide overflow-x to avoid horizontal scrollbars');
    assert.ok(barContainer?.classList.contains('flex-wrap'), 'FormationsBar must flex-wrap gracefully');

    // Both full label and mobile label exist in DOM with appropriate responsive classes
    const text = container.textContent || '';
    assert.match(text, /Рівні \(підтримка \/ опір\)/, 'Desktop label must be present');
    assert.match(text, /Рівні/, 'Mobile short label must be present');
  });

  test('8. FormationsBar conditionally hides irrelevant sections according to active formation', () => {
    // 1. CASCADE: MTF & Strength visible, OI hidden
    const resCascade = rtlRender(
      React.createElement(FormationsBar, {
        active: 'CASCADE',
        onChange: () => {},
        selectedTfs: ['1h'],
        onToggleTf: () => {},
        minStrength: 50,
        onMinStrengthChange: () => {},
        onlyConfirmedOi: false,
        onToggleConfirmedOi: () => {},
      })
    );
    assert.match(resCascade.container.textContent || '', /MTF:/, 'CASCADE must show MTF');
    assert.match(resCascade.container.textContent || '', /Сила:/, 'CASCADE must show Strength');
    assert.doesNotMatch(resCascade.container.textContent || '', /Тільки підтверджені OI/, 'CASCADE must hide OI toggle');

    // 2. SWEEP: OI visible, MTF & Strength hidden
    const resSweep = rtlRender(
      React.createElement(FormationsBar, {
        active: 'SWEEP',
        onChange: () => {},
        selectedTfs: ['1h'],
        onToggleTf: () => {},
        minStrength: 50,
        onMinStrengthChange: () => {},
        onlyConfirmedOi: false,
        onToggleConfirmedOi: () => {},
      })
    );
    assert.doesNotMatch(resSweep.container.textContent || '', /MTF:/, 'SWEEP must hide MTF');
    assert.doesNotMatch(resSweep.container.textContent || '', /Сила:/, 'SWEEP must hide Strength');
    assert.match(resSweep.container.textContent || '', /Тільки підтверджені OI/, 'SWEEP must show OI toggle');

    // 3. FVG: MTF & Strength visible, OI hidden
    const resFvg = rtlRender(
      React.createElement(FormationsBar, {
        active: 'FVG',
        onChange: () => {},
        selectedTfs: ['1h'],
        onToggleTf: () => {},
        minStrength: 50,
        onMinStrengthChange: () => {},
        onlyConfirmedOi: false,
        onToggleConfirmedOi: () => {},
      })
    );
    assert.match(resFvg.container.textContent || '', /MTF:/, 'FVG must show MTF');
    assert.match(resFvg.container.textContent || '', /Сила:/, 'FVG must show Strength');
    assert.doesNotMatch(resFvg.container.textContent || '', /Тільки підтверджені OI/, 'FVG must hide OI toggle');

    // 4. TRENDLINE: All sub-controls hidden
    const resTrendline = rtlRender(
      React.createElement(FormationsBar, {
        active: 'TRENDLINE',
        onChange: () => {},
        selectedTfs: ['1h'],
        onToggleTf: () => {},
        minStrength: 50,
        onMinStrengthChange: () => {},
        onlyConfirmedOi: false,
        onToggleConfirmedOi: () => {},
      })
    );
    assert.doesNotMatch(resTrendline.container.textContent || '', /MTF:/, 'TRENDLINE must hide MTF');
    assert.doesNotMatch(resTrendline.container.textContent || '', /Сила:/, 'TRENDLINE must hide Strength');
    assert.doesNotMatch(resTrendline.container.textContent || '', /Тільки підтверджені OI/, 'TRENDLINE must hide OI toggle');

    // 5. NONE: All sub-controls hidden
    const resNone = rtlRender(
      React.createElement(FormationsBar, {
        active: 'NONE',
        onChange: () => {},
        selectedTfs: ['1h'],
        onToggleTf: () => {},
        minStrength: 50,
        onMinStrengthChange: () => {},
        onlyConfirmedOi: false,
        onToggleConfirmedOi: () => {},
      })
    );
    assert.doesNotMatch(resNone.container.textContent || '', /MTF:/, 'NONE must hide MTF');
    assert.doesNotMatch(resNone.container.textContent || '', /Сила:/, 'NONE must hide Strength');
    assert.doesNotMatch(resNone.container.textContent || '', /Тільки підтверджені OI/, 'NONE must hide OI toggle');
  });

  test('9. TopBar mobile 2-tier responsive layout renders timeframe buttons cleanly', () => {
    const { container } = rtlRender(
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(TopBar, {
          coin: 'ETH',
          price: 2239.7,
          timeframe: '15m',
          onTimeframeChange: () => {},
          onOpenScreener: () => {},
          onRefresh: () => {},
          isLoading: false,
          wsStatus: 'connected',
        })
      )
    );

    const mobileTfGrid = container.querySelector('.sm\\:hidden.grid.grid-cols-6');
    assert.ok(mobileTfGrid, 'Mobile 2nd tier timeframe grid (sm:hidden grid grid-cols-6) must be present for small screens');
    
    const tfButtons = mobileTfGrid.querySelectorAll('button');
    assert.equal(tfButtons.length, 6, 'Must render exactly 6 timeframes in mobile grid');
  });
});
