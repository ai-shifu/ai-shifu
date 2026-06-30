import type { CSSProperties } from 'react';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import { formatAdminCount } from '@/app/admin/lib/numberFormat';
import { TITLE_MAX_LENGTH } from '@/c-constants/uiConstants';
import type { AdminOperationCourseOverview } from './operation-course-types';
import { isValidEmail } from '@/lib/validators';

export type CourseFilters = {
  shifu_bid: string;
  course_name: string;
  creator_keyword: string;
  course_status: string;
  start_time: string;
  end_time: string;
  updated_start_time: string;
  updated_end_time: string;
};

export type CourseQuickFilterKey =
  | ''
  | 'draft'
  | 'published'
  | 'created_last_7d'
  | 'learning_active_30d'
  | 'paid_order_30d';

export type ErrorState = { message: string; code?: number };

export const PAGE_SIZE = 20;
export const ALL_OPTION_VALUE = '__all__';
export const COURSE_STATUS_PUBLISHED = 'published';
export const COURSE_STATUS_UNPUBLISHED = 'unpublished';
export const COURSE_QUICK_FILTER_DRAFT = 'draft';
export const COURSE_QUICK_FILTER_PUBLISHED = 'published';
export const COURSE_QUICK_FILTER_CREATED_LAST_7D = 'created_last_7d';
export const COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D = 'learning_active_30d';
export const COURSE_QUICK_FILTER_PAID_ORDER_30D = 'paid_order_30d';
export const COLUMN_MIN_WIDTH = 80;
export const COLUMN_MAX_WIDTH = 360;
export const COLUMN_WIDTH_STORAGE_KEY = 'adminOperationsColumnWidths';
export const DEFAULT_COLUMN_WIDTHS = {
  courseId: 260,
  courseName: 220,
  status: 110,
  price: 90,
  model: 170,
  coursePrompt: 120,
  creator: 170,
  modifier: 170,
  updatedAt: 170,
  createdAt: 170,
  action: 115,
} as const;
export type ColumnKey = keyof typeof DEFAULT_COLUMN_WIDTHS;
export const COLUMN_KEYS = Object.keys(DEFAULT_COLUMN_WIDTHS) as ColumnKey[];
export const SINGLE_SELECT_ITEM_CLASS =
  'pl-3 data-[state=checked]:bg-muted data-[state=checked]:text-foreground [&>span:first-child]:hidden';
export const TRANSFER_PHONE_PATTERN = /^\d{11}$/;
export const EMPTY_STATE_LABEL = '--';
export const EMPTY_COURSE_OVERVIEW: AdminOperationCourseOverview = {
  total_course_count: 0,
  draft_course_count: 0,
  published_course_count: 0,
  created_last_7d_course_count: 0,
  learning_active_30d_course_count: 0,
  paid_order_30d_course_count: 0,
};
export const TABLE_INLINE_ACTION_BUTTON_CLASS =
  'inline-flex h-8 items-center justify-center rounded-md px-2.5 text-sm font-normal text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2';
export const COLLAPSED_TEXT_STYLE: CSSProperties = {
  display: '-webkit-box',
  WebkitBoxOrient: 'vertical',
  WebkitLineClamp: 6,
  overflow: 'hidden',
};

export type TransferContactType = 'email' | 'phone';

export const createDefaultFilters = (): CourseFilters => ({
  shifu_bid: '',
  course_name: '',
  creator_keyword: '',
  course_status: '',
  start_time: '',
  end_time: '',
  updated_start_time: '',
  updated_end_time: '',
});

export const formatLocalDate = (date: Date): string => {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
};

export const buildCreatedLast7DaysFilters = (): Pick<
  CourseFilters,
  'start_time' | 'end_time'
> => {
  const endDate = new Date();
  const startDate = new Date(endDate);
  startDate.setDate(endDate.getDate() - 6);
  return {
    start_time: formatLocalDate(startDate),
    end_time: formatLocalDate(endDate),
  };
};

export const buildCopyCourseName = (
  courseName: string | undefined,
  fallbackName: string,
  suffix: string,
): string => {
  const normalizedCourseName = courseName?.trim() || fallbackName;
  if (normalizedCourseName.length + suffix.length <= TITLE_MAX_LENGTH) {
    return `${normalizedCourseName}${suffix}`;
  }
  return `${normalizedCourseName.slice(0, TITLE_MAX_LENGTH - suffix.length)}${suffix}`;
};

export const normalizeTransferIdentifier = (
  contactType: TransferContactType,
  value: string,
): string => {
  const trimmed = value.trim();
  return contactType === 'email' ? trimmed.toLowerCase() : trimmed;
};

export const isValidTransferIdentifier = (
  contactType: TransferContactType,
  value: string,
): boolean => {
  if (!value) {
    return false;
  }
  if (contactType === 'email') {
    return isValidEmail(value);
  }
  return TRANSFER_PHONE_PATTERN.test(value);
};

export const renderTooltipText = (text?: string, className?: string) => {
  return (
    <AdminTooltipText
      text={text}
      emptyValue={EMPTY_STATE_LABEL}
      className={className}
    />
  );
};

export const formatCount = (value: number, locale: string): string =>
  formatAdminCount(value, locale, EMPTY_STATE_LABEL);
