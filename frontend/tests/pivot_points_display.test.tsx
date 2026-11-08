import { test, describe, before } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { JSDOM } from 'jsdom';
import { SidebarLevels } from '../src/components/SidebarLevels';
import { ThemeProvider } from '../src/context/ThemeContext';
import { LevelItem, PivotPointsData } from '../src/types';

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

describe('Smart Money (SMC) Levels Display & UI Verification', () => {
  let rtlRender: any;

  before(async () => {
    const rtl = await import('@testing-library/react');
    rtlRender = rtl.render;
  });

  const mockResistances: LevelItem[] = [
    {
      price: 2000.0,
      top: 2005.0,
      bottom: 1995.0,
      touches: 2,
      distPct: 2.5,
      strength: 4,
      smc_type: 'ORDER_BLOCK',
      smc_label: 'OB Supply',
      status: 'active',
      strength_score: 92,
    },
    {
      price: 2050.0,
      top: 2055.0,
      bottom: 2045.0,
      touches: 2,
      distPct: 5.1,
      strength: 4,
      smc_type: 'LIQUIDITY_POOL',
      smc_label: 'BSL',
      status: 'active',
      strength_score: 85,
    },
  ];

  const mockSupports: LevelItem[] = [
    {
      price: 1950.0,
      top: 1955.0,
      bottom: 1945.0,
      touches: 3,
      distPct: -0.5,
      strength: 5,
      smc_type: 'ORDER_BLOCK',
      smc_label: 'OB Demand',
      status: 'active',
      strength_score: 95,
    },
    {
      price: 1900.0,
      top: 1905.0,
      bottom: 1895.0,
      touches: 2,
      distPct: -3.0,
      strength: 4,
      smc_type: 'BREAKER_BLOCK',
      smc_label: 'Breaker',
      status: 'retested',
      strength_score: 80,
    },
  ];

  test('1. Renders Smart Money (SMC) summary card with OB Supply and OB Demand', () => {
    const { container } = rtlRender(
      <ThemeProvider>
        <SidebarLevels
          resistances={mockResistances}
          supports={mockSupports}
          signals={[]}
          activeFormation="NONE"
        />
      </ThemeProvider>
    );

    const textContent = container.textContent || '';
    assert.match(textContent, /SMART MONEY \(SMC\) РІВНІ/);
    assert.match(textContent, /OB SUPPLY/);
    assert.match(textContent, /2000/);
    assert.match(textContent, /OB DEMAND/);
    assert.match(textContent, /1950/);
  });

  test('2. Renders OB Supply, OB Demand, BSL, Breaker badges next to levels', () => {
    const { container } = rtlRender(
      <ThemeProvider>
        <SidebarLevels
          resistances={mockResistances}
          supports={mockSupports}
          signals={[]}
          activeFormation="NONE"
        />
      </ThemeProvider>
    );

    const textContent = container.textContent || '';
    assert.match(textContent, /OB Supply/);
    assert.match(textContent, /BSL/);
    assert.match(textContent, /OB Demand/);
    assert.match(textContent, /Breaker/);
  });

  test('3. Graceful fallback when levels are absent', () => {
    const { container } = rtlRender(
      <ThemeProvider>
        <SidebarLevels
          resistances={[]}
          supports={[]}
          signals={[]}
          activeFormation="NONE"
        />
      </ThemeProvider>
    );

    const textContent = container.textContent || '';
    assert.match(textContent, /SMART MONEY \(SMC\) РІВНІ/);
    assert.match(textContent, /ЗОНИ ТА РІВНІ · 0/);
    assert.match(textContent, /Зон не виявлено/);
  });
});
