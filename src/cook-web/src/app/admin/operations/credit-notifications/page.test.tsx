import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { toast } from '@/hooks/useToast';
import AdminOperationCreditNotificationsPage from './page';

const mockReplace = jest.fn();
const mockPush = jest.fn();
let mockSearchParams = new URLSearchParams();
let mockLoginMethodsEnabled = ['phone'];
let mockDefaultLoginMethod = 'phone';

const mockTranslations: Record<string, string> = {
  'module.operationsCreditNotifications.errorReason.policy_disabled':
    'Notification policy is disabled, not sent.',
  'module.operationsCreditNotifications.errorReason.provider_failed':
    'SMS provider did not return an accepted response.',
};

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationCreditNotificationConfig: jest.fn(),
    getAdminOperationCreditNotificationDetail: jest.fn(),
    getAdminOperationCreditNotificationTemplates: jest.fn(),
    getAdminOperationCreditNotifications: jest.fn(),
    getAdminOperationCreditNotificationsOverview: jest.fn(),
    dryRunAdminOperationCreditNotifications: jest.fn(),
    requeueAdminOperationCreditNotification: jest.fn(),
    syncAdminOperationCreditNotificationTemplate: jest.fn(),
    updateAdminOperationCreditNotificationConfig: jest.fn(),
  },
}));

