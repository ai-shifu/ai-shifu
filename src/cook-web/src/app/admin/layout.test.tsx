import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useBillingOverview } from '@/hooks/useBillingData';
import { buildAdminMenuItems } from './admin-menu';
import AdminLayout from './layout';
import { SidebarContent } from './SidebarContent';

const footerLabel = 'footer';

jest.mock('next/image', () => ({
  __esModule: true,
  default: ({ alt, src }: { alt: string; src: string }) =>
    React.createElement('img', { alt, src }),
}));

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
  }) => (
    <a
      href={href}
      {...props}
    >
      {children}
    </a>
  ),
}));

jest.mock('next/navigation', () => ({
  usePathname: () => '/admin',
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
  }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en-US',
    },
  }),
}));

jest.mock('@/c-common/hooks/useDisclosure', () => ({
  useDisclosure: () => ({
    open: false,
    onToggle: jest.fn(),
    onClose: jest.fn(),
  }),
}));

jest.mock('@/config/environment', () => ({
  environment: {
    logoWideUrl: '/logo.png',
  },
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (
    selector:
      | ((state: { logoWideUrl: string; billingEnabled: string }) => unknown)
      | undefined,
  ) =>
    selector?.({ logoWideUrl: '/logo.png', billingEnabled: 'true' }) ??
    '/logo.png',
}));

const mockUserStoreState = {
  isInitialized: true,
  isGuest: false,
  userInfo: {
    is_operator: false,
  },
};

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (selector: (state: typeof mockUserStoreState) => unknown) =>
    selector(mockUserStoreState),
}));

jest.mock('@/c-components/NavDrawer/NavFooter', () => ({
  __esModule: true,
  default: React.forwardRef(function MockNavFooter(
    {
      onClick,
    }: {
      onClick?: () => void;
    },
    ref,
  ) {
    void ref;
    return <button onClick={onClick}>{footerLabel}</button>;
  }),
}));

