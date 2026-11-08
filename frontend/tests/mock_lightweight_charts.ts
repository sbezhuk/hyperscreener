export const chartSpies = {
  createChartCalls: [] as any[],
  removeCalls: 0,
  setDataCalls: [] as any[],
  updateCalls: [] as any[],
  setVisibleLogicalRangeCalls: [] as any[],
  unsubscribeCalls: 0,
  seriesApplyOptionsCalls: [] as any[],
  addCandlestickSeriesCalls: [] as any[],
};

export function resetSpies() {
  chartSpies.createChartCalls = [];
  chartSpies.removeCalls = 0;
  chartSpies.setDataCalls = [];
  chartSpies.updateCalls = [];
  chartSpies.setVisibleLogicalRangeCalls = [];
  chartSpies.unsubscribeCalls = 0;
  chartSpies.seriesApplyOptionsCalls = [];
  chartSpies.addCandlestickSeriesCalls = [];
}

export const LineStyle = {
  Solid: 0,
  Dotted: 1,
  Dashed: 2,
  LargeDashed: 3,
  SparseDotted: 4,
};

export const CrosshairMode = {
  Normal: 0,
  Magnet: 1,
  Hidden: 2,
};

export const mockCandleSeries = {
  setData: (data: any) => {
    chartSpies.setDataCalls.push(data);
  },
  update: (bar: any) => {
    chartSpies.updateCalls.push(bar);
  },
  applyOptions: (opts: any) => {
    chartSpies.seriesApplyOptionsCalls.push(opts);
  },
  setMarkers: () => {},
  createPriceLine: () => ({ applyOptions: () => {} }),
  removePriceLine: () => {},
  attachPrimitive: () => {},
  barsInLogicalRange: (range: any) => ({ barsBefore: 50, barsAfter: 5 }),
};

export const mockTimeScale = {
  subscribeVisibleLogicalRangeChange: (_cb: any) => {},
  unsubscribeVisibleLogicalRangeChange: (_cb: any) => {
    chartSpies.unsubscribeCalls++;
  },
  setVisibleLogicalRange: (range: any) => {
    chartSpies.setVisibleLogicalRangeCalls.push(range);
  },
  getVisibleLogicalRange: () => ({ from: 500, to: 612 }),
};

export const mockChartApi = {
  timeScale: () => mockTimeScale,
  addCandlestickSeries: (opts?: any) => {
    chartSpies.addCandlestickSeriesCalls.push(opts);
    return mockCandleSeries;
  },
  applyOptions: () => {},
  remove: () => {
    chartSpies.removeCalls++;
  },
};

export function createChart(container: any, options: any) {
  chartSpies.createChartCalls.push({ container, options });
  return mockChartApi;
}
