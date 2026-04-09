import React from 'react';
import { useTranslation } from 'react-i18next';
import { BillingPlaceholderSection } from './BillingPlaceholderSection';

export function BillingDomainsTab() {
  const { t } = useTranslation();

  return (
    <BillingPlaceholderSection
      title={t('module.billing.domains.title')}
      description={t('module.billing.domains.description')}
    />
  );
}
