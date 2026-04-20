'use client';

import dynamic from 'next/dynamic';
import React from 'react';
import type { EChartsOption } from 'echarts';
import type { CSSProperties } from 'react';

// echarts-for-react depends on browser APIs; keep it client-only.
const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false });

export type EChartProps = {
  option: EChartsOption;
  className?: string;
  style?: CSSProperties;
  loading?: boolean;
  notMerge?: boolean;
  lazyUpdate?: boolean;
  opts?: Record<string, unknown>;
  theme?: string | Record<string, unknown>;
  onEvents?: Record<string, (params: unknown) => void>;
};

export default function EChart({
  option,
  className,
  style,
  loading,
  notMerge,
  lazyUpdate,
  opts,
  theme,
  onEvents,
}: EChartProps) {
  return (
    // ReactECharts is dynamically imported; its prop typing is not stable enough
    // for strict TS inference across Next dynamic boundaries.

    <ReactECharts
      className={className}
      style={style}
      option={option as any}
      showLoading={Boolean(loading)}
      notMerge={notMerge}
      lazyUpdate={lazyUpdate}
      opts={opts}
      theme={theme}
      onEvents={onEvents}
    />
  );
}
