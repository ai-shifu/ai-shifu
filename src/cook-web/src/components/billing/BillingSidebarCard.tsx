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
  const shouldShowCredits = availableCredits > 0;
  const creditsValue =
    !isLoading && shouldShowCredits
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
      className='mt-4 block cursor-pointer rounded-[var(--border-radius-rounded-xl,14px)] border border-[var(--base-border,#E5E5E5)] bg-[var(--base-card,#FFF)] py-[14px] pl-4 pr-3 shadow-[0_10px_24px_rgba(15,23,42,0.06)] transition-colors hover:border-[var(--base-border-hover,#D4D4D4)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-400'
      data-testid='admin-billing-sidebar-card'
    >
      <div className='flex items-center justify-between gap-3 border-b border-[rgba(0,0,0,0.05)] pb-3 mr-1'>
        <div className='flex min-w-0 items-center gap-2.5'>
          <div className='flex shrink-0 items-center justify-center text-slate-950'>
            <Crown className='h-4 w-4' />
          </div>
          <p className='truncate text-sm font-extrabold leading-5 text-slate-950'>
            {t('module.billing.sidebar.summaryTitle')}
          </p>
        </div>
        <span className='inline-flex h-6 min-h-6 shrink-0 items-center whitespace-nowrap rounded-full bg-slate-950 px-4 py-0 text-sm font-semibold leading-5 text-white'>
          {t('module.billing.sidebar.upgradeCta')}
        </span>
      </div>
      <div className='pt-3'>
        <div className='flex min-w-0 items-center justify-between gap-3 text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-normal,400)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-card-foreground,#0A0A0A)]'>
          <span className='shrink-0'>
            {t('module.billing.sidebar.nonMemberBalanceTitle')}
          </span>
          <span className='truncate pr-1'>{creditsValue}</span>
        </div>
        <div className='flex min-w-0 items-center justify-between gap-3 pt-2.5 text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-normal,400)] leading-[var(--text-sm-line-height,20px)] text-[rgba(10,10,10,0.45)]'>
          <div className='min-w-0'>
            {expiryCountdown ? (
              <p className='truncate'>{expiryCountdown}</p>
            ) : null}
          </div>
          <Link
            href={BILLING_DETAILS_HREF}
            onClick={event => event.stopPropagation()}
            className='inline-flex shrink-0 items-center gap-1 leading-none transition-colors hover:text-[rgba(10,10,10,0.6)]'
          >
            <span className='leading-5'>
              {t('module.billing.sidebar.usageCta')}
            </span>
            <ChevronRight className='h-4 w-4 shrink-0 text-[rgba(10,10,10,0.45)]' />
          </Link>
        </div>
      </div>
    </div>
  );
}
