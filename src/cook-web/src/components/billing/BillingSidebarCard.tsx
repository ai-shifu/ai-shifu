import React from 'react';
import Link from 'next/link';
import { ChevronRight, Crown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import type { CreatorBillingOverview } from '@/types/billing';
import { formatBillingCredits } from '@/lib/billing';

type BillingSidebarCardProps = {
  overview?: CreatorBillingOverview;
  isLoading?: boolean;
};

const resolveMembershipTitleKey = (overview?: CreatorBillingOverview) => {
  const productCode = overview?.subscription?.product_code?.toLowerCase() || '';

  if (!productCode) {
    return 'module.billing.sidebar.nonMemberTitle' as const;
  }

  if (productCode.includes('year')) {
    return 'module.billing.sidebar.yearlyTitle' as const;
  }

  if (productCode.includes('month')) {
    return 'module.billing.sidebar.monthlyTitle' as const;
  }

  return 'module.billing.sidebar.nonMemberTitle' as const;
};

const BILLING_CENTER_HREF = '/admin/billing';
const BILLING_PACKAGES_HREF = `${BILLING_CENTER_HREF}?tab=packages`;
const BILLING_DETAILS_HREF = `${BILLING_CENTER_HREF}?tab=details`;

export function BillingSidebarCard({
  overview,
  isLoading = false,
}: BillingSidebarCardProps) {
  const { t, i18n } = useTranslation();
  const availableCredits = overview?.wallet.available_credits ?? 0;
  const shouldShowCredits = !isLoading && availableCredits > 0;
  const membershipTitleKey = resolveMembershipTitleKey(overview);

  const creditsValue =
    overview && !isLoading
      ? formatBillingCredits(availableCredits, i18n.language)
      : t('module.billing.sidebar.placeholderValue');

  return (
    <div
      className='mt-4 rounded-[var(--border-radius-rounded-xl,14px)] border border-[var(--base-border,#E5E5E5)] bg-[var(--base-card,#FFF)] px-4 py-[14px] shadow-[0_10px_24px_rgba(15,23,42,0.06)]'
      data-testid='admin-billing-sidebar-card'
    >
      <div className='flex items-center justify-between gap-3'>
        <div className='flex min-w-0 items-center gap-3'>
          <div className='flex shrink-0 items-center justify-center text-slate-950'>
            <Crown className='h-4 w-4' />
          </div>
          <p className='mr-2 truncate text-sm font-extrabold leading-5 text-slate-950'>
            {t(membershipTitleKey)}
          </p>
        </div>
        <Button
          asChild
          className='h-6 min-h-6 rounded-full bg-slate-950 px-4 py-0 text-sm font-semibold leading-5 text-white hover:bg-slate-800'
        >
          <Link href={BILLING_PACKAGES_HREF}>
            {t('module.billing.sidebar.upgradeCta')}
          </Link>
        </Button>
      </div>
      {shouldShowCredits ? (
        <div className='mt-3 border-t border-slate-200 pt-3'>
          <div className='flex items-center justify-between gap-3'>
            <span className='text-sm font-medium leading-5 text-slate-900'>
              {t('module.billing.sidebar.totalCreditsLabel')}
            </span>
            <span className='text-sm font-medium leading-5 text-slate-950'>
              {creditsValue}
            </span>
          </div>
          <Link
            href={BILLING_DETAILS_HREF}
            className='mt-[10px] inline-flex items-center gap-1 text-sm font-normal leading-5 text-[rgba(10,10,10,0.45)] transition-colors hover:text-[rgba(10,10,10,0.6)]'
          >
            <span>{t('module.billing.sidebar.usageCta')}</span>
            <ChevronRight className='h-5 w-5 text-[rgba(10,10,10,0.45)]' />
          </Link>
        </div>
      ) : null}
    </div>
  );
}
