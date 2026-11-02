import type { OrderSummary } from '@/components/order/order-types';

export type OrderListResponse = {
  items: OrderSummary[];
  page: number;
  page_count: number;
  page_size: number;
  total: number;
};

export type OrderFilters = {
  order_bid: string;
  user_bid: string;
  shifu_bids: string[];
  status: string;
  payment_channel: string;
  start_time: string;
  end_time: string;
};

export const PAGE_SIZE = 20;
export const DEFAULT_ORDER_STATUS = '502';
export const QUERY_TAB_KEY = 'tab';
export const QUERY_STATUS_KEY = 'status';
export const QUERY_SHIFU_BID_KEY = 'shifu_bid';
export const COLUMN_MIN_WIDTH = 80;
export const COLUMN_MAX_WIDTH = 360;
export const COLUMN_WIDTH_STORAGE_KEY = 'adminOrdersColumnWidths';

export const DEFAULT_COLUMN_WIDTHS = {
  shifu: 120,
  user: 160,
  status: 110,
  paidAmount: 110,
  discountInfo: 120,
  payment: 90,
  createdAt: 170,
  orderId: 220,
  action: 100,
};

export type ColumnKey = keyof typeof DEFAULT_COLUMN_WIDTHS;
export type ColumnWidthState = Record<ColumnKey, number>;
export const COLUMN_KEYS = Object.keys(DEFAULT_COLUMN_WIDTHS) as ColumnKey[];
export type SearchParamsLike = Pick<
  URLSearchParams,
  'get' | 'has' | 'toString'
> | null;
export type OrdersPageTab = 'orders' | 'redemptionCodes';

export const resolveOrdersPageTab = (value: string | null): OrdersPageTab =>
  value === 'redemptionCodes' ? 'redemptionCodes' : 'orders';

export const createDefaultFilters = (): OrderFilters => ({
  order_bid: '',
  user_bid: '',
  shifu_bids: [],
  status: DEFAULT_ORDER_STATUS,
  payment_channel: '',
  start_time: '',
  end_time: '',
});

export const parseShifuBidQuery = (value: string | null): string[] =>
  Array.from(
    new Set(
      (value || '')
        .split(',')
        .map(item => item.trim())
        .filter(Boolean),
    ),
  );

export const serializeShifuBidQuery = (value: string[]): string =>
  parseShifuBidQuery(value.join(',')).join(',');

export const createFiltersFromSearchParams = (
  searchParams: SearchParamsLike,
): OrderFilters => ({
  ...createDefaultFilters(),
  shifu_bids: parseShifuBidQuery(
    searchParams?.get(QUERY_SHIFU_BID_KEY) || null,
  ),
  status: searchParams?.has(QUERY_STATUS_KEY)
    ? searchParams.get(QUERY_STATUS_KEY) || ''
    : DEFAULT_ORDER_STATUS,
});
