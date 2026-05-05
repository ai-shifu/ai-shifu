'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarIcon, ChevronDown, ChevronUp, Plus, X } from 'lucide-react';
import api from '@/api';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type {
  AdminPromotionCampaignItem,
  AdminPromotionCampaignRedemptionItem,
  AdminPromotionCouponCodeItem,
  AdminPromotionCouponItem,
  AdminPromotionCouponUsageItem,
  AdminPromotionListResponse,
} from '@/app/admin/operations/operation-promotion-types';
import useOperatorGuard from '@/app/admin/operations/useOperatorGuard';
import ErrorDisplay from '@/components/ErrorDisplay';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Calendar } from '@/components/ui/Calendar';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { Textarea } from '@/components/ui/Textarea';
import { useToast } from '@/hooks/useToast';
import { cn } from '@/lib/utils';

type PromotionTab = 'coupons' | 'campaigns';

type CouponFilters = {
  keyword: string;
  name: string;
  course_query: string;
  usage_type: string;
  discount_type: string;
  status: string;
  start_time: string;
  end_time: string;
};

type CampaignFilters = {
  keyword: string;
  course_query: string;
  discount_type: string;
  status: string;
  start_time: string;
  end_time: string;
};

type CouponFormState = {
  name: string;
  code: string;
  usage_type: string;
  discount_type: string;
  value: string;
  total_count: string;
  scope_type: string;
  shifu_bid: string;
  start_at: string;
  end_at: string;
  enabled: string;
};

type CampaignFormState = {
  name: string;
  apply_type: string;
  shifu_bid: string;
  discount_type: string;
  value: string;
  start_at: string;
  end_at: string;
  description: string;
  channel: string;
  enabled: string;
};

type ErrorState = { message: string } | null;

const PAGE_SIZE = 20;
const EMPTY_VALUE = '--';
const ALL_OPTION_VALUE = '__all__';
const COLUMN_MIN_WIDTH = 90;
const COLUMN_MAX_WIDTH = 420;
const COUPON_COLUMN_WIDTH_STORAGE_KEY = 'adminPromotionCouponsColumnWidths';
const CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY = 'adminPromotionCampaignsColumnWidths';
const COUPON_DEFAULT_COLUMN_WIDTHS = {
  name: 180,
  status: 110,
  usageType: 120,
  discountRule: 120,
  code: 180,
  scope: 120,
  course: 220,
  activeTime: 260,
  usageProgress: 110,
  codesEntry: 110,
  couponBid: 220,
  updatedAt: 170,
  createdAt: 170,
  action: 120,
} as const;
const CAMPAIGN_DEFAULT_COLUMN_WIDTHS = {
  name: 180,
  status: 110,
  applyType: 120,
  channel: 140,
  course: 220,
  discountRule: 120,
  campaignTime: 260,
  appliedOrderCount: 130,
  promoBid: 220,
  updatedAt: 170,
  createdAt: 170,
  action: 120,
} as const;
const SINGLE_SELECT_ITEM_CLASS =
  'pl-3 data-[state=checked]:bg-muted data-[state=checked]:text-foreground [&>span:first-child]:hidden';
const SEARCH_LABEL_CLASS =
  "shrink-0 mr-2 w-20 text-right text-sm font-medium whitespace-nowrap text-foreground after:ml-0.5 after:content-[':']";
const TABLE_HEAD_CLASS = ADMIN_TABLE_HEADER_CELL_CENTER_CLASS;
const TABLE_ACTION_HEAD_CLASS = getAdminStickyRightHeaderClass('text-center');
const TABLE_CELL_CLASS =
  'border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center';
const TABLE_LAST_CELL_CLASS =
  'whitespace-nowrap overflow-hidden text-ellipsis text-center';
const TABLE_ACTION_CELL_CLASS = getAdminStickyRightCellClass(
  'whitespace-nowrap text-center',
);
type CouponColumnKey = keyof typeof COUPON_DEFAULT_COLUMN_WIDTHS;
type CampaignColumnKey = keyof typeof CAMPAIGN_DEFAULT_COLUMN_WIDTHS;

const createDefaultCouponFilters = (): CouponFilters => ({
  keyword: '',
  name: '',
  course_query: '',
  usage_type: '',
  discount_type: '',
  status: '',
  start_time: '',
  end_time: '',
});

const createDefaultCampaignFilters = (): CampaignFilters => ({
  keyword: '',
  course_query: '',
  discount_type: '',
  status: '',
  start_time: '',
  end_time: '',
});

const createDefaultCouponForm = (): CouponFormState => ({
  name: '',
  code: '',
  usage_type: '',
  discount_type: '',
  value: '',
  total_count: '',
  scope_type: 'single_course',
  shifu_bid: '',
  start_at: '',
  end_at: '',
  enabled: 'true',
});

function normalizePromotionFormDateTimeValue(value?: string) {
  const formatted = formatAdminUtcDateTime(value || '');
  return formatted || value || '';
}

const createCouponFormFromItem = (
  item: AdminPromotionCouponItem,
): CouponFormState => ({
  name: item.name || '',
  code: item.code || '',
  usage_type: String(item.usage_type || ''),
  discount_type: String(item.discount_type || ''),
  value: item.value || '',
  total_count: String(item.total_count || ''),
  scope_type: item.scope_type || 'single_course',
  shifu_bid: item.shifu_bid || '',
  start_at: normalizePromotionFormDateTimeValue(item.start_at),
  end_at: normalizePromotionFormDateTimeValue(item.end_at),
  enabled: 'true',
});

const createDefaultCampaignForm = (): CampaignFormState => ({
  name: '',
  apply_type: '',
  shifu_bid: '',
  discount_type: '',
  value: '',
  start_at: '',
  end_at: '',
  description: '',
  channel: '',
  enabled: 'true',
});

const createCampaignFormFromItem = (
  item: AdminPromotionCampaignItem,
  description: string,
): CampaignFormState => ({
  name: item.name || '',
  apply_type: String(item.apply_type || ''),
  shifu_bid: item.shifu_bid || '',
  discount_type: String(item.discount_type || ''),
  value: item.value || '',
  start_at: normalizePromotionFormDateTimeValue(item.start_at),
  end_at: normalizePromotionFormDateTimeValue(item.end_at),
  description: description || '',
  channel: item.channel || '',
  enabled: 'true',
});

const SectionCard = ({
  title,
  action,
  children,
}: React.PropsWithChildren<{ title: string; action?: React.ReactNode }>) => (
  <div className='rounded-xl border border-border bg-white p-5 shadow-sm'>
    {title || action ? (
      <div
        className={cn(
          'mb-4 flex items-center gap-4',
          title ? 'justify-between' : 'justify-start',
        )}
      >
        {title ? (
          <h2 className='text-base font-semibold text-foreground'>{title}</h2>
        ) : null}
        {action}
      </div>
    ) : null}
    {children}
  </div>
);

const renderTimeRange = (startAt?: string, endAt?: string) => {
  const start = formatAdminUtcDateTime(startAt || '');
  const end = formatAdminUtcDateTime(endAt || '');
  if (!start && !end) return EMPTY_VALUE;
  return `${start || EMPTY_VALUE} ~ ${end || EMPTY_VALUE}`;
};

const downloadExcelCompatibleCodesFile = (
  fileName: string,
  headerLabel: string,
  codes: string[],
) => {
  const tableRows = codes
    .map(
      code =>
        `<tr><td style="mso-number-format:'\\@';">${String(code)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')}</td></tr>`,
    )
    .join('');
  const html = `<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8" />
  </head>
  <body>
    <table>
      <thead>
        <tr><th>${headerLabel
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')}</th></tr>
      </thead>
      <tbody>${tableRows}</tbody>
    </table>
  </body>
</html>`;
  const blob = new Blob(['\ufeff', html], {
    type: 'application/vnd.ms-excel;charset=utf-8;',
  });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.URL.revokeObjectURL(url);
};

const renderRuleLabel = (discountTypeKey: string, value: string) => {
  if (discountTypeKey.endsWith('percent')) {
    return `${value}%`;
  }
  return `- ¥${value}`;
};

const toPromotionRelativeKey = (key?: string) => {
  if (!key) {
    return '';
  }
  return key.startsWith('module.operationsPromotion.')
    ? key.replace('module.operationsPromotion.', '')
    : key;
};

const resolveCouponUsageTypeLabel = (
  tPromotion: (key: string) => string,
  usageType: number | string,
  usageTypeKey?: string,
) => {
  if (usageTypeKey) {
    const translated = tPromotion(toPromotionRelativeKey(usageTypeKey));
    if (translated && translated !== usageTypeKey) {
      return translated;
    }
  }
  if (Number(usageType) === 801) {
    return tPromotion('usageType.generic');
  }
  if (Number(usageType) === 802) {
    return tPromotion('usageType.singleUse');
  }
  return EMPTY_VALUE;
};

const resolveCouponScopeLabel = (
  tPromotion: (key: string) => string,
  scopeType?: string,
) => {
  if (scopeType === 'all_courses') {
    return tPromotion('scope.allCourses');
  }
  if (scopeType === 'single_course') {
    return tPromotion('scope.singleCourse');
  }
  return EMPTY_VALUE;
};

const resolvePromotionStatusLabel = (
  tPromotion: (key: string) => string,
  statusKey?: string,
) => {
  if (!statusKey) {
    return EMPTY_VALUE;
  }
  const translated = tPromotion(toPromotionRelativeKey(statusKey));
  return translated && translated !== statusKey ? translated : EMPTY_VALUE;
};

const resolveCampaignApplyTypeLabel = (
  tPromotion: (key: string) => string,
  applyType: number | string,
) => {
  if (Number(applyType) === 2101) {
    return tPromotion('campaign.applyTypeAuto');
  }
  if (Number(applyType) === 2102) {
    return tPromotion('campaign.applyTypeEvent');
  }
  if (Number(applyType) === 2103) {
    return tPromotion('campaign.applyTypeManual');
  }
  return EMPTY_VALUE;
};

const canEditCampaignStrategyFields = (item: AdminPromotionCampaignItem) => {
  const startAt = parseLocalDateTimeInput(item.start_at || '');
  if (!startAt) {
    return false;
  }
  return startAt.getTime() > Date.now() && !item.has_redemptions;
};

const canEnableCouponItem = (item: AdminPromotionCouponItem) => {
  const endAt = parseDateValue(item.end_at || '');
  if (endAt && endAt.getTime() < Date.now()) {
    return false;
  }
  return Number(item.used_count || 0) < Number(item.total_count || 0);
};

const canEnableCampaignItem = (item: AdminPromotionCampaignItem) => {
  const endAt = parseDateValue(item.end_at || '');
  return !endAt || endAt.getTime() >= Date.now();
};

const shouldShowCouponStatusToggle = (item: AdminPromotionCouponItem) =>
  item.computed_status !== 'inactive' || canEnableCouponItem(item);

const shouldShowCampaignStatusToggle = (item: AdminPromotionCampaignItem) =>
  item.computed_status !== 'inactive' || canEnableCampaignItem(item);

const renderUserLabel = (
  item:
    | AdminPromotionCouponUsageItem
    | AdminPromotionCouponCodeItem
    | AdminPromotionCampaignRedemptionItem,
) => {
  return item.user_mobile || item.user_email || item.user_bid || EMPTY_VALUE;
};

