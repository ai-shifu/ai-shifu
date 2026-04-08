import React from 'react';
import { useTranslation } from 'react-i18next';
import { BillingPlaceholderSection } from './BillingPlaceholderSection';

export function BillingLedgerTab() {
  const { t } = useTranslation();

  return (
    <BillingPlaceholderSection
      title={t('module.billing.ledger.title')}
      description={t('module.billing.ledger.description')}
    />
  );
}
