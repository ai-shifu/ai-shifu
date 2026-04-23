'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import api from '@/api';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Badge } from '@/components/ui/Badge';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { ErrorWithCode } from '@/lib/request';
import { useTranslation } from 'react-i18next';
import { getOperationOrderSourceLabel } from '../operation-order-source';
import type { AdminOperationOrderDetailResponse } from '../operation-order-types';

type OperatorOrderDetailSheetProps = {
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

const TITLE_SEPARATOR = '/';

const DetailRow = ({ label, value }: { label: string; value: string }) => (
  <div className='grid grid-cols-[88px_minmax(0,1fr)] items-start gap-4 text-sm'>
    <span className='whitespace-nowrap text-muted-foreground'>{label}</span>
    <span className='min-w-0 break-all text-right text-foreground'>
      {value}
    </span>
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

const OperatorOrderDetailSheet = ({
  open,
  orderBid,
  onOpenChange,
}: OperatorOrderDetailSheetProps) => {
  const { t } = useTranslation();
  const { t: tOperationsOrder } = useTranslation('module.operationsOrder');
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
  const [detail, setDetail] =
    useState<AdminOperationOrderDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ message: string; code?: number } | null>(
    null,
  );

  const emptyValue = useMemo(() => t('module.order.emptyValue'), [t]);

  const fetchDetail = useCallback(async () => {
    if (!orderBid) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = (await api.getAdminOperationOrderDetail({
        order_bid: orderBid,
      })) as AdminOperationOrderDetailResponse;
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
  }, [fetchDetail, open]);

  useEffect(() => {
    if (!open) {
      setDetail(null);
      setError(null);
      setLoading(false);
    }
  }, [open]);

  const summary = detail?.order;
  const payment = detail?.payment;
  const displayUser =
    (isEmailMode ? summary?.user_email : summary?.user_mobile) ||
    summary?.user_bid ||
    '';
  const sourceLabel = useMemo(() => {
    if (!summary) {
      return emptyValue;
    }
    return getOperationOrderSourceLabel(
      summary,
      key => tOperationsOrder(key),
      emptyValue,
    );
  }, [emptyValue, summary, tOperationsOrder]);

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
    >
      <SheetContent className='flex w-full flex-col overflow-hidden border-l border-border bg-white p-0 sm:w-[360px] md:w-[460px] lg:w-[560px]'>
        <SheetHeader className='border-b border-border px-6 py-4 pr-12'>
          <SheetTitle className='flex items-center gap-2 text-base font-semibold text-foreground'>
            <span className='shrink-0 text-sm font-medium text-muted-foreground'>
              {tOperationsOrder('detail.title')}
            </span>
            <span className='text-muted-foreground'>{TITLE_SEPARATOR}</span>
            <span className='truncate text-base font-semibold text-foreground'>
              {summary?.order_bid || tOperationsOrder('detail.fallback')}
            </span>
          </SheetTitle>
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

          {!loading && !error && detail && summary ? (
            <div className='space-y-6'>
              <Section title={tOperationsOrder('detail.sections.summary')}>
                <DetailRow
                  label={t('module.order.fields.status')}
                  value={
                    summary.status_key ? t(summary.status_key) : emptyValue
                  }
                />
                <DetailRow
                  label={tOperationsOrder('table.source')}
                  value={sourceLabel}
                />
                <DetailRow
                  label={t('module.order.fields.createdAt')}
                  value={fallbackValue(summary.created_at, emptyValue)}
                />
                <DetailRow
                  label={tOperationsOrder('table.updatedAt')}
                  value={fallbackValue(summary.updated_at, emptyValue)}
                />
              </Section>

              <Section title={tOperationsOrder('detail.sections.user')}>
                <DetailRow
                  label={t('module.order.fields.user')}
                  value={fallbackValue(displayUser, emptyValue)}
                />
                <DetailRow
                  label={t('module.operationsUser.table.nickname')}
                  value={fallbackValue(summary.user_nickname, emptyValue)}
                />
              </Section>

              <Section title={tOperationsOrder('detail.sections.course')}>
                <DetailRow
                  label={t('module.order.fields.shifu')}
                  value={fallbackValue(summary.shifu_name, emptyValue)}
                />
                <DetailRow
                  label={t('module.operationsCourse.table.courseId')}
                  value={fallbackValue(summary.shifu_bid, emptyValue)}
                />
              </Section>

              <Section title={tOperationsOrder('detail.sections.payment')}>
                <DetailRow
                  label={t('module.order.fields.paid')}
                  value={fallbackValue(summary.paid_price, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.discount')}
                  value={fallbackValue(summary.discount_amount, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.payable')}
                  value={fallbackValue(summary.payable_price, emptyValue)}
                />
                <DetailRow
                  label={t('module.order.fields.paymentChannel')}
                  value={
                    summary.payment_channel_key
                      ? t(summary.payment_channel_key)
                      : emptyValue
                  }
                />
                <DetailRow
                  label={t('module.order.fields.paymentStatus')}
                  value={
                    payment?.status_key ? t(payment.status_key) : emptyValue
                  }
                />
              </Section>

              <Section title={tOperationsOrder('detail.sections.coupons')}>
                {summary.coupon_codes.length > 0 ? (
                  <div className='flex flex-wrap gap-2'>
                    {summary.coupon_codes.map(code => (
                      <Badge
                        key={code}
                        variant='secondary'
                      >
                        {code}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <div className='text-sm text-muted-foreground'>
                    {t('module.order.emptyCoupons')}
                  </div>
                )}
              </Section>

              {detail.activities.length > 0 ? (
                <Section title={tOperationsOrder('detail.sections.activities')}>
                  <div className='space-y-2'>
                    {detail.activities.map(activity => (
                      <div
                        key={
                          activity.active_id ||
                          `${activity.active_name}-${activity.created_at}`
                        }
                        className='rounded-md border border-border px-3 py-2'
                      >
                        <div className='text-sm font-medium text-foreground'>
                          {activity.active_name || emptyValue}
                        </div>
                        <div className='mt-1 text-xs text-muted-foreground'>
                          {activity.status_key
                            ? t(activity.status_key)
                            : emptyValue}
                        </div>
                      </div>
                    ))}
                  </div>
                </Section>
              ) : null}
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default OperatorOrderDetailSheet;
