import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ChevronRight, Crown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { CreatorBillingOverview } from '@/types/billing';
import {
  formatBillingCreditBalance,
  formatBillingExpiryCountdown,
} from '@/lib/billing';

type BillingSidebarCardProps = {
  overview?: CreatorBillingOverview;
  isLoading?: boolean;
};

const resolveMembershipBalanceTitleKey = (
  overview?: CreatorBillingOverview,
) => {
  const productCode = overview?.subscription?.product_code?.toLowerCase() || '';

  if (!productCode) {
    return 'module.billing.sidebar.nonMemberBalanceTitle' as const;
  }

  if (productCode.includes('year')) {
    return 'module.billing.sidebar.yearlyBalanceTitle' as const;
  }

  if (productCode.includes('day')) {
    return 'module.billing.sidebar.dailyBalanceTitle' as const;
  }

  if (productCode.includes('month')) {
    return 'module.billing.sidebar.monthlyBalanceTitle' as const;
  }

  return 'module.billing.sidebar.nonMemberBalanceTitle' as const;
};

const BILLING_CENTER_HREF = '/admin/billing';
const BILLING_PACKAGES_HREF = `${BILLING_CENTER_HREF}?tab=packages`;
const BILLING_DETAILS_HREF = `${BILLING_CENTER_HREF}?tab=details`;

export function BillingSidebarCard({
  overview,
  isLoading = false,
}: BillingSidebarCardProps) {
  const { t } = useTranslation();
  const router = useRouter();
  const availableCredits = overview?.wallet.available_credits ?? 0;
  const shouldShowCredits = !isLoading && availableCredits > 0;
  const membershipBalanceTitleKey = resolveMembershipBalanceTitleKey(overview);

  const creditsValue =
    overview && !isLoading
      ? formatBillingCreditBalance(availableCredits)
      : t('module.billing.sidebar.placeholderValue');

  const expiryCountdown = !isLoading
    ? formatBillingExpiryCountdown(
        t as (key: string, opts?: Record<string, unknown>) => string,
        overview?.subscription?.current_period_end_at,
      )
    : '';

  const handleCardClick = React.useCallback(() => {
    router.push(BILLING_PACKAGES_HREF);
  }, [router]);

  const handleCardKeyDown = React.useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        router.push(BILLING_PACKAGES_HREF);
      }
    },
    [router],
  );

  return (
    <div
      role='link'
      tabIndex={0}
      data-href={BILLING_PACKAGES_HREF}
      onClick={handleCardClick}
      onKeyDown={handleCardKeyDown}
      className='mt-4 block cursor-pointer rounded-[var(--border-radius-rounded-xl,14px)] border border-[var(--base-border,#E5E5E5)] bg-[var(--base-card,#FFF)] px-3.5 py-[14px] shadow-[0_10px_24px_rgba(15,23,42,0.06)] transition-colors hover:border-[var(--base-border-hover,#D4D4D4)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-400'
      data-testid='admin-billing-sidebar-card'
    >
      <div className='flex items-center justify-between gap-2.5'>
        <div className='flex min-w-0 flex-col gap-1'>
          <div className='flex min-w-0 items-center gap-2.5'>
            <div className='flex shrink-0 items-center justify-center text-slate-950'>
              <Crown className='h-4 w-4' />
            </div>
            <p className='truncate text-sm font-extrabold leading-5 text-slate-950'>
              {t(membershipBalanceTitleKey)}
              {shouldShowCredits ? (
                <span className='ml-2 font-medium text-slate-500'>
                  {creditsValue}
                </span>
              ) : null}
            </p>
          </div>
          {expiryCountdown && (
            <div className='ml-7 flex items-center gap-1.5 text-sm leading-5'>
              <span className='font-semibold text-slate-900'>
                {expiryCountdown}
              </span>
            </div>
          )}
        </div>
        <span className='inline-flex h-6 min-h-6 shrink-0 items-center whitespace-nowrap rounded-full bg-slate-950 px-4 py-0 text-sm font-semibold leading-5 text-white'>
          {t('module.billing.sidebar.upgradeCta')}
        </span>
      </div>
      <div className='mt-3 border-t border-slate-200 pt-3'>
        <Link
          href={BILLING_DETAILS_HREF}
          onClick={event => event.stopPropagation()}
          className='inline-flex items-center gap-1 text-sm font-normal leading-5 text-[rgba(10,10,10,0.45)] transition-colors hover:text-[rgba(10,10,10,0.6)]'
        >
          <span>{t('module.billing.sidebar.usageCta')}</span>
          <ChevronRight className='h-5 w-5 text-[rgba(10,10,10,0.45)]' />
        </Link>
      </div>
    </div>
  );
}
