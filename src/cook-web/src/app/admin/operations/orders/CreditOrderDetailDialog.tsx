'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminTimezoneHint from '@/app/admin/components/AdminTimezoneHint';
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
import {
  formatBillingCredits,
  formatBillingDateTime,
  formatBillingPrice,
} from '@/lib/billing';
import type { AdminOperationCreditOrderDetailResponse } from '../operation-credit-order-types';
import {
  resolveOperationCreditOrderKindLabel,
  resolveOperationCreditOrderPaymentChannelLabel,
  resolveOperationCreditOrderProductName,
  resolveOperationCreditOrderStatusLabel,
  resolveOperationCreditOrderTypeLabel,
  resolveOperationCreditOrderValidityLabel,
} from '../operation-credit-order-helpers';

type CreditOrderDetailDialogProps = {
  open: boolean;
  billOrderBid?: string;
  onOpenChange?: (open: boolean) => void;
};

type ErrorState = { message: string; code?: number };

type DetailRowProps = {
  label: string;
  value: React.ReactNode;
};

function DetailRow({ label, value }: DetailRowProps) {
  return (
    <div className='grid grid-cols-[112px_minmax(0,1fr)] items-start gap-4 text-sm'>
      <span className='whitespace-nowrap text-muted-foreground'>{label}</span>
      <div className='min-w-0 break-all text-right text-foreground'>
        {value}
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className='space-y-3 rounded-xl border border-border bg-white p-4'>
      <h4 className='text-sm font-semibold text-foreground'>{title}</h4>
      <div className='space-y-2'>{children}</div>
    </section>
  );
}

/**
 * t('module.operationsOrder.creditOrders.detail.title')
 * t('module.operationsOrder.creditOrders.detail.description')
 * t('module.operationsOrder.creditOrders.detail.sections.summary')
 * t('module.operationsOrder.creditOrders.detail.sections.creator')
 * t('module.operationsOrder.creditOrders.detail.sections.product')
 * t('module.operationsOrder.creditOrders.detail.sections.payment')
 * t('module.operationsOrder.creditOrders.detail.sections.grant')
 * t('module.operationsOrder.creditOrders.detail.sections.metadata')
 * t('module.operationsOrder.creditOrders.detail.labels.creatorId')
 * t('module.operationsOrder.creditOrders.detail.labels.failedAt')
 * t('module.operationsOrder.creditOrders.detail.labels.failureCode')
 * t('module.operationsOrder.creditOrders.detail.labels.failureMessage')
 * t('module.operationsOrder.creditOrders.detail.labels.grantSourceId')
 * t('module.operationsOrder.creditOrders.detail.labels.grantSourceType')
 * t('module.operationsOrder.creditOrders.detail.labels.grantedCredits')
 * t('module.operationsOrder.creditOrders.detail.labels.orderType')
 * t('module.operationsOrder.creditOrders.detail.labels.paidAt')
 * t('module.operationsOrder.creditOrders.detail.labels.productCode')
 * t('module.operationsOrder.creditOrders.detail.labels.providerReference')
 * t('module.operationsOrder.creditOrders.detail.labels.validFrom')
 */
