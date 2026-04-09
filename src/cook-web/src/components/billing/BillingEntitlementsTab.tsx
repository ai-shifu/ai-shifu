import React from 'react';
import { useTranslation } from 'react-i18next';
import { BillingPlaceholderSection } from './BillingPlaceholderSection';

export function BillingEntitlementsTab() {
  const { t } = useTranslation();

  return (
    <BillingPlaceholderSection
      title={t('module.billing.entitlements.title')}
      description={t('module.billing.entitlements.description')}
    />
  );
}
