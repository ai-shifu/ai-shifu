import React, { useMemo } from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { Button } from '@/components/ui/Button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import { Skeleton } from '@/components/ui/Skeleton';
import type { BillingOrderDetail } from '@/types/billing';
import {
  formatBillingDateTime,
  formatBillingPrice,
  registerBillingTranslationUsage,
  resolveBillingOrderStatusLabel,
  resolveBillingOrderTypeLabel,
  resolveBillingPaymentModeLabel,
  resolveBillingProviderLabel,
} from '@/lib/billing';

type BillingOrderDetailSheetProps = {
  open: boolean;
  orderBid?: string;
  onOpenChange: (open: boolean) => void;
};

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className='flex items-start justify-between gap-4 border-b border-slate-100 py-3 text-sm last:border-b-0'>
      <span className='text-slate-500'>{label}</span>
      <span className='max-w-[60%] break-words text-right font-medium text-slate-900'>
        {value}
      </span>
    </div>
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className='space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm'>
      <h4 className='text-sm font-semibold text-slate-900'>{title}</h4>
      <div className='space-y-1'>{children}</div>
    </section>
  );
}

function fallbackValue(
  value: string | null | undefined,
  fallback: string,
): string {
  const normalizedValue = String(value || '').trim();
  return normalizedValue || fallback;
}

export function BillingOrderDetailSheet({
  open,
  orderBid,
  onOpenChange,
}: BillingOrderDetailSheetProps) {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const emptyValue = t('module.billing.sidebar.placeholderValue');

  const {
    data: detail,
    error,
    isLoading,
    mutate,
  } = useSWR<BillingOrderDetail>(
    open && orderBid ? ['billing-order-detail', orderBid] : null,
    async () =>
      (await api.getBillingOrderDetail({
        billing_order_bid: orderBid,
      })) as BillingOrderDetail,
    {
      revalidateOnFocus: false,
    },
  );

  const metadataText = useMemo(() => {
    if (!detail?.metadata || !Object.keys(detail.metadata).length) {
      return '';
    }
    try {
      return JSON.stringify(detail.metadata, null, 2);
    } catch {
      return String(detail.metadata);
    }
  }, [detail?.metadata]);

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
    >
      <SheetContent className='flex w-full flex-col overflow-hidden border-l border-border bg-white p-0 sm:w-[360px] md:w-[420px] lg:w-[520px]'>
        <SheetHeader className='border-b border-border px-6 py-4 pr-12'>
          <SheetTitle>{t('module.billing.orders.detail.title')}</SheetTitle>
          <SheetDescription>{orderBid || ''}</SheetDescription>
        </SheetHeader>

        <div className='flex-1 overflow-auto px-6 py-4'>
          {isLoading ? (
            <div className='space-y-4'>
              <Skeleton className='h-28 rounded-2xl' />
              <Skeleton className='h-32 rounded-2xl' />
              <Skeleton className='h-48 rounded-2xl' />
            </div>
          ) : null}

          {!isLoading && error ? (
            <div className='space-y-3 rounded-2xl border border-rose-200 bg-rose-50 p-4'>
              <p className='text-sm text-rose-700'>
                {t('module.billing.orders.detail.loadError')}
              </p>
              <Button
                variant='outline'
                size='sm'
                onClick={() => void mutate()}
              >
                {t('common.core.retry')}
              </Button>
            </div>
          ) : null}

          {!isLoading && !error && detail ? (
            <div className='space-y-6'>
              <DetailSection
                title={t('module.billing.orders.detail.sections.summary')}
              >
                <DetailRow
                  label={t('module.billing.orders.detail.fields.orderType')}
                  value={resolveBillingOrderTypeLabel(t, detail.order_type)}
                />
                <DetailRow
                  label={t('module.billing.orders.detail.fields.status')}
                  value={resolveBillingOrderStatusLabel(t, detail.status)}
                />
                <DetailRow
                  label={t('module.billing.orders.detail.fields.provider')}
                  value={resolveBillingProviderLabel(
                    t,
                    detail.payment_provider,
                  )}
                />
                <DetailRow
                  label={t('module.billing.orders.detail.fields.paymentMode')}
                  value={resolveBillingPaymentModeLabel(t, detail.payment_mode)}
                />
                <DetailRow
                  label={t('module.billing.orders.detail.fields.orderBid')}
                  value={detail.billing_order_bid}
                />
              </DetailSection>

              <DetailSection
                title={t('module.billing.orders.detail.sections.amounts')}
              >
                <DetailRow
                  label={t('module.billing.orders.detail.fields.payableAmount')}
                  value={formatBillingPrice(
                    detail.payable_amount,
                    detail.currency,
                    i18n.language,
                  )}
                />
                <DetailRow
                  label={t('module.billing.orders.detail.fields.paidAmount')}
                  value={formatBillingPrice(
                    detail.paid_amount,
                    detail.currency,
                    i18n.language,
                  )}
                />
                <DetailRow
                  label={t('module.billing.orders.detail.fields.createdAt')}
                  value={formatBillingDateTime(
                    detail.created_at,
                    i18n.language,
                  )}
                />
                <DetailRow
                  label={t('module.billing.orders.detail.fields.paidAt')}
                  value={
                    formatBillingDateTime(detail.paid_at, i18n.language) ||
                    emptyValue
                  }
                />
                <DetailRow
                  label={t('module.billing.orders.detail.fields.failedAt')}
                  value={
                    formatBillingDateTime(detail.failed_at, i18n.language) ||
                    emptyValue
                  }
                />
                <DetailRow
                  label={t('module.billing.orders.detail.fields.refundedAt')}
                  value={
                    formatBillingDateTime(detail.refunded_at, i18n.language) ||
                    emptyValue
                  }
                />
              </DetailSection>

              <DetailSection
                title={t('module.billing.orders.detail.sections.references')}
              >
                <DetailRow
                  label={t('module.billing.orders.detail.fields.productBid')}
                  value={fallbackValue(detail.product_bid, emptyValue)}
                />
                <DetailRow
                  label={t(
                    'module.billing.orders.detail.fields.subscriptionBid',
                  )}
                  value={fallbackValue(detail.subscription_bid, emptyValue)}
                />
                <DetailRow
                  label={t(
                    'module.billing.orders.detail.fields.providerReferenceId',
                  )}
                  value={fallbackValue(
                    detail.provider_reference_id,
                    emptyValue,
                  )}
                />
                <DetailRow
                  label={t('module.billing.orders.detail.fields.failureCode')}
                  value={fallbackValue(detail.failure_code, emptyValue)}
                />
                <DetailRow
                  label={t(
                    'module.billing.orders.detail.fields.failureMessage',
                  )}
                  value={fallbackValue(detail.failure_message, emptyValue)}
                />
              </DetailSection>

              <DetailSection
                title={t('module.billing.orders.detail.sections.metadata')}
              >
                {metadataText ? (
                  <pre className='overflow-x-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100'>
                    {metadataText}
                  </pre>
                ) : (
                  <div className='rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500'>
                    {t('module.billing.orders.detail.emptyMetadata')}
                  </div>
                )}
              </DetailSection>
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
