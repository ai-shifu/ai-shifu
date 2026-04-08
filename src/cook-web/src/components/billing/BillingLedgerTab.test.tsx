import React from 'react';
import { render, screen } from '@testing-library/react';
import { SWRConfig } from 'swr';
import api from '@/api';

import { BillingLedgerTab } from './BillingLedgerTab';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en-US',
    },
  }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getBillingWalletBuckets: jest.fn(),
  },
}));

const mockGetBillingWalletBuckets = api.getBillingWalletBuckets as jest.Mock;

describe('BillingLedgerTab', () => {
  beforeEach(() => {
    mockGetBillingWalletBuckets.mockResolvedValue([
      {
        wallet_bucket_bid: 'bucket-free',
        category: 'free',
        source_type: 'gift',
        source_bid: 'grant-1',
        available_credits: 80,
        effective_from: '2026-03-01T00:00:00Z',
        effective_to: '2026-05-01T00:00:00Z',
        priority: 10,
        status: 'active',
      },
      {
        wallet_bucket_bid: 'bucket-topup',
        category: 'topup',
        source_type: 'topup',
        source_bid: 'topup-1',
        available_credits: 24.5,
        effective_from: '2026-03-02T00:00:00Z',
        effective_to: null,
        priority: 30,
        status: 'active',
      },
    ]);
  });

  test('renders wallet bucket details and the pending ledger placeholder', async () => {
    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <BillingLedgerTab />
      </SWRConfig>,
    );

    expect(mockGetBillingWalletBuckets).toHaveBeenCalledTimes(1);
    expect(
      screen.getByText('module.billing.ledger.entriesTitle'),
    ).toBeInTheDocument();

    expect(await screen.findByText('grant-1')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.source.gift'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.neverExpires'),
    ).toBeInTheDocument();
  });
});
