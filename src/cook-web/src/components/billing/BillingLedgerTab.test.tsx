import React from 'react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

jest.mock('@/lib/browser-timezone', () => ({
  __esModule: true,
  getBrowserTimeZone: () => 'Asia/Shanghai',
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getBillingLedger: jest.fn(),
    getBillingWalletBuckets: jest.fn(),
  },
}));

const mockGetBillingLedger = api.getBillingLedger as jest.Mock;
const mockGetBillingWalletBuckets = api.getBillingWalletBuckets as jest.Mock;

describe('BillingLedgerTab', () => {
  beforeEach(() => {
    mockGetBillingWalletBuckets.mockResolvedValue({
      items: [
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
      ],
    });
    mockGetBillingLedger.mockResolvedValue({
      items: [
        {
          ledger_bid: 'ledger-consume',
          wallet_bucket_bid: 'bucket-free',
          entry_type: 'consume',
          source_type: 'usage',
          source_bid: 'usage-1',
          idempotency_key: 'usage-1-bucket-free',
          amount: -2.5,
          balance_after: 97.5,
          expires_at: null,
          consumable_from: null,
          metadata: {
            usage_bid: 'usage-1',
            usage_scene: 'production',
            course_name: 'Published Course 1',
            user_identify: 'learner@example.com',
            metric_breakdown: [
              {
                billing_metric: 'llm_output_tokens',
                raw_amount: 1234,
                unit_size: 1000,
                credits_per_unit: 1.25,
                rounding_mode: 'ceil',
                consumed_credits: 2.5,
              },
            ],
          },
          created_at: '2026-04-06T10:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 10,
      total: 1,
    });
  });

  test('renders wallet bucket details and opens usage detail rows', async () => {
    const user = userEvent.setup();

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
    expect(mockGetBillingLedger).toHaveBeenCalledTimes(1);
    expect(mockGetBillingWalletBuckets).toHaveBeenCalledWith({
      timezone: 'Asia/Shanghai',
    });
    expect(mockGetBillingLedger).toHaveBeenCalledWith({
      page_index: 1,
      page_size: 10,
      timezone: 'Asia/Shanghai',
    });
    expect(
      screen.getAllByText('module.billing.ledger.entriesTitle').length,
    ).toBeGreaterThan(0);

    expect(await screen.findByText('grant-1')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.source.gift'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.billing.ledger.usageScene.production - Published Course 1 - learner@example.com',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.neverExpires'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.billing.ledger.table.detail',
      }),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.ledger.table.detail',
        }),
      );
    });

    expect(
      screen.getAllByText('module.billing.ledger.detail.title').length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText('usage-1').length).toBeGreaterThan(1);
    expect(screen.getByText('-2.5000000')).toBeInTheDocument();
    expect(screen.getAllByText('97.5000000').length).toBeGreaterThan(0);
    expect(screen.getByText('1.2500000')).toBeInTheDocument();
    expect(screen.getByText('2.5000000')).toBeInTheDocument();
  });

  test('renders empty state when wallet bucket dto is empty', async () => {
    mockGetBillingWalletBuckets.mockResolvedValue({
      items: [],
    });

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <BillingLedgerTab />
      </SWRConfig>,
    );

    expect(
      await screen.findByText('module.billing.ledger.empty'),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('module.billing.ledger.neverExpires').length,
    ).toBeGreaterThan(0);
  });
});
