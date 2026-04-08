import React from 'react';
import { useTranslation } from 'react-i18next';
import { BillingPlaceholderSection } from './BillingPlaceholderSection';

export function BillingOrdersTab() {
  const { t } = useTranslation();

  return (
    <BillingPlaceholderSection
      title={t('module.billing.orders.title')}
      description={t('module.billing.orders.description')}
    />
  );
}
