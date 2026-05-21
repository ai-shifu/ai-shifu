import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import AdminOperationCreditNotificationsPage from './page';

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationCreditNotificationConfig: jest.fn(),
    getAdminOperationCreditNotifications: jest.fn(),
    dryRunAdminOperationCreditNotifications: jest.fn(),
    requeueAdminOperationCreditNotification: jest.fn(),
    updateAdminOperationCreditNotificationConfig: jest.fn(),
  },
}));

jest.mock('../useOperatorGuard', () => ({
  __esModule: true,
  default: () => ({
    isReady: true,
  }),
}));

const mockT = (key: string, fallback?: string) => fallback || key;

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

describe('AdminOperationCreditNotificationsPage', () => {
  beforeEach(() => {
    mockGetConfig.mockReset();
    mockGetRecords.mockReset();
    mockRequeue.mockReset();
    mockGetConfig.mockResolvedValue({ enabled: false });
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
          template_params: {},
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
  });

  it('lists failed provider records and requeues them', async () => {
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
      expect(mockRequeue).toHaveBeenCalledWith({
        notification_bid: 'notification-1',
      });
    });
  });
});
