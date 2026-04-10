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
              wallet_bucket_bid: 'bucket-free',
              entry_type: 'grant',
              source_type: 'gift',
              source_bid: 'gift-11',
              idempotency_key: 'gift-11-bucket-free',
              amount: 5,
              balance_after: 102.5,
              expires_at: null,
              consumable_from: null,
              metadata: {
                usage_scene: 'debug',
              },
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
              usage_scene: 'production',
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
      });
    });

    expect(
      await screen.findByText(
        'module.billing.details.usageTable.columns.scene',
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByText('module.billing.ledger.usageScene.production'),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Apr 6, 2026,/)).toBeInTheDocument();
    expect(await screen.findByText('-2.5')).toBeInTheDocument();
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
      await screen.findByText('module.billing.ledger.usageScene.production'),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.ledger.table.detail',
        }),
      );
    });

    expect(
      screen.getByText('module.billing.ledger.detail.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.detail.usageBid'),
    ).toBeInTheDocument();
    expect(screen.getByText('-2.5000000')).toBeInTheDocument();
    expect(screen.getAllByText('97.5000000').length).toBeGreaterThan(0);
    expect(screen.getByText('1.2500000')).toBeInTheDocument();
    expect(screen.getByText('2.5000000')).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.orders.table.order',
        }),
      );
    });

    await act(async () => {
      await user.click(screen.getByRole('link', { name: '2' }));
    });

    await waitFor(() => {
      expect(mockGetBillingLedger).toHaveBeenCalledWith({
        page_index: 2,
        page_size: 10,
      });
    });

    expect(
      await screen.findByText('module.billing.ledger.usageScene.debug'),
    ).toBeInTheDocument();
    expect(await screen.findByText('+5')).toBeInTheDocument();
  });
});
