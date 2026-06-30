import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import api from '@/api';
import CreatorRedemptionCodesTab from './CreatorRedemptionCodesTab';

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getCreatorCourseRedemptionCodes: jest.fn(),
    getCreatorCourseRedemptionCodeDetail: jest.fn(),
    updateCreatorCourseRedemptionCodeStatus: jest.fn(),
    updateCreatorCourseRedemptionCode: jest.fn(),
    getAdminOrderShifus: jest.fn(),
    getCreatorCourseRedemptionCodeUsages: jest.fn(),
    getCreatorCourseRedemptionCodeCodes: jest.fn(),
  },
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (selector: (state: { currencySymbol: string }) => unknown) =>
    selector({ currencySymbol: '¥' }),
}));

const mockTranslate = (key: string, options?: Record<string, unknown>) =>
  options && typeof options.count !== 'undefined'
    ? `${key}:${String(options.count)}`
    : key;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mockTranslate,
  }),
  Trans: ({ i18nKey }: { i18nKey: string }) => <span>{i18nKey}</span>,
}));

jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: ({ errorMessage }: { errorMessage: string }) => (
    <div>{errorMessage}</div>
  ),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
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
      children,
    }: React.PropsWithChildren<{ value: string }>) => {
      const context = ReactModule.useContext(SelectContext);
      return (
        <button
          type='button'
          onClick={() => context.onValueChange(value)}
        >
          {children}
        </button>
      );
    },
  };
});

const CONFIRM_STATUS_LABEL = 'confirm-status';

jest.mock('@/app/admin/components/AdminRowActions', () => ({
  __esModule: true,
  default: ({
    actions,
  }: {
    actions: Array<{
      key: string;
      label: string;
      hidden?: boolean;
      onClick: () => void;
    }>;
  }) => (
    <div>
      {actions
        .filter(action => !action.hidden)
        .map(action => (
          <button
            key={action.key}
            type='button'
            onClick={action.onClick}
          >
            {action.label}
          </button>
        ))}
    </div>
  ),
}));

jest.mock(
  '@/app/admin/operations/promotions/PromotionStatusConfirmDialog',
  () => ({
    __esModule: true,
    default: ({
      changeTarget,
      onConfirm,
    }: {
      changeTarget: unknown;
      onConfirm: () => Promise<void>;
    }) =>
      changeTarget ? (
        <button
          type='button'
          onClick={() => void onConfirm()}
        >
          {CONFIRM_STATUS_LABEL}
        </button>
      ) : null,
  }),
);

const mockToast = jest.fn();

jest.mock('@/hooks/useToast', () => ({
  __esModule: true,
  showDefaultToast: (description: unknown) => mockToast({ description }),
  showErrorToast: (description: unknown) =>
    mockToast({ description, variant: 'destructive' }),
}));

const mockGetCreatorCourseRedemptionCodes =
  api.getCreatorCourseRedemptionCodes as jest.Mock;
const mockGetCreatorCourseRedemptionCodeDetail =
  api.getCreatorCourseRedemptionCodeDetail as jest.Mock;
const mockUpdateCreatorCourseRedemptionCodeStatus =
  api.updateCreatorCourseRedemptionCodeStatus as jest.Mock;
const mockGetCreatorCourseRedemptionCodeUsages =
  api.getCreatorCourseRedemptionCodeUsages as jest.Mock;
const mockGetCreatorCourseRedemptionCodeCodes =
  api.getCreatorCourseRedemptionCodeCodes as jest.Mock;
const mockGetAdminOrderShifus = api.getAdminOrderShifus as jest.Mock;

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
};

const createListResponse = (
  name: string,
  total = 1,
): Record<string, unknown> => ({
  items: [
    {
      coupon_bid: `coupon-${name}`,
      name,
      code: 'CODE-A',
      usage_type: 801,
      usage_type_key: 'module.operationsPromotion.usageType.generic',
      discount_type: 701,
      discount_type_key: 'module.operationsPromotion.discountType.fixed',
      value: '10',
      scope_type: 'single_course',
      shifu_bid: 'course-1',
      course_name: 'Course A',
      start_at: '2026-05-01 00:00:00',
      end_at: '2026-06-01 23:59:59',
      total_count: 20,
      used_count: 3,
      computed_status: 'active',
      computed_status_key: 'module.operationsPromotion.status.active',
      created_at: '2026-05-01 12:00:00',
      updated_at: '2026-05-01 12:00:00',
    },
  ],
  page: 1,
  page_count: 1,
  page_size: 20,
  total,
  summary: {},
});

