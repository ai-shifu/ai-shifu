import React from 'react';
import Link from 'next/link';
import { CreditCardIcon } from '@heroicons/react/24/outline';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import type { CreatorBillingOverview } from '@/types/billing';
import {
  formatBillingCredits,
  resolveBillingSubscriptionStatusLabel,
} from '@/lib/billing';

type BillingSidebarCardProps = {
  overview?: CreatorBillingOverview;
  isLoading?: boolean;
};

export function BillingSidebarCard({
  overview,
  isLoading = false,
}: BillingSidebarCardProps) {
  const { t, i18n } = useTranslation();

  const creditsValue =
    overview && !isLoading
      ? formatBillingCredits(overview.wallet.available_credits, i18n.language)
      : t('module.billing.sidebar.placeholderValue');
  const statusValue =
    overview && !isLoading
      ? resolveBillingSubscriptionStatusLabel(t, overview.subscription?.status)
      : t('module.billing.sidebar.subscriptionPending');

  return (
    <div
      className='mt-4 rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-[0_10px_24px_rgba(15,23,42,0.06)]'
      data-testid='admin-billing-sidebar-card'
    >
      <div className='flex items-start justify-between gap-3'>
        <div className='min-w-0'>
          <p className='text-sm font-semibold text-slate-900'>
            {t('module.billing.sidebar.title')}
          </p>
          <p className='mt-1 text-xs leading-5 text-slate-500'>
            {t('module.billing.sidebar.description')}
          </p>
        </div>
        <div className='flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-amber-50 text-amber-600'>
          <CreditCardIcon className='h-5 w-5' />
        </div>
      </div>
      <div className='mt-4 grid gap-2 rounded-xl bg-slate-50 p-3'>
        <div className='flex items-center justify-between gap-3 text-sm'>
          <span className='text-slate-500'>
            {t('module.billing.sidebar.totalCreditsLabel')}
          </span>
          <span className='font-semibold text-slate-900'>{creditsValue}</span>
        </div>
        <div className='flex items-center justify-between gap-3 text-sm'>
          <span className='text-slate-500'>
            {t('module.billing.sidebar.subscriptionStatusLabel')}
          </span>
          <span className='font-semibold text-slate-900'>{statusValue}</span>
        </div>
      </div>
      <Button
        asChild
        className='mt-4 w-full justify-between rounded-xl'
      >
        <Link href='/admin/billing'>{t('module.billing.sidebar.cta')}</Link>
      </Button>
    </div>
  );
}
