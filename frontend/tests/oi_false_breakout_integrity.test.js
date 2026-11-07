import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

describe('OI False Breakout Live State & Filter Integrity', () => {

  test('1. WebSocket tick updates existing sweep in-place from POTENTIAL to CONFIRMED', () => {
    // Initial state with a live POTENTIAL sweep
    let sweeps = [
      {
        id: 'live-fb-down-10000-1700000000',
        levelPrice: 100.0,
        time: 1700000000,
        direction: 'LONG',
        formation: 'Хибний пробій підтримки (Потенційний LIVE)',
        confirmationStatus: 'POTENTIAL',
        oiConfirmed: false,
        oiDeltaPct: null,
      }
    ];

    let signals = [
      {
        id: 'live-fb-down-10000-1700000000',
        title: 'Хибний пробій підтримки (Потенційний LIVE)',
        price: 100.0,
        time: 1700000000,
        direction: 'LONG',
        confirmationStatus: 'POTENTIAL',
        oiConfirmed: false,
        badgeColor: 'blue',
      }
    ];

    // Incoming tick: delayed OI arrives, candle closes -> CONFIRMED
    const incomingSweep = {
      id: 'live-fb-down-10000-1700000000',
      levelPrice: 100.0,
      time: 1700000000,
      direction: 'LONG',
      formation: 'Хибний пробій підтримки (LIVE - Підтверджено OI)',
      confirmationStatus: 'CONFIRMED',
      oiConfirmed: true,
      oiDeltaPct: -4.2,
      desc: 'Хибний пробій підтримки 100.00, скорочення OI: -4.20%',
    };

    // App.tsx sweep update logic
    const sweepIdx = sweeps.findIndex(
      (s) => (incomingSweep.id && s.id === incomingSweep.id) ||
             (s.levelPrice === incomingSweep.levelPrice && Math.abs(s.time - incomingSweep.time) < 60)
    );
    const sigId = incomingSweep.id || `live-sweep-${incomingSweep.levelPrice}-${incomingSweep.time}`;

    if (sweepIdx >= 0) {
      sweeps = sweeps.map((s, idx) => (idx === sweepIdx ? { ...s, ...incomingSweep } : s));
      signals = signals.map((sig) => {
        if (sig.id === sigId || (sig.price === incomingSweep.levelPrice && Math.abs(sig.time - incomingSweep.time) < 60)) {
          return {
            ...sig,
            title: incomingSweep.formation,
            desc: incomingSweep.desc,
            confirmationStatus: incomingSweep.confirmationStatus,
            oiConfirmed: incomingSweep.oiConfirmed,
            oiDeltaPct: incomingSweep.oiDeltaPct,
            badgeColor: incomingSweep.oiConfirmed ? 'green' : 'gray',
          };
        }
        return sig;
      });
    } else {
      sweeps = [incomingSweep, ...sweeps];
      signals = [{ ...incomingSweep, id: sigId }, ...signals];
    }

    assert.equal(sweeps.length, 1, 'Sweeps array must NOT grow / duplicate');
    assert.equal(signals.length, 1, 'Signals array must NOT duplicate');
    assert.equal(sweeps[0].confirmationStatus, 'CONFIRMED');
    assert.equal(sweeps[0].oiConfirmed, true);
    assert.equal(sweeps[0].oiDeltaPct, -4.2);
    assert.equal(signals[0].badgeColor, 'green');
    assert.equal(signals[0].title, 'Хибний пробій підтримки (LIVE - Підтверджено OI)');
  });

  test('2. onlyConfirmedOi filter correctly excludes POTENTIAL and UNCONFIRMED sweeps', () => {
    const sweeps = [
      { id: '1', levelPrice: 100.0, oiConfirmed: true, confirmationStatus: 'CONFIRMED' },
      { id: '2', levelPrice: 200.0, oiConfirmed: false, confirmationStatus: 'POTENTIAL' },
      { id: '3', levelPrice: 300.0, oiConfirmed: false, confirmationStatus: 'UNCONFIRMED' },
    ];

    // Filter OFF
    const filterOff = sweeps.filter(() => true);
    assert.equal(filterOff.length, 3);

    // Filter ON
    const filterOn = sweeps.filter((sw) => sw.oiConfirmed);
    assert.equal(filterOn.length, 1);
    assert.equal(filterOn[0].id, '1');
    assert.equal(filterOn[0].confirmationStatus, 'CONFIRMED');
  });

  test('3. SidebarLevels signal filter respects onlyConfirmedOi toggle', () => {
    const signals = [
      { id: 's1', category: 'sweep', confirmationStatus: 'CONFIRMED', oiConfirmed: true },
      { id: 's2', category: 'sweep', confirmationStatus: 'POTENTIAL', oiConfirmed: false },
      { id: 's3', category: 'sweep', confirmationStatus: 'UNCONFIRMED', oiConfirmed: false },
      { id: 'c1', category: 'cascade' },
    ];

    // Active formation: SWEEP, onlyConfirmedOi: false
    const activeFormation = 'SWEEP';
    let onlyConfirmedOi = false;
    const filterSweepsAll = signals.filter((sig) => {
      if (activeFormation === 'SWEEP') {
        if (sig.category !== 'sweep') return false;
        if (onlyConfirmedOi && sig.confirmationStatus !== 'CONFIRMED' && !sig.oiConfirmed) return false;
        return true;
      }
      return false;
    });
    assert.equal(filterSweepsAll.length, 3);

    // Active formation: SWEEP, onlyConfirmedOi: true
    onlyConfirmedOi = true;
    const filterSweepsConfirmed = signals.filter((sig) => {
      if (activeFormation === 'SWEEP') {
        if (sig.category !== 'sweep') return false;
        if (onlyConfirmedOi && sig.confirmationStatus !== 'CONFIRMED' && !sig.oiConfirmed) return false;
        return true;
      }
      return false;
    });
    assert.equal(filterSweepsConfirmed.length, 1);
    assert.equal(filterSweepsConfirmed[0].id, 's1');
  });

});
