import React from 'react';
import { useTranslation } from 'react-i18next';
import { BillingMetricCard } from './BillingMetricCard';
import { BillingPlaceholderSection } from './BillingPlaceholderSection';

export function BillingOverviewTab() {
  const { t } = useTranslation();
  const placeholderValue = t('module.billing.sidebar.placeholderValue');
  const pendingValue = t('module.billing.overview.pendingValue');

  return (
    <div className='space-y-4'>
      <div>
        <h3 className='text-lg font-semibold text-slate-900'>
          {t('module.billing.overview.walletTitle')}
        </h3>
      </div>
      <div className='grid gap-4 md:grid-cols-3'>
        <BillingMetricCard
          label={t('module.billing.overview.availableCreditsLabel')}
          value={placeholderValue}
        />
        <BillingMetricCard
          label={t('module.billing.overview.subscriptionStatusLabel')}
          value={pendingValue}
        />
        <BillingMetricCard
          label={t('module.billing.overview.nextActionLabel')}
          value={pendingValue}
        />
      </div>
      <div className='grid gap-4 xl:grid-cols-[1.1fr,0.9fr]'>
        <BillingPlaceholderSection
          title={t('module.billing.overview.subscriptionTitle')}
          description={t('module.billing.overview.helper')}
        />
        <BillingPlaceholderSection
          title={t('module.billing.overview.catalogTitle')}
          description={t('module.billing.overview.helper')}
        />
      </div>
    </div>
  );
}
