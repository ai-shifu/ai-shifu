import React from 'react';
import { useTranslation } from 'react-i18next';
import { BillingPlaceholderSection } from './BillingPlaceholderSection';

export function BillingReportsTab() {
  const { t } = useTranslation();

  return (
    <BillingPlaceholderSection
      title={t('module.billing.reports.title')}
      description={t('module.billing.reports.description')}
    />
  );
}
