import React from 'react';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type {
  AdminPromotionCampaignItem,
  AdminPromotionCampaignRedemptionItem,
  AdminPromotionCouponCodeItem,
  AdminPromotionCouponItem,
  AdminPromotionCouponUsageItem,
} from '@/app/admin/operations/operation-promotion-types';
import { Badge } from '@/components/ui/Badge';
import { Label } from '@/components/ui/Label';
import { cn } from '@/lib/utils';

export type PromotionTab = 'coupons' | 'campaigns';

export type CouponFilters = {
  keyword: string;
  name: string;
  course_query: string;
  usage_type: string;
  ops_state: string;
  discount_type: string;
  status: string;
  start_time: string;
  end_time: string;
};

export type CampaignFilters = {
  keyword: string;
  course_query: string;
  apply_type: string;
  channel: string;
  discount_type: string;
  status: string;
  start_time: string;
  end_time: string;
};

export type CouponFormState = {
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

export type CampaignFormState = {
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

export type ErrorState = { message: string } | null;
export type PromotionStatusChangeTarget =
  | {
      entityType: 'coupon';
      enabling: boolean;
      item: AdminPromotionCouponItem;
    }
  | {
      entityType: 'campaign';
      enabling: boolean;
      item: AdminPromotionCampaignItem;
    };

export const PAGE_SIZE = 20;
export const EMPTY_VALUE = '--';
export const ALL_OPTION_VALUE = '__all__';
export const PROMOTION_EXPIRING_SOON_DAYS = 7;
export const COLUMN_MIN_WIDTH = 90;
export const COLUMN_MAX_WIDTH = 420;
export const COUPON_COLUMN_WIDTH_STORAGE_KEY =
  'adminPromotionCouponsColumnWidths';
export const CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY =
  'adminPromotionCampaignsColumnWidths';
export const COUPON_DEFAULT_COLUMN_WIDTHS = {
  name: 200,
  status: 110,
  usageType: 120,
  discountRule: 120,
  code: 180,
  scope: 120,
  course: 240,
  activeTime: 260,
  usageProgress: 110,
  codesEntry: 110,
  couponBid: 220,
  updatedAt: 170,
  createdAt: 170,
  action: 120,
} as const;
export const CAMPAIGN_DEFAULT_COLUMN_WIDTHS = {
  name: 200,
  status: 110,
  applyType: 120,
  channel: 180,
  course: 240,
  discountRule: 120,
  campaignTime: 280,
  appliedOrderCount: 130,
  promoBid: 220,
  updatedAt: 170,
  createdAt: 170,
  action: 120,
} as const;
export const PROMOTION_CODE_DIALOG_COLUMN_COUNT = 4;
export const PROMOTION_REDEMPTION_DIALOG_COLUMN_COUNT = 4;
export const PROMOTION_USAGE_DIALOG_COLUMN_COUNT = {
  default: 4,
  withCourse: 5,
} as const;
export const SINGLE_SELECT_ITEM_CLASS =
  'pl-3 data-[state=checked]:bg-muted data-[state=checked]:text-foreground [&>span:first-child]:hidden';
export const TABLE_HEAD_CLASS = ADMIN_TABLE_HEADER_CELL_CENTER_CLASS;
export const TABLE_ACTION_HEAD_CLASS =
  getAdminStickyRightHeaderClass('text-center');
export const TABLE_CELL_CLASS =
  'border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center';
export const TABLE_LAST_CELL_CLASS =
  'whitespace-nowrap overflow-hidden text-ellipsis text-center';
export const TABLE_ACTION_CELL_CLASS = getAdminStickyRightCellClass(
  'whitespace-nowrap text-center',
);
export type CouponColumnKey = keyof typeof COUPON_DEFAULT_COLUMN_WIDTHS;
export type CampaignColumnKey = keyof typeof CAMPAIGN_DEFAULT_COLUMN_WIDTHS;

export const createDefaultCouponFilters = (): CouponFilters => ({
  keyword: '',
  name: '',
  course_query: '',
  usage_type: '',
  ops_state: '',
  discount_type: '',
  status: '',
  start_time: '',
  end_time: '',
});

export const createDefaultCampaignFilters = (): CampaignFilters => ({
  keyword: '',
  course_query: '',
  apply_type: '',
  channel: '',
  discount_type: '',
  status: '',
  start_time: '',
  end_time: '',
});

export const createDefaultCouponForm = (): CouponFormState => ({
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

export const resolvePromotionEnabledFormValue = (item: {
  computed_status?: string;
  enabled?: boolean;
}) => {
  if (typeof item.enabled === 'boolean') {
    return String(item.enabled);
  }
  return item.computed_status === 'inactive' ? 'false' : 'true';
};

export function normalizePromotionFormDateTimeValue(value?: string) {
  const formatted = formatAdminUtcDateTime(value || '');
  return formatted || value || '';
}

export const createCouponFormFromItem = (
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
  enabled: resolvePromotionEnabledFormValue(item),
});

export const createDefaultCampaignForm = (): CampaignFormState => ({
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

export const createCampaignFormFromItem = (
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
  enabled: resolvePromotionEnabledFormValue(item),
});

export const SectionCard = ({
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

export const renderTimeRange = (startAt?: string, endAt?: string) => {
  const start = formatAdminUtcDateTime(startAt || '');
  const end = formatAdminUtcDateTime(endAt || '');
  if (!start && !end) return EMPTY_VALUE;
  return `${start || EMPTY_VALUE} ~ ${end || EMPTY_VALUE}`;
};

export const downloadExcelCompatibleCodesFile = (
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

export const renderRuleLabel = (
  discountTypeKey: string,
  value: string,
  currencySymbol = '',
) => {
  if (discountTypeKey.endsWith('percent')) {
    return `${value}%`;
  }
  return `- ${currencySymbol}${value}`;
};

export const toPromotionRelativeKey = (key?: string) => {
  if (!key) {
    return '';
  }
  return key.startsWith('module.operationsPromotion.')
    ? key.replace('module.operationsPromotion.', '')
    : key;
};

export const resolveCouponUsageTypeLabel = (
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

export const resolveCouponScopeLabel = (
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

export const PROMOTION_STATUS_FALLBACK_KEYS: Record<string, string> = {
  active: 'status.active',
  ended: 'status.ended',
  expired: 'status.expired',
  inactive: 'status.inactive',
  not_started: 'status.notStarted',
  upcoming: 'status.notStarted',
};

export const resolvePromotionStatusLabel = (
  tPromotion: (key: string) => string,
  statusKey?: string,
  status?: string,
) => {
  const fallbackKey = status ? PROMOTION_STATUS_FALLBACK_KEYS[status] : '';
  const translationKey = statusKey
    ? toPromotionRelativeKey(statusKey)
    : fallbackKey;
  if (!translationKey) {
    return EMPTY_VALUE;
  }
  const translated = tPromotion(translationKey);
  return translated && translated !== translationKey ? translated : EMPTY_VALUE;
};

export const resolvePromotionStatusBadgeClassName = (status?: string) => {
  switch (status) {
    case 'active':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-50';
    case 'not_started':
      return 'border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-50';
    case 'inactive':
      return 'border-slate-200 bg-slate-100 text-slate-700 hover:bg-slate-100';
    case 'expired':
    case 'ended':
      return 'border-orange-200 bg-orange-50 text-orange-700 hover:bg-orange-50';
    default:
      return 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-50';
  }
};

export const renderPromotionStatusBadge = ({
  tPromotion,
  statusKey,
  status,
}: {
  tPromotion: (key: string) => string;
  statusKey?: string;
  status?: string;
}) => (
  <Badge
    variant='outline'
    className={cn(
      'rounded-full px-2 py-0.5 text-xs font-medium',
      resolvePromotionStatusBadgeClassName(status),
    )}
  >
    {resolvePromotionStatusLabel(tPromotion, statusKey, status)}
  </Badge>
);

export const resolveCampaignApplyTypeLabel = (
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

export const canEditCampaignStrategyFields = (
  item: AdminPromotionCampaignItem,
) => {
  const startAt = parseLocalDateTimeInput(item.start_at || '');
  if (!startAt) {
    return false;
  }
  return startAt.getTime() > Date.now() && !item.has_redemptions;
};

export const canEnableCouponItem = (item: AdminPromotionCouponItem) => {
  const endAt = parseDateValue(item.end_at || '');
  if (endAt && endAt.getTime() < Date.now()) {
    return false;
  }
  return Number(item.used_count || 0) < Number(item.total_count || 0);
};

export const canEnableCampaignItem = (item: AdminPromotionCampaignItem) => {
  const endAt = parseDateValue(item.end_at || '');
  return !endAt || endAt.getTime() >= Date.now();
};

export const shouldShowCouponStatusToggle = (item: AdminPromotionCouponItem) =>
  item.computed_status !== 'inactive' || canEnableCouponItem(item);

export const shouldShowCampaignStatusToggle = (
  item: AdminPromotionCampaignItem,
) => item.computed_status !== 'inactive' || canEnableCampaignItem(item);

export const renderUserLabel = (
  item:
    | AdminPromotionCouponUsageItem
    | AdminPromotionCouponCodeItem
    | AdminPromotionCampaignRedemptionItem,
) => {
  return item.user_mobile || item.user_email || item.user_bid || EMPTY_VALUE;
};

export const parseLocalDateTimeInput = (value: string) => {
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

export const formatDateValue = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

export const formatTimeValue = (date: Date) => {
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${hours}:${minutes}`;
};

export const parseDateValue = (value: string) => {
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

export const isPromotionExpiringSoon = (endAt?: string) => {
  const endDate = parseDateValue(endAt || '');
  if (!endDate) {
    return false;
  }
  const now = new Date();
  const diff = endDate.getTime() - now.getTime();
  return (
    diff >= 0 && diff <= PROMOTION_EXPIRING_SOON_DAYS * 24 * 60 * 60 * 1000
  );
};

export const isCouponUsedUp = (item: AdminPromotionCouponItem) =>
  Number(item.used_count || 0) >= Number(item.total_count || 0);

export const renderCouponAttentionBadges = (
  item: AdminPromotionCouponItem,
  tPromotion: (key: string) => string,
) => {
  if (item.computed_status !== 'active') {
    return [];
  }

  if (isCouponUsedUp(item)) {
    return [
      <Badge
        key='used-up'
        variant='outline'
        className='rounded-full border-rose-200 bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700 hover:bg-rose-50'
      >
        {tPromotion('opsState.usedUp')}
      </Badge>,
    ];
  }

  if (isPromotionExpiringSoon(item.end_at)) {
    return [
      <Badge
        key='expiring-soon'
        variant='outline'
        className='rounded-full border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 hover:bg-amber-50'
      >
        {tPromotion('opsState.expiringSoon')}
      </Badge>,
    ];
  }

  return [];
};

export const DEFAULT_START_TIME = '00:00';
export const DEFAULT_END_TIME = '23:59';

export const resolveDateTimeParts = (
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

export const combineDateAndTime = (dateValue: string, timeValue: string) => {
  const normalizedDate = String(dateValue || '').trim();
  if (!normalizedDate) {
    return '';
  }
  const normalizedTime = String(timeValue || '').trim() || DEFAULT_START_TIME;
  return `${normalizedDate} ${normalizedTime}:00`;
};

export const isPositiveIntegerString = (value: string) =>
  /^\d+$/.test(value.trim());

export const renderTooltipText = (text?: string, className?: string) => (
  <AdminTooltipText
    text={text}
    emptyValue={EMPTY_VALUE}
    className={className}
  />
);

export const FormField = ({
  label,
  children,
}: React.PropsWithChildren<{ label: string }>) => (
  <div className='space-y-2'>
    <Label className='text-sm font-medium text-foreground'>{label}</Label>
    {children}
  </div>
);
