import React from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import { ErrorWithCode } from '@/lib/request';
import type { AdminOperationCreditNotificationItem } from '../operation-credit-notification-types';
import {
  EMPTY_LABEL,
  resolveCreditNotificationErrorText,
  resolveNotificationDeliveryStatus,
  resolveNotificationSkipReason,
} from './creditNotificationUtils';

type CreditNotificationDetailSheetProps = {
  notificationBid: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  resolveTypeLabel: (value: string) => string;
  resolveDeliveryStatusLabel: (value: string) => string;
  resolveSkipReasonLabel: (value: string) => string;
  resolveSourceTypeLabel: (value: string) => string;
};

const isEmptyObject = (value: Record<string, unknown>) =>
  Object.keys(value || {}).length === 0;

const formatValue = (value?: string | null) => value || EMPTY_LABEL;

const formatDateTime = (value?: string | null) =>
  value ? formatAdminUtcDateTime(value) || EMPTY_LABEL : EMPTY_LABEL;

const formatJson = (value?: Record<string, unknown> | null) => {
  if (!value || isEmptyObject(value)) {
    return EMPTY_LABEL;
  }
  return JSON.stringify(value, null, 2);
};

const formatParamValue = (value: unknown) => {
  if (value === null || value === undefined || value === '') {
    return EMPTY_LABEL;
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
};

const DetailRow = ({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) => (
  <div className='grid grid-cols-[112px_minmax(0,1fr)] items-start gap-4 text-sm'>
    <span className='whitespace-nowrap text-muted-foreground'>{label}</span>
    <span className='min-w-0 break-all text-right text-foreground'>
      {value}
    </span>
  </div>
);

const JsonRow = ({ label, value }: { label: string; value: string }) => (
  <div className='space-y-2 text-sm'>
    <div className='text-muted-foreground'>{label}</div>
    {value === EMPTY_LABEL ? (
      <div className='text-right text-foreground'>{EMPTY_LABEL}</div>
    ) : (
      <pre className='max-h-48 overflow-auto rounded-md bg-muted/40 p-3 text-left text-xs leading-5 text-foreground'>
        {value}
      </pre>
    )}
  </div>
);

const Section = ({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) => (
  <section className='space-y-3 rounded-lg border border-border bg-white p-4'>
    <h4 className='text-sm font-semibold text-foreground'>{title}</h4>
    <div className='space-y-2'>{children}</div>
  </section>
);

const SummaryCard = ({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) => (
  <div className='min-w-0 rounded-lg border border-border bg-muted/20 px-3 py-2'>
    <div className='text-xs text-muted-foreground'>{label}</div>
    <div className='mt-1 min-w-0 truncate text-sm text-foreground'>
      {children}
    </div>
  </div>
);

const TemplateParamRows = ({
  params,
  labelForParam,
}: {
  params: Record<string, unknown>;
  labelForParam: (key: string) => string;
}) => {
  const entries = Object.entries(params || {}).filter(([, value]) =>
    Boolean(formatParamValue(value) !== EMPTY_LABEL),
  );

  if (entries.length === 0) {
    return (
      <div className='text-right text-sm text-foreground'>{EMPTY_LABEL}</div>
    );
  }

  return (
    <div className='space-y-2'>
      {entries.map(([key, value]) => (
        <DetailRow
          key={key}
          label={labelForParam(key)}
          value={formatParamValue(value)}
        />
      ))}
    </div>
  );
};

export function CreditNotificationDetailSheet({
  notificationBid,
  open,
  onOpenChange,
  resolveTypeLabel,
  resolveDeliveryStatusLabel,
  resolveSkipReasonLabel,
  resolveSourceTypeLabel,
}: CreditNotificationDetailSheetProps) {
  const { t } = useTranslation();
  const [item, setItem] =
    React.useState<AdminOperationCreditNotificationItem | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<{
    message: string;
    code?: number;
  } | null>(null);
  const requestIdRef = React.useRef(0);

  const fetchDetail = React.useCallback(async () => {
    if (!notificationBid) {
      requestIdRef.current += 1;
      setItem(current => (current === null ? current : null));
      setLoading(current => (current ? false : current));
      setError(current => (current === null ? current : null));
      return;
    }
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    setError(null);
    try {
      const response = (await api.getAdminOperationCreditNotificationDetail({
        notification_bid: notificationBid,
      })) as AdminOperationCreditNotificationItem;
      if (requestId !== requestIdRef.current) {
        return;
      }
      setItem(response);
    } catch (requestError) {
      if (requestId !== requestIdRef.current) {
        return;
      }
      const resolvedError = requestError as ErrorWithCode;
      setError({
        message: resolvedError.message || t('common.core.unknownError'),
        code: resolvedError.code,
      });
      setItem(null);
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [notificationBid, t]);

  React.useEffect(() => {
    if (open) {
      void fetchDetail();
    }
  }, [fetchDetail, open]);

  React.useEffect(() => {
    if (!open) {
      requestIdRef.current += 1;
      setItem(current => (current === null ? current : null));
      setError(current => (current === null ? current : null));
      setLoading(current => (current ? false : current));
    }
  }, [open]);

  const sourceObjectLabel = item
    ? t(
        `module.operationsCreditNotifications.detail.sourceObject.${item.source_type}`,
        item.source_type || EMPTY_LABEL,
      )
    : EMPTY_LABEL;
  const labelForParam = React.useCallback(
    (key: string) =>
      t(`module.operationsCreditNotifications.detail.params.${key}`, key),
    [t],
  );
  const skipReason = item ? resolveNotificationSkipReason(item) : '';

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
    >
      <SheetContent className='flex w-full flex-col overflow-hidden border-l border-border bg-white p-0 sm:w-[360px] md:w-[480px] lg:w-[600px]'>
        <SheetHeader className='border-b border-border px-6 py-4 pr-12'>
          <SheetTitle className='text-base font-semibold text-foreground'>
            {t('module.operationsCreditNotifications.detail.title')}
          </SheetTitle>
          <SheetDescription className='sr-only'>
            {t('module.operationsCreditNotifications.detail.description')}
          </SheetDescription>
        </SheetHeader>

        <div className='flex-1 overflow-y-auto px-6 py-5'>
          {loading ? (
            <div className='flex h-40 items-center justify-center'>
              <Loading />
            </div>
          ) : null}

          {!loading && error ? (
            <ErrorDisplay
              errorCode={error.code || 0}
              errorMessage={error.message}
              onRetry={fetchDetail}
            />
          ) : null}

          {!loading && !error && item ? (
            <div className='space-y-5'>
              <div className='grid gap-2 sm:grid-cols-3'>
                <SummaryCard
                  label={t(
                    'module.operationsCreditNotifications.detail.summary.creator',
                  )}
                >
                  {formatValue(item.mobile_snapshot)}
                  {item.creator_nickname ? ` / ${item.creator_nickname}` : ''}
                </SummaryCard>
                <SummaryCard
                  label={t(
                    'module.operationsCreditNotifications.detail.summary.notification',
                  )}
                >
                  {resolveTypeLabel(item.notification_type)}
                </SummaryCard>
                <SummaryCard
                  label={t(
                    'module.operationsCreditNotifications.detail.summary.status',
                  )}
                >
                  {resolveDeliveryStatusLabel(
                    resolveNotificationDeliveryStatus(item),
                  )}
                </SummaryCard>
              </div>

              <Section
                title={t(
                  'module.operationsCreditNotifications.detail.sections.delivery',
                )}
              >
                <DetailRow
                  label={t(
                    'module.operationsCreditNotifications.detail.fields.createdAt',
                  )}
                  value={formatDateTime(item.created_at)}
                />
                <DetailRow
                  label={t(
                    'module.operationsCreditNotifications.detail.fields.requestedAt',
                  )}
                  value={formatDateTime(item.requested_at)}
                />
                <DetailRow
                  label={t(
                    'module.operationsCreditNotifications.detail.fields.attemptedAt',
                  )}
                  value={formatDateTime(item.attempted_at)}
                />
                <DetailRow
                  label={t(
                    'module.operationsCreditNotifications.detail.fields.sentAt',
                  )}
                  value={formatDateTime(item.sent_at)}
                />
                {skipReason ? (
                  <DetailRow
                    label={t(
                      'module.operationsCreditNotifications.detail.fields.skipReason',
                    )}
                    value={resolveSkipReasonLabel(skipReason)}
                  />
                ) : null}
                <DetailRow
                  label={t(
                    'module.operationsCreditNotifications.detail.fields.errorMessage',
                  )}
                  value={formatValue(
                    resolveCreditNotificationErrorText(
                      t,
                      item.error_code,
                      item.error_message,
                    ),
                  )}
                />
              </Section>

              <Section
                title={t(
                  'module.operationsCreditNotifications.detail.sections.trigger',
                )}
              >
                <DetailRow
                  label={t('module.operationsCreditNotifications.table.source')}
                  value={resolveSourceTypeLabel(item.source_type)}
                />
                <DetailRow
                  label={t(
                    'module.operationsCreditNotifications.detail.fields.sourceObject',
                  )}
                  value={sourceObjectLabel}
                />
                <DetailRow
                  label={t(
                    'module.operationsCreditNotifications.detail.fields.sourceBid',
                  )}
                  value={formatValue(item.source_bid)}
                />
              </Section>

              <Section
                title={t(
                  'module.operationsCreditNotifications.detail.sections.message',
                )}
              >
                <DetailRow
                  label={t(
                    'module.operationsCreditNotifications.detail.fields.templateName',
                  )}
                  value={formatValue(item.template_name)}
                />
                <DetailRow
                  label={t(
                    'module.operationsCreditNotifications.detail.fields.templateCode',
                  )}
                  value={formatValue(item.template_code)}
                />
                <div className='border-t border-border/70 pt-3'>
                  <TemplateParamRows
                    params={item.template_params || {}}
                    labelForParam={labelForParam}
                  />
                </div>
              </Section>

              <details className='rounded-lg border border-border bg-white p-4'>
                <summary className='cursor-pointer text-sm font-semibold text-foreground'>
                  {t(
                    'module.operationsCreditNotifications.detail.sections.diagnostics',
                  )}
                </summary>
                <div className='mt-3 space-y-2'>
                  <DetailRow
                    label={t(
                      'module.operationsCreditNotifications.detail.fields.notificationBid',
                    )}
                    value={formatValue(item.notification_bid)}
                  />
                  <DetailRow
                    label={t(
                      'module.operationsCreditNotifications.detail.fields.dedupeKey',
                    )}
                    value={formatValue(item.dedupe_key)}
                  />
                  <DetailRow
                    label={t(
                      'module.operationsCreditNotifications.detail.fields.errorCode',
                    )}
                    value={formatValue(item.error_code)}
                  />
                  <DetailRow
                    label={t(
                      'module.operationsCreditNotifications.detail.fields.updatedAt',
                    )}
                    value={formatDateTime(item.updated_at)}
                  />
                  <JsonRow
                    label={t(
                      'module.operationsCreditNotifications.detail.fields.providerResponse',
                    )}
                    value={formatJson(item.provider_response || {})}
                  />
                  <JsonRow
                    label={t(
                      'module.operationsCreditNotifications.detail.fields.policySnapshot',
                    )}
                    value={formatJson(item.policy_snapshot || {})}
                  />
                  <JsonRow
                    label={t(
                      'module.operationsCreditNotifications.detail.fields.metadata',
                    )}
                    value={formatJson(item.metadata || {})}
                  />
                </div>
              </details>
            </div>
          ) : null}

          {!loading && !error && !item ? (
            <div className='py-10 text-center text-sm text-muted-foreground'>
              {t('module.operationsCreditNotifications.detail.fallback')}
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
