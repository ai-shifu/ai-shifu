'use client';

import React from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Info, RefreshCw, RotateCcw, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { Switch } from '@/components/ui/Switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { toast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import { cn } from '@/lib/utils';
import useOperatorGuard from '../useOperatorGuard';
import type {
  AdminOperationCreditNotificationPolicy,
  AdminOperationCreditNotificationDryRunResponse,
  AdminOperationCreditNotificationItem,
  AdminOperationCreditNotificationListResponse,
  AdminOperationCreditNotificationRequeueResponse,
  AdminOperationCreditNotificationTemplateSyncResponse,
  CreditNotificationEstimatedDaysThreshold,
  CreditNotificationFixedThreshold,
  CreditNotificationThreshold,
} from '../operation-credit-notification-types';

type NotificationFilters = {
  creator_bid: string;
  mobile: string;
  notification_type: string;
  status: string;
  source_bid: string;
};

type ErrorState = { message: string; code?: number };
type PageTab = 'records' | 'config';

const PAGE_SIZE = 20;
const EMPTY_LABEL = '--';
const ALL_OPTION_VALUE = '__all__';
const DEFAULT_TAB: PageTab = 'records';
const NOTIFICATION_TYPES = [
  'credit_expiring',
  'credit_granted',
  'low_balance',
] as const;
const NOTIFICATION_STATUSES = [
  'pending',
  'sent',
  'skipped_no_mobile',
  'skipped_opt_out',
  'suppressed_duplicate',
  'failed_provider',
] as const;
type KnownNotificationType = (typeof NOTIFICATION_TYPES)[number];
type TemplatePlaceholderKey =
  | 'available_credits'
  | 'avg_daily_consumption'
  | 'credits'
  | 'estimated_remaining_days'
  | 'expires_at'
  | 'lookback_days'
  | 'source'
  | 'threshold'
  | 'threshold_kind'
  | 'trigger_days'
  | 'window';
type PlaceholderGuideGroup = {
  id: string;
  titleKey: string;
  descriptionKey?: string;
  placeholders: TemplatePlaceholderKey[];
};

const CREDIT_GRANTED_PLACEHOLDERS: TemplatePlaceholderKey[] = [
  'credits',
  'source',
  'expires_at',
];
const CREDIT_EXPIRING_PLACEHOLDERS: TemplatePlaceholderKey[] = [
  'credits',
  'expires_at',
  'window',
];
const LOW_BALANCE_FIXED_PLACEHOLDERS: TemplatePlaceholderKey[] = [
  'available_credits',
  'threshold',
  'threshold_kind',
];
const LOW_BALANCE_ESTIMATED_PLACEHOLDERS: TemplatePlaceholderKey[] = [
  'available_credits',
  'threshold_kind',
  'trigger_days',
  'lookback_days',
  'avg_daily_consumption',
  'estimated_remaining_days',
];
const DEFAULT_ESTIMATED_DAYS_THRESHOLD: CreditNotificationEstimatedDaysThreshold =
  {
    kind: 'estimated_days',
    days: 7,
    lookback_days: 7,
    min_consumed_days: 2,
    fallback_fixed_value: '0',
  };
const COLUMN_MIN_WIDTH = 90;
const COLUMN_MAX_WIDTH = 460;
const COLUMN_WIDTH_STORAGE_KEY = 'adminCreditNotificationColumnWidths';
const DEFAULT_COLUMN_WIDTHS = {
  notification: 240,
  creator: 180,
  source: 220,
  template: 300,
  error: 220,
  createdAt: 180,
  action: 120,
} as const;
type ColumnKey = keyof typeof DEFAULT_COLUMN_WIDTHS;
const TABLE_CELL_CLASS =
  'border-r border-border px-3 py-2 align-middle last:border-r-0';
const TABLE_TEXT_CELL_CLASS =
  'overflow-hidden whitespace-nowrap border-r border-border px-3 py-2 text-center text-ellipsis last:border-r-0';
const SEARCH_LABEL_CLASS =
  "mr-2 shrink-0 whitespace-nowrap text-right text-sm font-medium text-foreground after:ml-0.5 after:content-[':']";
const CREDIT_NOTIFICATION_TABS_LIST_CLASSNAME =
  'h-11 w-fit justify-start self-start rounded-[12px] bg-[var(--base-muted,#F5F5F5)] p-[3px] shadow-sm';
const CREDIT_NOTIFICATION_TABS_TRIGGER_CLASSNAME =
  'h-full rounded-[10px] border border-transparent px-5 py-2 text-sm font-medium text-[var(--base-foreground,#0A0A0A)] data-[state=active]:bg-white data-[state=active]:shadow-[0_1px_3px_rgba(0,0,0,0.1),0_1px_2px_rgba(0,0,0,0.06)]';

const createDefaultFilters = (): NotificationFilters => ({
  creator_bid: '',
  mobile: '',
  notification_type: '',
  status: '',
  source_bid: '',
});

const createDefaultPolicy = (): AdminOperationCreditNotificationPolicy => ({
  enabled: false,
  channel: 'sms',
  types: {
    credit_expiring: {
      enabled: false,
      template_code: '',
      windows: ['7d', '3d', '1d', '0d'],
      merge_same_creator: true,
    },
    credit_granted: {
      enabled: false,
      template_code: '',
    },
    low_balance: {
      enabled: false,
      template_code: '',
      thresholds: [{ kind: 'fixed', value: '0' }],
    },
  },
  softlimit: {
    enabled: false,
    threshold: { kind: 'fixed', value: '0' },
    teacher_page_alert: true,
    disable_debug: true,
    sms_enabled: false,
  },
  frequency: {
    per_mobile_per_day: 3,
    per_creator_per_type_per_day: 1,
  },
  quiet_hours: {
    enabled: false,
    start: '22:00',
    end: '09:00',
    timezone: 'Asia/Shanghai',
  },
  blacklist: {
    creator_bids: [],
    mobiles: [],
  },
  opt_out: {
    creator_bids: [],
    mobiles: [],
  },
  budget: {
    daily_sms_limit: 0,
    dry_run_required: true,
    sms_unit_cost: '0',
  },
});

const clonePolicy = (
  policy: AdminOperationCreditNotificationPolicy,
): AdminOperationCreditNotificationPolicy =>
  JSON.parse(JSON.stringify(policy)) as AdminOperationCreditNotificationPolicy;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const readRecord = (
  source: Record<string, unknown>,
  key: string,
): Record<string, unknown> => {
  const value = source[key];
  return isRecord(value) ? value : {};
};

const readStringArray = (value: unknown, fallback: string[]): string[] =>
  Array.isArray(value)
    ? value.map(item => String(item ?? '').trim()).filter(Boolean)
    : fallback;

const readBoolean = (value: unknown, fallback: boolean): boolean => {
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    return value !== 0;
  }
  if (typeof value === 'string') {
    return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
  }
  return fallback;
};

const readNumber = (value: unknown, fallback: number): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
};

const readPositiveNumber = (value: unknown, fallback: number): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback;
};

const readString = (value: unknown, fallback = ''): string => {
  const normalized = String(value ?? '').trim();
  return normalized || fallback;
};

const readThresholdValue = (
  value: unknown,
  fallback: string,
): { kind: 'fixed'; value: string } => {
  if (isRecord(value)) {
    return { kind: 'fixed', value: readString(value.value, fallback) };
  }
  return { kind: 'fixed', value: fallback };
};

const readLowBalanceThreshold = (
  value: unknown,
): CreditNotificationThreshold | null => {
  if (!isRecord(value)) {
    return null;
  }
  const kind = readString(value.kind, 'fixed');
  if (kind === 'estimated_days') {
    const fallbackFixedValue =
      value.fallback_fixed_value === undefined ||
      value.fallback_fixed_value === null
        ? undefined
        : String(value.fallback_fixed_value).trim();
    return {
      kind: 'estimated_days',
      days: readPositiveNumber(
        value.days,
        DEFAULT_ESTIMATED_DAYS_THRESHOLD.days,
      ),
      lookback_days: readPositiveNumber(
        value.lookback_days,
        DEFAULT_ESTIMATED_DAYS_THRESHOLD.lookback_days,
      ),
      min_consumed_days: readPositiveNumber(
        value.min_consumed_days,
        DEFAULT_ESTIMATED_DAYS_THRESHOLD.min_consumed_days,
      ),
      ...(fallbackFixedValue !== undefined
        ? { fallback_fixed_value: fallbackFixedValue }
        : {}),
    };
  }
  return readThresholdValue(value, '0');
};

