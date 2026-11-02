import { cn } from '@/lib/utils';

export const ORDER_FILTER_GRID_CLASS = 'gap-x-7 xl:grid-cols-4';
export const ORDER_FILTER_LABEL_CLASS = 'w-24';
export const ORDER_FILTER_COMPACT_LABEL_CLASS = 'w-16';
export const ORDER_FILTER_CONTENT_CLASS = 'min-w-0';

export type OrderFilterLabelWidth = 'default' | 'compact';

export const getOrdersTabFilterContentClassName = (locale?: string) =>
  cn(
    'min-w-0 flex-1',
    (!locale || !locale.startsWith('zh')) && 'xl:max-w-[220px]',
  );

export const getOrderFilterLabelClassName = (
  width: OrderFilterLabelWidth = 'default',
) =>
  width === 'compact'
    ? ORDER_FILTER_COMPACT_LABEL_CLASS
    : ORDER_FILTER_LABEL_CLASS;

export const getOrdersTabFilterLabelClassName = (locale?: string) =>
  locale?.startsWith('zh') ? 'w-16 text-right' : 'w-24 text-right';
