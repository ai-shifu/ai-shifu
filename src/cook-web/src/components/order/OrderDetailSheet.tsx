import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import { Badge } from '@/components/ui/Badge';
import Loading from '@/components/loading';
import ErrorDisplay from '@/components/ErrorDisplay';
import api from '@/api';
import { useTranslation } from 'react-i18next';
import { ErrorWithCode } from '@/lib/request';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import type { OrderDetail } from './order-types';

type OrderDetailSheetProps = {
  open: boolean;
  orderBid?: string;
  onOpenChange?: (open: boolean) => void;
};

const fallbackValue = (value: string | undefined, fallback: string) => {
  if (!value) {
    return fallback;
  }
  return value;
};

const DetailRow = ({ label, value }: { label: string; value: string }) => (
  <div className='flex items-start justify-between gap-4 text-sm'>
    <span className='text-muted-foreground'>{label}</span>
    <span className='text-right text-foreground break-words'>{value}</span>
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

const OrderDetailSheet = ({
  open,
  orderBid,
  onOpenChange,
}: OrderDetailSheetProps) => {
  const { t } = useTranslation();
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const defaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );
  const contactType = useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const isEmailMode = contactType === 'email';
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ message: string; code?: number } | null>(
    null,
  );

  const emptyValue = useMemo(() => t('module.order.emptyValue'), [t]);
  const paymentStatusLabels = useMemo(
    () => ({
      pending: t('module.order.paymentStatus.pending'),
      paid: t('module.order.paymentStatus.paid'),
      refunded: t('module.order.paymentStatus.refunded'),
      closed: t('module.order.paymentStatus.closed'),
      failed: t('module.order.paymentStatus.failed'),
      unknown: t('module.order.paymentStatus.unknown'),
    }),
    [t],
  );
  const paymentChannelLabels = useMemo(
    () => ({
      pingxx: t('module.order.paymentChannel.pingxx'),
      stripe: t('module.order.paymentChannel.stripe'),
      unknown: t('module.order.paymentChannel.unknown'),
    }),
    [t],
  );
  const activeStatusLabels = useMemo(
    () => ({
      active: t('module.order.activeStatus.active'),
      failed: t('module.order.activeStatus.failed'),
      unknown: t('module.order.activeStatus.unknown'),
    }),
    [t],
  );
  const couponStatusLabels = useMemo(
    () => ({
      inactive: t('module.order.couponStatus.inactive'),
      active: t('module.order.couponStatus.active'),
      used: t('module.order.couponStatus.used'),
      timeout: t('module.order.couponStatus.timeout'),
      unknown: t('module.order.couponStatus.unknown'),
    }),
    [t],
  );
  const couponTypeLabels = useMemo(
    () => ({
      fixed: t('module.order.couponType.fixed'),
      percent: t('module.order.couponType.percent'),
      unknown: t('module.order.couponType.unknown'),
    }),
    [t],
  );
  const paymentStatusByCode = useMemo(
    () => ({
      0: paymentStatusLabels.pending,
      1: paymentStatusLabels.paid,
      2: paymentStatusLabels.refunded,
      3: paymentStatusLabels.closed,
      4: paymentStatusLabels.failed,
    }),
    [paymentStatusLabels],
  );
  const activityStatusByCode = useMemo(
    () => ({
      4101: activeStatusLabels.active,
      4102: activeStatusLabels.failed,
    }),
    [activeStatusLabels],
  );
  const couponStatusByCode = useMemo(
    () => ({
      901: couponStatusLabels.inactive,
      902: couponStatusLabels.active,
      903: couponStatusLabels.used,
      904: couponStatusLabels.timeout,
    }),
    [couponStatusLabels],
  );
  const couponTypeByCode = useMemo(
    () => ({
      701: couponTypeLabels.fixed,
      702: couponTypeLabels.percent,
    }),
    [couponTypeLabels],
  );

  const fetchDetail = useCallback(async () => {
    if (!orderBid) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.getAdminOrderDetail({ order_bid: orderBid });
      setDetail(result);
    } catch (err) {
      if (err instanceof ErrorWithCode) {
        setError({ message: err.message, code: err.code });
      } else if (err instanceof Error) {
        setError({ message: err.message });
      } else {
        setError({ message: t('common.core.unknownError') });
      }
    } finally {
      setLoading(false);
    }
  }, [orderBid, t]);

  useEffect(() => {
    if (open) {
      fetchDetail();
    }
  }, [open, fetchDetail]);

  useEffect(() => {
    if (!open) {
      setDetail(null);
      setError(null);
      setLoading(false);
    }
  }, [open]);

  const summary = detail?.order;
  const payment = detail?.payment;
  const paymentChannelLabel = summary?.payment_channel_key
    ? t(summary.payment_channel_key)
    : paymentChannelLabels[summary?.payment_channel as 'pingxx' | 'stripe'] ||
      paymentChannelLabels.unknown;
  const paymentStatusLabel = payment?.status_key
    ? t(payment.status_key)
    : paymentStatusByCode[payment?.status ?? 0] || paymentStatusLabels.unknown;

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
    >
      <SheetContent className='flex w-full flex-col overflow-hidden border-l border-border bg-white p-0 sm:w-[360px] md:w-[420px] lg:w-[520px]'>
        <SheetHeader className='border-b border-border px-6 py-4 pr-12'>
          <SheetTitle className='flex flex-col gap-2'>
            <span className='text-xs font-medium text-muted-foreground'>
              {t('module.order.detailTitle')}
            </span>
            <span className='text-base font-semibold text-foreground'>
              {summary?.order_bid || t('module.order.detailFallback')}
            </span>
          </SheetTitle>
        </SheetHeader>

        <div className='flex-1 overflow-y-auto px-6 py-5'>
          {loading && (
            <div className='flex h-40 items-center justify-center'>
              <Loading />
            </div>
          )}

          {!loading && error && (
            <ErrorDisplay
              errorCode={error.code || 0}
              errorMessage={error.message}
              onRetry={fetchDetail}
            />
          )}

          {!loading && !error && detail && summary && (
            <div className='space-y-6'>
              <Section title={t('module.order.sections.summary')}>
                <DetailRow
                  label={t('module.order.fields.shifu')}
                  value={fallbackValue(summary.shifu_name, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.user')}
                  value={fallbackValue(
                    (isEmailMode ? summary.user_email : summary.user_mobile) ||
                      summary.user_bid,
                    emptyValue,
                  )}
                />
                <DetailRow
                  label={t('module.order.fields.payable')}
                  value={summary.payable_price}
                />
                <DetailRow
                  label={t('module.order.fields.paid')}
                  value={summary.paid_price}
                />
                <DetailRow
                  label={t('module.order.fields.discount')}
                  value={summary.discount_amount}
                />
                <DetailRow
                  label={t('module.order.fields.status')}
                  value={t(summary.status_key)}
                />
                <DetailRow
                  label={t('module.order.fields.paymentChannel')}
                  value={paymentChannelLabel}
                />
                <DetailRow
                  label={t('module.order.fields.createdAt')}
                  value={summary.created_at}
                />
                <DetailRow
                  label={t('module.order.fields.updatedAt')}
                  value={summary.updated_at}
                />
              </Section>

              <Section title={t('module.order.sections.payment')}>
                <DetailRow
                  label={t('module.order.fields.paymentStatus')}
                  value={paymentStatusLabel}
                />
                <DetailRow
                  label={t('module.order.fields.paymentAmount')}
                  value={fallbackValue(payment?.amount, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.currency')}
                  value={fallbackValue(payment?.currency, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.transactionNo')}
                  value={fallbackValue(payment?.transaction_no, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.chargeId')}
                  value={fallbackValue(payment?.charge_id, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.paymentIntent')}
                  value={fallbackValue(payment?.payment_intent_id, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.checkoutSession')}
                  value={fallbackValue(
                    payment?.checkout_session_id,
                    emptyValue,
                  )}
                />
                <DetailRow
                  label={t('module.order.fields.latestCharge')}
                  value={fallbackValue(payment?.latest_charge_id, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.receipt')}
                  value={fallbackValue(payment?.receipt_url, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.paymentMethod')}
                  value={fallbackValue(payment?.payment_method, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.paymentCreatedAt')}
                  value={fallbackValue(payment?.created_at, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.paymentUpdatedAt')}
                  value={fallbackValue(payment?.updated_at, emptyValue)}
                />
              </Section>

              <Section title={t('module.order.sections.activities')}>
                {detail.activities.length === 0 && (
                  <p className='text-sm text-muted-foreground'>
                    {t('module.order.emptyActivities')}
                  </p>
                )}
                {detail.activities.map(activity => (
                  <div
                    key={`${activity.active_id}-${activity.created_at}`}
                    className='rounded-md border border-border bg-muted/30 px-3 py-2 text-sm'
                  >
                    <div className='flex items-center justify-between gap-2'>
                      <span className='font-medium text-foreground'>
                        {activity.active_name || activity.active_id}
                      </span>
                      <Badge variant='outline'>
                        {activity.status_key
                          ? t(activity.status_key)
                          : activityStatusByCode[activity.status] ||
                            activeStatusLabels.unknown}
                      </Badge>
                    </div>
                    <div className='mt-2 flex items-center justify-between text-xs text-muted-foreground'>
                      <span>
                        {t('module.order.fields.activityPrice')}:{' '}
                        {activity.price}
                      </span>
                      <span>{activity.created_at}</span>
                    </div>
                  </div>
                ))}
              </Section>

              <Section title={t('module.order.sections.coupons')}>
                {detail.coupons.length === 0 && (
                  <p className='text-sm text-muted-foreground'>
                    {t('module.order.emptyCoupons')}
                  </p>
                )}
                {detail.coupons.map(coupon => (
                  <div
                    key={`${coupon.coupon_bid}-${coupon.code}`}
                    className='rounded-md border border-border bg-muted/30 px-3 py-2 text-sm'
                  >
                    <div className='flex items-center justify-between gap-2'>
                      <span className='font-medium text-foreground'>
                        {coupon.name || coupon.code}
                      </span>
                      <Badge variant='outline'>
                        {coupon.status_key
                          ? t(coupon.status_key)
                          : couponStatusByCode[coupon.status] ||
                            couponStatusLabels.unknown}
                      </Badge>
                    </div>
                    <div className='mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground'>
                      <span>
                        {t('module.order.fields.couponType')}:{' '}
                        {coupon.discount_type_key
                          ? t(coupon.discount_type_key)
                          : couponTypeByCode[coupon.discount_type] ||
                            couponTypeLabels.unknown}
                      </span>
                      <span>
                        {t('module.order.fields.couponValue')}: {coupon.value}
                      </span>
                      <span>{coupon.created_at}</span>
                    </div>
                  </div>
                ))}
              </Section>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default OrderDetailSheet;