const isFixedThreshold = (
  threshold: CreditNotificationThreshold,
): threshold is CreditNotificationFixedThreshold => threshold.kind === 'fixed';

const isEstimatedDaysThreshold = (
  threshold: CreditNotificationThreshold,
): threshold is CreditNotificationEstimatedDaysThreshold =>
  threshold.kind === 'estimated_days';

const normalizePolicy = (
  payload: unknown,
): AdminOperationCreditNotificationPolicy => {
  const defaults = createDefaultPolicy();
  const source = isRecord(payload) ? payload : {};
  const types = readRecord(source, 'types');
  const expiring = readRecord(types, 'credit_expiring');
  const granted = readRecord(types, 'credit_granted');
  const lowBalance = readRecord(types, 'low_balance');
  const lowBalanceThresholds = Array.isArray(lowBalance.thresholds)
    ? lowBalance.thresholds
    : defaults.types.low_balance.thresholds || [];
  const softlimit = readRecord(source, 'softlimit');
  const frequency = readRecord(source, 'frequency');
  const quietHours = readRecord(source, 'quiet_hours');
  const blacklist = readRecord(source, 'blacklist');
  const optOut = readRecord(source, 'opt_out');
  const budget = readRecord(source, 'budget');

  return {
    ...defaults,
    enabled: readBoolean(source.enabled, defaults.enabled),
    channel: 'sms',
    types: {
      credit_expiring: {
        enabled: readBoolean(
          expiring.enabled,
          defaults.types.credit_expiring.enabled,
        ),
        template_code: readString(expiring.template_code),
        windows: readStringArray(
          expiring.windows,
          defaults.types.credit_expiring.windows || [],
        ),
        merge_same_creator: readBoolean(
          expiring.merge_same_creator,
          defaults.types.credit_expiring.merge_same_creator || false,
        ),
      },
      credit_granted: {
        enabled: readBoolean(
          granted.enabled,
          defaults.types.credit_granted.enabled,
        ),
        template_code: readString(granted.template_code),
      },
      low_balance: {
        enabled: readBoolean(
          lowBalance.enabled,
          defaults.types.low_balance.enabled,
        ),
        template_code: readString(lowBalance.template_code),
        thresholds: lowBalanceThresholds
          .map(readLowBalanceThreshold)
          .filter((item): item is CreditNotificationThreshold => item !== null),
      },
    },
    softlimit: {
      enabled: readBoolean(softlimit.enabled, defaults.softlimit.enabled),
      threshold: readThresholdValue(
        softlimit.threshold,
        defaults.softlimit.threshold.value,
      ),
      teacher_page_alert: readBoolean(
        softlimit.teacher_page_alert,
        defaults.softlimit.teacher_page_alert,
      ),
      disable_debug: readBoolean(
        softlimit.disable_debug,
        defaults.softlimit.disable_debug,
      ),
      sms_enabled: readBoolean(
        softlimit.sms_enabled,
        defaults.softlimit.sms_enabled,
      ),
    },
    frequency: {
      per_mobile_per_day: readNumber(
        frequency.per_mobile_per_day,
        defaults.frequency.per_mobile_per_day,
      ),
      per_creator_per_type_per_day: readNumber(
        frequency.per_creator_per_type_per_day,
        defaults.frequency.per_creator_per_type_per_day,
      ),
    },
    quiet_hours: {
      enabled: readBoolean(quietHours.enabled, defaults.quiet_hours.enabled),
      start: readString(quietHours.start, defaults.quiet_hours.start),
      end: readString(quietHours.end, defaults.quiet_hours.end),
      timezone: readString(quietHours.timezone, defaults.quiet_hours.timezone),
    },
    blacklist: {
      creator_bids: readStringArray(blacklist.creator_bids, []),
      mobiles: readStringArray(blacklist.mobiles, []),
    },
    opt_out: {
      creator_bids: readStringArray(optOut.creator_bids, []),
      mobiles: readStringArray(optOut.mobiles, []),
    },
    budget: {
      daily_sms_limit: readNumber(
        budget.daily_sms_limit,
        defaults.budget.daily_sms_limit,
      ),
      dry_run_required: readBoolean(
        budget.dry_run_required,
        defaults.budget.dry_run_required,
      ),
      sms_unit_cost: readString(
        budget.sms_unit_cost,
        defaults.budget.sms_unit_cost,
      ),
    },
  };
};

const parseListInput = (value: string): string[] =>
  value
    .split(/[,\n]/)
    .map(item => item.trim())
    .filter(Boolean);

const formatListInput = (value: string[]): string => value.join(', ');

const parseThresholdInput = (
  value: string,
): CreditNotificationFixedThreshold[] =>
  parseListInput(value).map(item => ({ kind: 'fixed' as const, value: item }));

const setEstimatedDaysThreshold = (
  policy: AdminOperationCreditNotificationPolicy,
  patch: Partial<CreditNotificationEstimatedDaysThreshold>,
) => {
  const thresholds = policy.types.low_balance.thresholds || [];
  const fixedThresholds = thresholds.filter(isFixedThreshold);
  const current =
    thresholds.find(isEstimatedDaysThreshold) ||
    DEFAULT_ESTIMATED_DAYS_THRESHOLD;
  policy.types.low_balance.thresholds = [
    ...fixedThresholds,
    {
      ...current,
      ...patch,
      kind: 'estimated_days',
    },
  ];
};

const removeEstimatedDaysThreshold = (
  policy: AdminOperationCreditNotificationPolicy,
) => {
  const fixedThresholds = (policy.types.low_balance.thresholds || []).filter(
    isFixedThreshold,
  );
  policy.types.low_balance.thresholds = fixedThresholds.length
    ? fixedThresholds
    : [{ kind: 'fixed', value: '0' }];
};

const formatValue = (value?: string | null) => {
  const normalized = String(value || '').trim();
  return normalized || EMPTY_LABEL;
};

const formatTemplateParams = (value: Record<string, unknown>): string => {
  const entries = Object.entries(value || {})
    .filter(([key]) => key.trim())
    .sort(([left], [right]) => left.localeCompare(right));
  if (!entries.length) {
    return EMPTY_LABEL;
  }
  return JSON.stringify(Object.fromEntries(entries));
};

const formatPlaceholderToken = (placeholder: string): string =>
  ['${', placeholder, '}'].join('');

const formatPlaceholderList = (items?: string[]): string => {
  const normalized = (items || [])
    .map(item => String(item || '').trim())
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right));
  return normalized.length
    ? normalized.map(formatPlaceholderToken).join(', ')
    : EMPTY_LABEL;
};

const buildPlaceholderGuideGroups = ({
  type,
  hasFixedLowBalancePath,
  hasEstimatedLowBalance,
}: {
  type: KnownNotificationType;
  hasFixedLowBalancePath: boolean;
  hasEstimatedLowBalance: boolean;
}): PlaceholderGuideGroup[] => {
  if (type === 'credit_granted') {
    return [
      {
        id: 'credit_granted',
        titleKey:
          'module.operationsCreditNotifications.config.placeholders.groups.creditGranted',
        descriptionKey:
          'module.operationsCreditNotifications.config.placeholders.notes.expiresAtOptional',
        placeholders: CREDIT_GRANTED_PLACEHOLDERS,
      },
    ];
  }
  if (type === 'credit_expiring') {
    return [
      {
        id: 'credit_expiring',
        titleKey:
          'module.operationsCreditNotifications.config.placeholders.groups.creditExpiring',
        descriptionKey:
          'module.operationsCreditNotifications.config.placeholders.notes.windowSource',
        placeholders: CREDIT_EXPIRING_PLACEHOLDERS,
      },
    ];
  }

  const groups: PlaceholderGuideGroup[] = [];
  if (hasFixedLowBalancePath) {
    groups.push({
      id: 'low_balance_fixed',
      titleKey:
        'module.operationsCreditNotifications.config.placeholders.groups.lowBalanceFixed',
      descriptionKey:
        'module.operationsCreditNotifications.config.placeholders.notes.fixedLowBalance',
      placeholders: LOW_BALANCE_FIXED_PLACEHOLDERS,
    });
  }
  if (hasEstimatedLowBalance) {
    groups.push({
      id: 'low_balance_estimated',
      titleKey:
        'module.operationsCreditNotifications.config.placeholders.groups.lowBalanceEstimated',
      descriptionKey:
        'module.operationsCreditNotifications.config.placeholders.notes.estimatedLowBalance',
      placeholders: LOW_BALANCE_ESTIMATED_PLACEHOLDERS,
    });
  }
  return groups;
};