describe('CreatorRedemptionCodesTab', () => {
  beforeEach(() => {
    mockToast.mockReset();
    mockGetCreatorCourseRedemptionCodes.mockReset();
    mockGetCreatorCourseRedemptionCodeDetail.mockReset();
    mockUpdateCreatorCourseRedemptionCodeStatus.mockReset();
    mockGetCreatorCourseRedemptionCodeUsages.mockReset();
    mockGetCreatorCourseRedemptionCodeCodes.mockReset();
    mockGetAdminOrderShifus.mockReset();
    mockGetCreatorCourseRedemptionCodes.mockResolvedValue({
      items: [
        {
          coupon_bid: 'coupon-1',
          name: 'Batch A',
          code: 'CODE-A',
          usage_type: 801,
          usage_type_key: 'module.operationsPromotion.usageType.generic',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '10',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Course A',
          start_at: '2026-05-01 00:00:00',
          end_at: '2026-06-01 23:59:59',
          total_count: 20,
          used_count: 3,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-05-01 12:00:00',
          updated_at: '2026-05-01 12:00:00',
        },
        {
          coupon_bid: 'coupon-2',
          name: 'Batch B',
          code: '',
          usage_type: 802,
          usage_type_key: 'module.operationsPromotion.usageType.singleUse',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '15',
          scope_type: 'single_course',
          shifu_bid: 'course-2',
          course_name: 'Course B',
          start_at: '2026-05-01 00:00:00',
          end_at: '2026-06-01 23:59:59',
          total_count: 30,
          used_count: 0,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-05-01 12:00:00',
          updated_at: '2026-05-01 12:00:00',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 2,
      summary: {},
    });
    mockGetCreatorCourseRedemptionCodeUsages.mockResolvedValue({
      items: [
        {
          coupon_usage_bid: 'usage-1',
          code: 'CODE-A',
          status: 903,
          status_key: 'module.order.couponStatus.used',
          user_bid: 'learner-1',
          user_mobile: '13812345678',
          user_email: '',
          user_nickname: 'Learner',
          shifu_bid: 'course-1',
          course_name: 'Course A',
          order_bid: 'order-1',
          order_status: 502,
          order_status_key: 'server.order.orderStatusPaid',
          payable_price: '99.00',
          discount_amount: '10.00',
          paid_price: '89.00',
          used_at: '2026-05-02 12:00:00',
          updated_at: '2026-05-02 12:00:00',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
      summary: {},
    });
    mockGetCreatorCourseRedemptionCodeCodes.mockResolvedValue({
      items: [
        {
          coupon_usage_bid: 'sub-code-1',
          code: 'SUBCODE001',
          status: 902,
          status_key: 'module.order.couponStatus.active',
          user_bid: '',
          user_mobile: '',
          user_email: '',
          user_nickname: '',
          order_bid: '',
          used_at: '',
          updated_at: '2026-05-02 12:00:00',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
      summary: {},
    });
    mockGetCreatorCourseRedemptionCodeDetail.mockResolvedValue({
      coupon: {
        coupon_bid: 'coupon-1',
        name: 'Batch A',
        code: 'CODE-A',
        usage_type: 801,
        usage_type_key: 'module.operationsPromotion.usageType.generic',
        discount_type: 701,
        discount_type_key: 'module.operationsPromotion.discountType.fixed',
        value: '10',
        scope_type: 'single_course',
        shifu_bid: 'course-1',
        course_name: 'Course A',
        start_at: '2026-05-01 00:00:00',
        end_at: '2026-06-01 23:59:59',
        total_count: 20,
        used_count: 3,
        computed_status: 'active',
        computed_status_key: 'module.operationsPromotion.status.active',
        created_at: '2026-05-01 12:00:00',
        updated_at: '2026-05-01 12:00:00',
      },
    });
    mockUpdateCreatorCourseRedemptionCodeStatus.mockResolvedValue({
      coupon_bid: 'coupon-1',
      enabled: false,
    });
    mockGetAdminOrderShifus.mockResolvedValue({
      items: [{ bid: 'course-1', name: 'Course A' }],
    });
  });

  test('loads and renders creator redemption code batches', async () => {
    render(<CreatorRedemptionCodesTab />);

    await waitFor(() => {
      expect(mockGetCreatorCourseRedemptionCodes).toHaveBeenCalledWith(
        expect.objectContaining({
          page_index: 1,
          page_size: 20,
          name: '',
          course_query: '',
        }),
      );
    });

    expect(await screen.findByText('Batch A')).toBeInTheDocument();
    expect(screen.getByText('Course A')).toBeInTheDocument();
    expect(screen.getByText('CODE-A')).toBeInTheDocument();
    expect(screen.getByText('3/20')).toBeInTheDocument();
    expect(screen.getByText('Batch B')).toBeInTheDocument();
    expect(screen.getAllByText('table.codesEntry').length).toBeGreaterThan(0);

    const actionHeader = screen.getByText('table.actions').closest('th');
    expect(actionHeader).toHaveClass('sticky');
    expect(actionHeader).toHaveClass('right-0');

    const genericRow = screen.getByText('Batch A').closest('tr');
    expect(genericRow?.querySelectorAll('td')[10]).toHaveTextContent(
      'actions.edit',
    );

    const singleUseRow = screen.getByText('Batch B').closest('tr');
    expect(singleUseRow?.querySelectorAll('td')[10]).toHaveTextContent(
      'actions.exportCodes',
    );
  });

  test('opens usage records dialog from usage progress', async () => {
    render(<CreatorRedemptionCodesTab />);

    const usageButton = await screen.findByText('3/20');
    fireEvent.click(usageButton);

    await waitFor(() => {
      expect(mockGetCreatorCourseRedemptionCodeUsages).toHaveBeenCalledWith({
        coupon_bid: 'coupon-1',
        page_index: 1,
        page_size: 20,
      });
    });
    expect(await screen.findByText('coupon.usages')).toBeInTheDocument();
    expect(screen.getAllByText('CODE-A').length).toBeGreaterThan(0);
    expect(screen.getByText('order-1')).toBeInTheDocument();
  });

  test('opens and exports single-use sub-codes', async () => {
    const createObjectURL = jest.fn(() => 'blob:creator-codes');
    const revokeObjectURL = jest.fn();
    const anchorClick = jest
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    const originalCreateObjectURL = window.URL.createObjectURL;
    const originalRevokeObjectURL = window.URL.revokeObjectURL;
    window.URL.createObjectURL = createObjectURL;
    window.URL.revokeObjectURL = revokeObjectURL;

    try {
      render(<CreatorRedemptionCodesTab />);

      await screen.findByText('Batch B');
      fireEvent.click(
        await screen.findByRole('button', {
          name: 'actions.exportCodes',
        }),
      );

      await waitFor(() => {
        expect(mockGetCreatorCourseRedemptionCodeCodes).toHaveBeenCalledWith({
          coupon_bid: 'coupon-2',
          page_index: 1,
          page_size: 100,
        });
      });
      expect(createObjectURL).toHaveBeenCalled();
      expect(anchorClick).toHaveBeenCalled();
      expect(mockToast).toHaveBeenCalledWith({
        description: 'messages.exportSuccess',
      });

      const codeEntry = screen
        .getAllByText('table.codesEntry')
        .map(element => element.closest('button'))
        .find(Boolean);
      expect(codeEntry).not.toBeNull();
      fireEvent.click(codeEntry!);

      await waitFor(() => {
        expect(mockGetCreatorCourseRedemptionCodeCodes).toHaveBeenCalledWith({
          coupon_bid: 'coupon-2',
          page_index: 1,
          page_size: 20,
          keyword: '',
        });
      });
      expect(await screen.findByText('SUBCODE001')).toBeInTheDocument();
    } finally {
      window.URL.createObjectURL = originalCreateObjectURL;
      window.URL.revokeObjectURL = originalRevokeObjectURL;
      anchorClick.mockRestore();
    }
  });

  test('opens edit dialog and toggles coupon status from row actions', async () => {
    render(<CreatorRedemptionCodesTab />);

    await screen.findByText('Batch A');
    fireEvent.click(screen.getAllByText('actions.edit')[0]);

    await waitFor(() => {
      expect(mockGetCreatorCourseRedemptionCodeDetail).toHaveBeenCalledWith({
        coupon_bid: 'coupon-1',
      });
    });
    await waitFor(() => {
      expect(
        screen.getAllByText('module.order.redemptionCodes.editDialogTitle')
          .length,
      ).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByText('common.core.cancel'));

    await waitFor(() => {
      expect(screen.getAllByText('actions.disable').length).toBeGreaterThan(0);
    });
    fireEvent.click(screen.getAllByText('actions.disable')[0]);
    fireEvent.click(screen.getByText(CONFIRM_STATUS_LABEL));

    await waitFor(() => {
      expect(mockUpdateCreatorCourseRedemptionCodeStatus).toHaveBeenCalledWith({
        coupon_bid: 'coupon-1',
        enabled: false,
      });
    });
    expect(
      mockGetCreatorCourseRedemptionCodes.mock.calls.length,
    ).toBeGreaterThan(1);
  });

  test('keeps the latest redemption code response when requests finish out of order', async () => {
    const oldRequest = createDeferred<Record<string, unknown>>();
    const latestRequest = createDeferred<Record<string, unknown>>();
    mockGetCreatorCourseRedemptionCodes
      .mockReturnValueOnce(oldRequest.promise)
      .mockReturnValueOnce(latestRequest.promise);

    render(<CreatorRedemptionCodesTab />);

    fireEvent.change(screen.getByPlaceholderText('filters.namePlaceholder'), {
      target: { value: 'Latest Batch' },
    });
    fireEvent.click(screen.getByText('module.order.filters.search'));
    await waitFor(() => {
      expect(mockGetCreatorCourseRedemptionCodes).toHaveBeenCalledTimes(2);
    });

    await act(async () => {
      latestRequest.resolve(createListResponse('Latest Batch'));
      await Promise.resolve();
    });
    await act(async () => {
      oldRequest.resolve(createListResponse('Old Batch'));
      await Promise.resolve();
    });

    expect(await screen.findByText('Latest Batch')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText('Old Batch')).not.toBeInTheDocument();
    });
  });

  test('does not render empty state when loading redemption codes fails', async () => {
    mockGetCreatorCourseRedemptionCodes.mockRejectedValueOnce(
      new Error('load failed'),
    );

    render(<CreatorRedemptionCodesTab />);

    expect(await screen.findByText('load failed')).toBeInTheDocument();
    expect(
      screen.queryByText('module.order.redemptionCodes.emptyList'),
    ).not.toBeInTheDocument();
  });

  test('clears stale redemption code rows when a reload fails', async () => {
    render(<CreatorRedemptionCodesTab />);

    expect(await screen.findByText('Batch A')).toBeInTheDocument();

    mockGetCreatorCourseRedemptionCodes.mockRejectedValueOnce(
      new Error('reload failed'),
    );
    fireEvent.change(screen.getByPlaceholderText('filters.namePlaceholder'), {
      target: { value: 'Missing Batch' },
    });
    fireEvent.click(screen.getByText('module.order.filters.search'));

    expect(await screen.findByText('reload failed')).toBeInTheDocument();
    expect(screen.queryByText('Batch A')).not.toBeInTheDocument();
    expect(screen.queryByText('Batch B')).not.toBeInTheDocument();
    expect(screen.queryByText('3/20')).not.toBeInTheDocument();
  });

  test('passes ops state filters to the redemption code list request', async () => {
    render(<CreatorRedemptionCodesTab />);

    await screen.findByText('Batch A');
    fireEvent.click(screen.getByText('common.core.expand'));
    fireEvent.click(screen.getByText('opsState.usedUp'));
    fireEvent.click(screen.getByText('module.order.filters.search'));

    await waitFor(() => {
      expect(mockGetCreatorCourseRedemptionCodes).toHaveBeenLastCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        name: '',
        course_query: '',
        usage_type: '',
        ops_state: 'used_up',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });
  });

  test('does not expose ended as a creator redemption status filter option', async () => {
    render(<CreatorRedemptionCodesTab />);

    await screen.findByText('Batch A');
    fireEvent.click(screen.getByText('common.core.expand'));

    expect(screen.queryByText('status.ended')).not.toBeInTheDocument();
  });
});