jest.mock('@/c-components/NavDrawer/MainMenuModal', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('@/hooks/useBillingData', () => ({
  __esModule: true,
  useBillingOverview: jest.fn(),
}));

jest.mock('@/components/billing/WelcomeTrialDialog', () => ({
  __esModule: true,
  WelcomeTrialDialog: () => null,
}));

const mockUseBillingOverview = useBillingOverview as jest.Mock;
const mockMutateBillingOverview = jest.fn();

describe('SidebarContent', () => {
  const t = (key: string) => key;
  const findOperationsCourseLink = () =>
    screen.queryByRole('link', { name: 'common.core.courseManagement' });
  const findOperationsUserLink = () =>
    screen.queryByRole('link', { name: 'common.core.userManagement' });
  const baseProps = {
    footerRef: { current: null },
    userMenuOpen: false,
    onFooterClick: jest.fn(),
    onUserMenuClose: jest.fn(),
    userMenuClassName: 'user-menu',
    logoSrc: '/logo.png',
    billingOverviewLoading: false,
    billingOverview: undefined,
  };

  beforeEach(() => {
    baseProps.onFooterClick.mockReset();
    baseProps.onUserMenuClose.mockReset();
  });

  test('auto expands the operations menu when the course submenu is active', () => {
    render(
      <SidebarContent
        {...baseProps}
        menuItems={buildAdminMenuItems({ t, isOperator: true })}
        activePath='/admin/operations'
      />,
    );

    const operationsButton = screen.getByRole('button', {
      name: 'common.core.operations',
    });
    const courseLink = findOperationsCourseLink();

    expect(operationsButton).toHaveAttribute('aria-expanded', 'true');
    expect(courseLink).toBeDefined();
    expect(courseLink).toHaveAttribute('href', '/admin/operations');
    expect(courseLink).toHaveAttribute('aria-current', 'page');
    expect(findOperationsUserLink()).toHaveAttribute(
      'href',
      '/admin/operations/users',
    );
  });

  test('toggles the operations submenu open and closed', () => {
    render(
      <SidebarContent
        {...baseProps}
        menuItems={buildAdminMenuItems({ t, isOperator: true })}
        activePath='/admin'
      />,
    );

    const operationsButton = screen.getByRole('button', {
      name: 'common.core.operations',
    });

    expect(operationsButton).toHaveAttribute('aria-expanded', 'false');
    expect(findOperationsCourseLink()).toBeNull();

    fireEvent.click(operationsButton);

    expect(operationsButton).toHaveAttribute('aria-expanded', 'true');
    expect(findOperationsCourseLink()).toHaveAttribute(
      'href',
      '/admin/operations',
    );
    expect(findOperationsUserLink()).toHaveAttribute(
      'href',
      '/admin/operations/users',
    );

    fireEvent.click(operationsButton);

    expect(operationsButton).toHaveAttribute('aria-expanded', 'false');
    expect(findOperationsCourseLink()).toBeNull();
  });

  test('hides the billing card while the user menu popup is open', () => {
    render(
      <SidebarContent
        {...baseProps}
        userMenuOpen
        billingOverview={{
          creator_bid: 'creator-1',
          wallet: {
            available_credits: 12500,
            reserved_credits: 0,
            lifetime_granted_credits: 20000,
            lifetime_consumed_credits: 7500,
          },
          subscription: null,
          billing_alerts: [],
          trial_offer: {
            enabled: true,
            status: 'ineligible',
            product_bid: 'bill-product-plan-trial',
            product_code: 'creator-plan-trial',
            display_name: 'module.billing.package.free.title',
            description: 'module.billing.package.free.description',
            currency: 'CNY',
            price_amount: 0,
            credit_amount: 100,
            valid_days: 15,
            highlights: [
              'module.billing.package.features.free.publish',
              'module.billing.package.features.free.preview',
            ],
            starts_on_first_grant: true,
            granted_at: null,
            expires_at: null,
          },
        }}
        menuItems={buildAdminMenuItems({ t, isOperator: true })}
        activePath='/admin'
      />,
    );

    expect(
      screen.queryByTestId('admin-billing-sidebar-card'),
    ).not.toBeInTheDocument();
  });

  test('does not render operations submenu items for non-operators', () => {
    render(
      <SidebarContent
        {...baseProps}
        menuItems={buildAdminMenuItems({ t, isOperator: false })}
        activePath='/admin'
      />,
    );

    expect(
      screen.queryByRole('button', { name: 'common.core.operations' }),
    ).toBeNull();
    expect(findOperationsCourseLink()).toBeNull();
    expect(findOperationsUserLink()).toBeNull();
  });
});

describe('AdminLayout', () => {
  const childText = 'content';
  const buildBillingOverview = ({
    availableCredits = 12500,
    subscription = {
      subscription_bid: 'sub-1',
      product_bid: 'plan-1',
      product_code: 'creator-plan-monthly',
      status: 'active' as const,
      billing_provider: 'stripe' as const,
      current_period_start_at: '2026-04-01T00:00:00Z',
      current_period_end_at: '2026-05-01T00:00:00Z',
      grace_period_end_at: null,
      cancel_at_period_end: false,
      next_product_bid: null,
      last_renewed_at: null,
      last_failed_at: null,
    },
  }: {
    availableCredits?: number;
    subscription?: {
      subscription_bid: string;
      product_bid: string;
      product_code: string;
      status: 'active';
      billing_provider: 'stripe';
      current_period_start_at: string | null;
      current_period_end_at: string | null;
      grace_period_end_at: string | null;
      cancel_at_period_end: boolean;
      next_product_bid: string | null;
      last_renewed_at: string | null;
      last_failed_at: string | null;
    } | null;
  }) => ({
    creator_bid: 'creator-1',
    wallet: {
      available_credits: availableCredits,
      reserved_credits: 0,
      lifetime_granted_credits: 20000,
      lifetime_consumed_credits: 7500,
    },
    subscription,
    billing_alerts: [],
    trial_offer: {
      enabled: true,
      status: 'ineligible',
      product_bid: 'bill-product-plan-trial',
      product_code: 'creator-plan-trial',
      display_name: 'module.billing.package.free.title',
      description: 'module.billing.package.free.description',
      currency: 'CNY',
      price_amount: 0,
      credit_amount: 100,
      valid_days: 15,
      highlights: [
        'module.billing.package.features.free.publish',
        'module.billing.package.features.free.preview',
      ],
      starts_on_first_grant: true,
      granted_at: null,
      expires_at: null,
      welcome_dialog_acknowledged_at: null,
    },
  });

  beforeEach(() => {
    mockUserStoreState.isInitialized = true;
    mockUserStoreState.isGuest = false;
    mockUserStoreState.userInfo = {
      is_operator: false,
    };
    mockMutateBillingOverview.mockReset();
    mockUseBillingOverview.mockReturnValue({
      data: buildBillingOverview({}),
      error: undefined,
      isLoading: false,
      mutate: mockMutateBillingOverview,
    });
  });

  test('shows sidebar loading placeholder before user state is ready', () => {
    mockUserStoreState.isInitialized = false;
    mockUserStoreState.userInfo = null as unknown as {
      is_operator: false;
    };

    render(
      <AdminLayout>
        <div>{childText}</div>
      </AdminLayout>,
    );

    expect(screen.getByLabelText('admin-sidebar-loading')).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'common.core.shifu' }),
    ).not.toBeInTheDocument();
  });

  test('keeps sidebar in loading state for guests before redirect completes', () => {
    mockUserStoreState.isInitialized = true;
    mockUserStoreState.isGuest = true;
    mockUserStoreState.userInfo = null as unknown as {
      is_operator: false;
    };

    render(
      <AdminLayout>
        <div>{childText}</div>
      </AdminLayout>,
    );

    expect(screen.getByLabelText('admin-sidebar-loading')).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'common.core.shifu' }),
    ).not.toBeInTheDocument();
  });

  test('redirects guests to login from admin routes handled only by the layout', async () => {
    mockUserStoreState.isInitialized = true;
    mockUserStoreState.isGuest = true;
    mockUserStoreState.userInfo = null as unknown as {
      is_operator: false;
    };
    Object.assign(window.location, {
      href: '',
      pathname: '/admin/billing',
      search: '?tab=details',
    });

    render(
      <AdminLayout>
        <div>{childText}</div>
      </AdminLayout>,
    );

    await waitFor(() => {
      expect(window.location.href).toContain(
        '/login?redirect=%2Fadmin%2Fbilling%3Ftab%3Ddetails',
      );
    });
  });

  test('renders sidebar once initialization completes even if user info is unavailable', () => {
    mockUserStoreState.isInitialized = true;
    mockUserStoreState.isGuest = false;
    mockUserStoreState.userInfo = null as unknown as {
      is_operator: false;
    };

    render(
      <AdminLayout>
        <div>{childText}</div>
      </AdminLayout>,
    );

    expect(
      screen.queryByLabelText('admin-sidebar-loading'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'common.core.shifu' }),
    ).toBeInTheDocument();
  });

  test('renders the billing navigation entry and membership card with credits', () => {
    render(
      <AdminLayout>
        <div data-testid='child-content' />
      </AdminLayout>,
    );

    expect(screen.getByTestId('admin-layout-content')).toHaveClass(
      'overflow-y-auto',
    );
    expect(screen.getByTestId('admin-sidebar-nav')).toHaveClass('flex-1');
    expect(
      screen.getByTestId('admin-billing-sidebar-card'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.sidebar.monthlyBalanceTitle'),
    ).toBeInTheDocument();
    expect(screen.getByText('12500')).toBeInTheDocument();
    expect(
      screen.getByRole('link', {
        name: 'module.billing.sidebar.usageCta',
      }),
    ).toHaveAttribute('href', '/admin/billing?tab=details');
    expect(screen.getByTestId('admin-billing-sidebar-card')).toHaveAttribute(
      'data-href',
      '/admin/billing?tab=packages',
    );
    expect(
      screen.queryByText('module.billing.sidebar.subscriptionStatusLabel'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.billing.sidebar.cta'),
    ).not.toBeInTheDocument();
  });

  test('hides the credits section when available credits are zero', () => {
    mockUseBillingOverview.mockReturnValue({
      data: buildBillingOverview({ availableCredits: 0, subscription: null }),
      error: undefined,
      isLoading: false,
      mutate: mockMutateBillingOverview,
    });

    render(
      <AdminLayout>
        <div data-testid='child-content' />
      </AdminLayout>,
    );

    expect(
      screen.getByText('module.billing.sidebar.nonMemberBalanceTitle'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('admin-billing-sidebar-card')).toHaveAttribute(
      'data-href',
      '/admin/billing?tab=packages',
    );
    expect(screen.queryByText(/0(?:\.0+)?/)).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', {
        name: 'module.billing.sidebar.usageCta',
      }),
    ).toHaveAttribute('href', '/admin/billing?tab=details');
  });

  test('renders yearly membership title for yearly subscription plans', () => {
    mockUseBillingOverview.mockReturnValue({
      data: buildBillingOverview({
        subscription: {
          subscription_bid: 'sub-yearly',
          product_bid: 'plan-yearly',
          product_code: 'creator-plan-yearly',
          status: 'active',
          billing_provider: 'stripe',
          current_period_start_at: '2026-01-01T00:00:00Z',
          current_period_end_at: '2027-01-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
      }),
      error: undefined,
      isLoading: false,
      mutate: mockMutateBillingOverview,
    });

    render(
      <AdminLayout>
        <div data-testid='child-content' />
      </AdminLayout>,
    );

    expect(
      screen.getByText('module.billing.sidebar.yearlyBalanceTitle'),
    ).toBeInTheDocument();
  });
});
