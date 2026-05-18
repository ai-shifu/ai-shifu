import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import api from '@/api';
import UserCreditGrantDialog from './UserCreditGrantDialog';

const mockToast = jest.fn();
const mockGetAdminOperationUserGrantBootstrap =
  api.getAdminOperationUserGrantBootstrap as jest.Mock;
const mockGrantAdminOperationUserCredits =
  api.grantAdminOperationUserCredits as jest.Mock;
const mockGrantAdminOperationUserPackage =
  api.grantAdminOperationUserPackage as jest.Mock;
const translationCache = new Map<string, { t: (key: string) => string }>();
let mockLanguage = 'en-US';
const baseTranslation = (namespace?: string | string[]) => {
  const ns = Array.isArray(namespace) ? namespace[0] : namespace;
  const cacheKey = ns || 'translation';
  if (!translationCache.has(cacheKey)) {
    translationCache.set(cacheKey, {
      t: (key: string) => (ns && ns !== 'translation' ? `${ns}.${key}` : key),
    });
  }
  return translationCache.get(cacheKey)!;
};

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationUserGrantBootstrap: jest.fn(),
    grantAdminOperationUserCredits: jest.fn(),
    grantAdminOperationUserPackage: jest.fn(),
  },
}));

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => ({
    ...baseTranslation(namespace),
    i18n: {
      get language() {
        return mockLanguage;
      },
    },
  }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({
    toast: mockToast,
  }),
}));

jest.mock('uuid', () => ({
  v4: () => 'test-request-id',
}));

jest.mock('@/components/ui/Dialog', () => ({
  __esModule: true,
  Dialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogFooter: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
}));

