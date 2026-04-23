import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';
import { BillingRecentActivitySection } from './BillingRecentActivitySection';

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
  },
}));

const mockGetBillingLedger = api.getBillingLedger as jest.Mock;

function renderSection() {
  return render(
    <SWRConfig
      value={{
        provider: () => new Map(),
      }}
    >
      <BillingRecentActivitySection />
    </SWRConfig>,
  );
}

describe('BillingRecentActivitySection', () => {
  beforeEach(() => {
    mockGetBillingLedger.mockReset();

    mockGetBillingLedger.mockImplementation(({ page_index, page_size }) => {
      if (page_index === 2) {
        return Promise.resolve({
          items: [
            {
              ledger_bid: 'ledger-11',
              wallet_bucket_bid: 'bucket-topup',
              entry_type: 'grant',
              source_type: 'topup',
              source_bid: 'topup-11',
              idempotency_key: 'topup-11-bucket-topup',
              amount: 5,
              balance_after: 102.5,
              expires_at: null,
              consumable_from: null,
              metadata: {},
              created_at: '2026-04-07T10:00:00Z',
            },
          ],
          page: 2,
          page_count: 2,
          page_size,
          total: 11,
        });
      }

      return Promise.resolve({
        items: [
          {
            ledger_bid: 'ledger-1',
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
              usage_type: 1102,
              usage_scene: 'production',
              course_name: 'Published Course 1',
              user_identify: 'learner@example.com',
              metric_breakdown: [
                {
                  billing_metric: 'tts_request_count',
                  raw_amount: 1,
                  unit_size: 1,
                  credits_per_unit: 0.01,
                  rounding_mode: 'ceil',
                  consumed_credits: 0.01,
                },
              ],
            },
            created_at: '2026-04-06T10:00:00Z',
          },
          {
            ledger_bid: 'ledger-2',
            wallet_bucket_bid: 'bucket-free',
            entry_type: 'consume',
            source_type: 'usage',
            source_bid: 'usage-2',
            idempotency_key: 'usage-2-bucket-free',
            amount: -1.25,
            balance_after: 96.25,
            expires_at: null,
            consumable_from: null,
            metadata: {
              usage_bid: 'usage-2',
              usage_type: 1101,
              usage_scene: 'preview',
              course_name: 'Debug Course 1',
              user_identify: '15811237246',
            },
            created_at: '2026-04-06T09:00:00Z',
          },
        ],
        page: 1,
        page_count: 2,
        page_size,
        total: 11,
      });
    });
  });

  test('renders the credit usage details table from recent ledger entries', async () => {
    renderSection();

    await waitFor(() => {
      expect(mockGetBillingLedger).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 10,
        timezone: 'Asia/Shanghai',
      });
    });

    expect(
      await screen.findByText(
        'module.billing.details.usageTable.columns.scene',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.details.usageTable.title'),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(
        'module.billing.ledger.usageScene.tts - Published Course 1 - learner@example.com',
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(
        'module.billing.ledger.usageScene.debug - Debug Course 1 - 15811237246',
      ),
    ).toBeInTheDocument();
    expect(await screen.findAllByText(/Apr 6, 2026,/)).not.toHaveLength(0);
    expect(await screen.findByText('-2.50')).toBeInTheDocument();
    expect(
      screen.queryByText('module.billing.orders.title'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('usage-1')).not.toBeInTheDocument();
    expect(
      screen.getByRole('navigation', { name: 'pagination' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '1' })).toBeInTheDocument();
  });

  test('requests the next ledger page when pagination is used', async () => {
    const user = userEvent.setup();
    renderSection();

    expect(
      await screen.findByText(
        'module.billing.ledger.usageScene.tts - Published Course 1 - learner@example.com',
      ),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getByRole('link', { name: '2' }));
    });

    await waitFor(() => {
      expect(mockGetBillingLedger).toHaveBeenCalledWith({
        page_index: 2,
        page_size: 10,
        timezone: 'Asia/Shanghai',
      });
    });

    expect(
      await screen.findByText('module.billing.ledger.source.topup'),
    ).toBeInTheDocument();
    expect(await screen.findByText('+5.00')).toBeInTheDocument();
  });

  test('keeps a full 10-row skeleton height while the next ledger page is loading', async () => {
    const user = userEvent.setup();
    let resolveSecondPage:
      | ((value: {
          items: Array<Record<string, unknown>>;
          page: number;
          page_count: number;
          page_size: number;
          total: number;
        }) => void)
      | null = null;

    mockGetBillingLedger.mockImplementation(({ page_index, page_size }) => {
      if (page_index === 2) {
        return new Promise(resolve => {
          resolveSecondPage = resolve;
        });
      }

      return Promise.resolve({
        items: [
          {
            ledger_bid: 'ledger-1',
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
              usage_type: 1102,
              usage_scene: 'production',
              course_name: 'Published Course 1',
              user_identify: 'learner@example.com',
            },
            created_at: '2026-04-06T10:00:00Z',
          },
          {
            ledger_bid: 'ledger-2',
            wallet_bucket_bid: 'bucket-free',
            entry_type: 'consume',
            source_type: 'usage',
            source_bid: 'usage-2',
            idempotency_key: 'usage-2-bucket-free',
            amount: -1.25,
            balance_after: 96.25,
            expires_at: null,
            consumable_from: null,
            metadata: {
              usage_bid: 'usage-2',
              usage_type: 1101,
              usage_scene: 'preview',
              course_name: 'Debug Course 1',
              user_identify: '15811237246',
            },
            created_at: '2026-04-06T09:00:00Z',
          },
        ],
        page: 1,
        page_count: 2,
        page_size,
        total: 11,
      });
    });

    renderSection();

    expect(
      await screen.findByText(
        'module.billing.ledger.usageScene.tts - Published Course 1 - learner@example.com',
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(
        'module.billing.ledger.usageScene.debug - Debug Course 1 - 15811237246',
      ),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getByRole('link', { name: '2' }));
    });

    const skeleton = await screen.findByTestId('billing-usage-table-skeleton');
    expect(skeleton).toBeInTheDocument();
    expect(screen.getAllByTestId('billing-usage-skeleton-row')).toHaveLength(
      10,
    );

    await act(async () => {
      resolveSecondPage?.({
        items: [
          {
            ledger_bid: 'ledger-11',
            wallet_bucket_bid: 'bucket-topup',
            entry_type: 'grant',
            source_type: 'topup',
            source_bid: 'topup-11',
            idempotency_key: 'topup-11-bucket-topup',
            amount: 5,
            balance_after: 102.5,
            expires_at: null,
            consumable_from: null,
            metadata: {},
            created_at: '2026-04-07T10:00:00Z',
          },
        ],
        page: 2,
        page_count: 2,
        page_size: 10,
        total: 11,
      });
    });

    expect(
      await screen.findByText('module.billing.ledger.source.topup'),
    ).toBeInTheDocument();
  });
});
