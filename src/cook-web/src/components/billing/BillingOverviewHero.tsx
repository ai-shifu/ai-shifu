import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import {
  resolveBillingProductTitle,
  resolveBillingSubscriptionStatusLabel,
} from '@/lib/billing';
import type { BillingPlan, BillingSubscription } from '@/types/billing';

type BillingOverviewHeroProps = {
  currentPlan: BillingPlan | null;
  renewalMessage: string;
  subscription: BillingSubscription | null | undefined;
  subscriptionActionLoading: 'cancel' | 'resume' | '';
  onSubscriptionAction: (
    action: 'cancel' | 'resume',
    subscription: BillingSubscription,
  ) => void;
};

export function BillingOverviewHero({
  currentPlan,
  renewalMessage,
  subscription,
  subscriptionActionLoading,
  onSubscriptionAction,
}: BillingOverviewHeroProps) {
  const { t } = useTranslation();

  return (
    <div className='space-y-4 text-center'>
      <div className='space-y-2'>
        <h1 className='text-2xl font-semibold tracking-tight text-slate-950 md:text-3xl'>
          {t('module.billing.package.title')}
        </h1>
        <p className='mx-auto max-w-4xl text-sm leading-7 text-slate-500 md:text-base'>
          {t('module.billing.package.subtitle')}
        </p>
      </div>

      {subscription ? (
        <div className='mx-auto max-w-5xl rounded-[28px] border border-slate-200 bg-white px-6 py-5 text-left shadow-[0_18px_40px_rgba(15,23,42,0.06)]'>
          <div className='flex flex-col gap-4 md:flex-row md:items-center md:justify-between'>
            <div className='space-y-1'>
              <div className='text-sm font-medium uppercase tracking-[0.12em] text-slate-400'>
                {t('module.billing.overview.subscriptionTitle')}
              </div>
              <div className='flex flex-wrap items-center gap-3'>
                <div className='text-lg font-semibold text-slate-950 md:text-xl'>
                  {currentPlan
                    ? resolveBillingProductTitle(t, currentPlan)
                    : t('module.billing.overview.subscriptionEmptyTitle')}
                </div>
                <span className='rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-600'>
                  {resolveBillingSubscriptionStatusLabel(
                    t,
                    subscription.status,
                  )}
                </span>
              </div>
              <div className='text-sm text-slate-500'>{renewalMessage}</div>
            </div>

            <div className='flex flex-wrap gap-3'>
              {subscription.cancel_at_period_end ||
              subscription.status === 'paused' ? (
                <Button
                  className='rounded-2xl'
                  disabled={subscriptionActionLoading === 'resume'}
                  onClick={() => onSubscriptionAction('resume', subscription)}
                  type='button'
                >
                  {subscriptionActionLoading === 'resume'
                    ? t('module.billing.catalog.actions.processing')
                    : t('module.billing.overview.actions.resumeSubscription')}
                </Button>
              ) : (
                <Button
                  className='rounded-2xl'
                  disabled={subscriptionActionLoading === 'cancel'}
                  onClick={() => onSubscriptionAction('cancel', subscription)}
                  type='button'
                  variant='outline'
                >
                  {subscriptionActionLoading === 'cancel'
                    ? t('module.billing.catalog.actions.processing')
                    : t('module.billing.overview.actions.cancelSubscription')}
                </Button>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