export default function CreditOrderDetailDialog({
  open,
  billOrderBid,
  onOpenChange,
}: CreditOrderDetailDialogProps) {
  const { t, i18n } = useTranslation();
  const { t: tOperationsOrder } = useTranslation('module.operationsOrder');
  const [detail, setDetail] =
    React.useState<AdminOperationCreditOrderDetailResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<ErrorState | null>(null);
  const fetchRequestIdRef = React.useRef(0);

  const emptyValue = React.useMemo(() => t('module.order.emptyValue'), [t]);

  const fetchDetail = React.useCallback(async () => {
    if (!billOrderBid) {
      fetchRequestIdRef.current += 1;
      setDetail(null);
      setLoading(false);
      return;
    }

    const requestId = fetchRequestIdRef.current + 1;
    fetchRequestIdRef.current = requestId;
    setLoading(true);
    setError(null);

    try {
      const result = (await api.getAdminOperationCreditOrderDetail({
        bill_order_bid: billOrderBid,
      })) as AdminOperationCreditOrderDetailResponse;
      if (requestId !== fetchRequestIdRef.current) {
        return;
      }
      setDetail(result);
    } catch (requestError) {
      if (requestId !== fetchRequestIdRef.current) {
        return;
      }
      if (requestError instanceof ErrorWithCode) {
        setError({
          message: requestError.message,
          code: requestError.code,
        });
      } else if (requestError instanceof Error) {
        setError({ message: requestError.message });
      } else {
        setError({ message: t('common.core.unknownError') });
      }
    } finally {
      if (requestId === fetchRequestIdRef.current) {
        setLoading(false);
      }
    }
  }, [billOrderBid, t]);

  React.useEffect(() => {
    if (open) {
      void fetchDetail();
    }
  }, [fetchDetail, open]);

  React.useEffect(() => {
    if (!open) {
      fetchRequestIdRef.current += 1;
      setDetail(null);
      setError(null);
      setLoading(false);
    }
  }, [open]);

  const order = detail?.order;
  const grant = detail?.grant;
  const metadata = detail?.metadata;
  const locale = i18n.language || 'en-US';
  const creatorContact =
    order?.creator_email ||
    order?.creator_mobile ||
    order?.creator_identify ||
    '';
  const kindLabel = order
    ? resolveOperationCreditOrderKindLabel(t, order.credit_order_kind)
    : emptyValue;
  const statusLabel = resolveOperationCreditOrderStatusLabel(
    t,
    order?.status,
    emptyValue,
  );
  const orderTypeLabel = resolveOperationCreditOrderTypeLabel(
    t,
    order?.order_type,
    emptyValue,
  );
  const paymentChannelLabel = order
    ? resolveOperationCreditOrderPaymentChannelLabel(t, order)
    : emptyValue;
  const productName = order
    ? resolveOperationCreditOrderProductName(t, order, emptyValue)
    : emptyValue;
  const validityLabel = order
    ? resolveOperationCreditOrderValidityLabel(
        t,
        locale,
        order.valid_from,
        order.valid_to,
        emptyValue,
      )
    : emptyValue;

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
    >
      <SheetContent className='flex w-full flex-col overflow-hidden border-l border-border bg-white p-0 sm:w-[360px] md:w-[460px] lg:w-[560px]'>
        <SheetHeader className='border-b border-border px-6 py-4 pr-12'>
          <SheetTitle className='text-base font-semibold text-foreground'>
            {tOperationsOrder('creditOrders.detail.title')}
          </SheetTitle>
          <AdminTimezoneHint
            namespace='module.operationsOrder'
            textKey='timezoneHint'
          />
          <SheetDescription className='sr-only'>
            {tOperationsOrder('creditOrders.detail.description')}
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
              onRetry={() => void fetchDetail()}
            />
          ) : null}

          {!loading && !error && order ? (
            <div className='space-y-6'>
              <Section
                title={tOperationsOrder('creditOrders.detail.sections.summary')}
              >
                <DetailRow
                  label={tOperationsOrder('creditOrders.table.orderId')}
                  value={order.bill_order_bid}
                />
                <DetailRow
                  label={t('module.order.fields.status')}
                  value={statusLabel}
                />
                <DetailRow
                  label={tOperationsOrder('creditOrders.table.orderKind')}
                  value={kindLabel}
                />
                <DetailRow
                  label={tOperationsOrder(
                    'creditOrders.detail.labels.orderType',
                  )}
                  value={orderTypeLabel}
                />
                <DetailRow
                  label={t('module.order.fields.createdAt')}
                  value={
                    formatBillingDateTime(order.created_at, locale) ||
                    emptyValue
                  }
                />
                <DetailRow
                  label={tOperationsOrder('creditOrders.detail.labels.paidAt')}
                  value={
                    formatBillingDateTime(order.paid_at, locale) || emptyValue
                  }
                />
                {order.failed_at ? (
                  <DetailRow
                    label={tOperationsOrder(
                      'creditOrders.detail.labels.failedAt',
                    )}
                    value={
                      formatBillingDateTime(order.failed_at, locale) ||
                      emptyValue
                    }
                  />
                ) : null}
              </Section>

              <Section
                title={tOperationsOrder('creditOrders.detail.sections.creator')}
              >
                <DetailRow
                  label={tOperationsOrder('creditOrders.table.creator')}
                  value={creatorContact || emptyValue}
                />
                <DetailRow
                  label={t('module.operationsUser.table.nickname')}
                  value={order.creator_nickname || emptyValue}
                />
                <DetailRow
                  label={tOperationsOrder(
                    'creditOrders.detail.labels.creatorId',
                  )}
                  value={order.creator_bid || emptyValue}
                />
              </Section>

              <Section
                title={tOperationsOrder('creditOrders.detail.sections.product')}
              >
                <DetailRow
                  label={tOperationsOrder('creditOrders.table.product')}
                  value={productName}
                />
                <DetailRow
                  label={tOperationsOrder('creditOrders.table.creditAmount')}
                  value={tOperationsOrder('creditOrders.creditAmountValue', {
                    credits: formatBillingCredits(order.credit_amount, locale),
                  })}
                />
                <DetailRow
                  label={tOperationsOrder('creditOrders.table.validTo')}
                  value={validityLabel}
                />
              </Section>

              <Section
                title={tOperationsOrder('creditOrders.detail.sections.payment')}
              >
                <DetailRow
                  label={tOperationsOrder('creditOrders.table.paymentChannel')}
                  value={paymentChannelLabel}
                />
                <DetailRow
                  label={t('module.order.fields.payable')}
                  value={formatBillingPrice(
                    order.payable_amount,
                    order.currency,
                    locale,
                  )}
                />
                <DetailRow
                  label={t('module.order.fields.paid')}
                  value={formatBillingPrice(
                    order.paid_amount,
                    order.currency,
                    locale,
                  )}
                />
                <DetailRow
                  label={tOperationsOrder(
                    'creditOrders.detail.labels.providerReference',
                  )}
                  value={order.provider_reference_id || emptyValue}
                />
                {order.failure_code ? (
                  <DetailRow
                    label={tOperationsOrder(
                      'creditOrders.detail.labels.failureCode',
                    )}
                    value={order.failure_code}
                  />
                ) : null}
                {order.failure_message ? (
                  <DetailRow
                    label={tOperationsOrder(
                      'creditOrders.detail.labels.failureMessage',
                    )}
                    value={order.failure_message}
                  />
                ) : null}
              </Section>

              {grant ? (
                <Section
                  title={tOperationsOrder('creditOrders.detail.sections.grant')}
                >
                  <DetailRow
                    label={tOperationsOrder(
                      'creditOrders.detail.labels.grantedCredits',
                    )}
                    value={tOperationsOrder('creditOrders.creditAmountValue', {
                      credits: formatBillingCredits(
                        grant.granted_credits,
                        locale,
                      ),
                    })}
                  />
                  <DetailRow
                    label={tOperationsOrder(
                      'creditOrders.detail.labels.grantSourceType',
                    )}
                    value={grant.source_type || emptyValue}
                  />
                  <DetailRow
                    label={tOperationsOrder(
                      'creditOrders.detail.labels.grantSourceId',
                    )}
                    value={grant.source_bid || emptyValue}
                  />
                  <DetailRow
                    label={tOperationsOrder(
                      'creditOrders.detail.labels.validFrom',
                    )}
                    value={
                      formatBillingDateTime(grant.valid_from, locale) ||
                      emptyValue
                    }
                  />
                  <DetailRow
                    label={tOperationsOrder('creditOrders.table.validTo')}
                    value={resolveOperationCreditOrderValidityLabel(
                      t,
                      locale,
                      grant.valid_from,
                      grant.valid_to,
                      emptyValue,
                    )}
                  />
                </Section>
              ) : null}

              {metadata ? (
                <details className='rounded-xl border border-border bg-white p-4'>
                  <summary className='cursor-pointer text-sm font-semibold text-foreground'>
                    {tOperationsOrder('creditOrders.detail.sections.metadata')}
                  </summary>
                  <pre className='mt-3 overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs leading-6 text-slate-700'>
                    {JSON.stringify(metadata, null, 2)}
                  </pre>
                </details>
              ) : null}
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
