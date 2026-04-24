import React from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { getBrowserTimeZone } from '@/lib/browser-timezone';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import type {
  AdminBillingOrderItem,
  AdminBillingSubscriptionItem,
  BillingPagedResponse,
} from '@/types/billing';
import {
  buildBillingSwrKey,
  buildBillingRenewalContextLabel,
  formatBillingDateTime,
  formatBillingPrice,
  registerBillingTranslationUsage,
  resolveBillingEmptyLabel,
  resolveBillingOrderStatusLabel,
  resolveBillingOrderTypeLabel,
  resolveBillingRenewalEventStatusLabel,
  resolveBillingRenewalEventTypeLabel,
  resolveBillingSubscriptionStatusLabel,
  withBillingTimezone,
} from '@/lib/billing';

const EXCEPTION_PAGE_SIZE = 6;

function ExceptionRow({ label, value }: { label: string; value: string }) {
  return (
    <div className='flex items-center justify-between gap-3 text-sm'>
      <span className='text-slate-500'>{label}</span>
      <span className='text-right font-medium text-slate-900'>{value}</span>
    </div>
  );
}

type AdminBillingExceptionsPanelProps = {
  onAdjustCreatorBid?: (creatorBid: string) => void;
};

export function AdminBillingExceptionsPanel({
  onAdjustCreatorBid,
}: AdminBillingExceptionsPanelProps) {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const timezone = getBrowserTimeZone();
  const {
    data: subscriptions,
    error: subscriptionsError,
    isLoading: subscriptionsLoading,
  } = useSWR<BillingPagedResponse<AdminBillingSubscriptionItem>>(
    buildBillingSwrKey('admin-billing-subscriptions-exceptions', timezone),
    async () =>
      (await api.getAdminBillingSubscriptions({
        ...withBillingTimezone(
          {
            page_index: 1,
            page_size: EXCEPTION_PAGE_SIZE,
          },
          timezone,
        ),
      })) as BillingPagedResponse<AdminBillingSubscriptionItem>,
    {
      revalidateOnFocus: false,
    },
  );
  const {
    data: orders,
    error: ordersError,
    isLoading: ordersLoading,
  } = useSWR<BillingPagedResponse<AdminBillingOrderItem>>(
    buildBillingSwrKey('admin-billing-orders-exceptions', timezone),
    async () =>
      (await api.getAdminBillingOrders({
        ...withBillingTimezone(
          {
            page_index: 1,
            page_size: EXCEPTION_PAGE_SIZE,
          },
          timezone,
        ),
      })) as BillingPagedResponse<AdminBillingOrderItem>,
    {
      revalidateOnFocus: false,
    },
  );

  const subscriptionItems = (subscriptions?.items || []).filter(
    item => item.has_attention,
  );
  const orderItems = (orders?.items || []).filter(item => item.has_attention);
  const hasError = subscriptionsError || ordersError;
  const isLoading = subscriptionsLoading || ordersLoading;

  return (
    <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
      <CardHeader className='space-y-2'>
        <CardTitle className='text-lg text-slate-900'>
          {t('module.billing.admin.exceptions.title')}
        </CardTitle>
        <CardDescription className='leading-6 text-slate-600'>
          {t('module.billing.admin.exceptions.description')}
        </CardDescription>
      </CardHeader>

      <CardContent className='space-y-6'>
        {hasError ? (
          <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
            {t('module.billing.admin.exceptions.loadError')}
          </div>
        ) : null}

        {isLoading ? (
          <div className='space-y-3'>
            <Skeleton className='h-20 rounded-2xl' />
            <Skeleton className='h-20 rounded-2xl' />
          </div>
        ) : null}

        {!isLoading && !subscriptionItems.length && !orderItems.length ? (
          <div className='rounded-2xl border border-dashed border-slate-200 bg-slate-50/80 px-4 py-8 text-center text-sm text-slate-500'>
            {t('module.billing.admin.exceptions.empty')}
          </div>
        ) : null}

        {subscriptionItems.length ? (
          <div className='space-y-3'>
            <div className='flex items-center gap-2'>
              <h3 className='text-sm font-semibold text-slate-900'>
                {t('module.billing.admin.exceptions.sections.subscriptions')}
              </h3>
              <Badge
                variant='outline'
                className='border-amber-200 bg-amber-50 text-amber-700'
              >
                {subscriptionItems.length}
              </Badge>
            </div>
            <div className='grid gap-3 md:grid-cols-2'>
              {subscriptionItems.map(item => (
                <div
                  key={item.subscription_bid}
                  className='rounded-2xl border border-slate-200 bg-slate-50/80 p-4'
                >
                  <div className='mb-3 flex items-start justify-between gap-3'>
                    <div>
                      <p className='font-medium text-slate-900'>
                        {item.creator_bid}
                      </p>
                      <p className='text-xs text-slate-500'>
                        {item.subscription_bid}
                      </p>
                    </div>
                    <Badge
                      variant='outline'
                      className='border-amber-200 bg-amber-50 text-amber-700'
                    >
                      {resolveBillingSubscriptionStatusLabel(t, item.status)}
                    </Badge>
                  </div>
                  {onAdjustCreatorBid ? (
                    <Button
                      variant='outline'
                      size='sm'
                      className='mb-3 rounded-full'
                      onClick={() => onAdjustCreatorBid(item.creator_bid)}
                    >
                      {t('module.billing.admin.adjust.quickAction')}
                    </Button>
                  ) : null}
                  <div className='space-y-2'>
                    <ExceptionRow
                      label={t(
                        'module.billing.admin.exceptions.fields.periodEnd',
                      )}
                      value={
                        formatBillingDateTime(
                          item.current_period_end_at,
                          i18n.language,
                        ) || resolveBillingEmptyLabel(t)
                      }
                    />
                    <ExceptionRow
                      label={t(
                        'module.billing.admin.exceptions.fields.renewalEvent',
                      )}
                      value={
                        item.latest_renewal_event
                          ? `${resolveBillingRenewalEventTypeLabel(
                              t,
                              item.latest_renewal_event.event_type,
                            )} · ${resolveBillingRenewalEventStatusLabel(
                              t,
                              item.latest_renewal_event.status,
                            )}`
                          : resolveBillingEmptyLabel(t)
                      }
                    />
                    <ExceptionRow
                      label={t('module.billing.admin.exceptions.fields.detail')}
                      value={buildBillingRenewalContextLabel(
                        t,
                        i18n.language,
                        item.latest_renewal_event,
                      )}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {orderItems.length ? (
          <div className='space-y-3'>
            <div className='flex items-center gap-2'>
              <h3 className='text-sm font-semibold text-slate-900'>
                {t('module.billing.admin.exceptions.sections.orders')}
              </h3>
              <Badge
                variant='outline'
                className='border-amber-200 bg-amber-50 text-amber-700'
              >
                {orderItems.length}
              </Badge>
            </div>
            <div className='grid gap-3 md:grid-cols-2'>
              {orderItems.map(item => (
                <div
                  key={item.bill_order_bid}
                  className='rounded-2xl border border-slate-200 bg-slate-50/80 p-4'
                >
                  <div className='mb-3 flex items-start justify-between gap-3'>
                    <div>
                      <p className='font-medium text-slate-900'>
                        {item.creator_bid}
                      </p>
                      <p className='text-xs text-slate-500'>
                        {resolveBillingOrderTypeLabel(t, item.order_type)}
                      </p>
                    </div>
                    <Badge
                      variant='outline'
                      className='border-amber-200 bg-amber-50 text-amber-700'
                    >
                      {resolveBillingOrderStatusLabel(t, item.status)}
                    </Badge>
                  </div>
                  {onAdjustCreatorBid ? (
                    <Button
                      variant='outline'
                      size='sm'
                      className='mb-3 rounded-full'
                      onClick={() => onAdjustCreatorBid(item.creator_bid)}
                    >
                      {t('module.billing.admin.adjust.quickAction')}
                    </Button>
                  ) : null}
                  <div className='space-y-2'>
                    <ExceptionRow
                      label={t('module.billing.admin.exceptions.fields.amount')}
                      value={formatBillingPrice(
                        item.paid_amount || item.payable_amount,
                        item.currency,
                        i18n.language,
                      )}
                    />
                    <ExceptionRow
                      label={t('module.billing.admin.exceptions.fields.detail')}
                      value={
                        item.failure_message ||
                        item.failure_code ||
                        resolveBillingEmptyLabel(t)
                      }
                    />
                    <ExceptionRow
                      label={t(
                        'module.billing.admin.exceptions.fields.createdAt',
                      )}
                      value={
                        formatBillingDateTime(item.created_at, i18n.language) ||
                        resolveBillingEmptyLabel(t)
                      }
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
