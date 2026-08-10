import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import api from '@/api';
import AdminOperationsConfigPage from './page';

const mockToast = jest.fn();
let mockRenderRateTable = false;
const mockT = (key: string) =>
  new Map([
    ['title', '费率管理'],
    ['actions.addConfiguration', '添加费率'],
  ]).get(key) || key;

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationConfigRates: jest.fn(),
    updateAdminOperationConfigRate: jest.fn(),
  },
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: mockT }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('../useOperatorGuard', () => ({
  __esModule: true,
  default: () => ({ isReady: true }),
}));

jest.mock('@/app/admin/components/AdminBreadcrumb', () => ({
  __esModule: true,
  default: () => <div data-testid='breadcrumb' />,
}));

jest.mock('@/app/admin/components/AdminTitle', () => ({
  __esModule: true,
  default: ({
    title,
    actions,
    tabs,
  }: {
    title: React.ReactNode;
    actions: React.ReactNode;
    tabs: React.ReactNode;
  }) => (
    <section>
      <h1>{title}</h1>
      {actions}
      {tabs}
    </section>
  ),
}));

jest.mock('@/components/admin/AdminTableShell', () => ({
  __esModule: true,
  default: ({
    pagination,
    table,
  }: {
    pagination: { pageIndex: number };
    table: (emptyRow: React.ReactNode) => React.ReactNode;
  }) => (
    <div data-testid='rate-table'>
      <span>{pagination.pageIndex}</span>
      {mockRenderRateTable ? table(null) : null}
    </div>
  ),
}));

jest.mock('@/components/ui/Tabs', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const TabsContext = ReactModule.createContext<{
    value: string;
    onValueChange: (value: string) => void;
  }>({ value: '', onValueChange: () => undefined });

  return {
    Tabs: ({
      value,
      onValueChange,
      children,
    }: React.PropsWithChildren<{
      value: string;
      onValueChange: (value: string) => void;
    }>) => (
      <TabsContext.Provider value={{ value, onValueChange }}>
        {children}
      </TabsContext.Provider>
    ),
    TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
    TabsTrigger: ({
      value,
      children,
    }: React.PropsWithChildren<{ value: string }>) => {
      const context = ReactModule.useContext(TabsContext);
      return (
        <button
          type='button'
          onClick={() => context.onValueChange(value)}
        >
          {children}
        </button>
      );
    },
    TabsContent: ({
      value,
      children,
    }: React.PropsWithChildren<{ value: string }>) => {
      const context = ReactModule.useContext(TabsContext);
      return context.value === value ? <div>{children}</div> : null;
    },
  };
});

jest.mock('./RateCreateDialog', () => ({
  __esModule: true,
  default: ({
    open,
    usageType,
    onOpenChange,
    onCreate,
  }: {
    open: boolean;
    usageType: string;
    onOpenChange: (open: boolean) => void;
    onCreate: (
      payload: Record<string, unknown>,
      identity: Record<string, unknown>,
    ) => Promise<boolean>;
  }) =>
    open ? (
      <div data-testid='create-rate-dialog'>
        <span data-testid='create-rate-usage-type'>{usageType}</span>
        <button
          type='button'
          aria-label='mock-create'
          onClick={() =>
            void (async () => {
              const created = await onCreate(
                {
                  create_only: true,
                  usage_type: 'tts',
                  provider: 'tencent',
                  model: '',
                  rate_model: '',
                  billing_metric: 'tts_output_chars',
                  unit_size: 1,
                  credits_per_unit: 1,
                  status: 'active',
                },
                {
                  usageType: 'tts',
                  provider: 'tencent',
                  model: '',
                  rateModel: '',
                },
              );
              if (created) {
                onOpenChange(false);
              }
            })()
          }
        />
      </div>
    ) : null,
}));