jest.mock('@/components/ui/AlertDialog', () => ({
  __esModule: true,
  AlertDialog: ({
    open,
    children,
  }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div>{children}</div> : null,
  AlertDialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogCancel: ({
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
  AlertDialogAction: ({
    children,
    onClick,
  }: React.PropsWithChildren<{
    onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void;
  }>) => (
    <button
      type='button'
      onClick={onClick}
    >
      {children}
    </button>
  ),
}));

jest.mock('@/components/ui/Select', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const SelectContext = ReactModule.createContext<{
    value: string;
    onValueChange: (value: string) => void;
  }>({
    value: '',
    onValueChange: () => undefined,
  });

  return {
    __esModule: true,
    Select: ({
      value,
      onValueChange,
      children,
    }: React.PropsWithChildren<{
      value: string;
      onValueChange: (value: string) => void;
    }>) => (
      <SelectContext.Provider value={{ value, onValueChange }}>
        <div>{children}</div>
      </SelectContext.Provider>
    ),
    SelectTrigger: ({ children }: React.PropsWithChildren) => (
      <div>{children}</div>
    ),
    SelectValue: ({ placeholder }: { placeholder?: string }) => (
      <span>{placeholder}</span>
    ),
    SelectContent: ({ children }: React.PropsWithChildren) => (
      <div>{children}</div>
    ),
    SelectItem: ({
      value,
      disabled,
      children,
    }: React.PropsWithChildren<{ value: string; disabled?: boolean }>) => {
      const context = ReactModule.useContext(SelectContext);
      return (
        <button
          type='button'
          disabled={disabled}
          onClick={() => {
            if (!disabled) {
              context.onValueChange(value);
            }
          }}
        >
          {children}
        </button>
      );
    },
  };
});

jest.mock('@/components/ui/RadioGroup', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const RadioGroupContext = ReactModule.createContext<{
    value: string;
    onValueChange: (value: string) => void;
  }>({
    value: '',
    onValueChange: () => undefined,
  });

  return {
    __esModule: true,
    RadioGroup: ({
      value,
      onValueChange,
      children,
    }: React.PropsWithChildren<{
      value: string;
      onValueChange: (value: string) => void;
    }>) => (
      <RadioGroupContext.Provider value={{ value, onValueChange }}>
        <div>{children}</div>
      </RadioGroupContext.Provider>
    ),
    RadioGroupItem: ({ value, id }: { value: string; id?: string }) => {
      const context = ReactModule.useContext(RadioGroupContext);
      return (
        <button
          id={id}
          type='button'
          aria-pressed={context.value === value}
          onClick={() => context.onValueChange(value)}
        />
      );
    },
  };
});

const baseUser = {
  user_bid: 'user-1',
  mobile: '13812345678',
  email: 'user-1@example.com',
  nickname: 'Nick',
  user_status: 'paid',
  user_role: 'creator',
  user_roles: ['creator'],
  login_methods: ['email'],
  registration_source: 'email',
  language: 'zh-CN',
  learning_courses: [],
  learning_course_count: 0,
  created_courses: [],
  created_course_count: 0,
  total_paid_amount: '0',
  available_credits: '12',
  subscription_credits: '12',
  topup_credits: '0',
  credits_expire_at: '2026-05-01T00:00:00Z',
  has_active_subscription: true,
  last_login_at: '',
  last_learning_at: '',
  created_at: '2026-04-14T10:00:00Z',
  updated_at: '2026-04-14T11:00:00Z',
};

describe('UserCreditGrantDialog', () => {
  beforeEach(() => {
    mockToast.mockReset();
    mockGetAdminOperationUserGrantBootstrap.mockReset();
    mockGrantAdminOperationUserCredits.mockReset();
    mockGrantAdminOperationUserPackage.mockReset();
    mockLanguage = 'en-US';
    mockGetAdminOperationUserGrantBootstrap.mockImplementation(
      () => new Promise(() => undefined),
    );
    mockGrantAdminOperationUserCredits.mockResolvedValue({
      user_bid: 'user-1',
      amount: '10',
      grant_source: 'reward',
      validity_preset: '1d',
      expires_at: '2026-04-22T00:00:00Z',
      wallet_bucket_bid: 'bucket-1',
      ledger_bid: 'ledger-1',
      summary: {
        available_credits: '22',
        subscription_credits: '22',
        topup_credits: '0',
        credits_expire_at: '2026-04-22T00:00:00Z',
        has_active_subscription: true,
      },
    });
    mockGrantAdminOperationUserPackage.mockResolvedValue({
      user_bid: 'user-1',
      product_bid: 'bill-product-plan-monthly',
      subscription_bid: 'subscription-1',
      bill_order_bid: 'bill-order-1',
      current_period_start_at: '2026-04-21T00:00:00Z',
      current_period_end_at: '2026-05-20T23:59:59Z',
      notification_status: 'template_pending',
      summary: {
        available_credits: '17',
        subscription_credits: '17',
        topup_credits: '0',
        credits_expire_at: '2026-05-20T23:59:59Z',
        has_active_subscription: true,
      },
    });
  });

  test('validates required fields before opening confirm dialog', async () => {
    render(
      <UserCreditGrantDialog
        open
        user={baseUser}
        onOpenChange={jest.fn()}
        onGranted={jest.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.confirmButton',
      }),
    );

    expect(
      await screen.findByText(
        'module.operationsUser.grantDialog.validation.amountRequired',
      ),
    ).toBeInTheDocument();
    expect(mockGrantAdminOperationUserCredits).not.toHaveBeenCalled();
  });

  test('formats current available credits without grouping in Chinese locale', () => {
    mockLanguage = 'zh-CN';

    render(
      <UserCreditGrantDialog
        open
        user={{ ...baseUser, available_credits: '10000' }}
        onOpenChange={jest.fn()}
        onGranted={jest.fn()}
      />,
    );

    expect(screen.getByText('10000')).toBeInTheDocument();
    expect(screen.queryByText('10,000')).not.toBeInTheDocument();
  });

  test('submits a confirmed grant and reports success', async () => {
    const handleGranted = jest.fn();
    const handleOpenChange = jest.fn();

    render(
      <UserCreditGrantDialog
        open
        user={baseUser}
        onOpenChange={handleOpenChange}
        onGranted={handleGranted}
      />,
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsUser.grantDialog.placeholders.amount',
      ),
      {
        target: { value: '10' },
      },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.validityOptions.oneDay',
      }),
    );
    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsUser.grantDialog.placeholders.note',
      ),
      {
        target: { value: 'ops note' },
      },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.confirmButton',
      }),
    );

    expect(
      await screen.findByText('module.operationsUser.grantDialog.confirmTitle'),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.submitButton',
      }),
    );

    await waitFor(() => {
      expect(mockGrantAdminOperationUserCredits).toHaveBeenCalledWith({
        user_bid: 'user-1',
        request_id: 'testrequestid',
        amount: '10',
        grant_source: 'reward',
        validity_preset: '1d',
        note: 'ops note',
      });
    });

    expect(handleGranted).toHaveBeenCalledWith(
      expect.objectContaining({
        ledger_bid: 'ledger-1',
      }),
    );
    expect(handleOpenChange).toHaveBeenCalledWith(false);
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.operationsUser.grantDialog.submitSuccess',
    });
  });

  test('submits a confirmed package grant and reports success', async () => {
    const handleGranted = jest.fn();
    const handleOpenChange = jest.fn();
    mockGetAdminOperationUserGrantBootstrap.mockResolvedValueOnce({
      plans: [
        {
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          product_type: 'plan',
          display_name: 'module.billing.catalog.plans.creatorMonthly.title',
          description:
            'module.billing.catalog.plans.creatorMonthly.description',
          billing_interval: 'month',
          billing_interval_count: 1,
          currency: 'CNY',
          price_amount: 990,
          credit_amount: 5,
          auto_renew_enabled: true,
          highlights: [],
        },
      ],
      current_subscription_product_display_name_i18n_key:
        'module.billing.catalog.plans.creatorMonthly.title',
      notification_status: 'template_pending',
    });

    render(
      <UserCreditGrantDialog
        open
        user={baseUser}
        onOpenChange={handleOpenChange}
        onGranted={handleGranted}
      />,
    );

    await waitFor(() => {
      expect(mockGetAdminOperationUserGrantBootstrap).toHaveBeenCalledWith({
        user_bid: 'user-1',
      });
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.modeOptions.package',
      }),
    );
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.billing.catalog.plans.creatorMonthly.title',
      }),
    );
    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsUser.grantDialog.placeholders.note',
      ),
      {
        target: { value: 'package note' },
      },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.confirmButton',
      }),
    );

    expect(
      await screen.findByText(
        'module.operationsUser.grantDialog.packageConfirmTitle',
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.submitButton',
      }),
    );

    await waitFor(() => {
      expect(mockGrantAdminOperationUserPackage).toHaveBeenCalledWith({
        user_bid: 'user-1',
        request_id: 'testrequestid',
        product_bid: 'bill-product-plan-monthly',
        note: 'package note',
      });
    });

    expect(handleGranted).toHaveBeenCalledWith(
      expect.objectContaining({
        bill_order_bid: 'bill-order-1',
      }),
    );
    expect(handleOpenChange).toHaveBeenCalledWith(false);
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.operationsUser.grantDialog.submitSuccess',
    });
  });

  test('prefetches package bootstrap on open and shows a loading placeholder without disabling the package field', async () => {
    mockGetAdminOperationUserGrantBootstrap.mockImplementation(
      () => new Promise(() => undefined),
    );

    render(
      <UserCreditGrantDialog
        open
        user={baseUser}
        onOpenChange={jest.fn()}
        onGranted={jest.fn()}
      />,
    );

    await waitFor(() => {
      expect(mockGetAdminOperationUserGrantBootstrap).toHaveBeenCalledWith({
        user_bid: 'user-1',
      });
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.modeOptions.package',
      }),
    );

    expect(
      screen.getAllByText(
        'module.operationsUser.grantDialog.placeholders.productLoading',
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByText(
        'module.operationsUser.grantDialog.packageFields.packageName',
      ),
    ).not.toBeInTheDocument();
  });

  test('does not auto-retry bootstrap after a failure until the dialog is reopened', async () => {
    mockGetAdminOperationUserGrantBootstrap.mockRejectedValueOnce(
      new Error('bootstrap failed'),
    );

    const { rerender } = render(
      <UserCreditGrantDialog
        open
        user={baseUser}
        onOpenChange={jest.fn()}
        onGranted={jest.fn()}
      />,
    );

    await waitFor(() => {
      expect(mockGetAdminOperationUserGrantBootstrap).toHaveBeenCalledTimes(1);
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.modeOptions.package',
      }),
    );
    await waitFor(() => {
      expect(
        screen.getByText(
          'module.operationsUser.grantDialog.placeholders.product',
        ),
      ).toBeInTheDocument();
    });

    await act(async () => {
      await Promise.resolve();
    });
    expect(mockGetAdminOperationUserGrantBootstrap).toHaveBeenCalledTimes(1);

    mockGetAdminOperationUserGrantBootstrap.mockResolvedValueOnce({
      plans: [],
      current_subscription_product_display_name_i18n_key: '',
      notification_status: 'template_pending',
    });

    rerender(
      <UserCreditGrantDialog
        open={false}
        user={baseUser}
        onOpenChange={jest.fn()}
        onGranted={jest.fn()}
      />,
    );
    rerender(
      <UserCreditGrantDialog
        open
        user={baseUser}
        onOpenChange={jest.fn()}
        onGranted={jest.fn()}
      />,
    );

    await waitFor(() => {
      expect(mockGetAdminOperationUserGrantBootstrap).toHaveBeenCalledTimes(2);
    });
  });

  test('disables align subscription preset and falls back to one day without active subscription', async () => {
    render(
      <UserCreditGrantDialog
        open
        user={{
          ...baseUser,
          has_active_subscription: false,
          credits_expire_at: '',
        }}
        onOpenChange={jest.fn()}
        onGranted={jest.fn()}
      />,
    );

    expect(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.validityOptions.alignSubscription',
      }),
    ).toBeDisabled();

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsUser.grantDialog.placeholders.amount',
      ),
      {
        target: { value: '8' },
      },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.confirmButton',
      }),
    );

    expect(
      await screen.findByText('module.operationsUser.grantDialog.confirmTitle'),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(
        'module.operationsUser.grantDialog.validityOptions.oneDay',
      ).length,
    ).toBeGreaterThan(0);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.submitButton',
      }),
    );

    await waitFor(() => {
      expect(mockGrantAdminOperationUserCredits).toHaveBeenCalledWith(
        expect.objectContaining({
          request_id: 'testrequestid',
          validity_preset: '1d',
        }),
      );
    });
  });

  test('closes the confirm dialog and shows submit errors in the main dialog', async () => {
    mockGrantAdminOperationUserCredits.mockRejectedValueOnce(
      new Error('grant failed'),
    );

    render(
      <UserCreditGrantDialog
        open
        user={baseUser}
        onOpenChange={jest.fn()}
        onGranted={jest.fn()}
      />,
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsUser.grantDialog.placeholders.amount',
      ),
      {
        target: { value: '10' },
      },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.confirmButton',
      }),
    );

    expect(
      await screen.findByText('module.operationsUser.grantDialog.confirmTitle'),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.grantDialog.submitButton',
      }),
    );

    await waitFor(() => {
      expect(mockGrantAdminOperationUserCredits).toHaveBeenCalledWith(
        expect.objectContaining({
          request_id: 'testrequestid',
        }),
      );
    });

    await waitFor(() => {
      expect(
        screen.queryByText('module.operationsUser.grantDialog.confirmTitle'),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByText('grant failed')).toBeInTheDocument();
  });
});
