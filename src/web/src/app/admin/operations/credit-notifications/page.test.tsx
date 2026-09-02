import React from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import api from '@/api';
import {
  formatAdminDateRangeEndUtc,
  formatAdminDateRangeStartUtc,
} from '@/lib/admin-date-time';
import { toast } from '@/hooks/useToast';
import AdminOperationCreditNotificationsPage from './page';
import { normalizePolicy } from './creditNotificationUtils';

Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: jest.fn(),
});

const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockTrackEvent = jest.fn();
let mockSearchParams = new URLSearchParams();
let mockLoginMethodsEnabled = ['phone'];
let mockDefaultLoginMethod = 'phone';
const mockBrowserTimeZone = jest.fn(() => 'America/Los_Angeles');

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

const mockTranslations: Record<string, string> = {
  'module.user.defaultUserName': 'Anonymous User',
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

jest.mock('@/lib/browser-timezone', () => ({
  getBrowserTimeZone: () => mockBrowserTimeZone(),
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
jest.mock('@/app/admin/components/AdminDateRangeFilter', () => ({
  __esModule: true,
  default: ({
    placeholder,
    onChange,
  }: {
    placeholder: string;
    onChange: (range: { start: string; end: string }) => void;
  }) => (
    <button
      type='button'
      data-testid={`date-range-${placeholder}`}
      onClick={() => onChange({ start: '2026-07-02', end: '2026-07-02' })}
    >
      {placeholder}
    </button>
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
    disabled = false,
  }: React.PropsWithChildren<{ onClick?: () => void; disabled?: boolean }>) => (
    <button
      type='button'
      disabled={disabled}
      onClick={() => {
        if (!disabled) {
          onClick?.();
        }
      }}
    >
      {children}
    </button>
  ),
}));

jest.mock('@/hooks/useToast', () => ({
  toast: jest.fn(),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: mockTrackEvent,
  }),
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
    await screen.findByRole('button', {
      name: 'module.operationsCreditNotifications.ruleManagement.newRule',
    });
  }
};

const closeDialog = async () => {
  fireEvent.click(
    screen.getByRole('button', {
      name: 'component.header.close',
    }),
  );
  await waitFor(() => {
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
};

const openCreatorListsEditor = async () => {
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.operationsCreditNotifications.config.listDialog.manageLists',
    }),
  );
  const dialog = await screen.findByRole('dialog');
  expect(
    within(dialog).getByText(
      'module.operationsCreditNotifications.config.listDialog.manageLists',
    ),
  ).toBeInTheDocument();
  return dialog;
};

const openRuleAction = (action: 'edit' | 'delete') => {
  const actionName = `module.operationsCreditNotifications.ruleManagement.${action}`;
  if (!screen.queryByRole('button', { name: actionName })) {
    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.more',
      }),
    );
  }
  fireEvent.click(
    screen.getByRole('button', {
      name: actionName,
    }),
  );
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
    mockBrowserTimeZone.mockReturnValue('America/Los_Angeles');
    mockReplace.mockReset();
    mockPush.mockReset();
    mockTrackEvent.mockReset();
    mockGetConfig.mockReset();
    mockGetDetail.mockReset();
    mockGetTemplates.mockReset();
    mockGetRecords.mockReset();
    mockGetOverview.mockReset();
    mockDryRun.mockReset();
    mockRequeue.mockReset();
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
      created_at: '2026-05-21T00:00:00Z',
      updated_at: '2026-05-21T00:00:00Z',
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
          last_synced_at: '2026-05-22T00:00:00Z',
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
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
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

  it('shows notification records by default and switches to policy config tab', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Creator One')).toBeInTheDocument();
    });
    expect(screen.getByText('2026-05-20 17:00:00')).toBeInTheDocument();
    expect(screen.queryByText('2026-05-21T00:00:00Z')).not.toBeInTheDocument();
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
    expect(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.ruleManagement.newRule',
      }),
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

  it('shows the complete Alibaba Cloud template library in the templates tab', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    const templatesTab = screen.getByRole('tab', {
      name: 'module.operationsCreditNotifications.tabs.templates',
    });
    fireEvent.pointerDown(templatesTab, { button: 0, ctrlKey: false });
    fireEvent.mouseDown(templatesTab, { button: 0, ctrlKey: false });
    fireEvent.click(templatesTab);

    expect(await screen.findByText('Grant')).toBeInTheDocument();
    expect(screen.getByText('TPL-GRANT')).toBeInTheDocument();
    expect(screen.getByText('Credits ${credits}')).toBeInTheDocument();
    expect(mockGetTemplates).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_notification_template_library_viewed',
      { channel: 'sms', provider: 'aliyun' },
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCreditNotifications.templateManagement.searchPlaceholder',
      ),
      { target: { value: 'does-not-exist' } },
    );
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.templateManagement.empty',
      ),
    ).toBeInTheDocument();
    fireEvent.blur(
      screen.getByPlaceholderText(
        'module.operationsCreditNotifications.templateManagement.searchPlaceholder',
      ),
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_notification_template_filter_applied',
      { channel: 'sms', provider: 'aliyun', filter: 'keyword' },
    );
  });

  it('shows managed rule names as template bindings', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      rules: [
        {
          rule_bid: 'rule-grant',
          name: 'Grant follow-up',
          trigger_event: 'credit_granted',
          channel: 'sms',
          template_code: 'TPL-GRANT',
          enabled: true,
          conditions: {},
        },
      ],
    });
    render(<AdminOperationCreditNotificationsPage />);

    const templatesTab = screen.getByRole('tab', {
      name: 'module.operationsCreditNotifications.tabs.templates',
    });
    fireEvent.pointerDown(templatesTab, { button: 0, ctrlKey: false });
    fireEvent.mouseDown(templatesTab, { button: 0, ctrlKey: false });
    fireEvent.click(templatesTab);

    expect(await screen.findByText('Grant follow-up')).toBeInTheDocument();
  });

  it('does not mark templates unbound when the binding config fails to load', async () => {
    mockGetConfig.mockRejectedValueOnce(new Error('config unavailable'));
    render(<AdminOperationCreditNotificationsPage />);

    const templatesTab = screen.getByRole('tab', {
      name: 'module.operationsCreditNotifications.tabs.templates',
    });
    fireEvent.pointerDown(templatesTab, { button: 0, ctrlKey: false });
    fireEvent.mouseDown(templatesTab, { button: 0, ctrlKey: false });
    fireEvent.click(templatesTab);

    expect(await screen.findByText('Grant')).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.templateManagement.bindingsUnavailable',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        'module.operationsCreditNotifications.templateManagement.unbound',
      ),
    ).not.toBeInTheDocument();
  });

  it('shows email template positioning without SMS templates on email sites', async () => {
    mockLoginMethodsEnabled = ['email'];
    mockDefaultLoginMethod = 'email';
    render(<AdminOperationCreditNotificationsPage />);

    const templatesTab = screen.getByRole('tab', {
      name: 'module.operationsCreditNotifications.tabs.templates',
    });
    fireEvent.pointerDown(templatesTab, { button: 0, ctrlKey: false });
    fireEvent.mouseDown(templatesTab, { button: 0, ctrlKey: false });
    fireEvent.click(templatesTab);

    expect(
      await screen.findByText(
        'module.operationsCreditNotifications.templateManagement.emailTitle',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('TPL-GRANT')).not.toBeInTheDocument();
  });

  it('disables manual template sync while tracking its terminal result', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    const templatesTab = screen.getByRole('tab', {
      name: 'module.operationsCreditNotifications.tabs.templates',
    });
    fireEvent.pointerDown(templatesTab, { button: 0, ctrlKey: false });
    fireEvent.mouseDown(templatesTab, { button: 0, ctrlKey: false });
    fireEvent.click(templatesTab);
    await screen.findByText('Grant');

    const refreshRequest = createDeferred<{
      items: unknown[];
      source: 'provider';
      provider_available: true;
      error_code: string;
      error_message: string;
    }>();
    mockGetTemplates.mockReturnValueOnce(refreshRequest.promise);

    const refreshButton = screen.getByRole('button', {
      name: 'module.operationsCreditNotifications.templateManagement.refresh',
    });
    fireEvent.click(refreshButton);

    expect(refreshButton).toBeDisabled();
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_notification_template_sync_attempt',
      { channel: 'sms', provider: 'aliyun' },
    );

    refreshRequest.resolve({
      items: [],
      source: 'provider',
      provider_available: true,
      error_code: '',
      error_message: '',
    });

    await waitFor(() => {
      expect(refreshButton).not.toBeDisabled();
    });
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_notification_template_sync_result',
      {
        channel: 'sms',
        provider: 'aliyun',
        outcome: 'success',
        source: 'provider',
      },
    );
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
    expect(screen.getAllByText('2026-05-20 17:00:00').length).toBeGreaterThan(
      0,
    );
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
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
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
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
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

    expect(await screen.findByText('config unavailable')).toBeInTheDocument();
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
        'module.operationsCreditNotifications.filters.creatorPlaceholderPhone',
      ),
      { target: { value: '13800138000' } },
    );
    fireEvent.click(
      screen.getByTestId(
        'date-range-module.operationsCreditNotifications.filters.timeRangePlaceholder',
      ),
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
        start_time: formatAdminDateRangeStartUtc('2026-07-02'),
        end_time: formatAdminDateRangeEndUtc('2026-07-02'),
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

  it('uses email teacher search placeholder when email login is enabled', async () => {
    mockLoginMethodsEnabled = ['email'];
    mockDefaultLoginMethod = 'email';
    render(<AdminOperationCreditNotificationsPage />);

    await waitFor(() => {
      expect(mockGetRecords).toHaveBeenCalledTimes(1);
    });

    expect(
      screen.getByPlaceholderText(
        'module.operationsCreditNotifications.filters.creatorPlaceholderEmail',
      ),
    ).toBeInTheDocument();
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

  it('renders managed rules and opens the rule editor', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      rules: [
        {
          rule_bid: 'rule-grant',
          name: 'Grant follow-up',
          trigger_event: 'credit_granted',
          channel: 'sms',
          template_code: 'TPL-GRANT',
          enabled: true,
          conditions: {},
        },
      ],
    });
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    expect(screen.getByText('Grant follow-up')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('switch', { name: 'Grant follow-up' }));
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_notification_rule_action',
      {
        action: 'toggled',
        channel: 'sms',
        trigger_event: 'credit_granted',
      },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.ruleManagement.newRule',
      }),
    );
    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByLabelText(
        'module.operationsCreditNotifications.ruleManagement.fields.name',
      ),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole('switch', {
        name: 'module.operationsCreditNotifications.ruleManagement.fields.enabled',
      }),
    ).not.toBeChecked();
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'module.operationsCreditNotifications.ruleManagement.cancel',
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
          rules: [
            expect.objectContaining({
              rule_bid: 'rule-grant',
              enabled: false,
            }),
          ],
        }),
      );
    });
  });

  it('only offers approved and synced Aliyun SMS templates when editing a rule', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      rules: [
        {
          rule_bid: 'rule-grant',
          name: 'Grant follow-up',
          trigger_event: 'credit_granted',
          channel: 'sms',
          template_code: 'TPL-GRANT',
          enabled: false,
          conditions: {},
        },
      ],
    });
    mockGetTemplates.mockResolvedValueOnce({
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
          last_synced_at: '2026-05-22T00:00:00Z',
          source: 'provider',
        },
        {
          channel: 'sms',
          provider: 'aliyun',
          template_code: 'TPL-FAILED',
          template_name: 'Failed sync',
          template_content: 'Credits ${credits}',
          template_status: 'AUDIT_STATE_PASS',
          template_type: '0',
          sync_status: 'failed_provider',
          error_code: 'provider_exception',
          error_message: 'provider_exception',
          last_synced_at: '2026-05-22T00:00:00Z',
          source: 'local',
        },
        {
          channel: 'sms',
          provider: 'aliyun',
          template_code: 'TPL-PENDING',
          template_name: 'Pending',
          template_content: 'Credits ${credits}',
          template_status: 'AUDIT_STATE_INIT',
          template_type: '0',
          sync_status: 'synced',
          error_code: '',
          error_message: '',
          last_synced_at: '2026-05-22T00:00:00Z',
          source: 'provider',
        },
      ],
      source: 'provider',
      provider_available: true,
      error_code: '',
      error_message: '',
    });
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();
    openRuleAction('edit');
    const dialog = await screen.findByRole('dialog');
    const templateSelect = within(dialog).getAllByRole('combobox')[1];
    fireEvent.click(templateSelect);

    expect(
      await screen.findByRole('option', { name: 'Grant' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('option', { name: 'Pending' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('option', { name: 'Failed sync' }),
    ).not.toBeInTheDocument();
  });

  it('preserves legacy type settings as rules when the API has no rules field', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: true,
      types: {
        credit_expiring: {
          enabled: true,
          template_code: 'TPL-EXPIRING',
          windows: ['7d', '1d'],
          merge_same_creator: true,
        },
        credit_granted: {
          enabled: true,
          template_code: 'TPL-GRANT',
        },
        low_balance: {
          enabled: false,
          template_code: 'TPL-LOW',
          thresholds: [{ kind: 'fixed', value: '100' }],
        },
      },
    });
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    expect(screen.getAllByText('credit_expiring')).toHaveLength(2);
    expect(screen.getAllByText('credit_granted')).toHaveLength(2);
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.actions.applyConfig',
      }),
    );
    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          rules: expect.arrayContaining([
            expect.objectContaining({
              rule_bid: 'legacy-credit_expiring',
              legacy: true,
              conditions: expect.objectContaining({ windows: ['7d', '1d'] }),
            }),
            expect.objectContaining({
              rule_bid: 'legacy-credit_granted',
              template_code: 'TPL-GRANT',
              legacy: true,
            }),
            expect.objectContaining({
              rule_bid: 'legacy-low_balance',
              legacy: true,
              conditions: {
                thresholds: [{ kind: 'fixed', value: '100' }],
              },
            }),
          ]),
        }),
      );
    });
  });

  it('keeps fixed thresholds when editing an estimated-days rule condition', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      rules: [
        {
          rule_bid: 'rule-low-balance',
          name: 'Balance follow-up',
          trigger_event: 'low_balance',
          channel: 'sms',
          template_code: 'TPL-GRANT',
          enabled: true,
          conditions: {
            thresholds: [
              { kind: 'fixed', value: '100' },
              {
                kind: 'estimated_days',
                days: 7,
                lookback_days: 14,
                min_consumed_days: 3,
              },
            ],
          },
        },
      ],
    });
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    openRuleAction('edit');
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(
      within(dialog).getByLabelText(
        'module.operationsCreditNotifications.config.fields.estimatedDays',
      ),
      { target: { value: '9' } },
    );
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'module.operationsCreditNotifications.ruleManagement.saveRule',
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
          rules: [
            expect.objectContaining({
              conditions: {
                thresholds: expect.arrayContaining([
                  { kind: 'fixed', value: '100' },
                  expect.objectContaining({
                    kind: 'estimated_days',
                    days: 9,
                    lookback_days: 14,
                    min_consumed_days: 3,
                  }),
                ]),
              },
            }),
          ],
        }),
      );
    });
  });

  it('allows a disabled legacy expiring rule with empty windows to be saved', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      rules: [
        {
          rule_bid: 'legacy-credit_expiring',
          name: 'credit_expiring',
          trigger_event: 'credit_expiring',
          channel: 'sms',
          template_code: '',
          enabled: false,
          conditions: { windows: [] },
          legacy: true,
        },
      ],
    });
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();
    openRuleAction('edit');
    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByRole('button', {
        name: 'module.operationsCreditNotifications.ruleManagement.saveRule',
      }),
    ).toBeEnabled();
  });

  it('keeps an in-progress comma-separated expiry window list visible while editing', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      rules: [
        {
          rule_bid: 'rule-expiring',
          name: 'Expiry follow-up',
          trigger_event: 'credit_expiring',
          channel: 'sms',
          template_code: 'TPL-GRANT',
          enabled: true,
          conditions: { windows: ['7d'] },
        },
      ],
    });
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();
    openRuleAction('edit');
    const dialog = await screen.findByRole('dialog');
    const windowsInput = within(dialog).getByLabelText(
      'module.operationsCreditNotifications.ruleManagement.fields.windows',
    );
    fireEvent.change(windowsInput, { target: { value: '7d,' } });
    expect(windowsInput).toHaveValue('7d,');
    fireEvent.change(windowsInput, { target: { value: '7d,3d' } });
    fireEvent.blur(windowsInput);
    expect(windowsInput).toHaveValue('7d, 3d');
  });

  it('keeps an in-progress comma-separated fixed threshold list visible while editing', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      rules: [
        {
          rule_bid: 'rule-low-balance',
          name: 'Balance follow-up',
          trigger_event: 'low_balance',
          channel: 'sms',
          template_code: 'TPL-GRANT',
          enabled: true,
          conditions: {
            thresholds: [{ kind: 'fixed', value: '100' }],
          },
        },
      ],
    });
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();
    openRuleAction('edit');
    const dialog = await screen.findByRole('dialog');
    const thresholdsInput = within(dialog).getByLabelText(
      'module.operationsCreditNotifications.ruleManagement.fields.thresholds',
    );
    fireEvent.change(thresholdsInput, { target: { value: '100,' } });
    expect(thresholdsInput).toHaveValue('100,');
    fireEvent.change(thresholdsInput, { target: { value: '100,50' } });
    fireEvent.blur(thresholdsInput);
    expect(thresholdsInput).toHaveValue('100, 50');
  });

  it('clears a rule template when its trigger event changes', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      rules: [
        {
          rule_bid: 'rule-grant',
          name: 'Grant follow-up',
          trigger_event: 'credit_granted',
          channel: 'sms',
          template_code: 'TPL-GRANT',
          enabled: true,
          conditions: {},
        },
      ],
    });
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();
    openRuleAction('edit');
    const dialog = await screen.findByRole('dialog');
    const [triggerSelect] = within(dialog).getAllByRole('combobox');
    fireEvent.click(triggerSelect);
    fireEvent.click(await screen.findByRole('option', { name: 'low_balance' }));
    fireEvent.click(
      within(dialog).getByRole('switch', {
        name: 'module.operationsCreditNotifications.ruleManagement.fields.enabled',
      }),
    );
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'module.operationsCreditNotifications.ruleManagement.saveRule',
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
          rules: [
            expect.objectContaining({
              trigger_event: 'low_balance',
              template_code: '',
              enabled: false,
            }),
          ],
        }),
      );
    });
  });

  it('does not allow a synthesized legacy rule to be deleted', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      types: {
        credit_expiring: {
          enabled: false,
          template_code: '',
          windows: ['7d'],
          merge_same_creator: false,
        },
        credit_granted: { enabled: false, template_code: '' },
        low_balance: {
          enabled: false,
          template_code: '',
          thresholds: [],
        },
      },
    });
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();
    fireEvent.click(
      screen.getAllByRole('button', { name: 'common.core.more' })[0],
    );
    expect(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.ruleManagement.delete',
      }),
    ).toBeDisabled();
  });

  it('does not allow an incomplete disabled rule to be enabled inline', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      rules: [
        {
          rule_bid: 'rule-incomplete',
          name: 'Incomplete rule',
          trigger_event: 'credit_granted',
          channel: 'sms',
          template_code: '',
          enabled: false,
          conditions: {},
        },
      ],
    });
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();
    expect(
      screen.getByRole('switch', { name: 'Incomplete rule' }),
    ).toBeDisabled();
  });

  it('keeps rule controls usable when analytics tracking fails', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      rules: [
        {
          rule_bid: 'rule-grant',
          name: 'Grant follow-up',
          trigger_event: 'credit_granted',
          channel: 'sms',
          template_code: 'TPL-GRANT',
          enabled: true,
          conditions: {},
        },
      ],
    });
    mockTrackEvent.mockImplementationOnce(() => {
      throw new Error('analytics unavailable');
    });
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();
    const ruleSwitch = screen.getByRole('switch', { name: 'Grant follow-up' });
    fireEvent.click(ruleSwitch);

    expect(ruleSwitch).not.toBeChecked();
  });

  it('rejects managed rules without a stable rule business id', () => {
    const policy = normalizePolicy({
      rules: [
        {
          rule_bid: ' ',
          name: 'Invalid rule',
          trigger_event: 'credit_granted',
          channel: 'sms',
          template_code: 'TPL-GRANT',
          enabled: true,
          conditions: {},
        },
      ],
    });

    expect(policy.rules).toEqual([]);
  });

  it('requires confirmation before deleting a managed rule', async () => {
    mockGetConfig.mockResolvedValueOnce({
      enabled: false,
      rules: [
        {
          rule_bid: 'rule-grant',
          name: 'Grant follow-up',
          trigger_event: 'credit_granted',
          channel: 'sms',
          template_code: 'TPL-GRANT',
          enabled: true,
          conditions: {},
        },
      ],
    });
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();
    openRuleAction('delete');

    const dialog = await screen.findByRole('alertdialog');
    expect(
      within(dialog).getByText(
        'module.operationsCreditNotifications.ruleManagement.deleteTitle',
      ),
    ).toBeInTheDocument();
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'module.operationsCreditNotifications.ruleManagement.cancel',
      }),
    );
    expect(screen.getByText('Grant follow-up')).toBeInTheDocument();

    openRuleAction('delete');
    fireEvent.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', {
        name: 'module.operationsCreditNotifications.ruleManagement.delete',
      }),
    );
    await waitFor(() => {
      expect(screen.queryByText('Grant follow-up')).not.toBeInTheDocument();
    });
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_notification_rule_action',
      {
        action: 'deleted',
        channel: 'sms',
        trigger_event: 'credit_granted',
      },
    );
  });

  it('uses email wording for the blocked creator field on email login sites', async () => {
    mockLoginMethodsEnabled = ['email'];
    mockDefaultLoginMethod = 'email';

    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    expect(
      screen.getByRole('button', {
        name: 'module.operationsCreditNotifications.ruleManagement.newRule',
      }),
    ).toBeInTheDocument();

    const listsDialog = await openCreatorListsEditor();

    expect(
      within(listsDialog).getByPlaceholderText(
        'module.operationsCreditNotifications.config.inputPlaceholders.blockedCreatorsEmail',
      ),
    ).toBeInTheDocument();
    expect(
      within(listsDialog).queryByPlaceholderText(
        'module.operationsCreditNotifications.config.inputPlaceholders.blockedCreatorsPhone',
      ),
    ).not.toBeInTheDocument();
  });

  it('extracts blocked creators from spreadsheet-style pasted contacts and rejects invalid rows', async () => {
    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    const listsDialog = await openCreatorListsEditor();
    const blockedCreatorsInput = within(listsDialog).getByLabelText(
      'module.operationsCreditNotifications.config.fields.blockedCreators',
    );
    fireEvent.change(blockedCreatorsInput, {
      target: {
        value: '15811237246\t美少女大战哥斯拉\n15911234444\t测试昵称',
      },
    });
    fireEvent.click(
      within(listsDialog).getByRole('button', {
        name: 'module.operationsCreditNotifications.config.listDialog.add',
      }),
    );

    expect(screen.getAllByText(/15811237246/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/15911234444/).length).toBeGreaterThan(0);
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
      within(listsDialog).getByRole('button', {
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

    const listsDialog = await openCreatorListsEditor();
    const blockedCreatorsInput = within(listsDialog).getByLabelText(
      'module.operationsCreditNotifications.config.fields.blockedCreators',
    );
    fireEvent.paste(blockedCreatorsInput, {
      clipboardData: {
        getData: () => 'owner@example.com\tOwner\nsecond@example.com\tSecond',
      },
    });
    fireEvent.click(
      within(listsDialog).getByRole('button', {
        name: 'module.operationsCreditNotifications.config.listDialog.add',
      }),
    );

    expect(screen.getAllByText(/owner@example.com/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/second@example.com/).length).toBeGreaterThan(0);
    await closeDialog();
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

  it('uses the shared anonymous user label and removes an item from the draft list', async () => {
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
              nickname: '   ',
            },
          ],
        },
      },
    });

    render(<AdminOperationCreditNotificationsPage />);

    await openConfigTab();

    expect(screen.getAllByText(/13800000000/).length).toBeGreaterThan(0);
    fireEvent.click(
      screen.getByText(
        'module.operationsCreditNotifications.config.listDialog.manage',
      ),
    );
    expect(
      screen.getByText(
        'module.operationsCreditNotifications.config.fields.blockedCreatorList',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Anonymous User')).toBeInTheDocument();

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

    const listsDialog = await openCreatorListsEditor();
    const blockedCreatorsInput = within(listsDialog).getByLabelText(
      'module.operationsCreditNotifications.config.fields.blockedCreators',
    );
    fireEvent.change(blockedCreatorsInput, {
      target: { value: 'creator-unsaved' },
    });
    fireEvent.click(
      within(listsDialog).getByRole('button', {
        name: 'module.operationsCreditNotifications.config.listDialog.add',
      }),
    );
    await waitFor(() => {
      expect(screen.getAllByText(/creator-unsaved/).length).toBeGreaterThan(0);
    });
    await closeDialog();

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
    const resetListsDialog = await openCreatorListsEditor();
    expect(
      within(resetListsDialog).getByLabelText(
        'module.operationsCreditNotifications.config.fields.blockedCreators',
      ),
    ).toHaveValue('');
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
});
