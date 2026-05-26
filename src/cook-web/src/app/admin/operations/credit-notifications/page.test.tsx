import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { toast } from '@/hooks/useToast';
import AdminOperationCreditNotificationsPage from './page';

const mockReplace = jest.fn();
let mockSearchParams = new URLSearchParams();

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationCreditNotificationConfig: jest.fn(),
    getAdminOperationCreditNotifications: jest.fn(),
    dryRunAdminOperationCreditNotifications: jest.fn(),
    requeueAdminOperationCreditNotification: jest.fn(),
    syncAdminOperationCreditNotificationTemplate: jest.fn(),
    updateAdminOperationCreditNotificationConfig: jest.fn(),
  },
}));

jest.mock('next/navigation', () => ({
  usePathname: () => '/admin/operations/credit-notifications',
  useRouter: () => ({
    replace: mockReplace,
  }),
  useSearchParams: () => mockSearchParams,
}));

jest.mock('../useOperatorGuard', () => ({
  __esModule: true,
  default: () => ({
    isReady: true,
  }),
}));

const mockT = (key: string, fallback?: string | Record<string, unknown>) =>
  typeof fallback === 'string' ? fallback : key;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mockT,
  }),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: ({ errorMessage }: { errorMessage: string }) => (
    <div>{errorMessage}</div>
  ),
}));

jest.mock('@/hooks/useToast', () => ({
  toast: jest.fn(),
}));

const mockGetConfig =
  api.getAdminOperationCreditNotificationConfig as jest.Mock;
const mockGetRecords = api.getAdminOperationCreditNotifications as jest.Mock;
const mockRequeue = api.requeueAdminOperationCreditNotification as jest.Mock;
const mockSyncTemplate =
  api.syncAdminOperationCreditNotificationTemplate as jest.Mock;
const mockUpdateConfig =
  api.updateAdminOperationCreditNotificationConfig as jest.Mock;
const mockDryRun = api.dryRunAdminOperationCreditNotifications as jest.Mock;
const mockToast = toast as jest.Mock;

const openConfigTab = async () => {
  const configTab = screen.getByRole('tab', {
    name: 'module.operationsCreditNotifications.tabs.config',
  });
  fireEvent.pointerDown(configTab, { button: 0, ctrlKey: false });
  fireEvent.mouseDown(configTab, { button: 0, ctrlKey: false });
  fireEvent.click(configTab);
  await waitFor(() => {
    expect(
      screen.getByRole('tab', {
        name: 'module.operationsCreditNotifications.tabs.config',
      }),
    ).toHaveAttribute('data-state', 'active');
  });
};

