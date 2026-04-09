import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
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
  resolveBillingEmptyLabel,
  resolveBillingPlanCreditsLabel,
  resolveBillingProviderLabel,
  resolveBillingProductDescription,
  resolveBillingProductTitle,
  resolveBillingSubscriptionStatusLabel,
} from '@/lib/billing';

type BillingSubscriptionCardProps = {
  currentPlan: BillingPlan | null;
  subscription: BillingSubscription | null;
  actionLoading?: 'cancel' | 'resume' | '';
  onCancelSubscription?: (subscription: BillingSubscription) => void;
  onResumeSubscription?: (subscription: BillingSubscription) => void;
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
  actionLoading = '',
  onCancelSubscription,
  onResumeSubscription,
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
  const subscriptionStatus = subscription?.status || 'none';

  const canResume =
    Boolean(subscription) &&
    (subscriptionStatus === 'cancel_scheduled' ||
      subscriptionStatus === 'paused');
  const canCancel =
    Boolean(subscription) &&
    !subscription?.cancel_at_period_end &&
    subscriptionStatus !== 'canceled' &&
    subscriptionStatus !== 'expired' &&
    subscriptionStatus !== 'draft';
  const creditsLabel =
    currentPlan && subscription
      ? resolveBillingPlanCreditsLabel(t, currentPlan, i18n.language)
      : t('module.billing.overview.subscriptionEmptyDescription');

  return (
    <Card className='h-full rounded-[30px] border-slate-200 bg-white shadow-[0_18px_40px_rgba(15,23,42,0.08)]'>
      <CardHeader className='gap-5 pb-5'>
        <div className='flex items-center justify-between gap-3'>
          <div>
            <CardDescription className='text-sm font-medium uppercase tracking-[0.12em] text-slate-400'>
              {t('module.billing.overview.subscriptionTitle')}
            </CardDescription>
            <CardTitle className='mt-3 text-xl leading-tight text-slate-950 md:text-2xl'>
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
      <CardContent className='space-y-5'>
        <p className='text-sm leading-7 text-slate-500'>
          {subscription && currentPlan
            ? resolveBillingProductDescription(t, currentPlan)
            : t('module.billing.overview.subscriptionEmptyDescription')}
        </p>
        <div className='grid gap-3 rounded-[24px] border border-slate-200 bg-slate-50/80 p-4 text-sm text-slate-600'>
          <div className='flex items-center justify-between gap-3'>
            <span>{t('module.billing.overview.availableCreditsLabel')}</span>
            <span className='font-semibold text-slate-900'>{creditsLabel}</span>
          </div>
          <div className='flex items-center justify-between gap-3'>
            <span>
              {t('module.billing.overview.subscriptionProviderLabel')}
            </span>
            <span className='font-semibold text-slate-900'>
              {subscription?.billing_provider
                ? resolveBillingProviderLabel(t, subscription.billing_provider)
                : resolveBillingEmptyLabel(t)}
            </span>
          </div>
          <div className='flex items-center justify-between gap-3'>
            <span>{t('module.billing.overview.subscriptionTimingLabel')}</span>
            <span className='text-right font-semibold text-slate-900'>
              {renewalMessage}
            </span>
          </div>
        </div>

        {subscription ? (
          <div className='flex flex-wrap gap-3'>
            {canCancel ? (
              <Button
                variant='outline'
                className='rounded-full'
                disabled={actionLoading === 'cancel'}
                onClick={() => onCancelSubscription?.(subscription)}
              >
                {actionLoading === 'cancel'
                  ? t('module.billing.catalog.actions.processing')
                  : t('module.billing.overview.actions.cancelSubscription')}
              </Button>
            ) : null}
            {canResume ? (
              <Button
                className='rounded-full'
                disabled={actionLoading === 'resume'}
                onClick={() => onResumeSubscription?.(subscription)}
              >
                {actionLoading === 'resume'
                  ? t('module.billing.catalog.actions.processing')
                  : t('module.billing.overview.actions.resumeSubscription')}
              </Button>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