jest.mock('next/navigation', () => ({
  usePathname: () => '/admin/operations/credit-notifications',
  useRouter: () => ({
    push: mockPush,
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

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (
    selector: (state: {
      loginMethodsEnabled: string[];
      defaultLoginMethod: string;
    }) => unknown,
  ) =>
    selector({
      loginMethodsEnabled: mockLoginMethodsEnabled,
      defaultLoginMethod: mockDefaultLoginMethod,
    }),
}));

const mockT = (
  key: string,
  fallback?: string | { defaultValue?: string } | Record<string, unknown>,
) => {
  if (typeof fallback === 'string') {
    return fallback;
  }
  if (mockTranslations[key]) {
    return mockTranslations[key];
  }
  if (
    fallback &&
    typeof fallback === 'object' &&
    'defaultValue' in fallback &&
    typeof fallback.defaultValue === 'string'
  ) {
    return fallback.defaultValue;
  }
  return key;
};

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

jest.mock('@/components/ui/DropdownMenu', () => ({
  __esModule: true,
  DropdownMenu: ({ children }: React.PropsWithChildren) => {
    const React = jest.requireActual('react') as typeof import('react');
    const [open, setOpen] = React.useState(false);
    return (
      <div
        data-open={open}
        data-testid='dropdown-menu'
      >
        {React.Children.map(children, child => {
          if (!React.isValidElement(child)) {
            return child;
          }
          return React.cloneElement(child, {
            __dropdownOpen: open,
            __setDropdownOpen: setOpen,
          } as Record<string, unknown>);
        })}
      </div>
    );
  },
  DropdownMenuTrigger: ({
    children,
    __setDropdownOpen,
  }: React.PropsWithChildren<{
    asChild?: boolean;
    __setDropdownOpen?: React.Dispatch<React.SetStateAction<boolean>>;
  }>) => {
    const React = jest.requireActual('react') as typeof import('react');
    if (React.isValidElement(children)) {
      const child = children as React.ReactElement<{
        onClick?: (event: React.MouseEvent) => void;
      }>;
      return React.cloneElement(children, {
        onClick: (event: React.MouseEvent) => {
          child.props.onClick?.(event);
          __setDropdownOpen?.(current => !current);
        },
      } as Record<string, unknown>);
    }
    return <>{children}</>;
  },
  DropdownMenuContent: ({
    children,
    __dropdownOpen,
  }: React.PropsWithChildren<{
    align?: string;
    __dropdownOpen?: boolean;
  }>) => (__dropdownOpen ? <div>{children}</div> : null),
  DropdownMenuItem: ({
    children,
    onClick,
  }: React.PropsWithChildren<{ onClick?: () => void }>) => (
    <button
      type='button'
      onClick={onClick}
    >
      {children}
    </button>
  ),
}));

jest.mock('@/hooks/useToast', () => ({
  toast: jest.fn(),
}));

const mockGetConfig =
  api.getAdminOperationCreditNotificationConfig as jest.Mock;
const mockGetDetail =
  api.getAdminOperationCreditNotificationDetail as jest.Mock;
const mockGetTemplates =
  api.getAdminOperationCreditNotificationTemplates as jest.Mock;
const mockGetRecords = api.getAdminOperationCreditNotifications as jest.Mock;
const mockGetOverview =
  api.getAdminOperationCreditNotificationsOverview as jest.Mock;
const mockRequeue = api.requeueAdminOperationCreditNotification as jest.Mock;
const mockSyncTemplate =
  api.syncAdminOperationCreditNotificationTemplate as jest.Mock;
const mockUpdateConfig =
  api.updateAdminOperationCreditNotificationConfig as jest.Mock;
const mockDryRun = api.dryRunAdminOperationCreditNotifications as jest.Mock;
const mockToast = toast as jest.Mock;

const openConfigTab = async ({
  waitForTemplates = true,
}: {
  waitForTemplates?: boolean;
} = {}) => {
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
  await waitFor(() => {
    expect(mockGetConfig).toHaveBeenCalled();
  });
  await screen.findByText('module.operationsCreditNotifications.config.title');
  if (waitForTemplates) {
    await waitFor(() => {
      expect(mockGetTemplates).toHaveBeenCalled();
    });
    await screen.findByText('Grant');
  }
};

const openRecordMoreMenu = () => {
  const moreButton = screen.getByRole('button', {
    name: 'module.operationsCreditNotifications.actions.more',
  });
  fireEvent.pointerDown(moreButton, { button: 0, ctrlKey: false });
  fireEvent.mouseDown(moreButton, { button: 0, ctrlKey: false });
  fireEvent.click(moreButton);
};

describe('AdminOperationCreditNotificationsPage', () => {
  beforeEach(() => {
    mockSearchParams = new URLSearchParams();
    mockLoginMethodsEnabled = ['phone'];
    mockDefaultLoginMethod = 'phone';
    mockReplace.mockReset();
    mockPush.mockReset();
    mockGetConfig.mockReset();
    mockGetDetail.mockReset();
    mockGetTemplates.mockReset();
    mockGetRecords.mockReset();
    mockGetOverview.mockReset();
    mockDryRun.mockReset();
    mockRequeue.mockReset();
    mockSyncTemplate.mockReset();
    mockUpdateConfig.mockReset();
    mockToast.mockReset();
    mockGetConfig.mockResolvedValue({ enabled: false });
    mockUpdateConfig.mockResolvedValue({ enabled: false });
    mockGetDetail.mockResolvedValue({
      notification_bid: 'notification-1',
      notification_type: 'credit_granted',
      channel: 'sms',
      creator_bid: 'creator-1',
      creator_nickname: 'Creator One',
      target_user_bid: 'creator-1',
      mobile_snapshot: '13800000000',
      source_type: 'ledger',
      source_bid: 'ledger-1',
      dedupe_key: 'credit_granted:ledger-1',
      status: 'failed_provider',
      template_code: 'TPL-GRANT',
      template_name: '',
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
    });
    mockGetOverview.mockResolvedValue({
      total: 10,
      pending: 2,
      sent: 5,
      failed: 1,
      skipped: 2,
    });
    mockGetTemplates.mockResolvedValue({
      items: [
        {
          channel: 'sms',
          provider: 'aliyun',
          template_code: 'TPL-GRANT',
          template_name: 'Grant',
          template_content: 'Credits ${credits}',
          template_status: 'AUDIT_STATE_PASS',
          template_type: '0',
          sync_status: 'synced',
          error_code: '',
          error_message: '',
          last_synced_at: '2026-05-22T00:00:00',
          source: 'provider',
        },
      ],
      source: 'provider',
      provider_available: true,
      error_code: '',
      error_message: '',
    });
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
          creator_nickname: 'Creator One',
          target_user_bid: 'creator-1',
          mobile_snapshot: '13800000000',
          source_type: 'ledger',
          source_bid: 'ledger-1',
          dedupe_key: 'credit_granted:ledger-1',
          status: 'failed_provider',
          template_code: 'TPL-GRANT',
          template_name: '',
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
      expect(screen.getByText('Creator One')).toBeInTheDocument();
    });
    expect(mockGetConfig).not.toHaveBeenCalled();
    expect(mockGetTemplates).not.toHaveBeenCalled();
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
      expect(screen.getByText('Creator One')).toBeInTheDocument();
    });
    expect(screen.getByText('ledger')).toBeInTheDocument();
    expect(
      screen.getByText('SMS provider did not return an accepted response.'),
    ).toBeInTheDocument();

    openRecordMoreMenu();
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
    await waitFor(() => {
      expect(mockGetRecords).toHaveBeenCalledTimes(2);
      expect(mockGetOverview).toHaveBeenCalledTimes(2);
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
      expect(screen.getByText('Creator One')).toBeInTheDocument();
    });
    openRecordMoreMenu();
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

  it('opens record details from the more menu', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Creator One')).toBeInTheDocument();
    });

    openRecordMoreMenu();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.detail',
      }),
    );

    await waitFor(() => {
      expect(mockGetDetail).toHaveBeenCalledWith({
        notification_bid: 'notification-1',
      });
    });
    expect(
      screen.getByText('module.operationsCreditNotifications.detail.title'),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('SMS provider did not return an accepted response.')
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getByText('notification-1')).toBeInTheDocument();
    expect(screen.getByText('credit_granted:ledger-1')).toBeInTheDocument();
  });

  it('localizes policy-disabled notification errors in the records table', async () => {
    mockGetRecords.mockResolvedValueOnce({
      page: 1,
      page_size: 20,
      page_count: 1,
      total: 1,
      items: [
        {
          notification_bid: 'notification-policy-disabled',
          notification_type: 'credit_expiring',
          channel: 'sms',
          creator_bid: 'creator-1',
          creator_nickname: 'Creator One',
          target_user_bid: 'creator-1',
          mobile_snapshot: '13800000000',
          source_type: 'wallet_bucket',
          source_bid: 'bucket-1',
          status: 'skipped_opt_out',
          template_code: 'TPL-EXPIRING',
          template_name: '',
          policy_snapshot: {},
          provider_response: {},
          error_code: 'policy_disabled',
          error_message: 'Notification policy is disabled.',
          requested_at: '',
          attempted_at: '',
          sent_at: '',
          created_at: '2026-05-21T00:00:00',
          updated_at: '2026-05-21T00:00:00',
          metadata: {},
        },
      ],
    });

    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(
        screen.getByText('Notification policy is disabled, not sent.'),
      ).toBeInTheDocument();
    });
  });

  it('uses backend fallback for new error codes without locale entries', async () => {
    mockGetRecords.mockResolvedValueOnce({
      page: 1,
      page_size: 20,
      page_count: 1,
      total: 1,
      items: [
        {
          notification_bid: 'notification-future-code',
          notification_type: 'low_balance',
          channel: 'sms',
          creator_bid: 'creator-1',
          creator_nickname: 'Creator One',
          target_user_bid: 'creator-1',
          mobile_snapshot: '13800000000',
          source_type: 'wallet',
          source_bid: 'creator-1',
          status: 'skipped_opt_out',
          template_code: 'TPL-LOW-BALANCE',
          template_name: '',
          policy_snapshot: {},
          provider_response: {},
          error_code: 'future_reason',
          error_message: 'Future backend reason.',
          requested_at: '',
          attempted_at: '',
          sent_at: '',
          created_at: '2026-05-21T00:00:00',
          updated_at: '2026-05-21T00:00:00',
          metadata: {},
        },
      ],
    });

    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Future backend reason.')).toBeInTheDocument();
    });
  });

  it('blocks config save when policy loading fails', async () => {
    mockGetConfig.mockRejectedValueOnce(new Error('config unavailable'));
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab({ waitForTemplates: false });

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

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.expand',
      }),
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCreditNotifications.filters.creatorPlaceholder',
      ),
      { target: { value: '13800138000' } },
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
        creator_keyword: '13800138000',
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
        creator_keyword: '',
        page_index: 1,
      }),
    );
  });

  it('applies overview card filters to the search results', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(mockGetRecords).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.overview.pending',
      }),
    );

    await waitFor(() => {
      expect(mockGetRecords).toHaveBeenCalledTimes(2);
    });
    expect(mockGetRecords.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        page_index: 1,
        delivery_status: 'pending',
      }),
    );
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.overview.activeFilter',
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.overview.pending common.core.close',
      }),
    );

    await waitFor(() => {
      expect(mockGetRecords).toHaveBeenCalledTimes(3);
    });
    expect(mockGetRecords.mock.calls[2][0]).toEqual(
      expect.objectContaining({
        page_index: 1,
        delivery_status: '',
        skip_reason: '',
      }),
    );
  });

  it('saves structured config changes without exposing a raw JSON editor', async () => {
    const { container } = render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    expect(container.querySelector('textarea')).toBeNull();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.changeTemplate',
      }),
    );
    const templateInputs = screen.getAllByLabelText(
      'module.operationsCreditNotifications.config.fields.templateCode',
    ) as HTMLInputElement[];
    fireEvent.change(templateInputs[1], {
      target: { value: 'TPL-GRANT-UPDATED' },
    });
    const windowsInput = screen.getByLabelText(
      'module.operationsCreditNotifications.config.fields.windows',
    );
    fireEvent.change(windowsInput, {
      target: { value: '７ｄ，' },
    });
    expect(windowsInput).toHaveValue('7d,');
    fireEvent.change(windowsInput, {
      target: { value: '７ｄ，３ｄ、１ｄ，０ｄ' },
    });
    expect(windowsInput).toHaveValue('7d,3d,1d,0d');
    fireEvent.blur(windowsInput);
    expect(windowsInput).toHaveValue('7d, 3d, 1d, 0d');
    const thresholdInput = screen.getByLabelText(
      'module.operationsCreditNotifications.config.fields.thresholds',
    );
    fireEvent.change(thresholdInput, {
      target: { value: '１００，５０，１０，' },
    });
    expect(thresholdInput).toHaveValue('100,50,10,');
    const perMobileInput = screen.getByLabelText(
      'module.operationsCreditNotifications.config.fields.perMobilePerDay',
    );
    expect(perMobileInput).not.toHaveAttribute('type', 'number');
    fireEvent.change(perMobileInput, {
      target: { value: '-３.５' },
    });
    expect(perMobileInput).toHaveValue('');
    const dailyLimitInput = screen.getByLabelText(
      'module.operationsCreditNotifications.config.fields.dailySmsLimit',
    );
    fireEvent.change(dailyLimitInput, {
      target: { value: '０' },
    });
    expect(dailyLimitInput).toHaveValue('0');
    const blockedCreatorsInput = screen.getByLabelText(
      'module.operationsCreditNotifications.config.fields.blockedCreators',
    );
    fireEvent.change(blockedCreatorsInput, {
      target: { value: 'creator-1，13800000000，owner@example.com' },
    });
    expect(blockedCreatorsInput).toHaveValue(
      'creator-1,13800000000,owner@example.com',
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.config.listDialog.add',
      }),
    );
    expect(blockedCreatorsInput).toHaveValue('');
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.config.fields.blockedCreatorList',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/13800000000/)).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.config.emptyOptedOutCreators',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(
        'module.operationsCreditNotifications.config.inputPlaceholders.blockedCreatorsPhone',
      ),
    ).toBeInTheDocument();
    expect(JSON.stringify(mockUpdateConfig.mock.calls)).not.toContain(
      '100,50,10',
    );

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
              template_code: 'TPL-GRANT',
            }),
            credit_expiring: expect.objectContaining({
              windows: ['7d', '3d', '1d', '0d'],
            }),
            low_balance: expect.objectContaining({
              thresholds: expect.arrayContaining([
                expect.objectContaining({ value: '100' }),
                expect.objectContaining({ value: '50' }),
                expect.objectContaining({ value: '10' }),
              ]),
            }),
          }),
          frequency: expect.objectContaining({
            per_mobile_per_day: 0,
          }),
          budget: expect.objectContaining({
            daily_sms_limit: 0,
          }),
          blacklist: expect.objectContaining({
            creator_bids: ['creator-1', 'owner@example.com'],
            mobiles: ['13800000000'],
          }),
        }),
      );
      expect(JSON.stringify(mockUpdateConfig.mock.calls[0][0])).not.toContain(
        'placeholders',
      );
    });
  });

  it('uses email wording for the blocked creator field on email login sites', async () => {
    mockLoginMethodsEnabled = ['email'];
    mockDefaultLoginMethod = 'email';

    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    expect(
      screen.getByPlaceholderText(
        'module.operationsCreditNotifications.config.inputPlaceholders.blockedCreatorsEmail',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText(
        'module.operationsCreditNotifications.config.inputPlaceholders.blockedCreatorsPhone',
      ),
    ).not.toBeInTheDocument();
  });

  it('shows recommended templates without marking config dirty before saving', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    expect(screen.getByText('Grant')).toBeInTheDocument();

    const recordsTab = screen.getByRole('tab', {
      name: 'module.operationsCreditNotifications.tabs.records',
    });
    fireEvent.pointerDown(recordsTab, { button: 0, ctrlKey: false });
    fireEvent.mouseDown(recordsTab, { button: 0, ctrlKey: false });
    fireEvent.click(recordsTab);

    expect(
      screen.queryByText(
        'module.operationsCreditNotifications.config.unsavedDialog.title',
      ),
    ).not.toBeInTheDocument();
    expect(recordsTab).toHaveAttribute('data-state', 'active');
  });

  it('writes recommended templates when saving config', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.applyConfig',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          types: expect.objectContaining({
            credit_granted: expect.objectContaining({
              template_code: 'TPL-GRANT',
            }),
          }),
        }),
      );
    });
  });

  it('extracts blocked creators from spreadsheet-style pasted contacts and rejects invalid rows', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    const blockedCreatorsInput = screen.getByLabelText(
      'module.operationsCreditNotifications.config.fields.blockedCreators',
    );
    fireEvent.change(blockedCreatorsInput, {
      target: {
        value: '15811237246\t美少女大战哥斯拉\n15911234444\t测试昵称',
      },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.config.listDialog.add',
      }),
    );

    expect(screen.getByText(/15811237246/)).toBeInTheDocument();
    expect(screen.getByText(/15911234444/)).toBeInTheDocument();
    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title:
          'module.operationsCreditNotifications.config.listDialog.addedBlockedCreators',
      }),
    );

    fireEvent.change(blockedCreatorsInput, {
      target: { value: '无法识别的老师' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.config.listDialog.add',
      }),
    );

    expect(mockToast).toHaveBeenLastCalledWith(
      expect.objectContaining({
        title:
          'module.operationsCreditNotifications.config.listDialog.invalidBlockedCreators',
        variant: 'destructive',
      }),
    );
  });

  it('extracts blocked creators from spreadsheet-style pasted emails on email sites', async () => {
    mockLoginMethodsEnabled = ['email'];
    mockDefaultLoginMethod = 'email';

    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    const blockedCreatorsInput = screen.getByLabelText(
      'module.operationsCreditNotifications.config.fields.blockedCreators',
    );
    fireEvent.paste(blockedCreatorsInput, {
      clipboardData: {
        getData: () => 'owner@example.com\tOwner\nsecond@example.com\tSecond',
      },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.config.listDialog.add',
      }),
    );

    expect(screen.getByText(/owner@example.com/)).toBeInTheDocument();
    expect(screen.getByText(/second@example.com/)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.applyConfig',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          blacklist: expect.objectContaining({
            creator_bids: ['owner@example.com', 'second@example.com'],
            mobiles: [],
          }),
        }),
      );
    });
  });

  it('opens blocked creators dialog and removes an item from the draft list', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      blacklist: {
        creator_bids: [],
        mobiles: ['13800000000'],
      },
      resolved_lists: {
        blacklist: {
          items: [
            {
              identifier: '13800000000',
              creator_bid: 'creator-1',
              mobile: '13800000000',
              email: '',
              nickname: 'Creator One',
            },
          ],
        },
      },
    });

    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    expect(screen.getByText(/13800000000/)).toBeInTheDocument();
    fireEvent.click(
      screen.getByText(
        'module.operationsCreditNotifications.config.listDialog.manage',
      ),
    );
    expect(
      screen.getAllByText(
        'module.operationsCreditNotifications.config.fields.blockedCreatorList',
      ).length,
    ).toBeGreaterThan(1);
    expect(screen.getByText('Creator One')).toBeInTheDocument();

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCreditNotifications.config.listDialog.searchPlaceholderPhone',
      ),
      { target: { value: '13800000000' } },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.operationsCreditNotifications.config.listDialog.delete/,
      }),
    );
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.config.listDialog.emptyResult',
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.confirm',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.applyConfig',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          blacklist: {
            creator_bids: [],
            mobiles: [],
          },
        }),
      );
    });
  });

  it('asks before leaving config tab with unsaved changes and restores discarded edits', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    const blockedCreatorsInput = screen.getByLabelText(
      'module.operationsCreditNotifications.config.fields.blockedCreators',
    );
    fireEvent.change(blockedCreatorsInput, {
      target: { value: 'creator-unsaved' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.config.listDialog.add',
      }),
    );
    await waitFor(() => {
      expect(screen.getByText(/creator-unsaved/)).toBeInTheDocument();
    });

    const recordsTab = screen.getByRole('tab', {
      name: 'module.operationsCreditNotifications.tabs.records',
    });
    fireEvent.pointerDown(recordsTab, { button: 0, ctrlKey: false });
    fireEvent.mouseDown(recordsTab, { button: 0, ctrlKey: false });
    fireEvent.click(recordsTab);

    await waitFor(() => {
      expect(
        screen.getByText(
          'module.operationsCreditNotifications.config.unsavedDialog.title',
        ),
      ).toBeInTheDocument();
    });
    expect(mockReplace).toHaveBeenLastCalledWith(
      '/admin/operations/credit-notifications?tab=config',
      { scroll: false },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.config.unsavedDialog.discard',
      }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole('tab', {
          name: 'module.operationsCreditNotifications.tabs.records',
        }),
      ).toHaveAttribute('data-state', 'active');
    });
    await openConfigTab();
    expect(
      screen.getByLabelText(
        'module.operationsCreditNotifications.config.fields.blockedCreators',
      ),
    ).toHaveValue('');
  });

  it('shows dynamic template placeholders and tolerance copy', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    expect(
      screen.getAllByText(
        'module.operationsCreditNotifications.config.placeholders.tolerance',
      ),
    ).toHaveLength(3);
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.config.placeholders.guideTitle.credit_expiring',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        'module.operationsCreditNotifications.config.placeholders.groups.creditExpiring',
      ),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.config.placeholders.notes.windowSource',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        'module.operationsCreditNotifications.config.placeholders.groups.lowBalanceFixed',
      ),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText('${credits}')).toHaveLength(2);
    expect(screen.getByText('${available_credits}')).toBeInTheDocument();
    expect(
      screen.queryByText('${estimated_remaining_days}'),
    ).not.toBeInTheDocument();
  });

  it('shows estimated-days and fallback placeholders when the low-balance mode is enabled', async () => {
    render(<AdminOperationCreditNotificationsPage />);

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

    await openConfigTab();

    const templateInputs = screen.getAllByLabelText(
      'module.operationsCreditNotifications.config.fields.templateCode',
    ) as HTMLInputElement[];
    fireEvent.change(templateInputs[0], {
      target: { value: 'TPL-EXPIRING' },
    });

    fireEvent.click(
      screen.getAllByRole('button', {
        name: 'module.operationsCreditNotifications.actions.applyTemplate',
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

  it('shows dry-run failures inside the config tab without reusing records errors', async () => {
    mockDryRun.mockRejectedValueOnce({
      message: 'dry-run failed',
      code: 5001,
    });

    render(<AdminOperationCreditNotificationsPage />);

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

    expect(screen.getByText('dry-run failed')).toBeInTheDocument();
    expect(
      screen.queryByText('module.operationsCreditNotifications.loadError'),
    ).not.toBeInTheDocument();
  });

  it('saves estimated-days low balance thresholds from the structured form', async () => {
    render(<AdminOperationCreditNotificationsPage />);

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
