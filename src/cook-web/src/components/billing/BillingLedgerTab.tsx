import React from 'react';
import { useTranslation } from 'react-i18next';
import { BillingPlaceholderSection } from './BillingPlaceholderSection';
import { BillingWalletBucketsCard } from './BillingWalletBucketsCard';

export function BillingLedgerTab() {
  const { t } = useTranslation();

  return (
    <div className='space-y-4'>
      <BillingWalletBucketsCard />

      <BillingPlaceholderSection
        title={t('module.billing.ledger.entriesTitle')}
        description={t('module.billing.ledger.entriesDescription')}
      />
    </div>
  );
}