const parseLocalDateTimeInput = (value: string) => {
  const normalized = String(value || '').trim();
  if (!normalized) {
    return null;
  }
  const parsed = new Date(
    normalized.includes(' ') ? normalized.replace(' ', 'T') : normalized,
  );
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
};

const formatDateValue = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const formatTimeValue = (date: Date) => {
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${hours}:${minutes}`;
};

const parseDateValue = (value: string) => {
  if (!value) {
    return undefined;
  }
  const parsed = new Date(
    String(value).includes(' ')
      ? String(value).replace(' ', 'T')
      : String(value),
  );
  if (Number.isNaN(parsed.getTime())) {
    return undefined;
  }
  return parsed;
};

const DEFAULT_START_TIME = '00:00';
const DEFAULT_END_TIME = '23:59';

const resolveDateTimeParts = (
  value: string,
  defaultTime: string,
): { date: string; time: string } => {
  const parsed = parseDateValue(value);
  if (!parsed) {
    return { date: '', time: defaultTime };
  }
  return {
    date: formatDateValue(parsed),
    time: formatTimeValue(parsed),
  };
};

const combineDateAndTime = (dateValue: string, timeValue: string) => {
  const normalizedDate = String(dateValue || '').trim();
  if (!normalizedDate) {
    return '';
  }
  const normalizedTime = String(timeValue || '').trim() || DEFAULT_START_TIME;
  return `${normalizedDate} ${normalizedTime}:00`;
};

const isPositiveIntegerString = (value: string) => /^\d+$/.test(value.trim());

const renderTooltipText = (text?: string, className?: string) => (
  <AdminTooltipText
    text={text}
    emptyValue={EMPTY_VALUE}
    className={className}
  />
);

const ClearableInput = ({
  value,
  onChange,
  placeholder,
  clearLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  clearLabel: string;
}) => (
  <div className='relative'>
    <Input
      value={value}
      onChange={event => onChange(event.target.value)}
      placeholder={placeholder}
      className={cn('h-9', value.trim() ? 'pr-9' : undefined)}
    />
    {value.trim() ? (
      <button
        type='button'
        aria-label={clearLabel}
        className='absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-foreground'
        onMouseDown={event => event.preventDefault()}
        onClick={() => onChange('')}
      >
        <X className='h-3.5 w-3.5' />
      </button>
    ) : null}
  </div>
);

const FormField = ({
  label,
  children,
}: React.PropsWithChildren<{ label: string }>) => (
  <div className='space-y-2'>
    <Label className='text-sm font-medium text-foreground'>{label}</Label>
    {children}
  </div>
);

const SearchField = ({
  label,
  children,
  contentClassName,
}: React.PropsWithChildren<{
  label: string;
  contentClassName?: string;
}>) => (
  <div className='flex items-center'>
    <span className={SEARCH_LABEL_CLASS}>{label}</span>
    <div className={cn('min-w-0 flex-1', contentClassName)}>{children}</div>
  </div>
);

const SearchActions = ({
  expanded,
  onReset,
  onSearch,
  onToggle,
  resetLabel,
  searchLabel,
  expandLabel,
  collapseLabel,
}: {
  expanded: boolean;
  onReset: () => void;
  onSearch: () => void;
  onToggle: () => void;
  resetLabel: string;
  searchLabel: string;
  expandLabel: string;
  collapseLabel: string;
}) => (
  <div className='flex items-center justify-end gap-2'>
    <Button
      size='sm'
      variant='outline'
      onClick={onReset}
    >
      {resetLabel}
    </Button>
    <Button
      size='sm'
      onClick={onSearch}
    >
      {searchLabel}
    </Button>
    <Button
      size='sm'
      variant='ghost'
      className='px-2 text-primary'
      onClick={onToggle}
    >
      {expanded ? collapseLabel : expandLabel}
      {expanded ? (
        <ChevronUp className='ml-1 h-4 w-4' />
      ) : (
        <ChevronDown className='ml-1 h-4 w-4' />
      )}
    </Button>
  </div>
);

const PromotionDateTimePicker = ({
  value,
  placeholder,
  resetLabel,
  clearLabel,
  timeLabel,
  defaultTime,
  minDateTime,
  maxDateTime,
  onChange,
}: {
  value: string;
  placeholder: string;
  resetLabel: string;
  clearLabel: string;
  timeLabel: string;
  defaultTime: string;
  minDateTime?: string;
  maxDateTime?: string;
  onChange: (value: string) => void;
}) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [draftDate, setDraftDate] = useState<Date | undefined>(undefined);
  const [draftTime, setDraftTime] = useState(defaultTime);
  const selectedDate = React.useMemo(() => parseDateValue(value), [value]);
  const minDate = React.useMemo(
    () => parseDateValue(minDateTime || ''),
    [minDateTime],
  );
  const maxDate = React.useMemo(
    () => parseDateValue(maxDateTime || ''),
    [maxDateTime],
  );
  const timeParts = React.useMemo(
    () => resolveDateTimeParts(value, defaultTime),
    [defaultTime, value],
  );
  const minParts = React.useMemo(
    () => resolveDateTimeParts(minDateTime || '', DEFAULT_START_TIME),
    [minDateTime],
  );
  const maxParts = React.useMemo(
    () => resolveDateTimeParts(maxDateTime || '', DEFAULT_END_TIME),
    [maxDateTime],
  );
  const minDateKey = minDate ? formatDateValue(minDate) : '';
  const maxDateKey = maxDate ? formatDateValue(maxDate) : '';
  const resolveInitialCalendarMonth = React.useCallback(
    () => selectedDate || minDate || maxDate || new Date(),
    [maxDate, minDate, selectedDate],
  );
  const [calendarMonth, setCalendarMonth] = useState<Date>(
    resolveInitialCalendarMonth,
  );
  const hasValue = Boolean(value);
  const label = selectedDate
    ? `${formatDateValue(selectedDate)} ${timeParts.time}`
    : placeholder;
  const draftDateKey = draftDate ? formatDateValue(draftDate) : '';
  const minTime =
    draftDateKey && draftDateKey === minDateKey ? minParts.time : undefined;
  const maxTime =
    draftDateKey && draftDateKey === maxDateKey ? maxParts.time : undefined;
  const isDraftTimeOutOfRange =
    (Boolean(minTime) && draftTime < String(minTime)) ||
    (Boolean(maxTime) && draftTime > String(maxTime));
  const isDayDisabled = React.useCallback(
    (date: Date) => {
      const dateKey = formatDateValue(date);
      if (minDateKey && dateKey < minDateKey) {
        return true;
      }
      if (maxDateKey && dateKey > maxDateKey) {
        return true;
      }
      return false;
    },
    [maxDateKey, minDateKey],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    setDraftDate(selectedDate);
    setDraftTime(timeParts.time);
    setCalendarMonth(resolveInitialCalendarMonth());
  }, [open, resolveInitialCalendarMonth, selectedDate, timeParts.time]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };

    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  const handleApply = () => {
    if (!draftDate) {
      return;
    }
    onChange(
      combineDateAndTime(formatDateValue(draftDate), draftTime || defaultTime),
    );
    setOpen(false);
  };

  return (
    <div className='relative'>
      <Button
        size='sm'
        variant='outline'
        type='button'
        aria-label={placeholder}
        onClick={() => setOpen(current => !current)}
        className={cn(
          'h-9 w-full justify-start font-normal',
          hasValue ? 'pr-16' : 'pr-10',
        )}
      >
        <span
          className={cn(
            'flex-1 truncate text-left',
            value ? 'text-foreground' : 'text-muted-foreground',
          )}
        >
          {label}
        </span>
      </Button>
      {hasValue ? (
        <button
          type='button'
          aria-label={clearLabel}
          className='absolute right-9 top-1/2 z-10 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-foreground'
          onMouseDown={event => {
            event.preventDefault();
            event.stopPropagation();
          }}
          onClick={event => {
            event.preventDefault();
            event.stopPropagation();
            onChange('');
          }}
        >
          <X className='h-3.5 w-3.5' />
        </button>
      ) : null}
      <CalendarIcon className='pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' />
      {open ? (
        <div className='fixed inset-0 z-[70] flex items-center justify-center p-4'>
          <button
            type='button'
            aria-label={clearLabel}
            className='absolute inset-0 bg-black/20'
            onClick={() => setOpen(false)}
          />
          <div
            className='relative w-auto max-w-[calc(100vw-2rem)] overflow-auto rounded-md border bg-popover p-0 shadow-md'
            onClick={event => event.stopPropagation()}
          >
            <Calendar
              mode='single'
              month={calendarMonth}
              numberOfMonths={1}
              selected={draftDate}
              disabled={isDayDisabled}
              onMonthChange={setCalendarMonth}
              onSelect={date => {
                setDraftDate(date || undefined);
                if (date) {
                  setCalendarMonth(date);
                }
              }}
              className='p-3 md:p-4 [--cell-size:2.3rem]'
            />
            <div className='border-t border-border px-4 py-3'>
              <FormField label={timeLabel}>
                <Input
                  type='time'
                  step={60}
                  className='h-9'
                  value={draftTime}
                  min={minTime}
                  max={maxTime}
                  onChange={event => setDraftTime(event.target.value)}
                />
              </FormField>
            </div>
            <div className='flex items-center justify-end gap-2 border-t border-border px-3 py-2'>
              <Button
                size='sm'
                variant='ghost'
                type='button'
                onClick={() => {
                  onChange('');
                  setOpen(false);
                }}
              >
                {resetLabel}
              </Button>
              <Button
                size='sm'
                type='button'
                disabled={!draftDate || isDraftTimeOutOfRange}
                onClick={handleApply}
              >
                {t('common.core.confirm')}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

const PromotionCouponCodesDialog = ({
  open,
  onOpenChange,
  couponBid,
  couponName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  couponBid: string;
  couponName: string;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [codes, setCodes] = useState<AdminPromotionCouponCodeItem[]>([]);
  const [keyword, setKeyword] = useState('');
  const [appliedKeyword, setAppliedKeyword] = useState('');

  const fetchCodes = useCallback(
    async (nextPage: number, nextKeyword: string) => {
      if (!couponBid) {
        return;
      }
      setLoading(true);
      try {
        const response = (await api.getAdminOperationPromotionCouponCodes({
          coupon_bid: couponBid,
          page_index: nextPage,
          page_size: PAGE_SIZE,
          keyword: nextKeyword,
        })) as AdminPromotionListResponse<AdminPromotionCouponCodeItem>;
        setCodes(response.items || []);
        setPageIndex(response.page || nextPage);
        setPageCount(response.page_count || 0);
      } catch (error) {
        setCodes([]);
        setPageIndex(nextPage);
        setPageCount(0);
        toast({
          description:
            (error as Error).message || t('common.core.submitFailed'),
        });
      } finally {
        setLoading(false);
      }
    },
    [couponBid, t, toast],
  );

  useEffect(() => {
    if (!open || !couponBid) {
      return;
    }
    setKeyword('');
    setAppliedKeyword('');
    void fetchCodes(1, '');
  }, [couponBid, fetchCodes, open]);

  const handleSearch = () => {
    const nextKeyword = keyword.trim();
    setAppliedKeyword(nextKeyword);
    void fetchCodes(1, nextKeyword);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-4xl'>
        <DialogHeader>
          <DialogTitle>{tPromotion('coupon.codes')}</DialogTitle>
        </DialogHeader>
        <div className='flex max-h-[70vh] min-h-0 flex-col overflow-hidden'>
          <div className='mb-4 text-sm text-muted-foreground'>
            {couponName || couponBid}
          </div>
          <div className='mb-4 flex items-center gap-3'>
            <div className='w-full max-w-sm'>
              <ClearableInput
                value={keyword}
                onChange={setKeyword}
                placeholder={tPromotion('coupon.subCodePlaceholder')}
                clearLabel={t('common.core.close')}
              />
            </div>
            <Button
              type='button'
              size='sm'
              onClick={handleSearch}
            >
              {tPromotion('actions.search')}
            </Button>
          </div>
          <AdminTableShell
            loading={loading}
            isEmpty={codes.length === 0}
            emptyContent={tPromotion('messages.emptyCodes')}
            emptyColSpan={4}
            withTooltipProvider
            containerClassName='min-h-0 flex-1'
            tableWrapperClassName='min-h-0 flex-1 overflow-auto'
            table={emptyRow => (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('coupon.subCode')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.status')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.user')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.orderBid')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {codes.map(item => (
                    <TableRow key={item.coupon_usage_bid}>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(item.code)}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(
                          item.status_key ? t(item.status_key) : EMPTY_VALUE,
                        )}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(renderUserLabel(item))}
                      </TableCell>
                      <TableCell className={TABLE_LAST_CELL_CLASS}>
                        {renderTooltipText(item.order_bid)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            footer={
              <AdminPagination
                pageIndex={pageIndex}
                pageCount={pageCount}
                onPageChange={page => void fetchCodes(page, appliedKeyword)}
                prevLabel={t('module.order.paginationPrev', 'Previous')}
                nextLabel={t('module.order.paginationNext', 'Next')}
                prevAriaLabel={t(
                  'module.order.paginationPrevAriaLabel',
                  'Go to previous page',
                )}
                nextAriaLabel={t(
                  'module.order.paginationNextAriaLabel',
                  'Go to next page',
                )}
                className='mx-0 w-auto justify-end'
                hideWhenSinglePage
              />
            }
            footerClassName='mt-3'
          />
        </div>
      </DialogContent>
    </Dialog>
  );
};

const PromotionCampaignRedemptionsDialog = ({
  open,
  onOpenChange,
  promoBid,
  campaignName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  promoBid: string;
  campaignName: string;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [redemptions, setRedemptions] = useState<
    AdminPromotionCampaignRedemptionItem[]
  >([]);

  const fetchRedemptions = useCallback(
    async (nextPage: number) => {
      if (!promoBid) {
        return;
      }
      setLoading(true);
      try {
        const response =
          (await api.getAdminOperationPromotionCampaignRedemptions({
            promo_bid: promoBid,
            page_index: nextPage,
            page_size: PAGE_SIZE,
          })) as AdminPromotionListResponse<AdminPromotionCampaignRedemptionItem>;
        setRedemptions(response.items || []);
        setPageIndex(response.page || nextPage);
        setPageCount(response.page_count || 0);
      } catch (error) {
        setRedemptions([]);
        setPageIndex(nextPage);
        setPageCount(0);
        toast({
          description:
            (error as Error).message || t('common.core.submitFailed'),
        });
      } finally {
        setLoading(false);
      }
    },
    [promoBid, t, toast],
  );

  useEffect(() => {
    if (!open || !promoBid) {
      return;
    }
    void fetchRedemptions(1);
  }, [fetchRedemptions, open, promoBid]);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-5xl'>
        <DialogHeader>
          <DialogTitle>{tPromotion('campaign.redemptions')}</DialogTitle>
        </DialogHeader>
        <div className='flex max-h-[70vh] min-h-0 flex-col overflow-hidden'>
          <div className='mb-4 text-sm text-muted-foreground'>
            {campaignName || promoBid}
          </div>
          <AdminTableShell
            loading={loading}
            isEmpty={redemptions.length === 0}
            emptyContent={tPromotion('messages.emptyRedemptions')}
            emptyColSpan={4}
            withTooltipProvider
            containerClassName='min-h-0 flex-1'
            tableWrapperClassName='min-h-0 flex-1 overflow-auto'
            table={emptyRow => (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.appliedAt')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.user')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.orderBid')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('campaign.discountAmount')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {redemptions.map(item => (
                    <TableRow key={item.redemption_bid}>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.applied_at),
                        )}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(renderUserLabel(item))}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(item.order_bid)}
                      </TableCell>
                      <TableCell className={TABLE_LAST_CELL_CLASS}>
                        {renderTooltipText(item.discount_amount)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            footer={
              <AdminPagination
                pageIndex={pageIndex}
                pageCount={pageCount}
                onPageChange={page => void fetchRedemptions(page)}
                prevLabel={t('module.order.paginationPrev', 'Previous')}
                nextLabel={t('module.order.paginationNext', 'Next')}
                prevAriaLabel={t(
                  'module.order.paginationPrevAriaLabel',
                  'Go to previous page',
                )}
                nextAriaLabel={t(
                  'module.order.paginationNextAriaLabel',
                  'Go to next page',
                )}
                className='mx-0 w-auto justify-end'
                hideWhenSinglePage
              />
            }
            footerClassName='mt-3'
          />
        </div>
      </DialogContent>
    </Dialog>
  );
};

const PromotionCouponUsageDialog = ({
  open,
  onOpenChange,
  couponBid,
  couponName,
  showCourseColumn,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  couponBid: string;
  couponName: string;
  showCourseColumn: boolean;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [usages, setUsages] = useState<AdminPromotionCouponUsageItem[]>([]);

  const fetchUsages = useCallback(
    async (nextPage: number) => {
      if (!couponBid) {
        return;
      }
      setLoading(true);
      try {
        const response = (await api.getAdminOperationPromotionCouponUsages({
          coupon_bid: couponBid,
          page_index: nextPage,
          page_size: PAGE_SIZE,
        })) as AdminPromotionListResponse<AdminPromotionCouponUsageItem>;
        setUsages(response.items || []);
        setPageIndex(response.page || nextPage);
        setPageCount(response.page_count || 0);
      } catch (error) {
        setUsages([]);
        setPageIndex(nextPage);
        setPageCount(0);
        toast({
          description:
            (error as Error).message || t('common.core.submitFailed'),
        });
      } finally {
        setLoading(false);
      }
    },
    [couponBid, t, toast],
  );

  useEffect(() => {
    if (!open || !couponBid) {
      return;
    }
    void fetchUsages(1);
  }, [couponBid, fetchUsages, open]);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-4xl'>
        <DialogHeader>
          <DialogTitle>{tPromotion('coupon.usages')}</DialogTitle>
        </DialogHeader>
        <div className='flex max-h-[70vh] min-h-0 flex-col overflow-hidden'>
          <div className='mb-4 text-sm text-muted-foreground'>
            {couponName || couponBid}
          </div>
          <AdminTableShell
            loading={loading}
            isEmpty={usages.length === 0}
            emptyContent={tPromotion('messages.emptyUsages')}
            emptyColSpan={showCourseColumn ? 5 : 4}
            withTooltipProvider
            containerClassName='min-h-0 flex-1'
            tableWrapperClassName='min-h-0 flex-1 overflow-auto'
            table={emptyRow => (
              <Table containerClassName='overflow-visible max-h-none'>
                <TableHeader>
                  <TableRow>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.usedAt')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('coupon.code')}
                    </TableHead>
                    {showCourseColumn ? (
                      <TableHead className={TABLE_HEAD_CLASS}>
                        {tPromotion('table.redeemedCourse')}
                      </TableHead>
                    ) : null}
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.user')}
                    </TableHead>
                    <TableHead className={TABLE_HEAD_CLASS}>
                      {tPromotion('table.orderBid')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {usages.map(item => (
                    <TableRow key={item.coupon_usage_bid}>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.used_at),
                        )}
                      </TableCell>
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(item.code)}
                      </TableCell>
                      {showCourseColumn ? (
                        <TableCell className={TABLE_CELL_CLASS}>
                          {renderTooltipText(
                            item.course_name || item.shifu_bid || EMPTY_VALUE,
                          )}
                        </TableCell>
                      ) : null}
                      <TableCell className={TABLE_CELL_CLASS}>
                        {renderTooltipText(renderUserLabel(item))}
                      </TableCell>
                      <TableCell className={TABLE_LAST_CELL_CLASS}>
                        {renderTooltipText(item.order_bid)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            footer={
              <AdminPagination
                pageIndex={pageIndex}
                pageCount={pageCount}
                onPageChange={page => void fetchUsages(page)}
                prevLabel={t('module.order.paginationPrev', 'Previous')}
                nextLabel={t('module.order.paginationNext', 'Next')}
                prevAriaLabel={t(
                  'module.order.paginationPrevAriaLabel',
                  'Go to previous page',
                )}
                nextAriaLabel={t(
                  'module.order.paginationNextAriaLabel',
                  'Go to next page',
                )}
                className='mx-0 w-auto justify-end'
                hideWhenSinglePage
              />
            }
            footerClassName='mt-3'
          />
        </div>
      </DialogContent>
    </Dialog>
  );
};

const PromotionCouponDialog = ({
  open,
  onOpenChange,
  onSubmit,
  coupon,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: CouponFormState) => Promise<void>;
  coupon?: AdminPromotionCouponItem | null;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const { toast } = useToast();
  const [form, setForm] = useState<CouponFormState>(() =>
    createDefaultCouponForm(),
  );
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(
        coupon ? createCouponFormFromItem(coupon) : createDefaultCouponForm(),
      );
    }
  }, [coupon, open]);

  const isEditing = Boolean(coupon);
  const isSingleUseCoupon = form.usage_type === '802';
  const isPercentDiscount = form.discount_type === '702';
  const valueLabel = isPercentDiscount
    ? tPromotion('coupon.valuePercent')
    : tPromotion('coupon.valueAmount');
  const valuePlaceholder = isPercentDiscount
    ? tPromotion('coupon.valuePercentPlaceholder')
    : tPromotion('coupon.valueAmountPlaceholder');

  const handleSubmit = async () => {
    const normalizedName = form.name.trim();
    const normalizedCode = form.code.trim();
    const normalizedQuantity = form.total_count.trim();
    const normalizedCourseId = form.shifu_bid.trim();
    const normalizedValue = form.value.trim();
    const startAtDate = parseLocalDateTimeInput(form.start_at);
    const endAtDate = parseLocalDateTimeInput(form.end_at);

    if (!normalizedName) {
      toast({ description: tPromotion('validation.couponNameRequired') });
      return;
    }
    if (!form.usage_type) {
      toast({ description: tPromotion('validation.usageTypeRequired') });
      return;
    }
    if (!form.discount_type) {
      toast({ description: tPromotion('validation.discountTypeRequired') });
      return;
    }
    if (!normalizedValue) {
      toast({
        description: isPercentDiscount
          ? tPromotion('validation.valuePercentRequired')
          : tPromotion('validation.valueAmountRequired'),
      });
      return;
    }

    const numericValue = Number(normalizedValue);
    if (!Number.isFinite(numericValue)) {
      toast({
        description: isPercentDiscount
          ? tPromotion('validation.valuePercentInvalid')
          : tPromotion('validation.valueAmountInvalid'),
      });
      return;
    }
    if (isPercentDiscount) {
      if (numericValue <= 0 || numericValue > 100) {
        toast({ description: tPromotion('validation.valuePercentInvalid') });
        return;
      }
    } else if (numericValue <= 0) {
      toast({ description: tPromotion('validation.valueAmountInvalid') });
      return;
    }

    if (!isSingleUseCoupon && !normalizedCode) {
      toast({ description: tPromotion('validation.codeRequired') });
      return;
    }
    if (!normalizedQuantity) {
      toast({ description: tPromotion('validation.quantityRequired') });
      return;
    }
    if (
      !isPositiveIntegerString(normalizedQuantity) ||
      Number(normalizedQuantity) <= 0
    ) {
      toast({ description: tPromotion('validation.quantityInvalid') });
      return;
    }
    if (form.scope_type === 'single_course' && !normalizedCourseId) {
      toast({ description: tPromotion('validation.courseIdRequired') });
      return;
    }
    if (!form.start_at) {
      toast({ description: tPromotion('validation.startAtRequired') });
      return;
    }
    if (!form.end_at) {
      toast({ description: tPromotion('validation.endAtRequired') });
      return;
    }
    if (
      !startAtDate ||
      !endAtDate ||
      endAtDate.getTime() < startAtDate.getTime()
    ) {
      toast({ description: tPromotion('validation.endAtInvalid') });
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(form);
      onOpenChange(false);
    } catch (error) {
      toast({
        description: (error as Error).message || t('common.core.submitFailed'),
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-[680px]'>
        <DialogHeader>
          <DialogTitle>
            {isEditing
              ? tPromotion('coupon.editDialogTitle')
              : tPromotion('coupon.dialogTitle')}
          </DialogTitle>
        </DialogHeader>
        <div className='grid gap-4 md:grid-cols-2'>
          <FormField label={tPromotion('table.name')}>
            <Input
              className='h-9'
              value={form.name}
              placeholder={tPromotion('filters.namePlaceholder')}
              onChange={event =>
                setForm(current => ({ ...current, name: event.target.value }))
              }
            />
          </FormField>
          <FormField label={tPromotion('table.usageType')}>
            <Select
              value={form.usage_type}
              onValueChange={value =>
                setForm(current => ({
                  ...current,
                  usage_type: value,
                  code: value === '801' ? current.code : '',
                }))
              }
              disabled={isEditing}
            >
              <SelectTrigger className='h-9'>
                <SelectValue placeholder={tPromotion('filters.usageType')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='801'>
                  {tPromotion('usageType.generic')}
                </SelectItem>
                <SelectItem value='802'>
                  {tPromotion('usageType.singleUse')}
                </SelectItem>
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={tPromotion('filters.discountType')}>
            <Select
              value={form.discount_type}
              onValueChange={value =>
                setForm(current => ({ ...current, discount_type: value }))
              }
              disabled={isEditing}
            >
              <SelectTrigger className='h-9'>
                <SelectValue placeholder={tPromotion('filters.discountType')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='701'>
                  {tPromotion('discountType.fixed')}
                </SelectItem>
                <SelectItem value='702'>
                  {tPromotion('discountType.percent')}
                </SelectItem>
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={valueLabel}>
            <Input
              className='h-9'
              value={form.value}
              placeholder={valuePlaceholder}
              onChange={event =>
                setForm(current => ({ ...current, value: event.target.value }))
              }
              disabled={isEditing}
            />
          </FormField>
          {isSingleUseCoupon ? null : (
            <FormField label={tPromotion('coupon.code')}>
              <Input
                className='h-9'
                value={form.code}
                placeholder={tPromotion('coupon.codePlaceholder')}
                onChange={event =>
                  setForm(current => ({ ...current, code: event.target.value }))
                }
                disabled={isEditing}
              />
            </FormField>
          )}
          <FormField label={tPromotion('coupon.quantity')}>
            <Input
              className='h-9'
              value={form.total_count}
              placeholder={tPromotion('coupon.quantityPlaceholder')}
              onChange={event =>
                setForm(current => ({
                  ...current,
                  total_count: event.target.value,
                }))
              }
            />
          </FormField>
          <FormField label={tPromotion('coupon.scopeType')}>
            <Select
              value={form.scope_type}
              onValueChange={value =>
                setForm(current => ({
                  ...current,
                  scope_type: value,
                  shifu_bid: value === 'single_course' ? current.shifu_bid : '',
                }))
              }
              disabled={isEditing}
            >
              <SelectTrigger className='h-9'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='all_courses'>
                  {tPromotion('scope.allCourses')}
                </SelectItem>
                <SelectItem value='single_course'>
                  {tPromotion('scope.singleCourse')}
                </SelectItem>
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={tPromotion('coupon.courseId')}>
            <Input
              className='h-9'
              value={form.shifu_bid}
              placeholder={tPromotion('filters.courseIdPlaceholder')}
              onChange={event =>
                setForm(current => ({
                  ...current,
                  shifu_bid: event.target.value,
                }))
              }
              disabled={isEditing || form.scope_type !== 'single_course'}
            />
          </FormField>
          <FormField label={tPromotion('coupon.startAt')}>
            <PromotionDateTimePicker
              value={form.start_at}
              placeholder={tPromotion('coupon.startAt')}
              resetLabel={t('module.order.filters.reset')}
              clearLabel={t('common.core.close')}
              timeLabel={tPromotion('coupon.startAt')}
              defaultTime={DEFAULT_START_TIME}
              maxDateTime={form.end_at}
              onChange={nextValue =>
                setForm(current => ({
                  ...current,
                  start_at: nextValue,
                }))
              }
            />
          </FormField>
          <FormField label={tPromotion('coupon.endAt')}>
            <PromotionDateTimePicker
              value={form.end_at}
              placeholder={tPromotion('coupon.endAt')}
              resetLabel={t('module.order.filters.reset')}
              clearLabel={t('common.core.close')}
              timeLabel={tPromotion('coupon.endAt')}
              defaultTime={DEFAULT_END_TIME}
              minDateTime={form.start_at}
              onChange={nextValue =>
                setForm(current => ({
                  ...current,
                  end_at: nextValue,
                }))
              }
            />
          </FormField>
          {isEditing ? (
            <div className='space-y-1 md:col-span-2'>
              <p className='text-sm text-muted-foreground'>
                {tPromotion('messages.partialTimeEditHint')}
              </p>
              <p className='text-sm text-muted-foreground'>
                {tPromotion('messages.couponEditPolicyHint')}
              </p>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            onClick={() => onOpenChange(false)}
          >
            {t('common.core.cancel')}
          </Button>
          <Button
            type='button'
            onClick={() => void handleSubmit()}
            disabled={submitting}
          >
            {isEditing
              ? tPromotion('actions.confirmUpdate')
              : tPromotion('actions.confirmCreate')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const PromotionCampaignDialog = ({
  open,
  onOpenChange,
  onSubmit,
  campaign,
  strategyEditable,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: CampaignFormState) => Promise<void>;
  campaign?: {
    item: AdminPromotionCampaignItem;
    description: string;
  } | null;
  strategyEditable?: boolean;
}) => {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const { toast } = useToast();
  const [form, setForm] = useState<CampaignFormState>(() =>
    createDefaultCampaignForm(),
  );
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(
        campaign
          ? createCampaignFormFromItem(campaign.item, campaign.description)
          : createDefaultCampaignForm(),
      );
    }
  }, [campaign, open]);

  const isEditing = Boolean(campaign);

  const isPercentDiscount = form.discount_type === '702';
  const valueLabel = form.discount_type
    ? isPercentDiscount
      ? tPromotion('coupon.valuePercent')
      : tPromotion('coupon.valueAmount')
    : tPromotion('campaign.value');
  const valuePlaceholder = form.discount_type
    ? isPercentDiscount
      ? tPromotion('coupon.valuePercentPlaceholder')
      : tPromotion('coupon.valueAmountPlaceholder')
    : tPromotion('campaign.valuePlaceholder');

  const handleSubmit = async () => {
    const normalizedName = form.name.trim();
    const normalizedCourseId = form.shifu_bid.trim();
    const normalizedValue = form.value.trim();
    const startAtDate = parseLocalDateTimeInput(form.start_at);
    const endAtDate = parseLocalDateTimeInput(form.end_at);

    if (!normalizedName) {
      toast({ description: tPromotion('validation.campaignNameRequired') });
      return;
    }
    if (!form.apply_type) {
      toast({
        description: tPromotion('validation.campaignApplyTypeRequired'),
      });
      return;
    }
    if (!normalizedCourseId) {
      toast({ description: tPromotion('validation.courseIdRequired') });
      return;
    }
    if (!form.discount_type) {
      toast({ description: tPromotion('validation.discountTypeRequired') });
      return;
    }
    if (!normalizedValue) {
      toast({
        description: isPercentDiscount
          ? tPromotion('validation.valuePercentRequired')
          : tPromotion('validation.valueAmountRequired'),
      });
      return;
    }
    const numericValue = Number(normalizedValue);
    if (!Number.isFinite(numericValue)) {
      toast({
        description: isPercentDiscount
          ? tPromotion('validation.valuePercentInvalid')
          : tPromotion('validation.valueAmountInvalid'),
      });
      return;
    }
    if (isPercentDiscount) {
      if (numericValue <= 0 || numericValue > 100) {
        toast({ description: tPromotion('validation.valuePercentInvalid') });
        return;
      }
    } else if (numericValue <= 0) {
      toast({ description: tPromotion('validation.valueAmountInvalid') });
      return;
    }
    if (!form.start_at) {
      toast({ description: tPromotion('validation.startAtRequired') });
      return;
    }
    if (!form.end_at) {
      toast({ description: tPromotion('validation.endAtRequired') });
      return;
    }
    if (
      !startAtDate ||
      !endAtDate ||
      endAtDate.getTime() < startAtDate.getTime()
    ) {
      toast({ description: tPromotion('validation.endAtInvalid') });
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(form);
      onOpenChange(false);
    } catch (error) {
      toast({
        description: (error as Error).message || t('common.core.submitFailed'),
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-[700px]'>
        <DialogHeader>
          <DialogTitle>
            {isEditing
              ? tPromotion('campaign.editDialogTitle')
              : tPromotion('campaign.dialogTitle')}
          </DialogTitle>
        </DialogHeader>
        <div className='grid gap-4 md:grid-cols-2'>
          <FormField label={tPromotion('table.campaignName')}>
            <Input
              className='h-9'
              value={form.name}
              placeholder={tPromotion('campaign.namePlaceholder')}
              onChange={event =>
                setForm(current => ({ ...current, name: event.target.value }))
              }
            />
          </FormField>
          <FormField label={tPromotion('coupon.courseId')}>
            <Input
              className='h-9'
              value={form.shifu_bid}
              placeholder={tPromotion('filters.courseIdPlaceholder')}
              onChange={event =>
                setForm(current => ({
                  ...current,
                  shifu_bid: event.target.value,
                }))
              }
              disabled={isEditing}
            />
          </FormField>
          <FormField label={tPromotion('campaign.applyType')}>
            <Select
              value={form.apply_type}
              onValueChange={value =>
                setForm(current => ({ ...current, apply_type: value }))
              }
              disabled={isEditing && !strategyEditable}
            >
              <SelectTrigger className='h-9'>
                <SelectValue
                  placeholder={tPromotion('campaign.applyTypePlaceholder')}
                />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='2101'>
                  {tPromotion('campaign.applyTypeAuto')}
                </SelectItem>
                <SelectItem value='2102'>
                  {tPromotion('campaign.applyTypeEvent')}
                </SelectItem>
                <SelectItem value='2103'>
                  {tPromotion('campaign.applyTypeManual')}
                </SelectItem>
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={tPromotion('campaign.channel')}>
            <Input
              className='h-9'
              value={form.channel}
              placeholder={tPromotion('campaign.channelPlaceholder')}
              onChange={event =>
                setForm(current => ({
                  ...current,
                  channel: event.target.value,
                }))
              }
              disabled={isEditing}
            />
          </FormField>
          <FormField label={tPromotion('filters.discountType')}>
            <Select
              value={form.discount_type}
              onValueChange={value =>
                setForm(current => ({ ...current, discount_type: value }))
              }
              disabled={isEditing}
            >
              <SelectTrigger className='h-9'>
                <SelectValue placeholder={tPromotion('filters.discountType')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='701'>
                  {tPromotion('discountType.fixed')}
                </SelectItem>
                <SelectItem value='702'>
                  {tPromotion('discountType.percent')}
                </SelectItem>
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={valueLabel}>
            <Input
              className='h-9'
              value={form.value}
              placeholder={valuePlaceholder}
              onChange={event =>
                setForm(current => ({ ...current, value: event.target.value }))
              }
              disabled={isEditing}
            />
          </FormField>
          <FormField label={tPromotion('campaign.startAt')}>
            <PromotionDateTimePicker
              value={form.start_at}
              placeholder={tPromotion('campaign.startAtPlaceholder')}
              resetLabel={t('module.order.filters.reset')}
              clearLabel={t('common.core.close')}
              timeLabel={tPromotion('campaign.startAt')}
              defaultTime={DEFAULT_START_TIME}
              maxDateTime={form.end_at}
              onChange={nextValue =>
                setForm(current => ({
                  ...current,
                  start_at: nextValue,
                }))
              }
            />
          </FormField>
          <FormField label={tPromotion('campaign.endAt')}>
            <PromotionDateTimePicker
              value={form.end_at}
              placeholder={tPromotion('campaign.endAtPlaceholder')}
              resetLabel={t('module.order.filters.reset')}
              clearLabel={t('common.core.close')}
              timeLabel={tPromotion('campaign.endAt')}
              defaultTime={DEFAULT_END_TIME}
              minDateTime={form.start_at}
              onChange={nextValue =>
                setForm(current => ({
                  ...current,
                  end_at: nextValue,
                }))
              }
            />
          </FormField>
          <div className='md:col-span-2'>
            <FormField label={tPromotion('campaign.description')}>
              <Textarea
                value={form.description}
                placeholder={tPromotion('campaign.descriptionPlaceholder')}
                onChange={event =>
                  setForm(current => ({
                    ...current,
                    description: event.target.value,
                  }))
                }
              />
            </FormField>
          </div>
          {isEditing ? (
            <div className='space-y-1 md:col-span-2'>
              <p className='text-sm text-muted-foreground'>
                {tPromotion('messages.partialTimeEditHint')}
              </p>
              <p className='text-sm text-muted-foreground'>
                {tPromotion('messages.campaignEditPolicyHint')}
              </p>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            onClick={() => onOpenChange(false)}
          >
            {t('common.core.cancel')}
          </Button>
          <Button
            type='button'
            onClick={() => void handleSubmit()}
            disabled={submitting}
          >
            {isEditing
              ? tPromotion('actions.confirmUpdate')
              : tPromotion('actions.confirmCreate')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default function AdminOperationPromotionsPage() {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const { isReady } = useOperatorGuard();
  const { toast } = useToast();
  const clearLabel = t('common.core.close');
  const [tab, setTab] = useState<PromotionTab>('coupons');
  const [couponLoading, setCouponLoading] = useState(true);
  const [campaignLoading, setCampaignLoading] = useState(false);
  const [couponError, setCouponError] = useState<ErrorState>(null);
  const [campaignError, setCampaignError] = useState<ErrorState>(null);
  const [coupons, setCoupons] = useState<AdminPromotionCouponItem[]>([]);
  const [campaigns, setCampaigns] = useState<AdminPromotionCampaignItem[]>([]);
  const [couponPage, setCouponPage] = useState(1);
  const [campaignPage, setCampaignPage] = useState(1);
  const [couponPageCount, setCouponPageCount] = useState(0);
  const [campaignPageCount, setCampaignPageCount] = useState(0);
  const [couponFilters, setCouponFilters] = useState<CouponFilters>(() =>
    createDefaultCouponFilters(),
  );
  const [campaignFilters, setCampaignFilters] = useState<CampaignFilters>(() =>
    createDefaultCampaignFilters(),
  );
  const campaignPageRef = useRef(campaignPage);
  const campaignFiltersRef = useRef(campaignFilters);
  const [couponCreateOpen, setCouponCreateOpen] = useState(false);
  const [editingCoupon, setEditingCoupon] =
    useState<AdminPromotionCouponItem | null>(null);
  const [campaignCreateOpen, setCampaignCreateOpen] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState<{
    item: AdminPromotionCampaignItem;
    description: string;
  } | null>(null);
  const [selectedCouponBid, setSelectedCouponBid] = useState('');
  const [selectedCouponName, setSelectedCouponName] = useState('');
  const [selectedCouponShowCourseColumn, setSelectedCouponShowCourseColumn] =
    useState(false);
  const [couponCodesOpen, setCouponCodesOpen] = useState(false);
  const [selectedPromoBid, setSelectedPromoBid] = useState('');
  const [selectedPromoName, setSelectedPromoName] = useState('');
  const [couponUsageOpen, setCouponUsageOpen] = useState(false);
  const [campaignRedemptionsOpen, setCampaignRedemptionsOpen] = useState(false);
  const [couponFiltersExpanded, setCouponFiltersExpanded] = useState(false);
  const [campaignFiltersExpanded, setCampaignFiltersExpanded] = useState(false);
  const {
    getColumnStyle: getCouponColumnStyle,
    getResizeHandleProps: getCouponResizeHandleProps,
  } = useAdminResizableColumns<CouponColumnKey>({
    storageKey: COUPON_COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: COUPON_DEFAULT_COLUMN_WIDTHS,
    minWidth: COLUMN_MIN_WIDTH,
    maxWidth: COLUMN_MAX_WIDTH,
  });
  const {
    getColumnStyle: getCampaignColumnStyle,
    getResizeHandleProps: getCampaignResizeHandleProps,
  } = useAdminResizableColumns<CampaignColumnKey>({
    storageKey: CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: CAMPAIGN_DEFAULT_COLUMN_WIDTHS,
    minWidth: COLUMN_MIN_WIDTH,
    maxWidth: COLUMN_MAX_WIDTH,
  });

  const renderCouponResizeHandle = (key: CouponColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getCouponResizeHandleProps(key)}
    />
  );

  const renderCampaignResizeHandle = (key: CampaignColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getCampaignResizeHandleProps(key)}
    />
  );

  const fetchCoupons = useCallback(
    async (pageIndex: number, filters: CouponFilters) => {
      setCouponLoading(true);
      setCouponError(null);
      try {
        const requestPayload = {
          page_index: pageIndex,
          page_size: PAGE_SIZE,
          keyword: filters.keyword.trim(),
          name: filters.name.trim(),
          course_query: filters.course_query.trim(),
          usage_type: filters.usage_type,
          discount_type: filters.discount_type,
          status: filters.status,
          start_time: filters.start_time,
          end_time: filters.end_time,
        };
        let response = (await api.getAdminOperationPromotionCoupons(
          requestPayload,
        )) as AdminPromotionListResponse<AdminPromotionCouponItem>;
        const responsePage = response.page || pageIndex;
        const responsePageCount = response.page_count || 0;
        if (
          responsePageCount > 0 &&
          responsePage > responsePageCount &&
          (response.items || []).length === 0
        ) {
          response = (await api.getAdminOperationPromotionCoupons({
            ...requestPayload,
            page_index: responsePageCount,
          })) as AdminPromotionListResponse<AdminPromotionCouponItem>;
        }
        setCoupons(response.items || []);
        setCouponPage(response.page || 1);
        setCouponPageCount(response.page_count || 0);
      } catch (error) {
        setCouponError({
          message: (error as Error).message || 'Failed to load coupons',
        });
        setCoupons([]);
        setCouponPage(pageIndex);
        setCouponPageCount(0);
      } finally {
        setCouponLoading(false);
      }
    },
    [],
  );

  const fetchCampaigns = useCallback(
    async (pageIndex: number, filters: CampaignFilters) => {
      setCampaignLoading(true);
      setCampaignError(null);
      try {
        const requestPayload = {
          page_index: pageIndex,
          page_size: PAGE_SIZE,
          keyword: filters.keyword.trim(),
          course_query: filters.course_query.trim(),
          discount_type: filters.discount_type,
          status: filters.status,
          start_time: filters.start_time,
          end_time: filters.end_time,
        };
        let response = (await api.getAdminOperationPromotionCampaigns(
          requestPayload,
        )) as AdminPromotionListResponse<AdminPromotionCampaignItem>;
        const responsePage = response.page || pageIndex;
        const responsePageCount = response.page_count || 0;
        if (
          responsePageCount > 0 &&
          responsePage > responsePageCount &&
          (response.items || []).length === 0
        ) {
          response = (await api.getAdminOperationPromotionCampaigns({
            ...requestPayload,
            page_index: responsePageCount,
          })) as AdminPromotionListResponse<AdminPromotionCampaignItem>;
        }
        setCampaigns(response.items || []);
        setCampaignPage(response.page || 1);
        setCampaignPageCount(response.page_count || 0);
      } catch (error) {
        setCampaignError({
          message: (error as Error).message || 'Failed to load campaigns',
        });
        setCampaigns([]);
        setCampaignPage(pageIndex);
        setCampaignPageCount(0);
      } finally {
        setCampaignLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (!isReady) return;
    void fetchCoupons(1, createDefaultCouponFilters());
  }, [fetchCoupons, isReady]);

  campaignPageRef.current = campaignPage;
  campaignFiltersRef.current = campaignFilters;

  useEffect(() => {
    if (!isReady || tab !== 'campaigns') return;
    // Re-entering the tab should keep the operator on the same filtered page.
    void fetchCampaigns(campaignPageRef.current, campaignFiltersRef.current);
  }, [fetchCampaigns, isReady, tab]);

  const handleCouponSearch = () => void fetchCoupons(1, couponFilters);
  const handleCouponReset = () => {
    const next = createDefaultCouponFilters();
    setCouponFilters(next);
    void fetchCoupons(1, next);
  };
  const handleCampaignSearch = () => void fetchCampaigns(1, campaignFilters);
  const handleCampaignReset = () => {
    const next = createDefaultCampaignFilters();
    setCampaignFilters(next);
    void fetchCampaigns(1, next);
  };

  const handleCouponCreate = async (payload: CouponFormState) => {
    await api.createAdminOperationPromotionCoupon({
      name: payload.name.trim(),
      usage_type: Number(payload.usage_type),
      discount_type: Number(payload.discount_type),
      value: payload.value.trim(),
      total_count: Number(payload.total_count.trim()),
      code: payload.usage_type === '801' ? payload.code.trim() : '',
      scope_type: payload.scope_type,
      shifu_bid: payload.shifu_bid.trim(),
      start_at: payload.start_at,
      end_at: payload.end_at,
      enabled: payload.enabled === 'true',
    });
    toast({ description: tPromotion('messages.createSuccess') });
    await fetchCoupons(1, couponFilters);
  };

  const handleCouponUpdate = async (payload: CouponFormState) => {
    if (!editingCoupon) {
      return;
    }
    await api.updateAdminOperationPromotionCoupon({
      coupon_bid: editingCoupon.coupon_bid,
      name: payload.name.trim(),
      code: payload.usage_type === '801' ? payload.code.trim() : '',
      usage_type: Number(payload.usage_type),
      discount_type: Number(payload.discount_type),
      value: payload.value.trim(),
      total_count: Number(payload.total_count.trim()),
      scope_type: payload.scope_type,
      shifu_bid: payload.shifu_bid.trim(),
      start_at: payload.start_at,
      end_at: payload.end_at,
      enabled: payload.enabled === 'true',
    });
    toast({ description: tPromotion('messages.updateSuccess') });
    await fetchCoupons(couponPage, couponFilters);
    setEditingCoupon(null);
  };

  const handleCouponCodeExport = async (coupon: AdminPromotionCouponItem) => {
    if (Number(coupon.usage_type) !== 802) {
      return;
    }

    try {
      const allCodes: string[] = [];
      let nextPage = 1;
      let pageCount = 1;

      while (nextPage <= pageCount) {
        const response = (await api.getAdminOperationPromotionCouponCodes({
          coupon_bid: coupon.coupon_bid,
          page_index: nextPage,
          page_size: 100,
        })) as AdminPromotionListResponse<AdminPromotionCouponCodeItem>;
        (response.items || []).forEach(item => {
          if (item.code) {
            allCodes.push(item.code);
          }
        });
        pageCount = response.page_count || 0;
        nextPage += 1;
      }

      if (!allCodes.length) {
        toast({ description: tPromotion('messages.emptyCodes') });
        return;
      }

      const safeBaseName = (coupon.name || coupon.coupon_bid || 'coupon-codes')
        .trim()
        .replace(/[\\/:*?"<>|]+/g, '-');
      downloadExcelCompatibleCodesFile(
        `${safeBaseName}.xls`,
        tPromotion('coupon.code'),
        allCodes,
      );
      toast({ description: tPromotion('messages.exportSuccess') });
    } catch (error) {
      toast({
        description:
          (error as Error).message || tPromotion('messages.exportFailed'),
      });
    }
  };

  const handleCampaignCreate = async (payload: CampaignFormState) => {
    await api.createAdminOperationPromotionCampaign({
      name: payload.name.trim(),
      apply_type: Number(payload.apply_type),
      shifu_bid: payload.shifu_bid.trim(),
      discount_type: Number(payload.discount_type),
      value: payload.value.trim(),
      start_at: payload.start_at,
      end_at: payload.end_at,
      description: payload.description.trim(),
      channel: payload.channel.trim(),
      enabled: payload.enabled === 'true',
    });
    toast({ description: tPromotion('messages.createSuccess') });
    await fetchCampaigns(1, campaignFilters);
  };

  const handleCampaignUpdate = async (payload: CampaignFormState) => {
    if (!editingCampaign) {
      return;
    }
    await api.updateAdminOperationPromotionCampaign({
      promo_bid: editingCampaign.item.promo_bid,
      name: payload.name.trim(),
      apply_type: Number(payload.apply_type),
      shifu_bid: payload.shifu_bid.trim(),
      discount_type: Number(payload.discount_type),
      value: payload.value.trim(),
      start_at: payload.start_at,
      end_at: payload.end_at,
      description: payload.description.trim(),
      channel: payload.channel.trim(),
      enabled: payload.enabled === 'true',
    });
    toast({ description: tPromotion('messages.updateSuccess') });
    await fetchCampaigns(campaignPage, campaignFilters);
    setEditingCampaign(null);
  };

  const handleCouponStatusToggle = async (item: AdminPromotionCouponItem) => {
    const enabling = item.computed_status === 'inactive';
    try {
      await api.updateAdminOperationPromotionCouponStatus({
        coupon_bid: item.coupon_bid,
        enabled: enabling,
      });
      toast({
        description: tPromotion(
          enabling ? 'messages.enabledSuccess' : 'messages.disabledSuccess',
        ),
      });
      await fetchCoupons(couponPage, couponFilters);
    } catch (error) {
      toast({
        description: (error as Error).message || t('common.core.submitFailed'),
      });
    }
  };

  const handleCampaignStatusToggle = async (
    item: AdminPromotionCampaignItem,
  ) => {
    const enabling = item.computed_status === 'inactive';
    try {
      await api.updateAdminOperationPromotionCampaignStatus({
        promo_bid: item.promo_bid,
        enabled: enabling,
      });
      toast({
        description: tPromotion(
          enabling ? 'messages.enabledSuccess' : 'messages.disabledSuccess',
        ),
      });
      await fetchCampaigns(campaignPage, campaignFilters);
    } catch (error) {
      toast({
        description: (error as Error).message || t('common.core.submitFailed'),
      });
    }
  };

  const handleStartCouponEdit = useCallback(
    async (item: AdminPromotionCouponItem) => {
      try {
        const detail = (await api.getAdminOperationPromotionCouponDetail({
          coupon_bid: item.coupon_bid,
        })) as {
          coupon?: AdminPromotionCouponItem;
        };
        setEditingCoupon(detail.coupon || item);
      } catch (error) {
        toast({
          description:
            (error as Error).message || t('common.core.submitFailed'),
        });
      }
    },
    [t, toast],
  );

  const handleOpenCampaignRedemptions = useCallback(
    (promoBid: string, campaignName: string) => {
      setSelectedPromoBid(promoBid);
      setSelectedPromoName(campaignName);
      setCampaignRedemptionsOpen(true);
    },
    [],
  );

  const handleStartCampaignEdit = useCallback(
    async (item: AdminPromotionCampaignItem) => {
      try {
        const detail = (await api.getAdminOperationPromotionCampaignDetail({
          promo_bid: item.promo_bid,
        })) as {
          campaign?: AdminPromotionCampaignItem;
          description?: string;
        };
        setEditingCampaign({
          item: detail.campaign || item,
          description: detail.description || '',
        });
      } catch (error) {
        toast({
          description:
            (error as Error).message || t('common.core.submitFailed'),
        });
      }
    },
    [t, toast],
  );

  if (!isReady) {
    return null;
  }

  return (
    <div className='space-y-6 pb-6'>
      <div>
        <h1 className='text-2xl font-semibold text-foreground'>
          {tPromotion('title')}
        </h1>
      </div>

      <Tabs
        value={tab}
        onValueChange={value => setTab(value as PromotionTab)}
      >
        <TabsList className='h-9'>
          <TabsTrigger value='coupons'>
            {tPromotion('tabs.coupons')}
          </TabsTrigger>
          <TabsTrigger value='campaigns'>
            {tPromotion('tabs.campaigns')}
          </TabsTrigger>
        </TabsList>

        <TabsContent
          value='coupons'
          className='mt-6 space-y-6'
        >
          <SectionCard
            title=''
            action={
              <Button
                size='sm'
                variant='outline'
                onClick={() => setCouponCreateOpen(true)}
              >
                <Plus className='mr-1 h-4 w-4' />
                {tPromotion('actions.createCoupon')}
              </Button>
            }
          >
            <div className='space-y-4'>
              <div
                className={cn(
                  'grid gap-4',
                  couponFiltersExpanded
                    ? 'grid-cols-1 xl:grid-cols-3'
                    : 'grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]',
                )}
              >
                <SearchField label={tPromotion('filters.keyword')}>
                  <ClearableInput
                    value={couponFilters.keyword}
                    onChange={value =>
                      setCouponFilters(current => ({
                        ...current,
                        keyword: value,
                      }))
                    }
                    placeholder={tPromotion('filters.keywordPlaceholder')}
                    clearLabel={clearLabel}
                  />
                </SearchField>
                <SearchField label={tPromotion('filters.name')}>
                  <ClearableInput
                    value={couponFilters.name}
                    onChange={value =>
                      setCouponFilters(current => ({ ...current, name: value }))
                    }
                    placeholder={tPromotion('filters.namePlaceholder')}
                    clearLabel={clearLabel}
                  />
                </SearchField>
                <SearchField label={tPromotion('filters.status')}>
                  <Select
                    value={couponFilters.status || ALL_OPTION_VALUE}
                    onValueChange={value =>
                      setCouponFilters(current => ({
                        ...current,
                        status: value === ALL_OPTION_VALUE ? '' : value,
                      }))
                    }
                  >
                    <SelectTrigger className='h-9'>
                      <SelectValue placeholder={tPromotion('filters.status')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem
                        value={ALL_OPTION_VALUE}
                        className={SINGLE_SELECT_ITEM_CLASS}
                      >
                        {t('common.core.all')}
                      </SelectItem>
                      <SelectItem
                        value='not_started'
                        className={SINGLE_SELECT_ITEM_CLASS}
                      >
                        {tPromotion('status.notStarted')}
                      </SelectItem>
                      <SelectItem
                        value='active'
                        className={SINGLE_SELECT_ITEM_CLASS}
                      >
                        {tPromotion('status.active')}
                      </SelectItem>
                      <SelectItem
                        value='expired'
                        className={SINGLE_SELECT_ITEM_CLASS}
                      >
                        {tPromotion('status.expired')}
                      </SelectItem>
                      <SelectItem
                        value='inactive'
                        className={SINGLE_SELECT_ITEM_CLASS}
                      >
                        {tPromotion('status.inactive')}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </SearchField>

                {!couponFiltersExpanded ? (
                  <SearchActions
                    expanded={false}
                    onReset={handleCouponReset}
                    onSearch={handleCouponSearch}
                    onToggle={() => setCouponFiltersExpanded(true)}
                    resetLabel={t('module.order.filters.reset')}
                    searchLabel={t('module.order.filters.search')}
                    expandLabel={t('common.core.expand')}
                    collapseLabel={t('common.core.collapse')}
                  />
                ) : null}
              </div>

              {couponFiltersExpanded ? (
                <div className='space-y-4'>
                  <div className='grid gap-4 xl:grid-cols-3 2xl:grid-cols-5'>
                    <SearchField label={tPromotion('filters.courseId')}>
                      <ClearableInput
                        value={couponFilters.course_query}
                        onChange={value =>
                          setCouponFilters(current => ({
                            ...current,
                            course_query: value,
                          }))
                        }
                        placeholder={tPromotion('filters.courseIdPlaceholder')}
                        clearLabel={clearLabel}
                      />
                    </SearchField>
                    <SearchField label={tPromotion('filters.usageType')}>
                      <Select
                        value={couponFilters.usage_type || ALL_OPTION_VALUE}
                        onValueChange={value =>
                          setCouponFilters(current => ({
                            ...current,
                            usage_type: value === ALL_OPTION_VALUE ? '' : value,
                          }))
                        }
                      >
                        <SelectTrigger className='h-9'>
                          <SelectValue
                            placeholder={tPromotion('filters.usageType')}
                          />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem
                            value={ALL_OPTION_VALUE}
                            className={SINGLE_SELECT_ITEM_CLASS}
                          >
                            {t('common.core.all')}
                          </SelectItem>
                          <SelectItem
                            value='801'
                            className={SINGLE_SELECT_ITEM_CLASS}
                          >
                            {tPromotion('usageType.generic')}
                          </SelectItem>
                          <SelectItem
                            value='802'
                            className={SINGLE_SELECT_ITEM_CLASS}
                          >
                            {tPromotion('usageType.singleUse')}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </SearchField>
                    <SearchField label={tPromotion('filters.discountType')}>
                      <Select
                        value={couponFilters.discount_type || ALL_OPTION_VALUE}
                        onValueChange={value =>
                          setCouponFilters(current => ({
                            ...current,
                            discount_type:
                              value === ALL_OPTION_VALUE ? '' : value,
                          }))
                        }
                      >
                        <SelectTrigger className='h-9'>
                          <SelectValue
                            placeholder={tPromotion('filters.discountType')}
                          />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem
                            value={ALL_OPTION_VALUE}
                            className={SINGLE_SELECT_ITEM_CLASS}
                          >
                            {t('common.core.all')}
                          </SelectItem>
                          <SelectItem
                            value='701'
                            className={SINGLE_SELECT_ITEM_CLASS}
                          >
                            {tPromotion('discountType.fixed')}
                          </SelectItem>
                          <SelectItem
                            value='702'
                            className={SINGLE_SELECT_ITEM_CLASS}
                          >
                            {tPromotion('discountType.percent')}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </SearchField>
                    <SearchField
                      label={tPromotion('filters.activeTime')}
                      contentClassName='max-w-[280px]'
                    >
                      <AdminDateRangeFilter
                        startValue={couponFilters.start_time}
                        endValue={couponFilters.end_time}
                        onChange={range =>
                          setCouponFilters(current => ({
                            ...current,
                            start_time: range.start,
                            end_time: range.end,
                          }))
                        }
                        placeholder={tPromotion('filters.activeTime')}
                        resetLabel={t('module.order.filters.reset')}
                        clearLabel={clearLabel}
                      />
                    </SearchField>
                  </div>

                  <SearchActions
                    expanded
                    onReset={handleCouponReset}
                    onSearch={handleCouponSearch}
                    onToggle={() => setCouponFiltersExpanded(false)}
                    resetLabel={t('module.order.filters.reset')}
                    searchLabel={t('module.order.filters.search')}
                    expandLabel={t('common.core.expand')}
                    collapseLabel={t('common.core.collapse')}
                  />
                </div>
              ) : null}
            </div>
          </SectionCard>
          {couponError ? (
            <ErrorDisplay
              errorMessage={couponError.message}
              errorCode={0}
            />
          ) : null}
          <AdminTableShell
            loading={couponLoading}
            isEmpty={!coupons.length}
            emptyContent={tPromotion('messages.emptyCoupons')}
            emptyColSpan={14}
            withTooltipProvider
            tableWrapperClassName='max-h-[calc(100vh-18rem)] overflow-auto'
            table={emptyRow => (
              <Table containerClassName='overflow-visible max-h-none'>
                <TableHeader>
                  <TableRow>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('name')}
                    >
                      {tPromotion('table.name')}
                      {renderCouponResizeHandle('name')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('status')}
                    >
                      {tPromotion('table.status')}
                      {renderCouponResizeHandle('status')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('usageType')}
                    >
                      {tPromotion('table.usageType')}
                      {renderCouponResizeHandle('usageType')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('discountRule')}
                    >
                      {tPromotion('table.discountRule')}
                      {renderCouponResizeHandle('discountRule')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('code')}
                    >
                      {tPromotion('coupon.code')}
                      {renderCouponResizeHandle('code')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('scope')}
                    >
                      {tPromotion('table.scope')}
                      {renderCouponResizeHandle('scope')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('course')}
                    >
                      {tPromotion('table.course')}
                      {renderCouponResizeHandle('course')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('activeTime')}
                    >
                      {tPromotion('table.activeTime')}
                      {renderCouponResizeHandle('activeTime')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('usageProgress')}
                    >
                      {tPromotion('table.usageProgress')}
                      {renderCouponResizeHandle('usageProgress')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('codesEntry')}
                    >
                      {tPromotion('table.codesEntry')}
                      {renderCouponResizeHandle('codesEntry')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('couponBid')}
                    >
                      {tPromotion('table.couponBid')}
                      {renderCouponResizeHandle('couponBid')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('updatedAt')}
                    >
                      {tPromotion('table.updatedAt')}
                      {renderCouponResizeHandle('updatedAt')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCouponColumnStyle('createdAt')}
                    >
                      {tPromotion('table.createdAt')}
                      {renderCouponResizeHandle('createdAt')}
                    </TableHead>
                    <TableHead
                      className={TABLE_ACTION_HEAD_CLASS}
                      style={getCouponColumnStyle('action')}
                    >
                      {tPromotion('table.actions')}
                      {renderCouponResizeHandle('action')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {coupons.map(item => (
                    <TableRow key={item.coupon_bid}>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('name')}
                      >
                        {renderTooltipText(item.name)}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('status')}
                      >
                        {renderTooltipText(
                          resolvePromotionStatusLabel(
                            tPromotion,
                            item.computed_status_key,
                          ),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('usageType')}
                      >
                        {renderTooltipText(
                          resolveCouponUsageTypeLabel(
                            tPromotion,
                            item.usage_type,
                            item.usage_type_key,
                          ),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('discountRule')}
                      >
                        {renderTooltipText(
                          renderRuleLabel(item.discount_type_key, item.value),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('code')}
                      >
                        {renderTooltipText(item.code)}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('scope')}
                      >
                        {renderTooltipText(
                          resolveCouponScopeLabel(tPromotion, item.scope_type),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('course')}
                      >
                        {renderTooltipText(
                          item.course_name ||
                            item.shifu_bid ||
                            tPromotion('scope.allCourses'),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('activeTime')}
                      >
                        {renderTooltipText(
                          renderTimeRange(item.start_at, item.end_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('usageProgress')}
                      >
                        <button
                          type='button'
                          className='text-primary transition-colors hover:text-primary/80 hover:underline'
                          onClick={() => {
                            setSelectedCouponBid(item.coupon_bid);
                            setSelectedCouponName(item.name || item.coupon_bid);
                            setSelectedCouponShowCourseColumn(
                              item.scope_type === 'all_courses',
                            );
                            setCouponUsageOpen(true);
                          }}
                        >
                          {renderTooltipText(
                            `${item.used_count}/${item.total_count}`,
                          )}
                        </button>
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('codesEntry')}
                      >
                        {Number(item.usage_type) === 802 ? (
                          <button
                            type='button'
                            className='text-primary transition-colors hover:text-primary/80 hover:underline'
                            onClick={() => {
                              setSelectedCouponBid(item.coupon_bid);
                              setSelectedCouponName(
                                item.name || item.coupon_bid,
                              );
                              setCouponCodesOpen(true);
                            }}
                          >
                            {tPromotion('table.codesEntry')}
                          </button>
                        ) : (
                          EMPTY_VALUE
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('couponBid')}
                      >
                        {renderTooltipText(item.coupon_bid)}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCouponColumnStyle('updatedAt')}
                      >
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.updated_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_LAST_CELL_CLASS}
                        style={getCouponColumnStyle('createdAt')}
                      >
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.created_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_ACTION_CELL_CLASS}
                        style={getCouponColumnStyle('action')}
                      >
                        <div className='flex justify-center'>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <button
                                type='button'
                                className='inline-flex h-8 items-center justify-center gap-1 rounded-md px-2 text-sm font-normal text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none'
                              >
                                {t('common.core.more')}
                                <ChevronDown className='h-3.5 w-3.5' />
                              </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align='center'>
                              <DropdownMenuItem
                                onClick={() => void handleStartCouponEdit(item)}
                              >
                                {tPromotion('actions.edit')}
                              </DropdownMenuItem>
                              {Number(item.usage_type) === 802 ? (
                                <DropdownMenuItem
                                  onClick={() =>
                                    void handleCouponCodeExport(item)
                                  }
                                >
                                  {tPromotion('actions.exportCodes')}
                                </DropdownMenuItem>
                              ) : null}
                              {shouldShowCouponStatusToggle(item) ? (
                                <DropdownMenuItem
                                  onClick={() =>
                                    void handleCouponStatusToggle(item)
                                  }
                                >
                                  {item.computed_status === 'inactive'
                                    ? tPromotion('actions.enable')
                                    : tPromotion('actions.disable')}
                                </DropdownMenuItem>
                              ) : null}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            footer={
              <AdminPagination
                pageIndex={couponPage}
                pageCount={couponPageCount}
                onPageChange={page => void fetchCoupons(page, couponFilters)}
                prevLabel={t('module.order.paginationPrev', 'Previous')}
                nextLabel={t('module.order.paginationNext', 'Next')}
                prevAriaLabel={t(
                  'module.order.paginationPrevAriaLabel',
                  'Go to previous page',
                )}
                nextAriaLabel={t(
                  'module.order.paginationNextAriaLabel',
                  'Go to next page',
                )}
                className='mx-0 w-auto justify-end'
                hideWhenSinglePage
              />
            }
            footerClassName='mt-3'
          />
        </TabsContent>

        <TabsContent
          value='campaigns'
          className='mt-6 space-y-6'
        >
          <SectionCard
            title=''
            action={
              <Button
                size='sm'
                variant='outline'
                onClick={() => setCampaignCreateOpen(true)}
              >
                <Plus className='mr-1 h-4 w-4' />
                {tPromotion('actions.createCampaign')}
              </Button>
            }
          >
            <div className='space-y-4'>
              <div
                className={cn(
                  'grid gap-4',
                  campaignFiltersExpanded
                    ? 'grid-cols-1 xl:grid-cols-3'
                    : 'grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]',
                )}
              >
                <SearchField label={tPromotion('filters.campaignName')}>
                  <ClearableInput
                    value={campaignFilters.keyword}
                    onChange={value =>
                      setCampaignFilters(current => ({
                        ...current,
                        keyword: value,
                      }))
                    }
                    placeholder={tPromotion('filters.campaignNamePlaceholder')}
                    clearLabel={clearLabel}
                  />
                </SearchField>
                <SearchField label={tPromotion('filters.courseId')}>
                  <ClearableInput
                    value={campaignFilters.course_query}
                    onChange={value =>
                      setCampaignFilters(current => ({
                        ...current,
                        course_query: value,
                      }))
                    }
                    placeholder={tPromotion('filters.courseIdPlaceholder')}
                    clearLabel={clearLabel}
                  />
                </SearchField>
                <SearchField label={tPromotion('filters.status')}>
                  <Select
                    value={campaignFilters.status || ALL_OPTION_VALUE}
                    onValueChange={value =>
                      setCampaignFilters(current => ({
                        ...current,
                        status: value === ALL_OPTION_VALUE ? '' : value,
                      }))
                    }
                  >
                    <SelectTrigger className='h-9'>
                      <SelectValue placeholder={tPromotion('filters.status')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem
                        value={ALL_OPTION_VALUE}
                        className={SINGLE_SELECT_ITEM_CLASS}
                      >
                        {t('common.core.all')}
                      </SelectItem>
                      <SelectItem
                        value='not_started'
                        className={SINGLE_SELECT_ITEM_CLASS}
                      >
                        {tPromotion('status.notStarted')}
                      </SelectItem>
                      <SelectItem
                        value='active'
                        className={SINGLE_SELECT_ITEM_CLASS}
                      >
                        {tPromotion('status.active')}
                      </SelectItem>
                      <SelectItem
                        value='ended'
                        className={SINGLE_SELECT_ITEM_CLASS}
                      >
                        {tPromotion('status.ended')}
                      </SelectItem>
                      <SelectItem
                        value='inactive'
                        className={SINGLE_SELECT_ITEM_CLASS}
                      >
                        {tPromotion('status.inactive')}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </SearchField>

                {!campaignFiltersExpanded ? (
                  <SearchActions
                    expanded={false}
                    onReset={handleCampaignReset}
                    onSearch={handleCampaignSearch}
                    onToggle={() => setCampaignFiltersExpanded(true)}
                    resetLabel={t('module.order.filters.reset')}
                    searchLabel={t('module.order.filters.search')}
                    expandLabel={t('common.core.expand')}
                    collapseLabel={t('common.core.collapse')}
                  />
                ) : null}
              </div>

              {campaignFiltersExpanded ? (
                <div className='space-y-4'>
                  <div className='grid gap-4 xl:grid-cols-3 2xl:grid-cols-5'>
                    <SearchField label={tPromotion('filters.discountType')}>
                      <Select
                        value={
                          campaignFilters.discount_type || ALL_OPTION_VALUE
                        }
                        onValueChange={value =>
                          setCampaignFilters(current => ({
                            ...current,
                            discount_type:
                              value === ALL_OPTION_VALUE ? '' : value,
                          }))
                        }
                      >
                        <SelectTrigger className='h-9'>
                          <SelectValue
                            placeholder={tPromotion('filters.discountType')}
                          />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem
                            value={ALL_OPTION_VALUE}
                            className={SINGLE_SELECT_ITEM_CLASS}
                          >
                            {t('common.core.all')}
                          </SelectItem>
                          <SelectItem
                            value='701'
                            className={SINGLE_SELECT_ITEM_CLASS}
                          >
                            {tPromotion('discountType.fixed')}
                          </SelectItem>
                          <SelectItem
                            value='702'
                            className={SINGLE_SELECT_ITEM_CLASS}
                          >
                            {tPromotion('discountType.percent')}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </SearchField>
                    <SearchField
                      label={tPromotion('filters.campaignTime')}
                      contentClassName='max-w-[280px]'
                    >
                      <AdminDateRangeFilter
                        startValue={campaignFilters.start_time}
                        endValue={campaignFilters.end_time}
                        onChange={range =>
                          setCampaignFilters(current => ({
                            ...current,
                            start_time: range.start,
                            end_time: range.end,
                          }))
                        }
                        placeholder={tPromotion('filters.campaignTime')}
                        resetLabel={t('module.order.filters.reset')}
                        clearLabel={clearLabel}
                      />
                    </SearchField>
                  </div>

                  <SearchActions
                    expanded
                    onReset={handleCampaignReset}
                    onSearch={handleCampaignSearch}
                    onToggle={() => setCampaignFiltersExpanded(false)}
                    resetLabel={t('module.order.filters.reset')}
                    searchLabel={t('module.order.filters.search')}
                    expandLabel={t('common.core.expand')}
                    collapseLabel={t('common.core.collapse')}
                  />
                </div>
              ) : null}
            </div>
          </SectionCard>
          {campaignError ? (
            <ErrorDisplay
              errorMessage={campaignError.message}
              errorCode={0}
            />
          ) : null}
          <AdminTableShell
            loading={campaignLoading}
            isEmpty={!campaigns.length}
            emptyContent={tPromotion('messages.emptyCampaigns')}
            emptyColSpan={12}
            withTooltipProvider
            tableWrapperClassName='max-h-[calc(100vh-18rem)] overflow-auto'
            table={emptyRow => (
              <Table containerClassName='overflow-visible max-h-none'>
                <TableHeader>
                  <TableRow>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('name')}
                    >
                      {tPromotion('table.campaignName')}
                      {renderCampaignResizeHandle('name')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('status')}
                    >
                      {tPromotion('table.status')}
                      {renderCampaignResizeHandle('status')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('applyType')}
                    >
                      {tPromotion('table.applyType')}
                      {renderCampaignResizeHandle('applyType')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('channel')}
                    >
                      {tPromotion('table.channel')}
                      {renderCampaignResizeHandle('channel')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('course')}
                    >
                      {tPromotion('table.course')}
                      {renderCampaignResizeHandle('course')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('discountRule')}
                    >
                      {tPromotion('table.discountRule')}
                      {renderCampaignResizeHandle('discountRule')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('campaignTime')}
                    >
                      {tPromotion('filters.campaignTime')}
                      {renderCampaignResizeHandle('campaignTime')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('appliedOrderCount')}
                    >
                      {tPromotion('table.appliedOrderCount')}
                      {renderCampaignResizeHandle('appliedOrderCount')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('promoBid')}
                    >
                      {tPromotion('table.promoBid')}
                      {renderCampaignResizeHandle('promoBid')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('updatedAt')}
                    >
                      {tPromotion('table.updatedAt')}
                      {renderCampaignResizeHandle('updatedAt')}
                    </TableHead>
                    <TableHead
                      className={TABLE_HEAD_CLASS}
                      style={getCampaignColumnStyle('createdAt')}
                    >
                      {tPromotion('table.createdAt')}
                      {renderCampaignResizeHandle('createdAt')}
                    </TableHead>
                    <TableHead
                      className={TABLE_ACTION_HEAD_CLASS}
                      style={getCampaignColumnStyle('action')}
                    >
                      {tPromotion('table.actions')}
                      {renderCampaignResizeHandle('action')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {campaigns.map(item => (
                    <TableRow key={item.promo_bid}>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('name')}
                      >
                        {renderTooltipText(item.name)}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('status')}
                      >
                        {renderTooltipText(
                          resolvePromotionStatusLabel(
                            tPromotion,
                            item.computed_status_key,
                          ),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('applyType')}
                      >
                        {renderTooltipText(
                          resolveCampaignApplyTypeLabel(
                            tPromotion,
                            item.apply_type,
                          ),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('channel')}
                      >
                        {renderTooltipText(item.channel)}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('course')}
                      >
                        {renderTooltipText(item.course_name || item.shifu_bid)}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('discountRule')}
                      >
                        {renderTooltipText(
                          renderRuleLabel(item.discount_type_key, item.value),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('campaignTime')}
                      >
                        {renderTooltipText(
                          renderTimeRange(item.start_at, item.end_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('appliedOrderCount')}
                      >
                        <button
                          type='button'
                          className='inline-flex min-w-[2.5rem] items-center justify-center rounded-sm text-sm font-medium text-primary underline-offset-2 transition-colors hover:text-primary/80 hover:underline focus-visible:outline-none'
                          onClick={() =>
                            handleOpenCampaignRedemptions(
                              item.promo_bid,
                              item.name,
                            )
                          }
                          aria-label={`${tPromotion('actions.viewOrders')}: ${item.name || item.promo_bid}`}
                        >
                          {String(item.applied_order_count)}
                        </button>
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('promoBid')}
                      >
                        {renderTooltipText(item.promo_bid)}
                      </TableCell>
                      <TableCell
                        className={TABLE_CELL_CLASS}
                        style={getCampaignColumnStyle('updatedAt')}
                      >
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.updated_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_LAST_CELL_CLASS}
                        style={getCampaignColumnStyle('createdAt')}
                      >
                        {renderTooltipText(
                          formatAdminUtcDateTime(item.created_at),
                        )}
                      </TableCell>
                      <TableCell
                        className={TABLE_ACTION_CELL_CLASS}
                        style={getCampaignColumnStyle('action')}
                      >
                        <div className='flex justify-center'>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <button
                                type='button'
                                className='inline-flex h-8 items-center justify-center gap-1 rounded-md px-2 text-sm font-normal text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none'
                              >
                                {t('common.core.more')}
                                <ChevronDown className='h-3.5 w-3.5' />
                              </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align='center'>
                              <DropdownMenuItem
                                onClick={() =>
                                  void handleStartCampaignEdit(item)
                                }
                              >
                                {tPromotion('actions.edit')}
                              </DropdownMenuItem>
                              {shouldShowCampaignStatusToggle(item) ? (
                                <DropdownMenuItem
                                  onClick={() =>
                                    void handleCampaignStatusToggle(item)
                                  }
                                >
                                  {item.computed_status === 'inactive'
                                    ? tPromotion('actions.enable')
                                    : tPromotion('actions.disable')}
                                </DropdownMenuItem>
                              ) : null}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            footer={
              <AdminPagination
                pageIndex={campaignPage}
                pageCount={campaignPageCount}
                onPageChange={page =>
                  void fetchCampaigns(page, campaignFilters)
                }
                prevLabel={t('module.order.paginationPrev', 'Previous')}
                nextLabel={t('module.order.paginationNext', 'Next')}
                prevAriaLabel={t(
                  'module.order.paginationPrevAriaLabel',
                  'Go to previous page',
                )}
                nextAriaLabel={t(
                  'module.order.paginationNextAriaLabel',
                  'Go to next page',
                )}
                className='mx-0 w-auto justify-end'
                hideWhenSinglePage
              />
            }
            footerClassName='mt-3'
          />
        </TabsContent>
      </Tabs>

      <PromotionCouponDialog
        open={couponCreateOpen}
        onOpenChange={setCouponCreateOpen}
        onSubmit={handleCouponCreate}
      />
      <PromotionCouponDialog
        open={Boolean(editingCoupon)}
        onOpenChange={open => {
          if (!open) {
            setEditingCoupon(null);
          }
        }}
        onSubmit={handleCouponUpdate}
        coupon={editingCoupon}
      />
      <PromotionCampaignDialog
        open={campaignCreateOpen}
        onOpenChange={setCampaignCreateOpen}
        onSubmit={handleCampaignCreate}
      />
      <PromotionCampaignDialog
        open={Boolean(editingCampaign)}
        onOpenChange={open => {
          if (!open) {
            setEditingCampaign(null);
          }
        }}
        onSubmit={handleCampaignUpdate}
        campaign={editingCampaign}
        strategyEditable={
          editingCampaign
            ? canEditCampaignStrategyFields(editingCampaign.item)
            : false
        }
      />
      <PromotionCouponUsageDialog
        open={couponUsageOpen}
        onOpenChange={open => {
          setCouponUsageOpen(open);
          if (!open) {
            setSelectedCouponBid('');
            setSelectedCouponName('');
            setSelectedCouponShowCourseColumn(false);
          }
        }}
        couponBid={selectedCouponBid}
        couponName={selectedCouponName}
        showCourseColumn={selectedCouponShowCourseColumn}
      />
      <PromotionCouponCodesDialog
        open={couponCodesOpen}
        onOpenChange={open => {
          setCouponCodesOpen(open);
          if (!open) {
            setSelectedCouponBid('');
            setSelectedCouponName('');
          }
        }}
        couponBid={selectedCouponBid}
        couponName={selectedCouponName}
      />
      <PromotionCampaignRedemptionsDialog
        open={campaignRedemptionsOpen}
        onOpenChange={open => {
          setCampaignRedemptionsOpen(open);
          if (!open) {
            setSelectedPromoBid('');
            setSelectedPromoName('');
          }
        }}
        promoBid={selectedPromoBid}
        campaignName={selectedPromoName}
      />
    </div>
  );
}
