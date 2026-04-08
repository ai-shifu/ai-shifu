import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/Badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import type { BillingPlan, BillingSubscription } from '@/types/billing';
import {
  formatBillingDate,
  resolveBillingProductDescription,
  resolveBillingProductTitle,
  resolveBillingSubscriptionStatusLabel,
} from '@/lib/billing';

type BillingSubscriptionCardProps = {
  currentPlan: BillingPlan | null;
  subscription: BillingSubscription | null;
};

function resolveStatusClassName(
  status: BillingSubscription['status'] | 'none',
) {
  if (status === 'active') {
    return 'bg-emerald-100 text-emerald-700';
  }
  if (status === 'cancel_scheduled' || status === 'paused') {
    return 'bg-amber-100 text-amber-800';
  }
  if (status === 'past_due' || status === 'canceled' || status === 'expired') {
    return 'bg-rose-100 text-rose-700';
  }
  return 'bg-slate-100 text-slate-700';
}

export function BillingSubscriptionCard({
  currentPlan,
  subscription,
}: BillingSubscriptionCardProps) {
  const { t, i18n } = useTranslation();

  const status = subscription?.status || 'none';
  const cycleDate = useMemo(() => {
    if (!subscription?.current_period_end_at) {
      return '';
    }
    return formatBillingDate(subscription.current_period_end_at, i18n.language);
  }, [i18n.language, subscription?.current_period_end_at]);

  const renewalMessage = useMemo(() => {
    if (!subscription?.current_period_end_at) {
      return t('module.billing.overview.subscriptionEmptyDescription');
    }
    if (subscription.cancel_at_period_end) {
      return t('module.billing.overview.subscriptionEndsOn', {
        date: cycleDate,
      });
    }
    return t('module.billing.overview.subscriptionRenewsOn', {
      date: cycleDate,
    });
  }, [
    cycleDate,
    subscription?.cancel_at_period_end,
    subscription?.current_period_end_at,
    t,
  ]);

  return (
    <Card className='border-slate-200 bg-white/90 shadow-[0_12px_30px_rgba(15,23,42,0.06)]'>
      <CardHeader className='gap-4'>
        <div className='flex items-center justify-between gap-3'>
          <div>
            <CardDescription>
              {t('module.billing.overview.subscriptionTitle')}
            </CardDescription>
            <CardTitle className='mt-2 text-2xl text-slate-900'>
              {subscription && currentPlan
                ? resolveBillingProductTitle(t, currentPlan)
                : t('module.billing.overview.subscriptionEmptyTitle')}
            </CardTitle>
          </div>
          <Badge
            className={resolveStatusClassName(status)}
            variant='secondary'
          >
            {resolveBillingSubscriptionStatusLabel(t, subscription?.status)}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className='space-y-4'>
        <p className='text-sm leading-6 text-slate-500'>
          {subscription && currentPlan
            ? resolveBillingProductDescription(t, currentPlan)
            : t('module.billing.overview.subscriptionEmptyDescription')}
        </p>
        <div className='grid gap-3 rounded-2xl bg-slate-50 p-4 text-sm text-slate-600'>
          <div className='flex items-center justify-between gap-3'>
            <span>
              {t('module.billing.overview.subscriptionProviderLabel')}
            </span>
            <span className='font-semibold capitalize text-slate-900'>
              {subscription?.billing_provider ||
                t('module.billing.status.none')}
            </span>
          </div>
          <div className='flex items-center justify-between gap-3'>
            <span>{t('module.billing.overview.subscriptionTimingLabel')}</span>
            <span className='text-right font-semibold text-slate-900'>
              {renewalMessage}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
