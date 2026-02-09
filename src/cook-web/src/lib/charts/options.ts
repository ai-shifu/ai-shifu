import type { EChartsOption } from 'echarts';

type LineOptionArgs = {
  x: string[];
  y: number[];
  name?: string;
  smooth?: boolean;
};

type BarOptionArgs = {
  categories: string[];
  values: number[];
  name?: string;
};

const DEFAULT_GRID = {
  top: 24,
  left: 24,
  right: 24,
  bottom: 24,
  containLabel: true,
} as const;

export const buildLineOption = ({
  x,
  y,
  name,
  smooth = true,
}: LineOptionArgs): EChartsOption => ({
  grid: DEFAULT_GRID,
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: x,
    axisTick: { show: false },
    axisLine: { lineStyle: { color: '#e2e8f0' } },
    axisLabel: { color: '#64748b' },
  },
  yAxis: {
    type: 'value',
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: '#eef2f7' } },
    axisLabel: { color: '#64748b' },
  },
  series: [
    {
      type: 'line',
      name,
      data: y,
      smooth,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { width: 2, color: '#0f766e' },
      itemStyle: { color: '#0f766e' },
      areaStyle: { color: 'rgba(15, 118, 110, 0.12)' },
    },
  ],
});

export const buildBarOption = ({
  categories,
  values,
  name,
}: BarOptionArgs): EChartsOption => ({
  grid: DEFAULT_GRID,
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  xAxis: {
    type: 'category',
    data: categories,
    axisTick: { show: false },
    axisLine: { lineStyle: { color: '#e2e8f0' } },
    axisLabel: { color: '#64748b', interval: 0 },
  },
  yAxis: {
    type: 'value',
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: '#eef2f7' } },
    axisLabel: { color: '#64748b' },
  },
  series: [
    {
      type: 'bar',
      name,
      data: values,
      barMaxWidth: 32,
      itemStyle: {
        color: '#1d4ed8',
        borderRadius: [6, 6, 0, 0],
      },
    },
  ],
});