describe('AdminOperationCreditNotificationsPage', () => {
  beforeEach(() => {
    mockSearchParams = new URLSearchParams();
    mockReplace.mockReset();
    mockGetConfig.mockReset();
    mockGetRecords.mockReset();
    mockDryRun.mockReset();
    mockRequeue.mockReset();
    mockSyncTemplate.mockReset();
    mockUpdateConfig.mockReset();
    mockToast.mockReset();
    mockGetConfig.mockResolvedValue({ enabled: false });
    mockUpdateConfig.mockResolvedValue({ enabled: false });
    mockDryRun.mockResolvedValue({
      status: 'ok',
      candidate_count: 1,
      created_count: 0,
      dry_run: true,
      notifications: [{ notification_type: 'low_balance' }],
    });
    mockGetRecords.mockResolvedValue({
      page: 1,
      page_size: 20,
      page_count: 1,
      total: 1,
      items: [
        {
          notification_bid: 'notification-1',
          notification_type: 'credit_granted',
          channel: 'sms',
          creator_bid: 'creator-1',
          target_user_bid: 'creator-1',
          mobile_snapshot: '13800000000',
          source_type: 'ledger',
          source_bid: 'ledger-1',
          dedupe_key: 'credit_granted:ledger-1',
          status: 'failed_provider',
          template_code: 'TPL-GRANT',
          template_params: {
            credits: '12.50',
            source: 'operator',
          },
          policy_snapshot: {},
          provider_response: {},
          error_code: 'provider_failed',
          error_message: 'failed',
          requested_at: '',
          attempted_at: '',
          sent_at: '',
          created_at: '2026-05-21T00:00:00',
          updated_at: '2026-05-21T00:00:00',
          metadata: {},
        },
      ],
    });
    mockRequeue.mockResolvedValue({
      status: 'enqueued',
      notification_bid: 'notification-1',
      enqueued: true,
    });
    mockSyncTemplate.mockResolvedValue({
      notification_type: 'credit_expiring',
      channel: 'sms',
      provider: 'aliyun',
      template_code: 'TPL-EXPIRING',
      template_name: 'Expiring',
      template_content: 'Credits ${credits} expire soon ${bad_variable}',
      template_status: 'AUDIT_STATE_PASS',
      template_type: '0',
      variable_attribute: {},
      provider_response: {},
      placeholders: ['credits', 'bad_variable'],
      supported_placeholders: ['credits', 'expires_at', 'window'],
      unused_supported_placeholders: ['expires_at', 'window'],
      unsupported_placeholders: ['bad_variable'],
      sync_status: 'synced',
      error_code: '',
      error_message: '',
      last_synced_at: '2026-05-22T00:00:00',
      compatible: false,
    });
  });

  it('shows notification records by default and switches to policy config tab', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('notification-1')).toBeInTheDocument();
    });
    expect(
      screen.getByRole('tab', {
        name: 'module.operationsCreditNotifications.tabs.records',
      }),
    ).toHaveAttribute('data-state', 'active');

    await openConfigTab();

    expect(
      screen.getByText('module.operationsCreditNotifications.config.title'),
    ).toBeInTheDocument();
    expect(mockReplace).toHaveBeenCalledWith(
      '/admin/operations/credit-notifications?tab=config',
      { scroll: false },
    );
  });

  it('opens policy config tab from the tab query parameter', async () => {
    mockSearchParams = new URLSearchParams('tab=config');

    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(
        screen.getByRole('tab', {
          name: 'module.operationsCreditNotifications.tabs.config',
        }),
      ).toHaveAttribute('data-state', 'active');
    });
    expect(
      screen.getByText('module.operationsCreditNotifications.config.title'),
    ).toBeInTheDocument();
  });

  it('lists failed provider records and requeues them', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('notification-1')).toBeInTheDocument();
    });
    expect(
      screen.getByText('{"credits":"12.50","source":"operator"}'),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.requeue',
      }),
    );

    await waitFor(() => {
      expect(mockRequeue).toHaveBeenCalledWith({
        notification_bid: 'notification-1',
      });
    });
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.operationsCreditNotifications.messages.requeueDone',
    });
  });

  it('surfaces requeue failures without refreshing records as success', async () => {
    mockRequeue.mockResolvedValueOnce({
      status: 'enqueue_failed',
      notification_bid: 'notification-1',
      enqueued: false,
      message: 'queue unavailable',
    });
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('notification-1')).toBeInTheDocument();
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.requeue',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        title: 'module.operationsCreditNotifications.messages.requeueFailed',
        description: 'queue unavailable',
      });
    });
    expect(mockGetRecords).toHaveBeenCalledTimes(1);
  });

  it('blocks config save when policy loading fails', async () => {
    mockGetConfig.mockRejectedValueOnce(new Error('config unavailable'));
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    expect(screen.getByText('config unavailable')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.applyConfig',
      }),
    ).toBeDisabled();
  });

  it('searches with draft filters only after clicking search and resets filters', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(mockGetRecords).toHaveBeenCalledTimes(1);
    });

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCreditNotifications.filters.creatorBid',
      ),
      { target: { value: 'creator-draft' } },
    );
    expect(mockGetRecords).toHaveBeenCalledTimes(1);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetRecords).toHaveBeenCalledTimes(2);
    });
    expect(mockGetRecords.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        creator_bid: 'creator-draft',
        page_index: 1,
      }),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.reset',
      }),
    );

    await waitFor(() => {
      expect(mockGetRecords).toHaveBeenCalledTimes(3);
    });
    expect(mockGetRecords.mock.calls[2][0]).toEqual(
      expect.objectContaining({
        creator_bid: '',
        page_index: 1,
      }),
    );
  });

  it('saves structured config changes without exposing a raw JSON editor', async () => {
    const { container } = render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(mockGetConfig).toHaveBeenCalled();
    });
    await openConfigTab();

    expect(container.querySelector('textarea')).toBeNull();

    const templateInputs = screen.getAllByLabelText(
      'module.operationsCreditNotifications.config.fields.templateCode',
    ) as HTMLInputElement[];
    fireEvent.change(templateInputs[1], {
      target: { value: 'TPL-GRANT-UPDATED' },
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.applyConfig',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          channel: 'sms',
          types: expect.objectContaining({
            credit_granted: expect.objectContaining({
              template_code: 'TPL-GRANT-UPDATED',
            }),
          }),
        }),
      );
      expect(JSON.stringify(mockUpdateConfig.mock.calls[0][0])).not.toContain(
        'placeholders',
      );
    });
  });

  it('shows dynamic template placeholders and tolerance copy', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(mockGetConfig).toHaveBeenCalled();
    });
    await openConfigTab();

    expect(
      screen.getAllByText(
        'module.operationsCreditNotifications.config.placeholders.tolerance',
      ),
    ).toHaveLength(3);
    expect(
      screen.getAllByText(
        'module.operationsCreditNotifications.config.placeholders.available',
      ),
    ).toHaveLength(3);
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.config.placeholders.groups.creditExpiring',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.config.placeholders.notes.windowSource',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.config.placeholders.groups.lowBalanceFixed',
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText('${credits}')).toHaveLength(2);
    expect(screen.getByText('${available_credits}')).toBeInTheDocument();
    expect(
      screen.queryByText('${estimated_remaining_days}'),
    ).not.toBeInTheDocument();
  });

  it('shows estimated-days and fallback placeholders when the low-balance mode is enabled', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(mockGetConfig).toHaveBeenCalled();
    });
    await openConfigTab();

    fireEvent.click(
      screen.getByLabelText(
        'module.operationsCreditNotifications.config.fields.estimatedDaysEnabled',
      ),
    );

    expect(
      screen.getByText(
        'module.operationsCreditNotifications.config.placeholders.groups.lowBalanceEstimated',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('${trigger_days}')).toBeInTheDocument();
    expect(screen.getByText('${lookback_days}')).toBeInTheDocument();
    expect(screen.getByText('${avg_daily_consumption}')).toBeInTheDocument();
    expect(screen.getByText('${estimated_remaining_days}')).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.config.placeholders.notes.fallbackLowBalance',
      ),
    ).toBeInTheDocument();
  });

  it('syncs and displays Aliyun template variables without saving them into policy', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(mockGetConfig).toHaveBeenCalled();
    });
    await openConfigTab();

    const templateInputs = screen.getAllByLabelText(
      'module.operationsCreditNotifications.config.fields.templateCode',
    ) as HTMLInputElement[];
    fireEvent.change(templateInputs[0], {
      target: { value: 'TPL-EXPIRING' },
    });

    fireEvent.click(
      screen.getAllByRole('button', {
        name: 'module.operationsCreditNotifications.actions.syncTemplate',
      })[0],
    );

    await waitFor(() => {
      expect(mockSyncTemplate).toHaveBeenCalledWith({
        notification_type: 'credit_expiring',
        template_code: 'TPL-EXPIRING',
      });
    });
    expect(
      screen.getByText('Credits ${credits} expire soon ${bad_variable}'),
    ).toBeInTheDocument();
    expect(screen.getByText('${bad_variable}')).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.config.templateSync.incompatible',
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.applyConfig',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalled();
    });
    const savedPayload = JSON.stringify(mockUpdateConfig.mock.calls[0][0]);
    expect(savedPayload).not.toContain('template_content');
    expect(savedPayload).not.toContain('unsupported_placeholders');
  });

  it('keeps dry-run in the policy config tab', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(mockGetConfig).toHaveBeenCalled();
    });
    await openConfigTab();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.dryRun',
      }),
    );

    await waitFor(() => {
      expect(mockDryRun).toHaveBeenCalledWith({
        notification_type: '',
        creator_bid: '',
      });
    });
    expect(
      screen.getByText(/"notification_type": "low_balance"/),
    ).toBeInTheDocument();
  });

  it('saves estimated-days low balance thresholds from the structured form', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(mockGetConfig).toHaveBeenCalled();
    });
    await openConfigTab();

    fireEvent.click(
      screen.getByLabelText(
        'module.operationsCreditNotifications.config.fields.estimatedDaysEnabled',
      ),
    );
    fireEvent.change(
      screen.getByLabelText(
        'module.operationsCreditNotifications.config.fields.estimatedDays',
      ),
      { target: { value: '5' } },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.applyConfig',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          types: expect.objectContaining({
            low_balance: expect.objectContaining({
              thresholds: expect.arrayContaining([
                { kind: 'fixed', value: '0' },
                {
                  kind: 'estimated_days',
                  days: 5,
                  lookback_days: 7,
                  min_consumed_days: 2,
                  fallback_fixed_value: '0',
                },
              ]),
            }),
          }),
        }),
      );
    });
  });
});