const normalizeTab = (value?: string | null): PageTab =>
  value === 'config' ? 'config' : DEFAULT_TAB;

type SearchFieldProps = {
  label: React.ReactNode;
  children: React.ReactNode;
  className?: string;
};

const SearchField = ({ label, children, className }: SearchFieldProps) => (
  <div className={cn('flex items-center', className)}>
    <span className={cn(SEARCH_LABEL_CLASS, 'w-24')}>{label}</span>
    <div className='min-w-0 flex-1'>{children}</div>
  </div>
);

type FormFieldProps = {
  label: React.ReactNode;
  htmlFor?: string;
  children: React.ReactNode;
};

const FormField = ({ label, htmlFor, children }: FormFieldProps) => (
  <div>
    <Label
      htmlFor={htmlFor}
      className='text-xs font-medium text-muted-foreground'
    >
      {label}
    </Label>
    <div className='mt-1'>{children}</div>
  </div>
);

type ConfigSectionProps = {
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
};

const ConfigSection = ({
  title,
  description,
  children,
}: ConfigSectionProps) => (
  <section className='rounded-xl border border-border bg-white p-4 shadow-sm'>
    <div>
      <h2 className='text-sm font-semibold text-foreground'>{title}</h2>
      {description ? (
        <p className='mt-1 text-xs text-muted-foreground'>{description}</p>
      ) : null}
    </div>
    <div className='mt-4 space-y-4'>{children}</div>
  </section>
);