const mockGetRates = api.getAdminOperationConfigRates as jest.Mock;
const mockUpdateRate = api.updateAdminOperationConfigRate as jest.Mock;
const baseRateResponse = {
  baseline: {
    is_configured: true,
    unit_cost: 0.25,
    tts_chars_per_llm_token: 0.5,
  },
  llm_rates: [],
  tts_rates: [],
};

describe('AdminOperationsConfigPage create-rate wiring', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRenderRateTable = false;
    mockGetRates.mockResolvedValue(baseRateResponse);
    mockUpdateRate.mockResolvedValue({});
  });

  test('waits for the refreshed catalog before revealing the created rate', async () => {
    const initialResponse = {
      ...baseRateResponse,
      tts_rates: [
        {
          usage_type: 'tts',
          provider: 'tencent',
          model: '',
          rate_model: '',
          display_name: 'tencent/default',
          source: 'unconfigured',
        },
      ],
    };
    const refreshedResponse = {
      ...baseRateResponse,
      tts_rates: [
        ...Array.from({ length: 10 }, (_, index) => ({
          provider: `provider-${index}`,
          model: `model-${index}`,
          rate_model: `model-${index}`,
          source: 'exact',
        })),
        {
          provider: 'tencent',
          model: '',
          rate_model: '',
          source: 'exact',
        },
      ],
    };
    let resolveReload: (value: unknown) => void = () => undefined;
    const reloadPromise = new Promise<unknown>(resolve => {
      resolveReload = resolve;
    });
    mockGetRates
      .mockResolvedValueOnce(initialResponse)
      .mockReturnValueOnce(reloadPromise);
    render(<AdminOperationsConfigPage />);

    expect(
      screen.getByRole('heading', { name: '费率管理' }),
    ).toBeInTheDocument();
    await waitFor(() => expect(mockGetRates).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: 'tabs.tts' }));
    fireEvent.click(screen.getByRole('button', { name: '添加费率' }));

    expect(screen.getByTestId('create-rate-usage-type')).toHaveTextContent(
      'tts',
    );
    fireEvent.click(screen.getByRole('button', { name: 'mock-create' }));

    await waitFor(() =>
      expect(mockUpdateRate).toHaveBeenCalledWith({
        create_only: true,
        usage_type: 'tts',
        provider: 'tencent',
        model: '',
        rate_model: '',
        billing_metric: 'tts_output_chars',
        unit_size: 1,
        credits_per_unit: 1,
        status: 'active',
      }),
    );
    await waitFor(() => expect(mockGetRates).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId('rate-table')).toHaveTextContent('1');
    expect(mockToast).not.toHaveBeenCalledWith({ title: 'create.success' });

    await act(async () => {
      resolveReload(refreshedResponse);
      await reloadPromise;
    });
    await waitFor(() =>
      expect(screen.getByTestId('rate-table')).toHaveTextContent('2'),
    );
    expect(mockToast).toHaveBeenCalledWith({ title: 'create.success' });

    fireEvent.click(screen.getByRole('button', { name: 'tabs.llm' }));
    fireEvent.click(screen.getByRole('button', { name: 'tabs.tts' }));
    expect(screen.getByTestId('rate-table')).toHaveTextContent('1');
  });

  test('closes after a durable create and retries only the failed refresh', async () => {
    const refreshedResponse = {
      ...baseRateResponse,
      tts_rates: [
        ...Array.from({ length: 10 }, (_, index) => ({
          provider: `provider-${index}`,
          model: `model-${index}`,
          rate_model: `model-${index}`,
          source: 'exact',
        })),
        {
          provider: 'tencent',
          model: '',
          rate_model: '',
          source: 'exact',
        },
      ],
    };
    let resolveRetryRefresh: (value: unknown) => void = () => undefined;
    const retryRefreshPromise = new Promise<unknown>(resolve => {
      resolveRetryRefresh = resolve;
    });
    mockGetRates
      .mockResolvedValueOnce(baseRateResponse)
      .mockRejectedValueOnce(new Error('refresh failed'))
      .mockReturnValueOnce(retryRefreshPromise);
    render(<AdminOperationsConfigPage />);

    await waitFor(() => expect(mockGetRates).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: 'tabs.tts' }));
    fireEvent.click(screen.getByRole('button', { name: '添加费率' }));
    fireEvent.click(screen.getByRole('button', { name: 'mock-create' }));

    await waitFor(() => expect(mockUpdateRate).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockGetRates).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(
        screen.queryByTestId('create-rate-dialog'),
      ).not.toBeInTheDocument(),
    );
    expect(mockUpdateRate).toHaveBeenCalledTimes(1);
    expect(mockToast).not.toHaveBeenCalledWith({ title: 'create.success' });
    expect(mockToast).not.toHaveBeenCalledWith({
      title: 'refresh failed',
      variant: 'destructive',
    });
    const addRateButton = screen.getByRole('button', { name: '添加费率' });
    expect(addRateButton).toBeDisabled();
    fireEvent.click(addRateButton);
    expect(screen.queryByTestId('create-rate-dialog')).not.toBeInTheDocument();
    expect(mockUpdateRate).toHaveBeenCalledTimes(1);
    const partialSuccessAlert = screen.getByRole('alert');
    expect(partialSuccessAlert).toHaveTextContent('create.partialSuccessTitle');
    expect(partialSuccessAlert).toHaveTextContent(
      'create.partialSuccessDescription',
    );
    const inlineRetryButton = within(partialSuccessAlert).getByRole('button', {
      name: 'create.retryRefresh',
    });
    expect(inlineRetryButton).toBeEnabled();

    const partialSuccessToast = mockToast.mock.calls.find(
      ([options]) => options.title === 'create.partialSuccessTitle',
    )?.[0];
    expect(partialSuccessToast).toEqual(
      expect.objectContaining({
        title: 'create.partialSuccessTitle',
        description: 'create.partialSuccessDescription',
        variant: 'destructive',
        duration: 0,
      }),
    );
    const retryAction = partialSuccessToast.action as React.ReactElement<{
      altText: string;
      children: React.ReactNode;
      onClick: () => void;
    }>;
    expect(retryAction.props.altText).toBe('create.retryRefreshAltText');
    expect(retryAction.props.children).toBe('create.retryRefresh');

    fireEvent.click(inlineRetryButton);

    await waitFor(() => expect(mockGetRates).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(inlineRetryButton).toBeDisabled());
    expect(addRateButton).toBeDisabled();
    fireEvent.click(addRateButton);
    expect(screen.queryByTestId('create-rate-dialog')).not.toBeInTheDocument();
    expect(mockUpdateRate).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveRetryRefresh(refreshedResponse);
      await retryRefreshPromise;
    });

    await waitFor(() =>
      expect(screen.getByTestId('rate-table')).toHaveTextContent('2'),
    );
    await waitFor(() => expect(addRateButton).toBeEnabled());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(mockUpdateRate).toHaveBeenCalledTimes(1);
    expect(mockToast).toHaveBeenCalledWith({ title: 'create.success' });
  });

  test('clears a pending create after an edit refresh succeeds', async () => {
    mockRenderRateTable = true;
    const initialResponse = {
      ...baseRateResponse,
      llm_rates: [
        {
          usage_type: 'llm',
          provider: 'qwen',
          model: 'qwen/deepseek-v4-flash',
          rate_model: 'deepseek-v4-flash',
          display_name: 'DeepSeek V4 Flash',
          billing_metric: 'llm_output_tokens',
          unit_size: 1,
          credits_per_unit: 0.25,
          multiplier: 1,
          source: 'exact',
          updated_at: null,
        },
      ],
    };
    const refreshedResponse = {
      ...initialResponse,
      tts_rates: [
        {
          usage_type: 'tts',
          provider: 'tencent',
          model: '',
          rate_model: '',
          source: 'exact',
        },
      ],
    };
    let resolveEditRefresh: (value: unknown) => void = () => undefined;
    const editRefreshPromise = new Promise<unknown>(resolve => {
      resolveEditRefresh = resolve;
    });
    mockGetRates
      .mockResolvedValueOnce(initialResponse)
      .mockRejectedValueOnce(new Error('create refresh failed'))
      .mockReturnValueOnce(editRefreshPromise);
    render(<AdminOperationsConfigPage />);

    await waitFor(() => expect(mockGetRates).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: '添加费率' }));
    fireEvent.click(screen.getByRole('button', { name: 'mock-create' }));

    await waitFor(() => expect(mockUpdateRate).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockGetRates).toHaveBeenCalledTimes(2));
    const pendingAlert = await screen.findByRole('alert');
    const addRateButton = screen.getByRole('button', { name: '添加费率' });
    expect(addRateButton).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'actions.edit' }));
    fireEvent.click(screen.getByRole('button', { name: 'actions.save' }));
    const confirmDialog = await screen.findByRole('alertdialog');
    fireEvent.click(
      within(confirmDialog).getByRole('button', { name: 'actions.save' }),
    );

    await waitFor(() => expect(mockUpdateRate).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mockGetRates).toHaveBeenCalledTimes(3));
    expect(screen.getByRole('alert')).toBe(pendingAlert);
    expect(
      within(pendingAlert).getByRole('button', {
        name: 'create.retryRefresh',
      }),
    ).toBeDisabled();
    expect(addRateButton).toBeDisabled();
    expect(
      mockUpdateRate.mock.calls.filter(([payload]) => payload.create_only),
    ).toHaveLength(1);

    await act(async () => {
      resolveEditRefresh(refreshedResponse);
      await editRefreshPromise;
    });

    await waitFor(() =>
      expect(screen.queryByRole('alert')).not.toBeInTheDocument(),
    );
    await waitFor(() => expect(addRateButton).toBeEnabled());
    expect(mockGetRates).toHaveBeenCalledTimes(3);
    expect(mockUpdateRate).toHaveBeenCalledTimes(2);
    expect(
      mockUpdateRate.mock.calls.filter(([payload]) => payload.create_only),
    ).toHaveLength(1);
    expect(mockToast).toHaveBeenCalledWith({ title: 'saveSuccess' });
    expect(mockToast).not.toHaveBeenCalledWith({ title: 'create.success' });
  });

  test('keeps the create dialog open and does not reload when create rejects', async () => {
    mockUpdateRate.mockRejectedValueOnce(new Error('rate create rejected'));
    render(<AdminOperationsConfigPage />);

    await waitFor(() => expect(mockGetRates).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: 'tabs.tts' }));
    fireEvent.click(screen.getByRole('button', { name: '添加费率' }));
    fireEvent.click(screen.getByRole('button', { name: 'mock-create' }));

    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith({
        title: 'rate create rejected',
        variant: 'destructive',
      }),
    );
    expect(screen.getByTestId('create-rate-dialog')).toBeInTheDocument();
    expect(mockGetRates).toHaveBeenCalledTimes(1);
  });

  test('disables adding a rate while an inline edit is active', async () => {
    mockRenderRateTable = true;
    mockGetRates.mockResolvedValueOnce({
      ...baseRateResponse,
      llm_rates: [
        {
          usage_type: 'llm',
          provider: 'qwen',
          model: 'qwen/deepseek-v4-flash',
          rate_model: 'deepseek-v4-flash',
          display_name: 'DeepSeek V4 Flash',
          billing_metric: 'llm_output_tokens',
          unit_size: 1,
          credits_per_unit: 0.25,
          multiplier: 1,
          source: 'exact',
          updated_at: null,
        },
      ],
    });
    render(<AdminOperationsConfigPage />);

    await waitFor(() => expect(mockGetRates).toHaveBeenCalledTimes(1));
    const addRateButton = screen.getByRole('button', { name: '添加费率' });
    expect(addRateButton).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: 'actions.edit' }));
    expect(addRateButton).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'common.core:cancel' }));
    expect(addRateButton).toBeEnabled();
  });
});
