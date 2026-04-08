import React from 'react';
import { BillingLedgerTable } from './BillingLedgerTable';
import { BillingWalletBucketsCard } from './BillingWalletBucketsCard';

export function BillingLedgerTab() {
  return (
    <div className='space-y-4'>
      <BillingWalletBucketsCard />
      <BillingLedgerTable />
    </div>
  );
}
