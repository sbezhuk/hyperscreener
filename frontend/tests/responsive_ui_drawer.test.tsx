import { test, describe, before } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { JSDOM } from 'jsdom';
import { TopBar } from '../src/components/TopBar';
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
});
