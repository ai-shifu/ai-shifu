'use client';

import React from 'react';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Switch } from '@/components/ui/Switch';
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { toast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import useOperatorGuard from '../useOperatorGuard';
import type {
  AdminOperationCreditNotificationPolicy,
  AdminOperationCreditNotificationDryRunResponse,
  AdminOperationCreditNotificationItem,
  AdminOperationCreditNotificationListResponse,
  AdminOperationCreditNotificationRequeueResponse,
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

const PAGE_SIZE = 20;
const EMPTY_LABEL = '--';
const NOTIFICATION_TYPES = [
  'credit_expiring',
  'credit_granted',
  'low_balance',
] as const;
const DEFAULT_ESTIMATED_DAYS_THRESHOLD: CreditNotificationEstimatedDaysThreshold =
  {
    kind: 'estimated_days',
    days: 7,
    lookback_days: 7,
    min_consumed_days: 2,
    fallback_fixed_value: '0',
  };

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
    ? value.map(item => String(item || '').trim()).filter(Boolean)
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

export default function AdminOperationCreditNotificationsPage() {
  const { t } = useTranslation();
  const { isReady } = useOperatorGuard();
  const [items, setItems] = React.useState<
    AdminOperationCreditNotificationItem[]
  >([]);
  const [filters, setFilters] =
    React.useState<NotificationFilters>(createDefaultFilters);
  const [pageIndex, setPageIndex] = React.useState(1);
  const [pageCount, setPageCount] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<ErrorState | null>(null);
  const [policy, setPolicy] =
    React.useState<AdminOperationCreditNotificationPolicy>(createDefaultPolicy);
  const [configError, setConfigError] = React.useState('');
  const [dryRunResult, setDryRunResult] =
    React.useState<AdminOperationCreditNotificationDryRunResponse | null>(null);
  const requestIdRef = React.useRef(0);
  const lowBalanceThresholds = policy.types.low_balance.thresholds || [];
  const fixedLowBalanceThresholds =
    lowBalanceThresholds.filter(isFixedThreshold);
  const estimatedDaysThreshold =
    lowBalanceThresholds.find(isEstimatedDaysThreshold) || null;

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
    fetchConfig().catch(() => {
      setPolicy(createDefaultPolicy());
    });
    void fetchRecords(1, filters);
  }, [fetchConfig, fetchRecords, filters, isReady]);

  const updateFilter = React.useCallback(
    (field: keyof NotificationFilters, value: string) => {
      const nextFilters = {
        ...filters,
        [field]: value,
      };
      setFilters(nextFilters);
      setPageIndex(1);
      void fetchRecords(1, nextFilters);
    },
    [fetchRecords, filters],
  );

  const saveConfig = React.useCallback(async () => {
    try {
      const response =
        await api.updateAdminOperationCreditNotificationConfig(policy);
      setPolicy(normalizePolicy(response));
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
  }, [policy, t]);

  const dryRun = React.useCallback(async () => {
    try {
      const response = (await api.dryRunAdminOperationCreditNotifications({
        notification_type: filters.notification_type.trim(),
        creator_bid: filters.creator_bid.trim(),
      })) as AdminOperationCreditNotificationDryRunResponse;
      setDryRunResult(response);
    } catch (requestError) {
      const resolvedError = requestError as ErrorWithCode;
      setError({
        message: resolvedError.message || t('common.core.submitFailed'),
        code: resolvedError.code,
      });
    }
  }, [filters.creator_bid, filters.notification_type, t]);

  const requeue = React.useCallback(
    async (notificationBid: string) => {
      const response = (await api.requeueAdminOperationCreditNotification({
        notification_bid: notificationBid,
      })) as AdminOperationCreditNotificationRequeueResponse;
      if (response.enqueued) {
        toast({
          title: t('module.operationsCreditNotifications.messages.requeueDone'),
        });
      }
      void fetchRecords(pageIndex, filters);
    },
    [fetchRecords, filters, pageIndex, t],
  );

  if (!isReady) {
    return <Loading />;
  }

  return (
    <div className='flex h-full min-h-0 flex-col gap-5 p-0'>
      <div>
        <h1 className='text-2xl font-semibold text-gray-900'>
          {t('module.operationsCreditNotifications.title')}
        </h1>
        <p className='mt-1 text-sm text-gray-500'>
          {t('module.operationsCreditNotifications.subtitle')}
        </p>
      </div>

      <div className='grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]'>
        <section className='min-w-0 rounded-md border border-gray-200 bg-white p-4'>
          <div className='mb-4 flex flex-wrap items-end gap-3'>
            <Input
              className='h-9 w-44'
              value={filters.creator_bid}
              placeholder={t(
                'module.operationsCreditNotifications.filters.creatorBid',
              )}
              onChange={event =>
                updateFilter('creator_bid', event.target.value)
              }
            />
            <Input
              className='h-9 w-36'
              value={filters.mobile}
              placeholder={t(
                'module.operationsCreditNotifications.filters.mobile',
              )}
              onChange={event => updateFilter('mobile', event.target.value)}
            />
            <Input
              className='h-9 w-44'
              value={filters.notification_type}
              placeholder={t(
                'module.operationsCreditNotifications.filters.notificationType',
              )}
              onChange={event =>
                updateFilter('notification_type', event.target.value)
              }
            />
            <Input
              className='h-9 w-40'
              value={filters.status}
              placeholder={t(
                'module.operationsCreditNotifications.filters.status',
              )}
              onChange={event => updateFilter('status', event.target.value)}
            />
            <Input
              className='h-9 w-44'
              value={filters.source_bid}
              placeholder={t(
                'module.operationsCreditNotifications.filters.sourceBid',
              )}
              onChange={event => updateFilter('source_bid', event.target.value)}
            />
            <Button
              type='button'
              variant='outline'
              size='sm'
              onClick={() => fetchRecords(pageIndex, filters)}
            >
              <RefreshCw className='mr-2 h-4 w-4' />
              {t('module.operationsCreditNotifications.actions.refresh')}
            </Button>
            <Button
              type='button'
              size='sm'
              onClick={dryRun}
            >
              {t('module.operationsCreditNotifications.actions.dryRun')}
            </Button>
          </div>

          {error ? (
            <ErrorDisplay
              errorCode={error.code || 0}
              errorMessage={error.message}
            />
          ) : null}

          {loading ? (
            <Loading />
          ) : (
            <Table containerClassName='max-h-[560px] rounded-md border border-gray-200'>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    {t(
                      'module.operationsCreditNotifications.table.notification',
                    )}
                  </TableHead>
                  <TableHead>
                    {t('module.operationsCreditNotifications.table.creator')}
                  </TableHead>
                  <TableHead>
                    {t('module.operationsCreditNotifications.table.source')}
                  </TableHead>
                  <TableHead>
                    {t('module.operationsCreditNotifications.table.template')}
                  </TableHead>
                  <TableHead>
                    {t('module.operationsCreditNotifications.table.error')}
                  </TableHead>
                  <TableHead>
                    {t('module.operationsCreditNotifications.table.createdAt')}
                  </TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.length === 0 ? (
                  <TableEmpty colSpan={7}>
                    {t('module.operationsCreditNotifications.empty')}
                  </TableEmpty>
                ) : (
                  items.map(item => (
                    <TableRow key={item.notification_bid}>
                      <TableCell className='min-w-[220px]'>
                        <div className='font-medium text-gray-900'>
                          {resolveTypeLabel(item.notification_type)}
                        </div>
                        <Badge
                          variant={
                            item.status === 'failed_provider'
                              ? 'destructive'
                              : 'secondary'
                          }
                          className='mt-1'
                        >
                          {resolveStatusLabel(item.status)}
                        </Badge>
                        <div className='mt-1 text-xs text-gray-500'>
                          {formatValue(item.notification_bid)}
                        </div>
                      </TableCell>
                      <TableCell className='min-w-[180px]'>
                        <div>{formatValue(item.creator_bid)}</div>
                        <div className='text-xs text-gray-500'>
                          {formatValue(item.mobile_snapshot)}
                        </div>
                      </TableCell>
                      <TableCell className='min-w-[220px]'>
                        <div>{formatValue(item.source_type)}</div>
                        <div className='text-xs text-gray-500'>
                          {formatValue(item.source_bid)}
                        </div>
                      </TableCell>
                      <TableCell className='min-w-[160px]'>
                        {formatValue(item.template_code)}
                      </TableCell>
                      <TableCell className='min-w-[220px]'>
                        <div>{formatValue(item.error_code)}</div>
                        <div className='text-xs text-gray-500'>
                          {formatValue(item.error_message)}
                        </div>
                      </TableCell>
                      <TableCell className='min-w-[180px]'>
                        {formatValue(item.created_at)}
                      </TableCell>
                      <TableCell>
                        <Button
                          type='button'
                          variant='outline'
                          size='sm'
                          disabled={item.status !== 'failed_provider'}
                          onClick={() => requeue(item.notification_bid)}
                        >
                          {t(
                            'module.operationsCreditNotifications.actions.requeue',
                          )}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}

          <AdminPagination
            className='mt-4 justify-end'
            pageIndex={pageIndex}
            pageCount={pageCount}
            onPageChange={nextPage => {
              setPageIndex(nextPage);
              void fetchRecords(nextPage, filters);
            }}
            prevLabel={t('module.order.paginationPrev', 'Previous')}
            nextLabel={t('module.order.paginationNext', 'Next')}
            prevAriaLabel={t('module.order.paginationPrev', 'Previous')}
            nextAriaLabel={t('module.order.paginationNext', 'Next')}
            hideWhenSinglePage
          />
        </section>

        <aside className='flex min-w-0 flex-col gap-4'>
          <section className='rounded-md border border-gray-200 bg-white p-4'>
            <h2 className='text-base font-semibold text-gray-900'>
              {t('module.operationsCreditNotifications.config.title')}
            </h2>
            <p className='mt-1 text-sm text-gray-500'>
              {t('module.operationsCreditNotifications.config.description')}
            </p>
            <div className='mt-4 space-y-4'>
              <div className='flex items-center justify-between gap-4 rounded-md border border-gray-200 p-3'>
                <Label
                  htmlFor='credit-notification-enabled'
                  className='text-sm text-gray-700'
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

              <div className='space-y-3'>
                <h3 className='text-sm font-semibold text-gray-900'>
                  {t(
                    'module.operationsCreditNotifications.config.sections.types',
                  )}
                </h3>
                {NOTIFICATION_TYPES.map(type => {
                  const typePolicy = policy.types[type];
                  return (
                    <div
                      key={type}
                      className='space-y-3 rounded-md border border-gray-200 p-3'
                    >
                      <div className='flex items-center justify-between gap-4'>
                        <Label
                          htmlFor={`credit-notification-${type}-enabled`}
                          className='text-sm text-gray-700'
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
                      <div>
                        <Label
                          htmlFor={`credit-notification-${type}-template`}
                          className='text-xs text-gray-600'
                        >
                          {t(
                            'module.operationsCreditNotifications.config.fields.templateCode',
                          )}
                        </Label>
                        <Input
                          id={`credit-notification-${type}-template`}
                          className='mt-1 h-9'
                          value={typePolicy.template_code}
                          onChange={event =>
                            updatePolicy(draft => {
                              draft.types[type].template_code =
                                event.target.value;
                            })
                          }
                        />
                      </div>
                      {type === 'credit_expiring' ? (
                        <>
                          <div>
                            <Label
                              htmlFor='credit-notification-expiring-windows'
                              className='text-xs text-gray-600'
                            >
                              {t(
                                'module.operationsCreditNotifications.config.fields.windows',
                              )}
                            </Label>
                            <Input
                              id='credit-notification-expiring-windows'
                              className='mt-1 h-9'
                              value={formatListInput(
                                policy.types.credit_expiring.windows || [],
                              )}
                              onChange={event =>
                                updatePolicy(draft => {
                                  draft.types.credit_expiring.windows =
                                    parseListInput(event.target.value);
                                })
                              }
                            />
                          </div>
                          <div className='flex items-center justify-between gap-4'>
                            <Label
                              htmlFor='credit-notification-merge-same-creator'
                              className='text-xs text-gray-600'
                            >
                              {t(
                                'module.operationsCreditNotifications.config.fields.mergeSameCreator',
                              )}
                            </Label>
                            <Switch
                              id='credit-notification-merge-same-creator'
                              checked={
                                policy.types.credit_expiring
                                  .merge_same_creator || false
                              }
                              onCheckedChange={checked =>
                                updatePolicy(draft => {
                                  draft.types.credit_expiring.merge_same_creator =
                                    Boolean(checked);
                                })
                              }
                            />
                          </div>
                        </>
                      ) : null}
                      {type === 'low_balance' ? (
                        <>
                          <div>
                            <Label
                              htmlFor='credit-notification-low-balance-thresholds'
                              className='text-xs text-gray-600'
                            >
                              {t(
                                'module.operationsCreditNotifications.config.fields.thresholds',
                              )}
                            </Label>
                            <Input
                              id='credit-notification-low-balance-thresholds'
                              className='mt-1 h-9'
                              value={formatListInput(
                                fixedLowBalanceThresholds.map(
                                  threshold => threshold.value,
                                ),
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
                          </div>
                          <div className='space-y-3 rounded border border-gray-100 p-2'>
                            <div className='flex items-center justify-between gap-4'>
                              <Label
                                htmlFor='credit-notification-estimated-days-enabled'
                                className='text-xs text-gray-600'
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
                              <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2'>
                                <div>
                                  <Label
                                    htmlFor='credit-notification-estimated-days'
                                    className='text-xs text-gray-600'
                                  >
                                    {t(
                                      'module.operationsCreditNotifications.config.fields.estimatedDays',
                                    )}
                                  </Label>
                                  <Input
                                    id='credit-notification-estimated-days'
                                    type='number'
                                    min={1}
                                    className='mt-1 h-9'
                                    value={estimatedDaysThreshold.days}
                                    onChange={event =>
                                      updatePolicy(draft => {
                                        setEstimatedDaysThreshold(draft, {
                                          days: readPositiveNumber(
                                            event.target.value,
                                            DEFAULT_ESTIMATED_DAYS_THRESHOLD.days,
                                          ),
                                        });
                                      })
                                    }
                                  />
                                </div>
                                <div>
                                  <Label
                                    htmlFor='credit-notification-lookback-days'
                                    className='text-xs text-gray-600'
                                  >
                                    {t(
                                      'module.operationsCreditNotifications.config.fields.lookbackDays',
                                    )}
                                  </Label>
                                  <Input
                                    id='credit-notification-lookback-days'
                                    type='number'
                                    min={1}
                                    className='mt-1 h-9'
                                    value={estimatedDaysThreshold.lookback_days}
                                    onChange={event =>
                                      updatePolicy(draft => {
                                        setEstimatedDaysThreshold(draft, {
                                          lookback_days: readPositiveNumber(
                                            event.target.value,
                                            DEFAULT_ESTIMATED_DAYS_THRESHOLD.lookback_days,
                                          ),
                                        });
                                      })
                                    }
                                  />
                                </div>
                                <div>
                                  <Label
                                    htmlFor='credit-notification-min-consumed-days'
                                    className='text-xs text-gray-600'
                                  >
                                    {t(
                                      'module.operationsCreditNotifications.config.fields.minConsumedDays',
                                    )}
                                  </Label>
                                  <Input
                                    id='credit-notification-min-consumed-days'
                                    type='number'
                                    min={1}
                                    className='mt-1 h-9'
                                    value={
                                      estimatedDaysThreshold.min_consumed_days
                                    }
                                    onChange={event =>
                                      updatePolicy(draft => {
                                        setEstimatedDaysThreshold(draft, {
                                          min_consumed_days: readPositiveNumber(
                                            event.target.value,
                                            DEFAULT_ESTIMATED_DAYS_THRESHOLD.min_consumed_days,
                                          ),
                                        });
                                      })
                                    }
                                  />
                                </div>
                                <div>
                                  <Label
                                    htmlFor='credit-notification-fallback-fixed-value'
                                    className='text-xs text-gray-600'
                                  >
                                    {t(
                                      'module.operationsCreditNotifications.config.fields.fallbackFixedValue',
                                    )}
                                  </Label>
                                  <Input
                                    id='credit-notification-fallback-fixed-value'
                                    className='mt-1 h-9'
                                    value={
                                      estimatedDaysThreshold.fallback_fixed_value ||
                                      ''
                                    }
                                    onChange={event =>
                                      updatePolicy(draft => {
                                        setEstimatedDaysThreshold(draft, {
                                          fallback_fixed_value:
                                            event.target.value,
                                        });
                                      })
                                    }
                                  />
                                </div>
                              </div>
                            ) : null}
                          </div>
                        </>
                      ) : null}
                    </div>
                  );
                })}
              </div>

              <div className='space-y-3 rounded-md border border-gray-200 p-3'>
                <h3 className='text-sm font-semibold text-gray-900'>
                  {t(
                    'module.operationsCreditNotifications.config.sections.softlimit',
                  )}
                </h3>
                <div className='flex items-center justify-between gap-4'>
                  <Label
                    htmlFor='credit-notification-softlimit-enabled'
                    className='text-xs text-gray-600'
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
                <div>
                  <Label
                    htmlFor='credit-notification-softlimit-threshold'
                    className='text-xs text-gray-600'
                  >
                    {t(
                      'module.operationsCreditNotifications.config.fields.softlimitThreshold',
                    )}
                  </Label>
                  <Input
                    id='credit-notification-softlimit-threshold'
                    className='mt-1 h-9'
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
                </div>
                <div className='grid gap-3 sm:grid-cols-3 xl:grid-cols-1 2xl:grid-cols-3'>
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
                      className='flex items-center justify-between gap-3 rounded border border-gray-100 p-2'
                    >
                      <Label
                        htmlFor={field.id}
                        className='text-xs text-gray-600'
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
              </div>

              <div className='space-y-3 rounded-md border border-gray-200 p-3'>
                <h3 className='text-sm font-semibold text-gray-900'>
                  {t(
                    'module.operationsCreditNotifications.config.sections.frequency',
                  )}
                </h3>
                <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2'>
                  <div>
                    <Label
                      htmlFor='credit-notification-per-mobile'
                      className='text-xs text-gray-600'
                    >
                      {t(
                        'module.operationsCreditNotifications.config.fields.perMobilePerDay',
                      )}
                    </Label>
                    <Input
                      id='credit-notification-per-mobile'
                      type='number'
                      min={0}
                      className='mt-1 h-9'
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
                  </div>
                  <div>
                    <Label
                      htmlFor='credit-notification-per-creator-type'
                      className='text-xs text-gray-600'
                    >
                      {t(
                        'module.operationsCreditNotifications.config.fields.perCreatorPerTypePerDay',
                      )}
                    </Label>
                    <Input
                      id='credit-notification-per-creator-type'
                      type='number'
                      min={0}
                      className='mt-1 h-9'
                      value={policy.frequency.per_creator_per_type_per_day}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.frequency.per_creator_per_type_per_day =
                            readNumber(event.target.value, 0);
                        })
                      }
                    />
                  </div>
                </div>
              </div>

              <div className='space-y-3 rounded-md border border-gray-200 p-3'>
                <h3 className='text-sm font-semibold text-gray-900'>
                  {t(
                    'module.operationsCreditNotifications.config.sections.quietHours',
                  )}
                </h3>
                <div className='flex items-center justify-between gap-4'>
                  <Label
                    htmlFor='credit-notification-quiet-hours-enabled'
                    className='text-xs text-gray-600'
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
                <div className='grid gap-3 sm:grid-cols-3 xl:grid-cols-1 2xl:grid-cols-3'>
                  <div>
                    <Label
                      htmlFor='credit-notification-quiet-start'
                      className='text-xs text-gray-600'
                    >
                      {t(
                        'module.operationsCreditNotifications.config.fields.quietStart',
                      )}
                    </Label>
                    <Input
                      id='credit-notification-quiet-start'
                      className='mt-1 h-9'
                      value={policy.quiet_hours.start}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.quiet_hours.start = event.target.value;
                        })
                      }
                    />
                  </div>
                  <div>
                    <Label
                      htmlFor='credit-notification-quiet-end'
                      className='text-xs text-gray-600'
                    >
                      {t(
                        'module.operationsCreditNotifications.config.fields.quietEnd',
                      )}
                    </Label>
                    <Input
                      id='credit-notification-quiet-end'
                      className='mt-1 h-9'
                      value={policy.quiet_hours.end}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.quiet_hours.end = event.target.value;
                        })
                      }
                    />
                  </div>
                  <div>
                    <Label
                      htmlFor='credit-notification-timezone'
                      className='text-xs text-gray-600'
                    >
                      {t(
                        'module.operationsCreditNotifications.config.fields.timezone',
                      )}
                    </Label>
                    <Input
                      id='credit-notification-timezone'
                      className='mt-1 h-9'
                      value={policy.quiet_hours.timezone}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.quiet_hours.timezone = event.target.value;
                        })
                      }
                    />
                  </div>
                </div>
              </div>

              <div className='space-y-3 rounded-md border border-gray-200 p-3'>
                <h3 className='text-sm font-semibold text-gray-900'>
                  {t(
                    'module.operationsCreditNotifications.config.sections.lists',
                  )}
                </h3>
                <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2'>
                  <div>
                    <Label
                      htmlFor='credit-notification-blacklist-creators'
                      className='text-xs text-gray-600'
                    >
                      {t(
                        'module.operationsCreditNotifications.config.fields.blacklistCreatorBids',
                      )}
                    </Label>
                    <Input
                      id='credit-notification-blacklist-creators'
                      className='mt-1 h-9'
                      value={formatListInput(policy.blacklist.creator_bids)}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.blacklist.creator_bids = parseListInput(
                            event.target.value,
                          );
                        })
                      }
                    />
                  </div>
                  <div>
                    <Label
                      htmlFor='credit-notification-blacklist-mobiles'
                      className='text-xs text-gray-600'
                    >
                      {t(
                        'module.operationsCreditNotifications.config.fields.blacklistMobiles',
                      )}
                    </Label>
                    <Input
                      id='credit-notification-blacklist-mobiles'
                      className='mt-1 h-9'
                      value={formatListInput(policy.blacklist.mobiles)}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.blacklist.mobiles = parseListInput(
                            event.target.value,
                          );
                        })
                      }
                    />
                  </div>
                  <div>
                    <Label
                      htmlFor='credit-notification-opt-out-creators'
                      className='text-xs text-gray-600'
                    >
                      {t(
                        'module.operationsCreditNotifications.config.fields.optOutCreatorBids',
                      )}
                    </Label>
                    <Input
                      id='credit-notification-opt-out-creators'
                      className='mt-1 h-9'
                      value={formatListInput(policy.opt_out.creator_bids)}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.opt_out.creator_bids = parseListInput(
                            event.target.value,
                          );
                        })
                      }
                    />
                  </div>
                  <div>
                    <Label
                      htmlFor='credit-notification-opt-out-mobiles'
                      className='text-xs text-gray-600'
                    >
                      {t(
                        'module.operationsCreditNotifications.config.fields.optOutMobiles',
                      )}
                    </Label>
                    <Input
                      id='credit-notification-opt-out-mobiles'
                      className='mt-1 h-9'
                      value={formatListInput(policy.opt_out.mobiles)}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.opt_out.mobiles = parseListInput(
                            event.target.value,
                          );
                        })
                      }
                    />
                  </div>
                </div>
              </div>

              <div className='space-y-3 rounded-md border border-gray-200 p-3'>
                <h3 className='text-sm font-semibold text-gray-900'>
                  {t(
                    'module.operationsCreditNotifications.config.sections.budget',
                  )}
                </h3>
                <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2'>
                  <div>
                    <Label
                      htmlFor='credit-notification-daily-sms-limit'
                      className='text-xs text-gray-600'
                    >
                      {t(
                        'module.operationsCreditNotifications.config.fields.dailySmsLimit',
                      )}
                    </Label>
                    <Input
                      id='credit-notification-daily-sms-limit'
                      type='number'
                      min={0}
                      className='mt-1 h-9'
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
                  </div>
                  <div>
                    <Label
                      htmlFor='credit-notification-sms-unit-cost'
                      className='text-xs text-gray-600'
                    >
                      {t(
                        'module.operationsCreditNotifications.config.fields.smsUnitCost',
                      )}
                    </Label>
                    <Input
                      id='credit-notification-sms-unit-cost'
                      className='mt-1 h-9'
                      value={policy.budget.sms_unit_cost}
                      onChange={event =>
                        updatePolicy(draft => {
                          draft.budget.sms_unit_cost = event.target.value;
                        })
                      }
                    />
                  </div>
                </div>
                <div className='flex items-center justify-between gap-4 rounded border border-gray-100 p-2'>
                  <Label
                    htmlFor='credit-notification-dry-run-required'
                    className='text-xs text-gray-600'
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
              </div>
            </div>
            {configError ? (
              <p className='mt-2 text-sm text-red-600'>{configError}</p>
            ) : null}
            <Button
              type='button'
              className='mt-3'
              onClick={saveConfig}
            >
              {t('module.operationsCreditNotifications.actions.applyConfig')}
            </Button>
          </section>

          <section className='rounded-md border border-gray-200 bg-white p-4'>
            <h2 className='text-base font-semibold text-gray-900'>
              {t('module.operationsCreditNotifications.dryRun.title')}
            </h2>
            {dryRunResult ? (
              <pre className='mt-3 max-h-[260px] overflow-auto rounded bg-gray-50 p-3 text-xs text-gray-700'>
                {JSON.stringify(dryRunResult, null, 2)}
              </pre>
            ) : (
              <p className='mt-2 text-sm text-gray-500'>
                {t('module.operationsCreditNotifications.dryRun.empty')}
              </p>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
