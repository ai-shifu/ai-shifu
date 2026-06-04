import type { TFunction } from 'i18next';
import type {
  AdminOperationCreditNotificationItem,
  AdminOperationCreditNotificationPolicy,
  CreditNotificationEstimatedDaysThreshold,
  CreditNotificationFixedThreshold,
  CreditNotificationThreshold,
} from '../operation-credit-notification-types';

export type NotificationFilters = {
  creator_keyword: string;
  notification_type: string;
  status: string;
  delivery_status: string;
  skip_reason: string;
  source_type: string;
  start_time: string;
  end_time: string;
};

export type ErrorState = { message: string; code?: number };
export type PageTab = 'records' | 'config';
export type NotificationOverviewCardKey =
  | 'total'
  | 'pending'
  | 'sent'
  | 'failed'
  | 'skipped';

export const PAGE_SIZE = 20;
export const EMPTY_LABEL = '--';
export const ALL_OPTION_VALUE = '__all__';
export const DEFAULT_TAB: PageTab = 'records';
export const NOTIFICATION_TYPES = [
  'credit_expiring',
  'credit_granted',
  'low_balance',
] as const;
export const NOTIFICATION_SOURCE_TYPES = [
  'ledger',
  'wallet',
  'wallet_bucket',
] as const;
export const NOTIFICATION_DELIVERY_STATUSES = [
  'pending',
  'sent',
  'failed',
  'not_sent',
] as const;
export const NOTIFICATION_SKIP_REASONS = [
  'contact',
  'policy',
  'duplicate',
  'stale',
  'template_params',
] as const;
export type KnownNotificationType = (typeof NOTIFICATION_TYPES)[number];
export type TemplatePlaceholderKey =
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
export type PlaceholderGuideGroup = {
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

export const DEFAULT_ESTIMATED_DAYS_THRESHOLD: CreditNotificationEstimatedDaysThreshold =
  {
    kind: 'estimated_days',
    days: 7,
    lookback_days: 7,
    min_consumed_days: 2,
    fallback_fixed_value: '0',
  };

export const CREDIT_NOTIFICATION_TABS_LIST_CLASSNAME =
  'h-11 w-fit justify-start self-start rounded-[12px] bg-[var(--base-muted,#F5F5F5)] p-[3px] shadow-sm';
export const CREDIT_NOTIFICATION_TABS_TRIGGER_CLASSNAME =
  'h-full rounded-[10px] border border-transparent px-5 py-2 text-sm font-medium text-[var(--base-foreground,#0A0A0A)] data-[state=active]:bg-white data-[state=active]:shadow-[0_1px_3px_rgba(0,0,0,0.1),0_1px_2px_rgba(0,0,0,0.06)]';

export const createDefaultFilters = (): NotificationFilters => ({
  creator_keyword: '',
  notification_type: '',
  status: '',
  delivery_status: '',
  skip_reason: '',
  source_type: '',
  start_time: '',
  end_time: '',
});

export const createDefaultPolicy =
  (): AdminOperationCreditNotificationPolicy => ({
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

export const clonePolicy = (
  policy: AdminOperationCreditNotificationPolicy,
): AdminOperationCreditNotificationPolicy =>
  JSON.parse(JSON.stringify(policy)) as AdminOperationCreditNotificationPolicy;

const resolveErrorReasonCode = (
  errorCode?: string | null,
  errorMessage?: string | null,
) => {
  const normalizedCode = String(errorCode || '').trim();
  if (normalizedCode) {
    return normalizedCode;
  }

  const normalizedMessage = String(errorMessage || '').trim();
  const blockedMatch = normalizedMessage.match(
    /^Notification blocked by policy:\s*([A-Za-z0-9_]+)\.?$/i,
  );
  if (blockedMatch?.[1]) {
    return blockedMatch[1];
  }
  if (/SMS provider returned no accepted response/i.test(normalizedMessage)) {
    return 'provider_failed';
  }
  if (/Creator mobile is empty/i.test(normalizedMessage)) {
    return 'missing_mobile';
  }
  if (/Creator mobile is invalid/i.test(normalizedMessage)) {
    return 'invalid_mobile';
  }
  return '';
};

export const resolveCreditNotificationErrorText = (
  t: TFunction,
  errorCode?: string | null,
  errorMessage?: string | null,
) => {
  const reasonCode = resolveErrorReasonCode(errorCode, errorMessage);
  if (reasonCode) {
    const fallback = String(errorMessage || errorCode || '').trim();
    return String(
      t(`module.operationsCreditNotifications.errorReason.${reasonCode}`, {
        defaultValue: fallback,
      }),
    );
  }

  return String(errorMessage || '').trim();
};

export const resolveNotificationDeliveryStatus = (
  item: Pick<
    AdminOperationCreditNotificationItem,
    'status' | 'delivery_status'
  >,
) => {
  const normalizedDeliveryStatus = String(item.delivery_status || '').trim();
  if (normalizedDeliveryStatus) {
    return normalizedDeliveryStatus;
  }
  const normalizedStatus = String(item.status || '').trim();
  if (normalizedStatus === 'failed_provider') {
    return 'failed';
  }
  if (
    normalizedStatus.startsWith('skipped') ||
    normalizedStatus === 'suppressed_duplicate'
  ) {
    return 'not_sent';
  }
  return normalizedStatus;
};

export const resolveNotificationSkipReason = (
  item: Pick<
    AdminOperationCreditNotificationItem,
    'status' | 'skip_reason' | 'error_code'
  >,
) => {
  const normalizedSkipReason = String(item.skip_reason || '').trim();
  if (normalizedSkipReason) {
    return normalizedSkipReason;
  }
  const normalizedStatus = String(item.status || '').trim();
  const normalizedErrorCode = String(item.error_code || '').trim();
  if (normalizedStatus === 'skipped_no_mobile') {
    return 'contact';
  }
  if (normalizedStatus === 'suppressed_duplicate') {
    return 'duplicate';
  }
  if (
    normalizedStatus === 'skipped' ||
    normalizedErrorCode === 'expiry_extended'
  ) {
    return 'stale';
  }
  if (normalizedErrorCode === 'missing_template_params') {
    return 'template_params';
  }
  if (normalizedStatus === 'skipped_opt_out') {
    return 'policy';
  }
  if (normalizedStatus.startsWith('skipped')) {
    return 'policy';
  }
  return '';
};

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

export const normalizeIntegerInput = (value: unknown): string => {
  const normalized = String(value ?? '').normalize('NFKC');
  if (/^\s*-/.test(normalized)) {
    return '';
  }
  const integerPart = normalized.split(/[.。]/)[0] || '';
  return integerPart.replace(/\D/g, '');
};

export const readNumber = (value: unknown, fallback: number): number => {
  const normalized = normalizeIntegerInput(value);
  if (!normalized) {
    return fallback;
  }
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : fallback;
};

export const readPositiveNumber = (
  value: unknown,
  fallback: number,
): number => {
  const parsed = readNumber(value, fallback);
  return parsed > 0 ? parsed : fallback;
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

export const isFixedThreshold = (
  threshold: CreditNotificationThreshold,
): threshold is CreditNotificationFixedThreshold => threshold.kind === 'fixed';

export const isEstimatedDaysThreshold = (
  threshold: CreditNotificationThreshold,
): threshold is CreditNotificationEstimatedDaysThreshold =>
  threshold.kind === 'estimated_days';

export const normalizePolicy = (
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

export const normalizeListInputCharacters = (value: string): string =>
  value.normalize('NFKC').replace(/[，、]/g, ',');

export const normalizeListInput = (value: string): string =>
  value
    .normalize('NFKC')
    .replace(/[，、]/g, ',')
    .replace(/\s*,\s*/g, ', ')
    .trim();

export const parseListInput = (value: string): string[] =>
  normalizeListInput(value)
    .split(/[,\n]/)
    .map(item => item.trim())
    .filter(Boolean);

export const formatListInput = (value: string[]): string => value.join(', ');

export const parseThresholdInput = (
  value: string,
): CreditNotificationFixedThreshold[] =>
  parseListInput(value).map(item => ({ kind: 'fixed' as const, value: item }));

export const setEstimatedDaysThreshold = (
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

export const removeEstimatedDaysThreshold = (
  policy: AdminOperationCreditNotificationPolicy,
) => {
  const fixedThresholds = (policy.types.low_balance.thresholds || []).filter(
    isFixedThreshold,
  );
  policy.types.low_balance.thresholds = fixedThresholds.length
    ? fixedThresholds
    : [{ kind: 'fixed', value: '0' }];
};

export const formatValue = (value?: string | null) => {
  const normalized = String(value || '').trim();
  return normalized || EMPTY_LABEL;
};

export const formatTemplateParams = (
  value: Record<string, unknown>,
): string => {
  const entries = Object.entries(value || {})
    .filter(([key]) => key.trim())
    .sort(([left], [right]) => left.localeCompare(right));
  if (!entries.length) {
    return EMPTY_LABEL;
  }
  return JSON.stringify(Object.fromEntries(entries));
};

export const formatPlaceholderToken = (placeholder: string): string =>
  ['${', placeholder, '}'].join('');

export const formatPlaceholderList = (items?: string[]): string => {
  const normalized = (items || [])
    .map(item => String(item || '').trim())
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right));
  return normalized.length
    ? normalized.map(formatPlaceholderToken).join(', ')
    : EMPTY_LABEL;
};

export const buildPlaceholderGuideGroups = ({
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

export const normalizeTab = (value?: string | null): PageTab =>
  value === 'config' ? 'config' : DEFAULT_TAB;
