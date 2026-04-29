import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import AdminOperationPromotionsPage from './page';

const mockToast = jest.fn();
const MOCK_DIALOG_CLOSE_LABEL = 'mock-dialog-close';
const translationCache = new Map<string, { t: (key: string) => string }>();
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
    getAdminOperationPromotionCoupons: jest.fn(),
    createAdminOperationPromotionCoupon: jest.fn(),
    updateAdminOperationPromotionCoupon: jest.fn(),
    getAdminOperationPromotionCouponDetail: jest.fn(),
    getAdminOperationPromotionCouponUsages: jest.fn(),
    getAdminOperationPromotionCouponCodes: jest.fn(),
    updateAdminOperationPromotionCouponStatus: jest.fn(),
    getAdminOperationPromotionCampaigns: jest.fn(),
    createAdminOperationPromotionCampaign: jest.fn(),
    updateAdminOperationPromotionCampaign: jest.fn(),
    getAdminOperationPromotionCampaignDetail: jest.fn(),
    getAdminOperationPromotionCampaignRedemptions: jest.fn(),
    updateAdminOperationPromotionCampaignStatus: jest.fn(),
  },
}));

jest.mock('@/app/admin/operations/useOperatorGuard', () => ({
  __esModule: true,
  default: () => ({
    isReady: true,
  }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => baseTranslation(namespace),
}));


jest.mock('@/hooks/useToast', () => ({
  __esModule: true,
  useToast: () => ({
    toast: mockToast,
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
    startValue,
    endValue,
    placeholder,
    onChange = () => undefined,
  }: {
    startValue?: string;
    endValue?: string;
    placeholder: string;
    onChange?: (range: { start: string; end: string }) => void;
  }) => (
    <div>
      <span>{placeholder}</span>
      <input
        value={startValue || ''}
        placeholder={`${placeholder}-start`}
        onChange={event =>
          onChange({ start: event.target.value, end: endValue || '' })
        }
      />
      <input
        value={endValue || ''}
        placeholder={`${placeholder}-end`}
        onChange={event =>
          onChange({ start: startValue || '', end: event.target.value })
        }
      />
    </div>
  ),
}));

jest.mock('@/components/ui/Sheet', () => ({
  __esModule: true,
  Sheet: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SheetContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  SheetHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SheetTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

jest.mock('@/components/ui/Dialog', () => {
  const MockDialogContent = React.forwardRef<
    HTMLDivElement,
    React.PropsWithChildren
  >(({ children }, ref) => <div ref={ref}>{children}</div>);
  MockDialogContent.displayName = 'MockDialogContent';

  return {
    __esModule: true,
    Dialog: ({
      open = true,
      onOpenChange,
      children,
    }: React.PropsWithChildren<{
      open?: boolean;
      onOpenChange?: (open: boolean) => void;
    }>) =>
      open ? (
        <div>
          <button
            type='button'
            aria-label={MOCK_DIALOG_CLOSE_LABEL}
            onClick={() => onOpenChange?.(false)}
          >
            {MOCK_DIALOG_CLOSE_LABEL}
          </button>
          {children}
        </div>
      ) : null,
    DialogContent: MockDialogContent,
    DialogHeader: ({ children }: React.PropsWithChildren) => (
      <div>{children}</div>
    ),
    DialogTitle: ({ children }: React.PropsWithChildren) => (
      <div>{children}</div>
    ),
    DialogFooter: ({ children }: React.PropsWithChildren) => (
      <div>{children}</div>
    ),
  };
});

jest.mock('@/components/ui/DropdownMenu', () => ({
  __esModule: true,
  DropdownMenu: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuTrigger: ({ children }: React.PropsWithChildren) => (
    <>{children}</>
  ),
  DropdownMenuContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
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

jest.mock('@/components/ui/Select', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const SelectContext = ReactModule.createContext<{
    value: string;
    onValueChange: (value: string) => void;
    disabled: boolean;
  }>({
    value: '',
    onValueChange: () => undefined,
    disabled: false,
  });

  return {
    __esModule: true,
    Select: ({
      value,
      onValueChange,
      disabled = false,
      children,
    }: React.PropsWithChildren<{
      value: string;
      onValueChange: (value: string) => void;
      disabled?: boolean;
    }>) => (
      <SelectContext.Provider value={{ value, onValueChange, disabled }}>
        <div>{children}</div>
      </SelectContext.Provider>
    ),
    SelectTrigger: ({ children }: React.PropsWithChildren) => (
      <div>{children}</div>
    ),
    SelectValue: () => <span />,
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
          disabled={context.disabled}
          onClick={() => context.onValueChange(value)}
        >
          {children}
        </button>
      );
    },
  };
});

jest.mock('@/components/ui/Tabs', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const TabsContext = ReactModule.createContext<{
    value: string;
    onValueChange: (value: string) => void;
  }>({
    value: 'coupons',
    onValueChange: () => undefined,
  });

  return {
    __esModule: true,
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

const mockGetCoupons = api.getAdminOperationPromotionCoupons as jest.Mock;
const mockGetCampaigns = api.getAdminOperationPromotionCampaigns as jest.Mock;
const mockCreateCoupon = api.createAdminOperationPromotionCoupon as jest.Mock;
const mockUpdateCoupon = api.updateAdminOperationPromotionCoupon as jest.Mock;
const mockGetCouponDetail =
  api.getAdminOperationPromotionCouponDetail as jest.Mock;
const mockGetCouponCodes =
  api.getAdminOperationPromotionCouponCodes as jest.Mock;
const mockGetCouponUsages =
  api.getAdminOperationPromotionCouponUsages as jest.Mock;
const mockUpdateCouponStatus =
  api.updateAdminOperationPromotionCouponStatus as jest.Mock;
const mockUpdateCampaign =
  api.updateAdminOperationPromotionCampaign as jest.Mock;
const mockGetCampaignDetail =
  api.getAdminOperationPromotionCampaignDetail as jest.Mock;
const mockGetCampaignRedemptions =
  api.getAdminOperationPromotionCampaignRedemptions as jest.Mock;
const mockUpdateCampaignStatus =
  api.updateAdminOperationPromotionCampaignStatus as jest.Mock;

describe('AdminOperationPromotionsPage', () => {
  beforeEach(() => {
    mockToast.mockReset();
    mockGetCoupons.mockReset();
    mockGetCampaigns.mockReset();
    mockCreateCoupon.mockReset();
    mockUpdateCoupon.mockReset();
    mockGetCouponDetail.mockReset();
    mockGetCouponCodes.mockReset();
    mockGetCouponUsages.mockReset();
    mockUpdateCouponStatus.mockReset();
    mockUpdateCampaign.mockReset();
    mockGetCampaignDetail.mockReset();
    mockGetCampaignRedemptions.mockReset();
    mockUpdateCampaignStatus.mockReset();
    mockCreateCoupon.mockResolvedValue({ coupon_bid: 'created-coupon' });
    mockUpdateCoupon.mockResolvedValue({ coupon_bid: 'coupon-1' });
    mockGetCouponDetail.mockResolvedValue({
      coupon: {
        coupon_bid: 'coupon-1',
        name: 'Spring Batch',
        code: 'SPRING2026',
        usage_type: 801,
        usage_type_key: 'module.operationsPromotion.usageType.generic',
        discount_type: 701,
        discount_type_key: 'module.operationsPromotion.discountType.fixed',
        value: '20',
        scope_type: 'single_course',
        shifu_bid: 'course-1',
        course_name: 'Coupon Course',
        start_at: '2026-04-24T10:00:00Z',
        end_at: '2026-05-24T10:00:00Z',
        total_count: 10,
        used_count: 3,
        computed_status: 'active',
        computed_status_key: 'module.operationsPromotion.status.active',
        created_at: '2026-04-24T10:00:00Z',
        updated_at: '2026-04-24T11:00:00Z',
      },
    });
    mockUpdateCouponStatus.mockResolvedValue({
      coupon_bid: 'coupon-1',
      enabled: false,
    });
    mockUpdateCampaign.mockResolvedValue({ promo_bid: 'promo-1' });
    mockGetCouponCodes.mockResolvedValue({
      items: [],
      page: 1,
      page_count: 0,
      page_size: 20,
      total: 0,
    });
    mockGetCouponUsages.mockResolvedValue({
      items: [],
      page: 1,
      page_count: 0,
      page_size: 20,
      total: 0,
    });
    mockGetCampaignDetail.mockResolvedValue({
      campaign: {
        promo_bid: 'promo-1',
        name: 'Early Bird',
        shifu_bid: 'course-2',
        course_name: 'Campaign Course',
        apply_type: 2102,
        discount_type: 702,
        discount_type_key: 'module.operationsPromotion.discountType.percent',
        value: '15',
        channel: 'app',
        start_at: '2026-04-24T10:00:00Z',
        end_at: '2026-05-24T10:00:00Z',
        computed_status: 'active',
        computed_status_key: 'module.operationsPromotion.status.active',
        applied_order_count: 2,
        has_redemptions: true,
        total_discount_amount: '30',
        created_at: '2026-04-24T10:00:00Z',
        updated_at: '2026-04-24T11:00:00Z',
      },
      description: 'Launch campaign',
      created_user_bid: 'operator-1',
      created_user_name: 'Operator',
      updated_user_bid: 'operator-1',
      updated_user_name: 'Operator',
      latest_applied_at: '2026-04-24T12:00:00Z',
    });
    mockGetCampaignRedemptions.mockResolvedValue({
      items: [
        {
          redemption_bid: 'redemption-1',
          user_bid: 'learner-2',
          user_mobile: '',
          user_email: 'learner@example.com',
          user_nickname: 'Learner Two',
          order_bid: 'order-2',
          order_status: 0,
          order_status_key: 'module.order.orderStatus.success',
          payable_price: '99',
          discount_amount: '14.85',
          paid_price: '84.15',
          status: 4101,
          status_key: 'module.operationsPromotion.redemptionStatus.applied',
          applied_at: '2026-04-24T12:00:00Z',
          updated_at: '2026-04-24T12:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCoupons.mockResolvedValue({
      summary: {
        total: 1,
        active: 1,
        usage_count: 3,
        latest_usage_at: '2026-04-24T12:00:00Z',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-1',
          name: 'Spring Batch',
          code: 'SPRING2026',
          usage_type: 801,
          usage_type_key: 'module.operationsPromotion.usageType.generic',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          total_count: 10,
          used_count: 3,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCampaigns.mockResolvedValue({
      summary: {
        total: 1,
        active: 1,
        usage_count: 2,
        latest_usage_at: '2026-04-24T12:00:00Z',
        covered_courses: 1,
        discount_amount: '30',
      },
      items: [
        {
          promo_bid: 'promo-1',
          name: 'Early Bird',
          shifu_bid: 'course-2',
          course_name: 'Campaign Course',
          apply_type: 2102,
          discount_type: 702,
          discount_type_key: 'module.operationsPromotion.discountType.percent',
          value: '15',
          channel: 'app',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          applied_order_count: 2,
          has_redemptions: true,
          total_discount_amount: '30',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockUpdateCampaignStatus.mockResolvedValue({
      promo_bid: 'promo-1',
      enabled: false,
    });
  });

  test('loads coupon tab by default', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => {
      expect(mockGetCoupons).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        name: '',
        course_query: '',
        usage_type: '',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(await screen.findByText('Spring Batch')).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsPromotion.table.scope'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsPromotion.scope.singleCourse'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.createCoupon',
      }),
    ).toBeInTheDocument();
  });

  test('keeps coupon page when switching away and back', async () => {
    mockGetCoupons
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 3,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '0',
        },
        items: [
          {
            coupon_bid: 'coupon-1',
            name: 'Spring Batch',
            code: 'SPRING2026',
            usage_type: 801,
            usage_type_key: 'module.operationsPromotion.usageType.generic',
            discount_type: 701,
            discount_type_key: 'module.operationsPromotion.discountType.fixed',
            value: '20',
            scope_type: 'single_course',
            shifu_bid: 'course-1',
            course_name: 'Coupon Course',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            total_count: 10,
            used_count: 3,
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 1,
        page_count: 2,
        page_size: 20,
        total: 21,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 3,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '0',
        },
        items: [
          {
            coupon_bid: 'coupon-21',
            name: 'Page Two Coupon',
            code: 'PAGE2',
            usage_type: 801,
            usage_type_key: 'module.operationsPromotion.usageType.generic',
            discount_type: 701,
            discount_type_key: 'module.operationsPromotion.discountType.fixed',
            value: '20',
            scope_type: 'single_course',
            shifu_bid: 'course-1',
            course_name: 'Coupon Course',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            total_count: 10,
            used_count: 3,
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 2,
        page_count: 2,
        page_size: 20,
        total: 21,
      });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(screen.getByRole('link', { name: '2' }));

    await screen.findByText('Page Two Coupon');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.coupons',
      }),
    );

    expect(await screen.findByText('Page Two Coupon')).toBeInTheDocument();
  });

  test('switches to campaign tab and loads campaigns', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaigns).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        course_query: '',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(await screen.findByText('Early Bird')).toBeInTheDocument();
  });

  test('keeps campaign filter state aligned when switching tabs', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    const keywordInput = await screen.findByPlaceholderText(
      'module.operationsPromotion.filters.campaignNamePlaceholder',
    );
    fireEvent.change(keywordInput, { target: { value: 'Retention' } });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.coupons',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaigns).toHaveBeenLastCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: 'Retention',
        course_query: '',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });
  });

  test('keeps campaign page when switching away and back', async () => {
    mockGetCampaigns
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 2,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '30',
        },
        items: [
          {
            promo_bid: 'promo-1',
            name: 'Page One Campaign',
            shifu_bid: 'course-2',
            course_name: 'Campaign Course',
            apply_type: 2102,
            discount_type: 702,
            discount_type_key:
              'module.operationsPromotion.discountType.percent',
            value: '15',
            channel: 'app',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            applied_order_count: 2,
            has_redemptions: true,
            total_discount_amount: '30',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 1,
        page_count: 2,
        page_size: 20,
        total: 21,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 2,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '30',
        },
        items: [
          {
            promo_bid: 'promo-21',
            name: 'Page Two Campaign',
            shifu_bid: 'course-2',
            course_name: 'Campaign Course',
            apply_type: 2102,
            discount_type: 702,
            discount_type_key:
              'module.operationsPromotion.discountType.percent',
            value: '15',
            channel: 'app',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            applied_order_count: 2,
            has_redemptions: true,
            total_discount_amount: '30',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 2,
        page_count: 2,
        page_size: 20,
        total: 21,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 2,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '30',
        },
        items: [
          {
            promo_bid: 'promo-21',
            name: 'Page Two Campaign',
            shifu_bid: 'course-2',
            course_name: 'Campaign Course',
            apply_type: 2102,
            discount_type: 702,
            discount_type_key:
              'module.operationsPromotion.discountType.percent',
            value: '15',
            channel: 'app',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            applied_order_count: 2,
            has_redemptions: true,
            total_discount_amount: '30',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 2,
        page_count: 2,
        page_size: 20,
        total: 21,
      });

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Page One Campaign');

    fireEvent.click(screen.getByRole('link', { name: '2' }));

    await screen.findByText('Page Two Campaign');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.coupons',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaigns).toHaveBeenLastCalledWith({
        page_index: 2,
        page_size: 20,
        keyword: '',
        course_query: '',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });
  });

  test('shows operator-focused campaign columns and opens order list dialog from applied order count', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    expect(
      screen.getByPlaceholderText(
        'module.operationsPromotion.filters.campaignNamePlaceholder',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsPromotion.campaign.applyTypeEvent'),
    ).toBeInTheDocument();
    expect(screen.getByText('app')).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.viewOrders: Early Bird',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaignRedemptions).toHaveBeenCalledWith({
        promo_bid: 'promo-1',
        page_index: 1,
        page_size: 20,
      });
    });

    expect(mockGetCampaignDetail).not.toHaveBeenCalled();
    expect(
      await screen.findByText(
        'module.operationsPromotion.campaign.redemptions',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('order-2')).toBeInTheDocument();
  });

  test('shows toast when campaign redemptions request fails', async () => {
    mockGetCampaignRedemptions.mockRejectedValueOnce(
      new Error('redemptions failed'),
    );

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.viewOrders: Early Bird',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        description: 'redemptions failed',
      });
    });

    expect(
      await screen.findByText(
        'module.operationsPromotion.messages.emptyRedemptions',
      ),
    ).toBeInTheDocument();
  });

  test('only keeps apply type conditional and locks channel/value in campaign edit dialog', async () => {
    mockGetCampaigns.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 0,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          promo_bid: 'promo-1',
          name: 'Early Bird',
          shifu_bid: 'course-2',
          course_name: 'Campaign Course',
          apply_type: 2102,
          discount_type: 702,
          discount_type_key: 'module.operationsPromotion.discountType.percent',
          value: '15',
          channel: 'app',
          start_at: '2099-04-24T10:00:00Z',
          end_at: '2099-05-24T10:00:00Z',
          computed_status: 'not_started',
          computed_status_key: 'module.operationsPromotion.status.notStarted',
          applied_order_count: 0,
          has_redemptions: false,
          total_discount_amount: '0',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCampaignDetail.mockResolvedValueOnce({
      campaign: {
        promo_bid: 'promo-1',
        name: 'Early Bird',
        shifu_bid: 'course-2',
        course_name: 'Campaign Course',
        apply_type: 2102,
        discount_type: 702,
        discount_type_key: 'module.operationsPromotion.discountType.percent',
        value: '15',
        channel: 'app',
        start_at: '2099-04-24T10:00:00Z',
        end_at: '2099-05-24T10:00:00Z',
        computed_status: 'not_started',
        computed_status_key: 'module.operationsPromotion.status.notStarted',
        applied_order_count: 0,
        has_redemptions: false,
        total_discount_amount: '0',
        created_at: '2026-04-24T10:00:00Z',
        updated_at: '2026-04-24T11:00:00Z',
      },
      description: 'Launch campaign',
      created_user_bid: 'operator-1',
      created_user_name: 'Operator',
      updated_user_bid: 'operator-1',
      updated_user_name: 'Operator',
      latest_applied_at: '',
    });

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaignDetail).toHaveBeenCalledWith({
        promo_bid: 'promo-1',
      });
    });

    expect(await screen.findByDisplayValue('Early Bird')).not.toBeDisabled();
    expect(screen.getByDisplayValue('Launch campaign')).not.toBeDisabled();
    const startAtButtons = screen.getAllByRole('button', {
      name: 'module.operationsPromotion.campaign.startAtPlaceholder',
    });
    const endAtButtons = screen.getAllByRole('button', {
      name: 'module.operationsPromotion.campaign.endAtPlaceholder',
    });
    expect(startAtButtons.at(-1)).not.toBeDisabled();
    expect(endAtButtons.at(-1)).not.toBeDisabled();

    expect(screen.getByDisplayValue('course-2')).toBeDisabled();
    expect(screen.getByDisplayValue('app')).toBeDisabled();
    expect(screen.getByDisplayValue('15')).toBeDisabled();
    expect(
      screen.getByText(
        'module.operationsPromotion.messages.partialTimeEditHint',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsPromotion.messages.campaignEditPolicyHint',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.campaign.applyTypeEvent',
      }),
    ).not.toBeDisabled();
  });

  test('locks campaign apply type when redemptions exist but applied order count is zero', async () => {
    mockGetCampaigns.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 0,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          promo_bid: 'promo-voided',
          name: 'Voided Campaign',
          shifu_bid: 'course-2',
          course_name: 'Campaign Course',
          apply_type: 2102,
          discount_type: 702,
          discount_type_key: 'module.operationsPromotion.discountType.percent',
          value: '15',
          channel: 'app',
          start_at: '2099-04-24T10:00:00Z',
          end_at: '2099-05-24T10:00:00Z',
          computed_status: 'not_started',
          computed_status_key: 'module.operationsPromotion.status.notStarted',
          applied_order_count: 0,
          has_redemptions: true,
          total_discount_amount: '0',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCampaignDetail.mockResolvedValueOnce({
      campaign: {
        promo_bid: 'promo-voided',
        name: 'Voided Campaign',
        shifu_bid: 'course-2',
        course_name: 'Campaign Course',
        apply_type: 2102,
        discount_type: 702,
        discount_type_key: 'module.operationsPromotion.discountType.percent',
        value: '15',
        channel: 'app',
        start_at: '2099-04-24T10:00:00Z',
        end_at: '2099-05-24T10:00:00Z',
        computed_status: 'not_started',
        computed_status_key: 'module.operationsPromotion.status.notStarted',
        applied_order_count: 0,
        has_redemptions: true,
        total_discount_amount: '0',
        created_at: '2026-04-24T10:00:00Z',
        updated_at: '2026-04-24T11:00:00Z',
      },
      description: 'Launch campaign',
      created_user_bid: 'operator-1',
      created_user_name: 'Operator',
      updated_user_bid: 'operator-1',
      updated_user_name: 'Operator',
      latest_applied_at: '',
    });

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Voided Campaign');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaignDetail).toHaveBeenCalledWith({
        promo_bid: 'promo-voided',
      });
    });

    expect(
      await screen.findByRole('button', {
        name: 'module.operationsPromotion.campaign.applyTypeEvent',
      }),
    ).toBeDisabled();
  });

  test('uses detail payload to refresh campaign edit locks when list data is stale', async () => {
    mockGetCampaigns.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 0,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          promo_bid: 'promo-stale',
          name: 'Stale Campaign',
          shifu_bid: 'course-2',
          course_name: 'Campaign Course',
          apply_type: 2102,
          discount_type: 702,
          discount_type_key: 'module.operationsPromotion.discountType.percent',
          value: '15',
          channel: 'app',
          start_at: '2099-04-24T10:00:00Z',
          end_at: '2099-05-24T10:00:00Z',
          computed_status: 'not_started',
          computed_status_key: 'module.operationsPromotion.status.notStarted',
          applied_order_count: 0,
          has_redemptions: false,
          total_discount_amount: '0',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCampaignDetail.mockResolvedValueOnce({
      campaign: {
        promo_bid: 'promo-stale',
        name: 'Stale Campaign',
        shifu_bid: 'course-2',
        course_name: 'Campaign Course',
        apply_type: 2102,
        discount_type: 702,
        discount_type_key: 'module.operationsPromotion.discountType.percent',
        value: '15',
        channel: 'app',
        start_at: '2099-04-24T10:00:00Z',
        end_at: '2099-05-24T10:00:00Z',
        computed_status: 'not_started',
        computed_status_key: 'module.operationsPromotion.status.notStarted',
        applied_order_count: 0,
        has_redemptions: true,
        total_discount_amount: '0',
        created_at: '2026-04-24T10:00:00Z',
        updated_at: '2026-04-24T11:00:00Z',
      },
      description: 'Launch campaign',
      created_user_bid: 'operator-1',
      created_user_name: 'Operator',
      updated_user_bid: 'operator-1',
      updated_user_name: 'Operator',
      latest_applied_at: '',
    });

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Stale Campaign');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaignDetail).toHaveBeenCalledWith({
        promo_bid: 'promo-stale',
      });
    });

    expect(
      await screen.findByRole('button', {
        name: 'module.operationsPromotion.campaign.applyTypeEvent',
      }),
    ).toBeDisabled();
  });

  test('shows toast when campaign status update is rejected', async () => {
    mockUpdateCampaignStatus.mockRejectedValueOnce(new Error('status failed'));

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.disable',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        description: 'status failed',
      });
    });
  });

  test('shows specific success toast when coupon is disabled', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.disable',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateCouponStatus).toHaveBeenCalledWith({
        coupon_bid: 'coupon-1',
        enabled: false,
      });
    });
    expect(mockToast).toHaveBeenCalledWith({
      description: 'module.operationsPromotion.messages.disabledSuccess',
    });
  });

  test('shows specific success toast when campaign is disabled', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.disable',
      }),
    );

    await waitFor(() => {
      expect(mockUpdateCampaignStatus).toHaveBeenCalledWith({
        promo_bid: 'promo-1',
        enabled: false,
      });
    });
    expect(mockToast).toHaveBeenCalledWith({
      description: 'module.operationsPromotion.messages.disabledSuccess',
    });
  });

  test('hides coupon enable action when inactive batch is already expired', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 0,
        usage_count: 3,
        latest_usage_at: '2026-04-24T12:00:00Z',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-expired',
          name: 'Expired Coupon',
          code: 'EXPIRED',
          usage_type: 801,
          usage_type_key: 'module.operationsPromotion.usageType.generic',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-01T10:00:00Z',
          end_at: '2026-04-02T10:00:00Z',
          total_count: 10,
          used_count: 3,
          computed_status: 'inactive',
          computed_status_key: 'module.operationsPromotion.status.inactive',
          created_at: '2026-04-01T10:00:00Z',
          updated_at: '2026-04-02T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Expired Coupon');

    expect(
      screen.queryByRole('button', {
        name: 'module.operationsPromotion.actions.enable',
      }),
    ).not.toBeInTheDocument();
  });

  test('hides campaign enable action when inactive campaign is already ended', async () => {
    mockGetCampaigns.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 0,
        usage_count: 2,
        latest_usage_at: '2026-04-24T12:00:00Z',
        covered_courses: 1,
        discount_amount: '30',
      },
      items: [
        {
          promo_bid: 'promo-ended',
          name: 'Ended Campaign',
          shifu_bid: 'course-2',
          course_name: 'Campaign Course',
          apply_type: 2102,
          discount_type: 702,
          discount_type_key: 'module.operationsPromotion.discountType.percent',
          value: '15',
          channel: 'app',
          start_at: '2026-04-01T10:00:00Z',
          end_at: '2026-04-02T10:00:00Z',
          computed_status: 'inactive',
          computed_status_key: 'module.operationsPromotion.status.inactive',
          applied_order_count: 2,
          has_redemptions: true,
          total_discount_amount: '30',
          created_at: '2026-04-01T10:00:00Z',
          updated_at: '2026-04-02T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationPromotionsPage />);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Ended Campaign');

    expect(
      screen.queryByRole('button', {
        name: 'module.operationsPromotion.actions.enable',
      }),
    ).not.toBeInTheDocument();
  });

  test('supports clearable coupon keyword input and expanding filters', async () => {
    render(<AdminOperationPromotionsPage />);

    const keywordInput = await screen.findByPlaceholderText(
      'module.operationsPromotion.filters.keywordPlaceholder',
    );

    fireEvent.change(keywordInput, { target: { value: 'SPRING2026' } });
    expect(keywordInput).toHaveValue('SPRING2026');

    fireEvent.click(screen.getByRole('button', { name: 'common.core.close' }));
    expect(keywordInput).toHaveValue('');

    fireEvent.click(
      screen.getByRole('button', { name: /common\.core\.expand/i }),
    );

    expect(
      screen.getAllByPlaceholderText(
        'module.operationsPromotion.filters.courseIdPlaceholder',
      ).length,
    ).toBeGreaterThan(0);
  });

  test('only keeps name quantity and active time editable in coupon edit dialog', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockGetCouponDetail).toHaveBeenCalledWith({
        coupon_bid: 'coupon-1',
      });
    });

    expect(await screen.findByDisplayValue('Spring Batch')).not.toBeDisabled();
    expect(screen.getByDisplayValue('10')).not.toBeDisabled();
    const startAtButtons = screen.getAllByRole('button', {
      name: 'module.operationsPromotion.coupon.startAt',
    });
    const endAtButtons = screen.getAllByRole('button', {
      name: 'module.operationsPromotion.coupon.endAt',
    });
    expect(startAtButtons.at(-1)).not.toBeDisabled();
    expect(endAtButtons.at(-1)).not.toBeDisabled();

    expect(screen.getByDisplayValue('SPRING2026')).toBeDisabled();
    expect(screen.getByDisplayValue('20')).toBeDisabled();
    expect(screen.getByDisplayValue('course-1')).toBeDisabled();
    expect(
      screen.getByText(
        'module.operationsPromotion.messages.partialTimeEditHint',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsPromotion.messages.couponEditPolicyHint',
      ),
    ).toBeInTheDocument();
  });

  test('uses coupon detail payload to refresh stale edit values before opening dialog', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 3,
        latest_usage_at: '2026-04-24T12:00:00Z',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-stale',
          name: 'Spring Batch',
          code: 'SPRING2026',
          usage_type: 801,
          usage_type_key: 'module.operationsPromotion.usageType.generic',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          total_count: 10,
          used_count: 3,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCouponDetail.mockResolvedValueOnce({
      coupon: {
        coupon_bid: 'coupon-stale',
        name: 'Spring Batch',
        code: 'SPRING2026',
        usage_type: 801,
        usage_type_key: 'module.operationsPromotion.usageType.generic',
        discount_type: 701,
        discount_type_key: 'module.operationsPromotion.discountType.fixed',
        value: '20',
        scope_type: 'single_course',
        shifu_bid: 'course-1',
        course_name: 'Coupon Course',
        start_at: '2026-04-24T10:00:00Z',
        end_at: '2026-05-24T10:00:00Z',
        total_count: 20,
        used_count: 8,
        computed_status: 'active',
        computed_status_key: 'module.operationsPromotion.status.active',
        created_at: '2026-04-24T10:00:00Z',
        updated_at: '2026-04-25T11:00:00Z',
      },
    });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockGetCouponDetail).toHaveBeenCalledWith({
        coupon_bid: 'coupon-stale',
      });
    });

    const quantityInput = (await screen.findAllByDisplayValue('20')).find(
      element => !element.hasAttribute('disabled'),
    );
    expect(quantityInput).toBeDefined();
  });

  test('shows toast when coupon detail request fails', async () => {
    mockGetCouponDetail.mockRejectedValueOnce(new Error('detail failed'));

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.edit',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        description: 'detail failed',
      });
    });

    expect(screen.queryByDisplayValue('Spring Batch')).not.toBeInTheDocument();
  });

  test('clears course id when coupon scope switches to all courses', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.createCoupon',
      }),
    );

    const courseInput = screen
      .getAllByPlaceholderText(
        'module.operationsPromotion.filters.courseIdPlaceholder',
      )
      .at(-1)!;
    fireEvent.change(courseInput, { target: { value: 'course-123' } });
    expect(courseInput).toHaveValue('course-123');

    fireEvent.click(
      screen
        .getAllByRole('button', {
          name: 'module.operationsPromotion.scope.allCourses',
        })
        .at(-1)!,
    );

    expect(courseInput).toHaveValue('');
  });

  test('hides generic code input for single-use coupon', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.createCoupon',
      }),
    );

    const codeInputCountBefore = screen.getAllByPlaceholderText(
      'module.operationsPromotion.coupon.codePlaceholder',
    ).length;
    expect(codeInputCountBefore).toBeGreaterThan(0);

    fireEvent.click(
      screen
        .getAllByRole('button', {
          name: 'module.operationsPromotion.usageType.singleUse',
        })
        .at(-1)!,
    );

    expect(
      screen.queryAllByPlaceholderText(
        'module.operationsPromotion.coupon.codePlaceholder',
      ),
    ).toHaveLength(codeInputCountBefore - 1);
  });

  test('does not render coupon detail action in coupon operations', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    expect(
      screen.queryByText('module.operationsPromotion.coupon.codes'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.operationsPromotion.actions.viewDetail',
      }),
    ).not.toBeInTheDocument();
  });

  test('shows placeholder in codes entry column for generic coupon', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    expect(
      screen.queryByRole('button', {
        name: 'module.operationsPromotion.table.codesEntry',
      }),
    ).not.toBeInTheDocument();
  });

  test('opens sub-code dialog from codes entry column for single-use coupon', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-2',
          name: 'Single Use Batch',
          code: 'BATCHCODE',
          usage_type: 802,
          usage_type_key: 'module.operationsPromotion.usageType.singleUse',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          total_count: 2,
          used_count: 1,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCouponCodes.mockResolvedValueOnce({
      items: [
        {
          coupon_usage_bid: 'usage-1',
          code: 'CODE001',
          status: 902,
          status_key: 'module.order.couponStatus.active',
          user_bid: '',
          user_mobile: '',
          user_email: '',
          user_nickname: '',
          order_bid: '',
          used_at: '',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Single Use Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.table.codesEntry',
      }),
    );

    await waitFor(() => {
      expect(mockGetCouponCodes).toHaveBeenCalledWith({
        coupon_bid: 'coupon-2',
        page_index: 1,
        page_size: 20,
        keyword: '',
      });
    });

    expect(
      screen.getByText('module.operationsPromotion.coupon.codes'),
    ).toBeInTheDocument();
    expect(screen.getByText('CODE001')).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsPromotion.coupon.subCode'),
    ).toBeInTheDocument();
  });

  test('shows toast when coupon codes request fails', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-2',
          name: 'Single Use Batch',
          code: '',
          usage_type: 802,
          usage_type_key: 'module.operationsPromotion.usageType.singleUse',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          total_count: 2,
          used_count: 1,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCouponCodes.mockRejectedValueOnce(new Error('codes failed'));

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Single Use Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.table.codesEntry',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        description: 'codes failed',
      });
    });

    expect(
      await screen.findByText('module.operationsPromotion.messages.emptyCodes'),
    ).toBeInTheDocument();
  });

  test('supports sub-code keyword search in codes dialog', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-2',
          name: 'Single Use Batch',
          code: 'BATCHCODE',
          usage_type: 802,
          usage_type_key: 'module.operationsPromotion.usageType.singleUse',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          total_count: 2,
          used_count: 1,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCouponCodes
      .mockResolvedValueOnce({
        items: [],
        page: 1,
        page_count: 0,
        page_size: 20,
        total: 0,
      })
      .mockResolvedValueOnce({
        items: [
          {
            coupon_usage_bid: 'usage-1',
            code: 'CODE001',
            status: 902,
            status_key: 'module.order.couponStatus.active',
            user_bid: '',
            user_mobile: '',
            user_email: '',
            user_nickname: '',
            order_bid: '',
            used_at: '',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 1,
        page_count: 1,
        page_size: 20,
        total: 1,
      });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Single Use Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.table.codesEntry',
      }),
    );

    const searchInput = await screen.findByPlaceholderText(
      'module.operationsPromotion.coupon.subCodePlaceholder',
    );
    fireEvent.change(searchInput, { target: { value: 'CODE001' } });
    fireEvent.click(
      screen
        .getAllByRole('button', {
          name: 'module.operationsPromotion.actions.search',
        })
        .at(-1)!,
    );

    await waitFor(() => {
      expect(mockGetCouponCodes).toHaveBeenLastCalledWith({
        coupon_bid: 'coupon-2',
        page_index: 1,
        page_size: 20,
        keyword: 'CODE001',
      });
    });
  });

  test('resets coupon codes dialog search state when reopened', async () => {
    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-2',
          name: 'Single Use Batch',
          code: '',
          usage_type: 802,
          usage_type_key: 'module.operationsPromotion.usageType.singleUse',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          total_count: 2,
          used_count: 1,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCouponCodes
      .mockResolvedValueOnce({
        items: [],
        page: 1,
        page_count: 0,
        page_size: 20,
        total: 0,
      })
      .mockResolvedValueOnce({
        items: [],
        page: 1,
        page_count: 0,
        page_size: 20,
        total: 0,
      })
      .mockResolvedValueOnce({
        items: [],
        page: 1,
        page_count: 0,
        page_size: 20,
        total: 0,
      });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Single Use Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.table.codesEntry',
      }),
    );

    const searchInput = await screen.findByPlaceholderText(
      'module.operationsPromotion.coupon.subCodePlaceholder',
    );
    fireEvent.change(searchInput, { target: { value: 'CODE001' } });
    fireEvent.click(
      screen
        .getAllByRole('button', {
          name: 'module.operationsPromotion.actions.search',
        })
        .at(-1)!,
    );

    fireEvent.click(
      screen.getByRole('button', { name: MOCK_DIALOG_CLOSE_LABEL }),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.table.codesEntry',
      }),
    );

    expect(
      await screen.findByPlaceholderText(
        'module.operationsPromotion.coupon.subCodePlaceholder',
      ),
    ).toHaveValue('');
    await waitFor(() => {
      expect(mockGetCouponCodes).toHaveBeenLastCalledWith({
        coupon_bid: 'coupon-2',
        page_index: 1,
        page_size: 20,
        keyword: '',
      });
    });
  });

  test('shows toast when coupon usages request fails', async () => {
    mockGetCouponUsages.mockRejectedValueOnce(new Error('usages failed'));

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: '3/10',
      }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        description: 'usages failed',
      });
    });

    expect(
      await screen.findByText(
        'module.operationsPromotion.messages.emptyUsages',
      ),
    ).toBeInTheDocument();
  });

  test('shows export action for single-use coupon', async () => {
    const createObjectURL = jest.fn(() => 'blob:coupon-codes');
    const revokeObjectURL = jest.fn();
    const anchorClick = jest
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    Object.defineProperty(window.URL, 'createObjectURL', {
      writable: true,
      value: createObjectURL,
    });
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      writable: true,
      value: revokeObjectURL,
    });

    mockGetCoupons.mockResolvedValueOnce({
      summary: {
        total: 1,
        active: 1,
        usage_count: 0,
        latest_usage_at: '',
        covered_courses: 1,
        discount_amount: '0',
      },
      items: [
        {
          coupon_bid: 'coupon-2',
          name: 'Single Use Batch',
          code: 'BATCHCODE',
          usage_type: 802,
          usage_type_key: 'module.operationsPromotion.usageType.singleUse',
          discount_type: 701,
          discount_type_key: 'module.operationsPromotion.discountType.fixed',
          value: '20',
          scope_type: 'single_course',
          shifu_bid: 'course-1',
          course_name: 'Coupon Course',
          start_at: '2026-04-24T10:00:00Z',
          end_at: '2026-05-24T10:00:00Z',
          total_count: 2,
          used_count: 1,
          computed_status: 'active',
          computed_status_key: 'module.operationsPromotion.status.active',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetCouponCodes.mockResolvedValueOnce({
      items: [
        {
          coupon_usage_bid: 'usage-1',
          code: 'CODE001',
          status: 902,
          status_key: 'module.order.couponStatus.active',
          user_bid: '',
          user_mobile: '',
          user_email: '',
          user_nickname: '',
          order_bid: '',
          used_at: '',
          updated_at: '2026-04-24T11:00:00Z',
        },
        {
          coupon_usage_bid: 'usage-2',
          code: 'CODE002',
          status: 903,
          status_key: 'module.order.couponStatus.used',
          user_bid: 'learner-1',
          user_mobile: '13812345678',
          user_email: '',
          user_nickname: 'Learner',
          order_bid: 'order-1',
          used_at: '2026-04-25T11:00:00Z',
          updated_at: '2026-04-25T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 100,
      total: 2,
    });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Single Use Batch');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.exportCodes',
      }),
    );

    await waitFor(() => {
      expect(mockGetCouponCodes).toHaveBeenCalledWith({
        coupon_bid: 'coupon-2',
        page_index: 1,
        page_size: 100,
      });
    });
    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalled();
    anchorClick.mockRestore();
  });

  test('clears stale coupon list when reload fails', async () => {
    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Spring Batch');

    mockGetCoupons.mockRejectedValueOnce(new Error('coupon list failed'));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.filters.search',
      }),
    );

    expect(await screen.findByText('coupon list failed')).toBeInTheDocument();
    expect(screen.queryByText('Spring Batch')).not.toBeInTheDocument();
  });

  test('clears stale campaign list when reload fails', async () => {
    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Early Bird');

    mockGetCampaigns.mockRejectedValueOnce(new Error('campaign list failed'));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.filters.search',
      }),
    );

    expect(await screen.findByText('campaign list failed')).toBeInTheDocument();
    expect(screen.queryByText('Early Bird')).not.toBeInTheDocument();
  });

  test('falls back to the last valid coupon page when current page becomes empty', async () => {
    mockGetCoupons
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 3,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '0',
        },
        items: [
          {
            coupon_bid: 'coupon-21',
            name: 'Page Two Coupon',
            code: 'PAGE2',
            usage_type: 801,
            usage_type_key: 'module.operationsPromotion.usageType.generic',
            discount_type: 701,
            discount_type_key: 'module.operationsPromotion.discountType.fixed',
            value: '20',
            scope_type: 'single_course',
            shifu_bid: 'course-1',
            course_name: 'Coupon Course',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            total_count: 10,
            used_count: 3,
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 2,
        page_count: 2,
        page_size: 20,
        total: 21,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 20,
          active: 20,
          usage_count: 3,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '0',
        },
        items: [],
        page: 2,
        page_count: 1,
        page_size: 20,
        total: 20,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 20,
          active: 20,
          usage_count: 3,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '0',
        },
        items: [
          {
            coupon_bid: 'coupon-1',
            name: 'Recovered Coupon',
            code: 'RECOVER',
            usage_type: 801,
            usage_type_key: 'module.operationsPromotion.usageType.generic',
            discount_type: 701,
            discount_type_key: 'module.operationsPromotion.discountType.fixed',
            value: '20',
            scope_type: 'single_course',
            shifu_bid: 'course-1',
            course_name: 'Coupon Course',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            total_count: 10,
            used_count: 3,
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 1,
        page_count: 1,
        page_size: 20,
        total: 20,
      });

    render(<AdminOperationPromotionsPage />);

    await screen.findByText('Page Two Coupon');

    mockUpdateCouponStatus.mockResolvedValueOnce({
      coupon_bid: 'coupon-21',
      enabled: false,
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.disable',
      }),
    );

    await waitFor(() => {
      expect(mockGetCoupons).toHaveBeenLastCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        name: '',
        course_query: '',
        usage_type: '',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(await screen.findByText('Recovered Coupon')).toBeInTheDocument();
  });

  test('falls back to the last valid campaign page when current page becomes empty', async () => {
    mockGetCampaigns
      .mockResolvedValueOnce({
        summary: {
          total: 21,
          active: 21,
          usage_count: 2,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '30',
        },
        items: [
          {
            promo_bid: 'promo-21',
            name: 'Page Two Campaign',
            shifu_bid: 'course-2',
            course_name: 'Campaign Course',
            apply_type: 2102,
            discount_type: 702,
            discount_type_key:
              'module.operationsPromotion.discountType.percent',
            value: '15',
            channel: 'app',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            applied_order_count: 2,
            has_redemptions: true,
            total_discount_amount: '30',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 2,
        page_count: 2,
        page_size: 20,
        total: 21,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 20,
          active: 20,
          usage_count: 2,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '30',
        },
        items: [],
        page: 2,
        page_count: 1,
        page_size: 20,
        total: 20,
      })
      .mockResolvedValueOnce({
        summary: {
          total: 20,
          active: 20,
          usage_count: 2,
          latest_usage_at: '2026-04-24T12:00:00Z',
          covered_courses: 1,
          discount_amount: '30',
        },
        items: [
          {
            promo_bid: 'promo-1',
            name: 'Recovered Campaign',
            shifu_bid: 'course-2',
            course_name: 'Campaign Course',
            apply_type: 2102,
            discount_type: 702,
            discount_type_key:
              'module.operationsPromotion.discountType.percent',
            value: '15',
            channel: 'app',
            start_at: '2026-04-24T10:00:00Z',
            end_at: '2026-05-24T10:00:00Z',
            computed_status: 'active',
            computed_status_key: 'module.operationsPromotion.status.active',
            applied_order_count: 2,
            has_redemptions: true,
            total_discount_amount: '30',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T11:00:00Z',
          },
        ],
        page: 1,
        page_count: 1,
        page_size: 20,
        total: 20,
      });

    render(<AdminOperationPromotionsPage />);

    await waitFor(() => expect(mockGetCoupons).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.tabs.campaigns',
      }),
    );

    await screen.findByText('Page Two Campaign');

    mockUpdateCampaignStatus.mockResolvedValueOnce({
      promo_bid: 'promo-21',
      enabled: false,
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsPromotion.actions.disable',
      }),
    );

    await waitFor(() => {
      expect(mockGetCampaigns).toHaveBeenLastCalledWith({
        page_index: 1,
        page_size: 20,
        keyword: '',
        course_query: '',
        discount_type: '',
        status: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(await screen.findByText('Recovered Campaign')).toBeInTheDocument();
  });
});
