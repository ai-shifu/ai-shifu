import {
  formatAdminDateRangeEndUtc,
  formatAdminDateRangeStartUtc,
} from '@/app/admin/lib/dateTime';

export type AdminPaginationParams = {
  page_index: number;
  page_size: number;
};

const trimValue = (value: string | undefined | null) =>
  String(value || '').trim();

export const buildAdminPaginationParams = (
  pageIndex: number,
  pageSize: number,
): AdminPaginationParams => ({
  page_index: pageIndex,
  page_size: pageSize,
});

export const buildAdminDateRangeParams = (
  startTime?: string,
  endTime?: string,
  startKey = 'start_time',
  endKey = 'end_time',
): Record<string, string> => ({
  [startKey]: formatAdminDateRangeStartUtc(startTime || ''),
  [endKey]: formatAdminDateRangeEndUtc(endTime || ''),
});

export type AdminCourseListFilters = {
  shifu_bid: string;
  course_name: string;
  creator_keyword: string;
  course_status: string;
  start_time: string;
  end_time: string;
  updated_start_time: string;
  updated_end_time: string;
};

export const buildAdminCourseListParams = ({
  pageIndex,
  pageSize,
  filters,
  quickFilter,
}: {
  pageIndex: number;
  pageSize: number;
  filters: AdminCourseListFilters;
  quickFilter: string;
}) => ({
  ...buildAdminPaginationParams(pageIndex, pageSize),
  shifu_bid: trimValue(filters.shifu_bid),
  course_name: trimValue(filters.course_name),
  creator_keyword: trimValue(filters.creator_keyword),
  course_status: filters.course_status,
  quick_filter: quickFilter,
  ...buildAdminDateRangeParams(filters.start_time, filters.end_time),
  ...buildAdminDateRangeParams(
    filters.updated_start_time,
    filters.updated_end_time,
    'updated_start_time',
    'updated_end_time',
  ),
});

export type AdminUserListFilters = {
  identifier: string;
  nickname: string;
  user_status: string;
  user_role: string;
  start_time: string;
  end_time: string;
};

export const buildAdminUserListParams = ({
  pageIndex,
  pageSize,
  filters,
  quickFilter,
}: {
  pageIndex: number;
  pageSize: number;
  filters: AdminUserListFilters;
  quickFilter: string;
}) => ({
  ...buildAdminPaginationParams(pageIndex, pageSize),
  identifier: trimValue(filters.identifier),
  nickname: trimValue(filters.nickname),
  user_status: filters.user_status,
  user_role: filters.user_role,
  quick_filter: quickFilter,
  ...buildAdminDateRangeParams(filters.start_time, filters.end_time),
});

export type AdminLearnOrderListFilters = {
  user_keyword: string;
  order_bid: string;
  shifu_bid: string;
  course_name: string;
  status: string;
  order_source: string;
  payment_channel: string;
  start_time: string;
  end_time: string;
};

export const buildAdminLearnOrderListParams = ({
  pageIndex,
  pageSize,
  filters,
}: {
  pageIndex: number;
  pageSize: number;
  filters: AdminLearnOrderListFilters;
}) => ({
  ...buildAdminPaginationParams(pageIndex, pageSize),
  user_keyword: trimValue(filters.user_keyword),
  order_bid: trimValue(filters.order_bid),
  shifu_bid: trimValue(filters.shifu_bid),
  course_name: trimValue(filters.course_name),
  status: filters.status,
  order_source: filters.order_source,
  payment_channel: filters.payment_channel,
  ...buildAdminDateRangeParams(filters.start_time, filters.end_time),
});

export type AdminCreditOrderListFilters = {
  creator_keyword: string;
  product_keyword: string;
  bill_order_bid: string;
  credit_order_kind: string;
  status: string;
  has_available_credits: boolean;
  payment_provider: string;
  start_time: string;
  end_time: string;
};

export const buildAdminCreditOrderListParams = ({
  pageIndex,
  pageSize,
  filters,
}: {
  pageIndex: number;
  pageSize: number;
  filters: AdminCreditOrderListFilters;
}) => ({
  ...buildAdminPaginationParams(pageIndex, pageSize),
  creator_keyword: trimValue(filters.creator_keyword),
  product_keyword: trimValue(filters.product_keyword),
  ...(trimValue(filters.bill_order_bid)
    ? { bill_order_bid: trimValue(filters.bill_order_bid) }
    : {}),
  credit_order_kind: filters.credit_order_kind,
  status: filters.status,
  ...(filters.has_available_credits ? { has_available_credits: true } : {}),
  payment_provider: filters.payment_provider,
  ...buildAdminDateRangeParams(filters.start_time, filters.end_time),
});