export default function AdminOperationCreditNotificationsPage() {
  const { t } = useTranslation();
  const { isReady } = useOperatorGuard();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTabFromUrl = React.useMemo(
    () => normalizeTab(searchParams.get('tab')),
    [searchParams],
  );
  const [activeTab, setActiveTab] = React.useState<PageTab>(activeTabFromUrl);
  const [items, setItems] = React.useState<
    AdminOperationCreditNotificationItem[]
  >([]);
  const [draftFilters, setDraftFilters] =
    React.useState<NotificationFilters>(createDefaultFilters);
  const [appliedFilters, setAppliedFilters] =
    React.useState<NotificationFilters>(createDefaultFilters);
  const [pageIndex, setPageIndex] = React.useState(1);
  const [pageCount, setPageCount] = React.useState(0);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<ErrorState | null>(null);
  const [policy, setPolicy] =
    React.useState<AdminOperationCreditNotificationPolicy>(createDefaultPolicy);
  const [configError, setConfigError] = React.useState('');
  const [configLoaded, setConfigLoaded] = React.useState(false);
  const [dryRunResult, setDryRunResult] =
    React.useState<AdminOperationCreditNotificationDryRunResponse | null>(null);
  const [templateSyncResults, setTemplateSyncResults] = React.useState<
    Partial<
      Record<
        KnownNotificationType,
        AdminOperationCreditNotificationTemplateSyncResponse
      >
    >
  >({});
  const [templateSyncLoading, setTemplateSyncLoading] = React.useState<
    Partial<Record<KnownNotificationType, boolean>>
  >({});
  const requestIdRef = React.useRef(0);
  const lowBalanceThresholds = policy.types.low_balance.thresholds || [];
  const fixedLowBalanceThresholds =
    lowBalanceThresholds.filter(isFixedThreshold);
  const estimatedDaysThreshold =
    lowBalanceThresholds.find(isEstimatedDaysThreshold) || null;
  const { getColumnStyle, getResizeHandleProps } =
    useAdminResizableColumns<ColumnKey>({
      storageKey: COLUMN_WIDTH_STORAGE_KEY,
      defaultWidths: DEFAULT_COLUMN_WIDTHS,
      minWidth: COLUMN_MIN_WIDTH,
      maxWidth: COLUMN_MAX_WIDTH,
    });

  React.useEffect(() => {
    setActiveTab(activeTabFromUrl);
  }, [activeTabFromUrl]);

  const updateTab = React.useCallback(
    (nextTab: PageTab) => {
      setActiveTab(nextTab);
      const nextParams = new URLSearchParams(searchParams.toString());
      if (nextTab === DEFAULT_TAB) {
        nextParams.delete('tab');
      } else {
        nextParams.set('tab', nextTab);
      }
      const nextQuery = nextParams.toString();
      router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, {
        scroll: false,
      });
    },
    [pathname, router, searchParams],
  );

  const resolveTypeLabel = React.useCallback(
    (value: string) =>
      t(
        `module.operationsCreditNotifications.type.${value}`,
        value || EMPTY_LABEL,
      ),
    [t],
  );

  const resolveStatusLabel = React.useCallback(
    (value: string) =>
      t(
        `module.operationsCreditNotifications.status.${value}`,
        value || EMPTY_LABEL,
      ),
    [t],
  );

  const renderTooltipText = React.useCallback(
    (text?: string | null, className?: string) => (
      <AdminTooltipText
        text={text}
        emptyValue={EMPTY_LABEL}
        className={className}
      />
    ),
    [],
  );

  const renderResizeHandle = React.useCallback(
    (key: ColumnKey) => (
      <span
        className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
        {...getResizeHandleProps(key)}
      />
    ),
    [getResizeHandleProps],
  );

  const updatePolicy = React.useCallback(
    (updater: (draft: AdminOperationCreditNotificationPolicy) => void) => {
      setPolicy(currentPolicy => {
        const nextPolicy = clonePolicy(currentPolicy);
        updater(nextPolicy);
        return nextPolicy;
      });
    },
    [],
  );

  const fetchConfig = React.useCallback(async () => {
    const response = await api.getAdminOperationCreditNotificationConfig({});
    setPolicy(normalizePolicy(response));
    setConfigLoaded(true);
    setConfigError('');
  }, []);

  const fetchRecords = React.useCallback(
    async (targetPage: number, nextFilters: NotificationFilters) => {
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      setLoading(true);
      setError(null);
      try {
        const response = (await api.getAdminOperationCreditNotifications({
          page_index: targetPage,
          page_size: PAGE_SIZE,
          creator_bid: nextFilters.creator_bid.trim(),
          mobile: nextFilters.mobile.trim(),
          notification_type: nextFilters.notification_type.trim(),
          status: nextFilters.status.trim(),
          source_bid: nextFilters.source_bid.trim(),
        })) as AdminOperationCreditNotificationListResponse;
        if (requestId !== requestIdRef.current) {
          return;
        }
        setItems(response.items || []);
        setPageIndex(response.page || targetPage);
        setPageCount(response.page_count || 0);
        setTotal(response.total || 0);
      } catch (requestError) {
        if (requestId !== requestIdRef.current) {
          return;
        }
        const resolvedError = requestError as ErrorWithCode;
        setError({
          message:
            resolvedError.message ||
            t('module.operationsCreditNotifications.loadError'),
          code: resolvedError.code,
        });
        setItems([]);
        setPageCount(0);
        setTotal(0);
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [t],
  );

  React.useEffect(() => {
    if (!isReady) {
      return;
    }
    const initialFilters = createDefaultFilters();
    fetchConfig().catch(requestError => {
      const resolvedError = requestError as ErrorWithCode;
      setConfigLoaded(false);
      setConfigError(
        resolvedError.message ||
          t('module.operationsCreditNotifications.config.loadFailed'),
      );
    });
    void fetchRecords(1, initialFilters);
  }, [fetchConfig, fetchRecords, isReady, t]);

  const updateDraftFilter = React.useCallback(
    (field: keyof NotificationFilters, value: string) => {
      setDraftFilters(current => ({
        ...current,
        [field]: value,
      }));
    },
    [],
  );

  const searchRecords = React.useCallback(() => {
    const nextFilters = { ...draftFilters };
    setAppliedFilters(nextFilters);
    setPageIndex(1);
    void fetchRecords(1, nextFilters);
  }, [draftFilters, fetchRecords]);

  const resetRecords = React.useCallback(() => {
    const nextFilters = createDefaultFilters();
    setDraftFilters(nextFilters);
    setAppliedFilters(nextFilters);
    setPageIndex(1);
    void fetchRecords(1, nextFilters);
  }, [fetchRecords]);

  const saveConfig = React.useCallback(async () => {
    if (!configLoaded) {
      setConfigError(
        t('module.operationsCreditNotifications.config.loadRequired'),
      );
      return;
    }
    try {
      const response =
        await api.updateAdminOperationCreditNotificationConfig(policy);
      setPolicy(normalizePolicy(response));
      setConfigLoaded(true);
      setConfigError('');
      toast({
        title: t('module.operationsCreditNotifications.config.saved'),
      });
    } catch (requestError) {
      const resolvedError = requestError as ErrorWithCode;
      setConfigError(
        resolvedError.message ||
          t('module.operationsCreditNotifications.config.invalidConfig'),
      );
    }
  }, [configLoaded, policy, t]);

  const syncTemplate = React.useCallback(
    async (notificationType: KnownNotificationType) => {
      const templateCode = policy.types[notificationType].template_code.trim();
      if (!templateCode) {
        setConfigError(
          t(
            'module.operationsCreditNotifications.config.templateSync.templateCodeRequired',
          ),
        );
        return;
      }
      setTemplateSyncLoading(current => ({
        ...current,
        [notificationType]: true,
      }));
      try {
        const response =
          (await api.syncAdminOperationCreditNotificationTemplate({
            notification_type: notificationType,
            template_code: templateCode,
          })) as AdminOperationCreditNotificationTemplateSyncResponse;
        setTemplateSyncResults(current => ({
          ...current,
          [notificationType]: response,
        }));
        setConfigError('');
      } catch (requestError) {
        const resolvedError = requestError as ErrorWithCode;
        setConfigError(
          resolvedError.message ||
            t(
              'module.operationsCreditNotifications.config.templateSync.syncFailed',
            ),
        );
      } finally {
        setTemplateSyncLoading(current => ({
          ...current,
          [notificationType]: false,
        }));
      }
    },
    [policy.types, t],
  );

  const dryRun = React.useCallback(async () => {
    try {
      const response = (await api.dryRunAdminOperationCreditNotifications({
        notification_type: draftFilters.notification_type.trim(),
        creator_bid: draftFilters.creator_bid.trim(),
      })) as AdminOperationCreditNotificationDryRunResponse;
      setDryRunResult(response);
    } catch (requestError) {
      const resolvedError = requestError as ErrorWithCode;
      setError({
        message: resolvedError.message || t('common.core.submitFailed'),
        code: resolvedError.code,
      });
    }
  }, [draftFilters.creator_bid, draftFilters.notification_type, t]);

  const requeue = React.useCallback(
    async (notificationBid: string) => {
      try {
        const response = (await api.requeueAdminOperationCreditNotification({
          notification_bid: notificationBid,
        })) as AdminOperationCreditNotificationRequeueResponse;
        if (!response.enqueued) {
          toast({
            title: t(
              'module.operationsCreditNotifications.messages.requeueFailed',
            ),
            description:
              response.message ||
              response.status ||
              t('common.core.unknownError'),
          });
          return;
        }
        toast({
          title: t('module.operationsCreditNotifications.messages.requeueDone'),
        });
        await fetchRecords(pageIndex, appliedFilters);
      } catch (requestError) {
        const resolvedError = requestError as ErrorWithCode;
        toast({
          title: t(
            'module.operationsCreditNotifications.messages.requeueFailed',
          ),
          description: resolvedError.message || t('common.core.unknownError'),
        });
      }
    },
    [appliedFilters, fetchRecords, pageIndex, t],
  );

  const handlePageChange = React.useCallback(
    (nextPage: number) => {
      setPageIndex(nextPage);
      void fetchRecords(nextPage, appliedFilters);
    },
    [appliedFilters, fetchRecords],
  );

  const renderTypeSelect = () => (
    <Select
      value={draftFilters.notification_type || ALL_OPTION_VALUE}
      onValueChange={value =>
        updateDraftFilter(
          'notification_type',
          value === ALL_OPTION_VALUE ? '' : value,
        )
      }
    >
      <SelectTrigger className='h-9'>
        <SelectValue
          placeholder={t(
            'module.operationsCreditNotifications.filters.notificationType',
          )}
        />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL_OPTION_VALUE}>
          {t('module.operationsCreditNotifications.filters.all')}
        </SelectItem>
        {NOTIFICATION_TYPES.map(type => (
          <SelectItem
            key={type}
            value={type}
          >
            {resolveTypeLabel(type)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  const renderStatusSelect = () => (
    <Select
      value={draftFilters.status || ALL_OPTION_VALUE}
      onValueChange={value =>
        updateDraftFilter('status', value === ALL_OPTION_VALUE ? '' : value)
      }
    >
      <SelectTrigger className='h-9'>
        <SelectValue
          placeholder={t('module.operationsCreditNotifications.filters.status')}
        />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL_OPTION_VALUE}>
          {t('module.operationsCreditNotifications.filters.all')}
        </SelectItem>
        {NOTIFICATION_STATUSES.map(status => (
          <SelectItem
            key={status}
            value={status}
          >
            {resolveStatusLabel(status)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  const renderTemplateSyncResult = (
    syncResult: AdminOperationCreditNotificationTemplateSyncResponse,
  ) => (
    <div
      className={cn(
        'rounded-md border px-3 py-2 text-xs',
        syncResult.compatible
          ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
          : 'border-amber-200 bg-amber-50 text-amber-900',
      )}
    >
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <span className='font-medium'>
          {syncResult.compatible
            ? t(
                'module.operationsCreditNotifications.config.templateSync.compatible',
              )
            : t(
                'module.operationsCreditNotifications.config.templateSync.incompatible',
              )}
        </span>
        <Badge variant='secondary'>{formatValue(syncResult.sync_status)}</Badge>
      </div>
      <div className='mt-2 grid gap-2 lg:grid-cols-2'>
        {[
          {
            label:
              'module.operationsCreditNotifications.config.templateSync.content',
            value: formatValue(syncResult.template_content),
          },
          {
            label:
              'module.operationsCreditNotifications.config.templateSync.status',
            value: formatValue(syncResult.template_status),
          },
          {
            label:
              'module.operationsCreditNotifications.config.templateSync.variables',
            value: formatPlaceholderList(syncResult.placeholders),
          },
          {
            label:
              'module.operationsCreditNotifications.config.templateSync.unused',
            value: formatPlaceholderList(
              syncResult.unused_supported_placeholders,
            ),
          },
          {
            label:
              'module.operationsCreditNotifications.config.templateSync.unsupported',
            value: formatPlaceholderList(syncResult.unsupported_placeholders),
          },
          ...(syncResult.error_message
            ? [
                {
                  label:
                    'module.operationsCreditNotifications.config.templateSync.error',
                  value: syncResult.error_message,
                },
              ]
            : []),
        ].map(item => (
          <div
            key={item.label}
            className='min-w-0'
          >
            <div className='font-medium'>{t(item.label)}</div>
            <div className='mt-0.5 break-all'>{item.value}</div>
          </div>
        ))}
      </div>
    </div>
  );

  const renderPlaceholderGuide = (type: KnownNotificationType) => {
    const hasEstimatedLowBalance =
      type === 'low_balance' && Boolean(estimatedDaysThreshold);
    const hasEstimatedFallback =
      type === 'low_balance' &&
      Boolean(
        String(estimatedDaysThreshold?.fallback_fixed_value || '').trim(),
      );
    const hasFixedLowBalancePath =
      type === 'low_balance' &&
      (fixedLowBalanceThresholds.length > 0 || hasEstimatedFallback);
    const groups = buildPlaceholderGuideGroups({
      type,
      hasFixedLowBalancePath,
      hasEstimatedLowBalance,
    });
    const noteKeys = [
      'module.operationsCreditNotifications.config.placeholders.tolerance',
      'module.operationsCreditNotifications.config.placeholders.notes.emptyVariables',
      'module.operationsCreditNotifications.config.placeholders.notes.unsupportedValidation',
      ...(hasEstimatedFallback
        ? [
            'module.operationsCreditNotifications.config.placeholders.notes.fallbackLowBalance',
          ]
        : []),
    ];

    return (
      <div className='rounded-md border border-border bg-white px-3 py-2'>
        <div className='flex items-center gap-2 text-xs font-medium text-muted-foreground'>
          <Info className='h-3.5 w-3.5' />
          <span>
            {t(
              'module.operationsCreditNotifications.config.placeholders.available',
            )}
          </span>
        </div>
        <div className='mt-2 space-y-2'>
          {groups.map(group => (
            <div
              key={group.id}
              className='rounded-md border border-border bg-muted/30 p-2'
            >
              <div className='text-xs font-medium text-foreground'>
                {t(group.titleKey)}
              </div>
              {group.descriptionKey ? (
                <p className='mt-1 text-xs leading-5 text-muted-foreground'>
                  {t(group.descriptionKey)}
                </p>
              ) : null}
              <div className='mt-2 flex flex-wrap gap-1'>
                {group.placeholders.map(placeholder => (
                  <span
                    key={`${group.id}-${placeholder}`}
                    className='inline-flex items-center gap-1 rounded border border-border bg-white px-2 py-1 text-xs text-muted-foreground'
                  >
                    <code className='font-mono text-foreground'>
                      {formatPlaceholderToken(placeholder)}
                    </code>
                    <span>
                      {t(
                        `module.operationsCreditNotifications.config.placeholders.${placeholder}`,
                      )}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
        <ul className='mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-muted-foreground'>
          {noteKeys.map(noteKey => (
            <li key={noteKey}>{t(noteKey)}</li>
          ))}
        </ul>
      </div>
    );
  };

  const renderNotificationTypeConfig = (type: KnownNotificationType) => {
    const typePolicy = policy.types[type];
    const syncResult = templateSyncResults[type];
    return (
      <div
        key={type}
        className='space-y-3 rounded-md border border-border bg-muted/20 p-3'
      >
        <div className='flex items-center justify-between gap-4'>
          <Label
            htmlFor={`credit-notification-${type}-enabled`}
            className='text-sm font-medium text-foreground'
          >
            {resolveTypeLabel(type)}
          </Label>
          <Switch
            id={`credit-notification-${type}-enabled`}
            checked={typePolicy.enabled}
            onCheckedChange={checked =>
              updatePolicy(draft => {
                draft.types[type].enabled = Boolean(checked);
              })
            }
          />
        </div>

        <div className='grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]'>
          <FormField
            htmlFor={`credit-notification-${type}-template`}
            label={t(
              'module.operationsCreditNotifications.config.fields.templateCode',
            )}
          >
            <Input
              id={`credit-notification-${type}-template`}
              className='h-9'
              value={typePolicy.template_code}
              onChange={event => {
                const value = event.target.value;
                updatePolicy(draft => {
                  draft.types[type].template_code = value;
                });
                setTemplateSyncResults(current => ({
                  ...current,
                  [type]: undefined,
                }));
              }}
            />
          </FormField>
          <div className='flex items-end'>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='h-9'
              disabled={
                Boolean(templateSyncLoading[type]) ||
                !typePolicy.template_code.trim()
              }
              onClick={() => syncTemplate(type)}
            >
              {templateSyncLoading[type]
                ? t(
                    'module.operationsCreditNotifications.actions.syncingTemplate',
                  )
                : t(
                    'module.operationsCreditNotifications.actions.syncTemplate',
                  )}
            </Button>
          </div>
        </div>

        {renderPlaceholderGuide(type)}

        {syncResult ? renderTemplateSyncResult(syncResult) : null}

        {type === 'credit_expiring' ? (
          <div className='grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]'>
            <FormField
              htmlFor='credit-notification-expiring-windows'
              label={t(
                'module.operationsCreditNotifications.config.fields.windows',
              )}
            >
              <Input
                id='credit-notification-expiring-windows'
                className='h-9'
                value={formatListInput(
                  policy.types.credit_expiring.windows || [],
                )}
                onChange={event =>
                  updatePolicy(draft => {
                    draft.types.credit_expiring.windows = parseListInput(
                      event.target.value,
                    );
                  })
                }
              />
            </FormField>
            <div className='flex items-end'>
              <div className='flex h-9 w-full items-center justify-between gap-4 rounded-md border border-border bg-white px-3'>
                <Label
                  htmlFor='credit-notification-merge-same-creator'
                  className='text-xs font-medium text-muted-foreground'
                >
                  {t(
                    'module.operationsCreditNotifications.config.fields.mergeSameCreator',
                  )}
                </Label>
                <Switch
                  id='credit-notification-merge-same-creator'
                  checked={
                    policy.types.credit_expiring.merge_same_creator || false
                  }
                  onCheckedChange={checked =>
                    updatePolicy(draft => {
                      draft.types.credit_expiring.merge_same_creator =
                        Boolean(checked);
                    })
                  }
                />
              </div>
            </div>
          </div>
        ) : null}

        {type === 'low_balance' ? (
          <div className='space-y-3'>
            <FormField
              htmlFor='credit-notification-low-balance-thresholds'
              label={t(
                'module.operationsCreditNotifications.config.fields.thresholds',
              )}
            >
              <Input
                id='credit-notification-low-balance-thresholds'
                className='h-9'
                value={formatListInput(
                  fixedLowBalanceThresholds.map(threshold => threshold.value),
                )}
                onChange={event =>
                  updatePolicy(draft => {
                    const estimated = (
                      draft.types.low_balance.thresholds || []
                    ).find(isEstimatedDaysThreshold);
                    draft.types.low_balance.thresholds = [
                      ...parseThresholdInput(event.target.value),
                      ...(estimated ? [estimated] : []),
                    ];
                  })
                }
              />
            </FormField>

            <div className='rounded-md border border-border bg-white p-3'>
              <div className='flex items-center justify-between gap-4'>
                <Label
                  htmlFor='credit-notification-estimated-days-enabled'
                  className='text-xs font-medium text-muted-foreground'
                >
                  {t(
                    'module.operationsCreditNotifications.config.fields.estimatedDaysEnabled',
                  )}
                </Label>
                <Switch
                  id='credit-notification-estimated-days-enabled'
                  checked={Boolean(estimatedDaysThreshold)}
                  onCheckedChange={checked =>
                    updatePolicy(draft => {
                      if (checked) {
                        setEstimatedDaysThreshold(draft, {});
                        return;
                      }
                      removeEstimatedDaysThreshold(draft);
                    })
                  }
                />
              </div>
              {estimatedDaysThreshold ? (
                <div className='mt-3 grid gap-3 lg:grid-cols-4'>
                  <FormField
                    htmlFor='credit-notification-estimated-days'
                    label={t(
                      'module.operationsCreditNotifications.config.fields.estimatedDays',
                    )}
                  >
                    <Input
                      id='credit-notification-estimated-days'
                      type='number'
                      min={1}
                      className='h-9'
                      value={estimatedDaysThreshold.days}
                      onChange={event =>
                        updatePolicy(draft => {
                          setEstimatedDaysThreshold(draft, {
                            days: readPositiveNumber(event.target.value, 1),
                          });
                        })
                      }
                    />
                  </FormField>
                  <FormField
                    htmlFor='credit-notification-lookback-days'
                    label={t(
                      'module.operationsCreditNotifications.config.fields.lookbackDays',
                    )}
                  >
                    <Input
                      id='credit-notification-lookback-days'
                      type='number'
                      min={1}
                      className='h-9'
                      value={estimatedDaysThreshold.lookback_days}
                      onChange={event =>
                        updatePolicy(draft => {
                          setEstimatedDaysThreshold(draft, {
                            lookback_days: readPositiveNumber(
                              event.target.value,
                              1,
                            ),
                          });
                        })
                      }
                    />
                  </FormField>
                  <FormField
                    htmlFor='credit-notification-min-consumed-days'
                    label={t(
                      'module.operationsCreditNotifications.config.fields.minConsumedDays',
                    )}
                  >
                    <Input
                      id='credit-notification-min-consumed-days'
                      type='number'
                      min={1}
                      className='h-9'
                      value={estimatedDaysThreshold.min_consumed_days}
                      onChange={event =>
                        updatePolicy(draft => {
                          setEstimatedDaysThreshold(draft, {
                            min_consumed_days: readPositiveNumber(
                              event.target.value,
                              1,
                            ),
                          });
                        })
                      }
                    />
                  </FormField>
                  <FormField
                    htmlFor='credit-notification-fallback-fixed-value'
                    label={t(
                      'module.operationsCreditNotifications.config.fields.fallbackFixedValue',
                    )}
                  >
                    <Input
                      id='credit-notification-fallback-fixed-value'
                      className='h-9'
                      value={estimatedDaysThreshold.fallback_fixed_value || ''}
                      onChange={event =>
                        updatePolicy(draft => {
                          const normalized = event.target.value.trim();
                          setEstimatedDaysThreshold(draft, {
                            fallback_fixed_value: normalized || undefined,
                          });
                        })
                      }
                    />
                  </FormField>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    );
  };

  if (!isReady) {
    return <Loading />;
  }

  return (
    <div className='flex h-full min-h-0 flex-col gap-5 p-0'>
      <div>
        <h1 className='text-2xl font-semibold text-gray-900'>
          {t('module.operationsCreditNotifications.title')}
        </h1>
        <p className='mt-1 text-sm text-muted-foreground'>
          {t('module.operationsCreditNotifications.subtitle')}
        </p>
      </div>

      <Tabs
        value={activeTab}
        className='flex min-h-0 flex-1 flex-col gap-5'
        onValueChange={value => updateTab(value as PageTab)}
      >
        <TabsList
          className={CREDIT_NOTIFICATION_TABS_LIST_CLASSNAME}
          data-testid='admin-credit-notification-tabs'
        >
          <TabsTrigger
            value='records'
            className={CREDIT_NOTIFICATION_TABS_TRIGGER_CLASSNAME}
          >
            {t('module.operationsCreditNotifications.tabs.records')}
          </TabsTrigger>
          <TabsTrigger
            value='config'
            className={CREDIT_NOTIFICATION_TABS_TRIGGER_CLASSNAME}
          >
            {t('module.operationsCreditNotifications.tabs.config')}
          </TabsTrigger>
        </TabsList>

        <TabsContent
          value='records'
          className='mt-0 min-h-0 flex-1'
        >
          <div className='flex min-h-0 flex-col gap-4'>
            <div className='rounded-xl border border-border bg-white p-4 shadow-sm'>
              <div className='grid gap-x-5 gap-y-4 xl:grid-cols-5'>
                <SearchField
                  label={t(
                    'module.operationsCreditNotifications.filters.creatorBid',
                  )}
                >
                  <Input
                    className='h-9'
                    value={draftFilters.creator_bid}
                    placeholder={t(
                      'module.operationsCreditNotifications.filters.creatorBid',
                    )}
                    onChange={event =>
                      updateDraftFilter('creator_bid', event.target.value)
                    }
                  />
                </SearchField>
                <SearchField
                  label={t(
                    'module.operationsCreditNotifications.filters.mobile',
                  )}
                >
                  <Input
                    className='h-9'
                    value={draftFilters.mobile}
                    placeholder={t(
                      'module.operationsCreditNotifications.filters.mobile',
                    )}
                    onChange={event =>
                      updateDraftFilter('mobile', event.target.value)
                    }
                  />
                </SearchField>
                <SearchField
                  label={t(
                    'module.operationsCreditNotifications.filters.notificationType',
                  )}
                >
                  {renderTypeSelect()}
                </SearchField>
                <SearchField
                  label={t(
                    'module.operationsCreditNotifications.filters.status',
                  )}
                >
                  {renderStatusSelect()}
                </SearchField>
                <SearchField
                  label={t(
                    'module.operationsCreditNotifications.filters.sourceBid',
                  )}
                >
                  <Input
                    className='h-9'
                    value={draftFilters.source_bid}
                    placeholder={t(
                      'module.operationsCreditNotifications.filters.sourceBid',
                    )}
                    onChange={event =>
                      updateDraftFilter('source_bid', event.target.value)
                    }
                  />
                </SearchField>
              </div>
              <div className='mt-4 flex flex-wrap justify-end gap-2'>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  onClick={() => fetchRecords(pageIndex, appliedFilters)}
                >
                  <RefreshCw className='mr-2 h-4 w-4' />
                  {t('module.operationsCreditNotifications.actions.refresh')}
                </Button>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  onClick={resetRecords}
                >
                  <RotateCcw className='mr-2 h-4 w-4' />
                  {t('module.operationsCreditNotifications.actions.reset')}
                </Button>
                <Button
                  type='button'
                  size='sm'
                  onClick={searchRecords}
                >
                  <Search className='mr-2 h-4 w-4' />
                  {t('module.operationsCreditNotifications.actions.search')}
                </Button>
              </div>
            </div>

            {error ? (
              <ErrorDisplay
                errorCode={error.code || 0}
                errorMessage={error.message}
              />
            ) : null}

            <div className='text-sm text-muted-foreground'>
              {t('module.operationsCreditNotifications.records.totalCount', {
                count: total,
              })}
            </div>

            <AdminTableShell
              loading={loading}
              isEmpty={items.length === 0}
              emptyContent={t('module.operationsCreditNotifications.empty')}
              emptyColSpan={7}
              withTooltipProvider
              tableWrapperClassName='max-h-[calc(100vh-20rem)] overflow-auto'
              table={emptyRow => (
                <Table containerClassName='overflow-visible max-h-none'>
                  <TableHeader>
                    <TableRow>
                      <TableHead
                        className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                        style={getColumnStyle('notification')}
                      >
                        {t(
                          'module.operationsCreditNotifications.table.notification',
                        )}
                        {renderResizeHandle('notification')}
                      </TableHead>
                      <TableHead
                        className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                        style={getColumnStyle('creator')}
                      >
                        {t(
                          'module.operationsCreditNotifications.table.creator',
                        )}
                        {renderResizeHandle('creator')}
                      </TableHead>
                      <TableHead
                        className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                        style={getColumnStyle('source')}
                      >
                        {t('module.operationsCreditNotifications.table.source')}
                        {renderResizeHandle('source')}
                      </TableHead>
                      <TableHead
                        className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                        style={getColumnStyle('template')}
                      >
                        {t(
                          'module.operationsCreditNotifications.table.template',
                        )}
                        {renderResizeHandle('template')}
                      </TableHead>
                      <TableHead
                        className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                        style={getColumnStyle('error')}
                      >
                        {t('module.operationsCreditNotifications.table.error')}
                        {renderResizeHandle('error')}
                      </TableHead>
                      <TableHead
                        className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                        style={getColumnStyle('createdAt')}
                      >
                        {t(
                          'module.operationsCreditNotifications.table.createdAt',
                        )}
                        {renderResizeHandle('createdAt')}
                      </TableHead>
                      <TableHead
                        className={getAdminStickyRightHeaderClass(
                          'text-center',
                        )}
                        style={getColumnStyle('action')}
                      >
                        {t('module.operationsCreditNotifications.table.action')}
                        {renderResizeHandle('action')}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {emptyRow}
                    {items.map(item => (
                      <TableRow key={item.notification_bid}>
                        <TableCell
                          className={TABLE_CELL_CLASS}
                          style={getColumnStyle('notification')}
                        >
                          <div className='space-y-1 text-center'>
                            <div className='font-medium text-foreground'>
                              {resolveTypeLabel(item.notification_type)}
                            </div>
                            <Badge
                              variant={
                                item.status === 'failed_provider'
                                  ? 'destructive'
                                  : 'secondary'
                              }
                            >
                              {resolveStatusLabel(item.status)}
                            </Badge>
                            {renderTooltipText(
                              item.notification_bid,
                              'block text-xs text-muted-foreground',
                            )}
                          </div>
                        </TableCell>
                        <TableCell
                          className={TABLE_CELL_CLASS}
                          style={getColumnStyle('creator')}
                        >
                          <div className='space-y-1 text-center'>
                            {renderTooltipText(item.creator_bid, 'font-medium')}
                            {renderTooltipText(
                              item.mobile_snapshot,
                              'block text-xs text-muted-foreground',
                            )}
                          </div>
                        </TableCell>
                        <TableCell
                          className={TABLE_CELL_CLASS}
                          style={getColumnStyle('source')}
                        >
                          <div className='space-y-1 text-center'>
                            {renderTooltipText(item.source_type)}
                            {renderTooltipText(
                              item.source_bid,
                              'block text-xs text-muted-foreground',
                            )}
                            {renderTooltipText(
                              item.dedupe_key,
                              'block text-xs text-muted-foreground',
                            )}
                          </div>
                        </TableCell>
                        <TableCell
                          className={TABLE_CELL_CLASS}
                          style={getColumnStyle('template')}
                        >
                          <div className='space-y-1 text-center'>
                            {renderTooltipText(
                              item.template_code,
                              'font-medium',
                            )}
                            {renderTooltipText(
                              formatTemplateParams(item.template_params),
                              'block font-mono text-xs text-muted-foreground',
                            )}
                          </div>
                        </TableCell>
                        <TableCell
                          className={TABLE_CELL_CLASS}
                          style={getColumnStyle('error')}
                        >
                          <div className='space-y-1 text-center'>
                            {renderTooltipText(item.error_code)}
                            {renderTooltipText(
                              item.error_message,
                              'block text-xs text-muted-foreground',
                            )}
                          </div>
                        </TableCell>
                        <TableCell
                          className={TABLE_TEXT_CELL_CLASS}
                          style={getColumnStyle('createdAt')}
                        >
                          {renderTooltipText(item.created_at)}
                        </TableCell>
                        <TableCell
                          className={getAdminStickyRightCellClass(
                            'whitespace-nowrap px-3 py-2 text-center',
                          )}
                          style={getColumnStyle('action')}
                        >
                          <Button
                            type='button'
                            variant='ghost'
                            size='sm'
                            disabled={item.status !== 'failed_provider'}
                            className='text-primary hover:text-primary/80'
                            onClick={() => requeue(item.notification_bid)}
                          >
                            {t(
                              'module.operationsCreditNotifications.actions.requeue',
                            )}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
              footer={
                pageCount > 1 ? (
                  <AdminPagination
                    className='mx-0 w-auto justify-end'
                    pageIndex={pageIndex}
                    pageCount={pageCount}
                    onPageChange={handlePageChange}
                    prevLabel={t('module.order.paginationPrev')}
                    nextLabel={t('module.order.paginationNext')}
                    prevAriaLabel={t('module.order.paginationPrev')}
                    nextAriaLabel={t('module.order.paginationNext')}
                    hideWhenSinglePage
                  />
                ) : null
              }
              footerClassName='mt-3'
            />
          </div>
        </TabsContent>

        <TabsContent
          value='config'
          className='mt-0 min-h-0 flex-1'
        >
          <div className='space-y-4'>
            <ConfigSection
              title={t('module.operationsCreditNotifications.config.title')}
              description={t(
                'module.operationsCreditNotifications.config.description',
              )}
            >
              <div className='flex items-center justify-between gap-4 rounded-md border border-border bg-muted/20 p-3'>
                <Label
                  htmlFor='credit-notification-enabled'
                  className='text-sm font-medium text-foreground'
                >
                  {t(
                    'module.operationsCreditNotifications.config.fields.enabled',
                  )}
                </Label>
                <Switch
                  id='credit-notification-enabled'
                  checked={policy.enabled}
                  onCheckedChange={checked =>
                    updatePolicy(draft => {
                      draft.enabled = Boolean(checked);
                    })
                  }
                />
              </div>
            </ConfigSection>

            <ConfigSection
              title={t(
                'module.operationsCreditNotifications.config.sections.types',
              )}
            >
              <div className='space-y-3'>
                {NOTIFICATION_TYPES.map(type =>
                  renderNotificationTypeConfig(type),
                )}
              </div>
            </ConfigSection>

            <div className='grid gap-4 xl:grid-cols-2'>
              <ConfigSection
                title={t(
                  'module.operationsCreditNotifications.config.sections.softlimit',
                )}
              >
                <div className='flex items-center justify-between gap-4 rounded-md border border-border bg-muted/20 p-3'>
                  <Label
                    htmlFor='credit-notification-softlimit-enabled'
                    className='text-sm font-medium text-foreground'
                  >
                    {t(
                      'module.operationsCreditNotifications.config.fields.softlimitEnabled',
                    )}
                  </Label>
                  <Switch
                    id='credit-notification-softlimit-enabled'
                    checked={policy.softlimit.enabled}
                    onCheckedChange={checked =>
                      updatePolicy(draft => {
                        draft.softlimit.enabled = Boolean(checked);
                      })
                    }
                  />
                </div>
                <FormField
                  htmlFor='credit-notification-softlimit-threshold'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.softlimitThreshold',
                  )}
                >
                  <Input
                    id='credit-notification-softlimit-threshold'
                    className='h-9'
                    value={policy.softlimit.threshold.value}
                    onChange={event =>
                      updatePolicy(draft => {
                        draft.softlimit.threshold = {
                          kind: 'fixed',
                          value: event.target.value,
                        };
                      })
                    }
                  />
                </FormField>
                <div className='grid gap-3 sm:grid-cols-3'>
                  {[
                    {
                      id: 'credit-notification-teacher-page-alert',
                      label:
                        'module.operationsCreditNotifications.config.fields.teacherPageAlert',
                      checked: policy.softlimit.teacher_page_alert,
                      update: (checked: boolean) => {
                        updatePolicy(draft => {
                          draft.softlimit.teacher_page_alert = checked;
                        });
                      },
                    },
                    {
                      id: 'credit-notification-disable-debug',
                      label:
                        'module.operationsCreditNotifications.config.fields.disableDebug',
                      checked: policy.softlimit.disable_debug,
                      update: (checked: boolean) => {
                        updatePolicy(draft => {
                          draft.softlimit.disable_debug = checked;
                        });
                      },
                    },
                    {
                      id: 'credit-notification-softlimit-sms',
                      label:
                        'module.operationsCreditNotifications.config.fields.softlimitSms',
                      checked: policy.softlimit.sms_enabled,
                      update: (checked: boolean) => {
                        updatePolicy(draft => {
                          draft.softlimit.sms_enabled = checked;
                        });
                      },
                    },
                  ].map(field => (
                    <div
                      key={field.id}
                      className='flex items-center justify-between gap-3 rounded-md border border-border bg-muted/20 p-2'
                    >
                      <Label
                        htmlFor={field.id}
                        className='text-xs font-medium text-muted-foreground'
                      >
                        {t(field.label)}
                      </Label>
                      <Switch
                        id={field.id}
                        checked={field.checked}
                        onCheckedChange={checked =>
                          field.update(Boolean(checked))
                        }
                      />
                    </div>
                  ))}
                </div>
              </ConfigSection>

              <ConfigSection
                title={t(
                  'module.operationsCreditNotifications.config.sections.frequency',
                )}
              >
                <div className='grid gap-3 sm:grid-cols-2'>
                  <FormField
                    htmlFor='credit-notification-per-mobile'
                    label={t(
                      'module.operationsCreditNotifications.config.fields.perMobilePerDay',
                    )}
                  >
                    <Input
                      id='credit-notification-per-mobile'
                      type='number'
                      min={0}
                      className='h-9'
                      value={policy.frequency.per_mobile_per_day}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.frequency.per_mobile_per_day = readNumber(
                            event.target.value,
                            0,
                          );
                        })
                      }
                    />
                  </FormField>
                  <FormField
                    htmlFor='credit-notification-per-creator-type'
                    label={t(
                      'module.operationsCreditNotifications.config.fields.perCreatorPerTypePerDay',
                    )}
                  >
                    <Input
                      id='credit-notification-per-creator-type'
                      type='number'
                      min={0}
                      className='h-9'
                      value={policy.frequency.per_creator_per_type_per_day}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.frequency.per_creator_per_type_per_day =
                            readNumber(event.target.value, 0);
                        })
                      }
                    />
                  </FormField>
                </div>
              </ConfigSection>
            </div>

            <div className='grid gap-4 xl:grid-cols-2'>
              <ConfigSection
                title={t(
                  'module.operationsCreditNotifications.config.sections.quietHours',
                )}
              >
                <div className='flex items-center justify-between gap-4 rounded-md border border-border bg-muted/20 p-3'>
                  <Label
                    htmlFor='credit-notification-quiet-hours-enabled'
                    className='text-sm font-medium text-foreground'
                  >
                    {t(
                      'module.operationsCreditNotifications.config.fields.quietHoursEnabled',
                    )}
                  </Label>
                  <Switch
                    id='credit-notification-quiet-hours-enabled'
                    checked={policy.quiet_hours.enabled}
                    onCheckedChange={checked =>
                      updatePolicy(draft => {
                        draft.quiet_hours.enabled = Boolean(checked);
                      })
                    }
                  />
                </div>
                <div className='grid gap-3 sm:grid-cols-3'>
                  <FormField
                    htmlFor='credit-notification-quiet-start'
                    label={t(
                      'module.operationsCreditNotifications.config.fields.quietStart',
                    )}
                  >
                    <Input
                      id='credit-notification-quiet-start'
                      className='h-9'
                      value={policy.quiet_hours.start}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.quiet_hours.start = event.target.value;
                        })
                      }
                    />
                  </FormField>
                  <FormField
                    htmlFor='credit-notification-quiet-end'
                    label={t(
                      'module.operationsCreditNotifications.config.fields.quietEnd',
                    )}
                  >
                    <Input
                      id='credit-notification-quiet-end'
                      className='h-9'
                      value={policy.quiet_hours.end}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.quiet_hours.end = event.target.value;
                        })
                      }
                    />
                  </FormField>
                  <FormField
                    htmlFor='credit-notification-timezone'
                    label={t(
                      'module.operationsCreditNotifications.config.fields.timezone',
                    )}
                  >
                    <Input
                      id='credit-notification-timezone'
                      className='h-9'
                      value={policy.quiet_hours.timezone}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.quiet_hours.timezone = event.target.value;
                        })
                      }
                    />
                  </FormField>
                </div>
              </ConfigSection>

              <ConfigSection
                title={t(
                  'module.operationsCreditNotifications.config.sections.budget',
                )}
              >
                <div className='grid gap-3 sm:grid-cols-2'>
                  <FormField
                    htmlFor='credit-notification-daily-sms-limit'
                    label={t(
                      'module.operationsCreditNotifications.config.fields.dailySmsLimit',
                    )}
                  >
                    <Input
                      id='credit-notification-daily-sms-limit'
                      type='number'
                      min={0}
                      className='h-9'
                      value={policy.budget.daily_sms_limit}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.budget.daily_sms_limit = readNumber(
                            event.target.value,
                            0,
                          );
                        })
                      }
                    />
                  </FormField>
                  <FormField
                    htmlFor='credit-notification-sms-unit-cost'
                    label={t(
                      'module.operationsCreditNotifications.config.fields.smsUnitCost',
                    )}
                  >
                    <Input
                      id='credit-notification-sms-unit-cost'
                      className='h-9'
                      value={policy.budget.sms_unit_cost}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.budget.sms_unit_cost = event.target.value;
                        })
                      }
                    />
                  </FormField>
                </div>
                <div className='flex items-center justify-between gap-4 rounded-md border border-border bg-muted/20 p-3'>
                  <Label
                    htmlFor='credit-notification-dry-run-required'
                    className='text-xs font-medium text-muted-foreground'
                  >
                    {t(
                      'module.operationsCreditNotifications.config.fields.dryRunRequired',
                    )}
                  </Label>
                  <Switch
                    id='credit-notification-dry-run-required'
                    checked={policy.budget.dry_run_required}
                    onCheckedChange={checked =>
                      updatePolicy(draft => {
                        draft.budget.dry_run_required = Boolean(checked);
                      })
                    }
                  />
                </div>
              </ConfigSection>
            </div>

            <ConfigSection
              title={t(
                'module.operationsCreditNotifications.config.sections.lists',
              )}
            >
              <div className='grid gap-3 lg:grid-cols-4'>
                <FormField
                  htmlFor='credit-notification-blacklist-creators'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.blacklistCreatorBids',
                  )}
                >
                  <Input
                    id='credit-notification-blacklist-creators'
                    className='h-9'
                    value={formatListInput(policy.blacklist.creator_bids)}
                    onChange={event =>
                      updatePolicy(draft => {
                        draft.blacklist.creator_bids = parseListInput(
                          event.target.value,
                        );
                      })
                    }
                  />
                </FormField>
                <FormField
                  htmlFor='credit-notification-blacklist-mobiles'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.blacklistMobiles',
                  )}
                >
                  <Input
                    id='credit-notification-blacklist-mobiles'
                    className='h-9'
                    value={formatListInput(policy.blacklist.mobiles)}
                    onChange={event =>
                      updatePolicy(draft => {
                        draft.blacklist.mobiles = parseListInput(
                          event.target.value,
                        );
                      })
                    }
                  />
                </FormField>
                <FormField
                  htmlFor='credit-notification-opt-out-creators'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.optOutCreatorBids',
                  )}
                >
                  <Input
                    id='credit-notification-opt-out-creators'
                    className='h-9'
                    value={formatListInput(policy.opt_out.creator_bids)}
                    onChange={event =>
                      updatePolicy(draft => {
                        draft.opt_out.creator_bids = parseListInput(
                          event.target.value,
                        );
                      })
                    }
                  />
                </FormField>
                <FormField
                  htmlFor='credit-notification-opt-out-mobiles'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.optOutMobiles',
                  )}
                >
                  <Input
                    id='credit-notification-opt-out-mobiles'
                    className='h-9'
                    value={formatListInput(policy.opt_out.mobiles)}
                    onChange={event =>
                      updatePolicy(draft => {
                        draft.opt_out.mobiles = parseListInput(
                          event.target.value,
                        );
                      })
                    }
                  />
                </FormField>
              </div>
            </ConfigSection>

            <ConfigSection
              title={t('module.operationsCreditNotifications.dryRun.title')}
            >
              <div className='flex items-center justify-between gap-4 rounded-md border border-border bg-muted/20 p-3'>
                <div className='text-xs text-muted-foreground'>
                  {dryRunResult
                    ? t(
                        'module.operationsCreditNotifications.dryRun.candidateCount',
                        { count: dryRunResult.candidate_count || 0 },
                      )
                    : t('module.operationsCreditNotifications.dryRun.empty')}
                </div>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  onClick={dryRun}
                >
                  {t('module.operationsCreditNotifications.actions.dryRun')}
                </Button>
              </div>
              {dryRunResult ? (
                <pre className='max-h-[220px] overflow-auto rounded-md bg-muted p-3 text-xs text-muted-foreground'>
                  {JSON.stringify(dryRunResult, null, 2)}
                </pre>
              ) : null}
            </ConfigSection>

            {configError ? (
              <ErrorDisplay
                errorCode={0}
                errorMessage={configError}
              />
            ) : null}

            <div className='flex justify-end'>
              <Button
                type='button'
                onClick={saveConfig}
                disabled={!configLoaded}
              >
                {t('module.operationsCreditNotifications.actions.applyConfig')}
              </Button>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
