import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import api from '@/api';
import { BillingReportsTab } from './BillingReportsTab';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key}:${JSON.stringify(options)}` : key,
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
    getBillingDailyUsageMetrics: jest.fn(),
    getBillingDailyLedgerSummary: jest.fn(),
  },
}));

const mockGetBillingDailyUsageMetrics =
  api.getBillingDailyUsageMetrics as jest.Mock;
const mockGetBillingDailyLedgerSummary =
  api.getBillingDailyLedgerSummary as jest.Mock;

function renderComponent() {
  return render(
    <SWRConfig
      value={{
        provider: () => new Map(),
      }}
    >
      <BillingReportsTab />
    </SWRConfig>,
  );
}

describe('BillingReportsTab', () => {
  beforeEach(() => {
    mockGetBillingDailyUsageMetrics.mockReset();
    mockGetBillingDailyLedgerSummary.mockReset();
    mockGetBillingDailyUsageMetrics.mockResolvedValue({
      items: [
        {
          daily_usage_metric_bid: 'daily-usage-1',
          stat_date: '2026-04-06',
          shifu_bid: 'shifu-1',
          usage_scene: 'production',
          usage_type: 'llm',
          provider: 'openai',
          model: 'gpt-4o-mini',
          billing_metric: 'llm_output_tokens',
          raw_amount: 1234,
          record_count: 3,
          consumed_credits: 4.5,
          window_started_at: '2026-04-06T00:00:00+00:00',
          window_ended_at: '2026-04-07T00:00:00+00:00',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 8,
      total: 1,
    });
    mockGetBillingDailyLedgerSummary.mockResolvedValue({
      items: [
        {
          daily_ledger_summary_bid: 'daily-ledger-1',
          stat_date: '2026-04-06',
          entry_type: 'consume',
          source_type: 'usage',
          amount: -4.5,
          entry_count: 3,
          window_started_at: '2026-04-06T00:00:00+00:00',
          window_ended_at: '2026-04-07T00:00:00+00:00',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 8,
      total: 1,
    });
  });

  test('renders daily usage and ledger report rows', async () => {
    renderComponent();

    await waitFor(() => {
      expect(mockGetBillingDailyUsageMetrics).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 8,
        timezone: 'Asia/Shanghai',
      });
      expect(mockGetBillingDailyLedgerSummary).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 8,
        timezone: 'Asia/Shanghai',
      });
    });

    expect(
      screen.getByText('module.billing.reports.title'),
    ).toBeInTheDocument();
    expect(await screen.findByText('shifu-1')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.reports.metric.llmOutputTokens'),
    ).toBeInTheDocument();
    expect(screen.getByText('openai / gpt-4o-mini')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.entryType.consume'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.source.usage'),
    ).toBeInTheDocument();
  });
});
