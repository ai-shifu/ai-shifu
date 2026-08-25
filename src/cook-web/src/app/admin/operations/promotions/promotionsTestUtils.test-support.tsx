import React from 'react';
import api from '@/api';

export const mockToast = jest.fn();
export const MOCK_DIALOG_CLOSE_LABEL = 'mock-dialog-close';
const mockEnvState = {
  currencySymbol: '¥',
};
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
    getAdminOperationPromotionReferralCampaigns: jest.fn(),
    createAdminOperationPromotionReferralCampaign: jest.fn(),
    getAdminOperationPromotionReferralCampaignDetail: jest.fn(),
    updateAdminOperationPromotionReferralCampaign: jest.fn(),
    updateAdminOperationPromotionReferralCampaignStatus: jest.fn(),
    getAdminOperationPromotionReferralCampaignRelations: jest.fn(),
    getAdminOperationPromotionReferralCampaignInvitations: jest.fn(),
    getAdminBillingCampaignProductOptions: jest.fn(),
    getAdminBillingCampaigns: jest.fn(),
    createAdminBillingCampaign: jest.fn(),
    getAdminBillingCampaignDetail: jest.fn(),
    updateAdminBillingCampaign: jest.fn(),
    updateAdminBillingCampaignStatus: jest.fn(),
    getAdminBillingCampaignProviderDiscounts: jest.fn(),
    publishAdminBillingCampaign: jest.fn(),
    retryPublishAdminBillingCampaign: jest.fn(),
    retireAdminBillingCampaign: jest.fn(),
    validateAdminBillingCampaignProviderDiscount: jest.fn(),
  },
}));

jest.mock('@/app/admin/operations/useOperatorGuard', () => ({
  __esModule: true,
  default: () => ({
    isReady: true,
  }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => ({
    ...baseTranslation(namespace),
    i18n: { language: 'en-US' },
  }),
  Trans: ({
    i18nKey,
    values,
  }: {
    i18nKey: string;
    values?: Record<string, string>;
  }) => <span>{values?.name ? `${i18nKey}:${values.name}` : i18nKey}</span>,
}));

jest.mock('@/hooks/useToast', () => ({
  __esModule: true,
  showDefaultToast: (description: unknown, options?: Record<string, unknown>) =>
    mockToast({ ...options, description }),
  showErrorToast: (description: unknown, options?: Record<string, unknown>) =>
    mockToast({ ...options, description, variant: 'destructive' }),
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('@/lib/browser-timezone', () => ({
  __esModule: true,
  getBrowserTimeZone: () => 'Asia/Shanghai',
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

jest.mock('@/components/ui/Calendar', () => ({
  __esModule: true,
  Calendar: ({ onSelect }: { onSelect?: (date?: Date) => void }) => (
    <button
      type='button'
      aria-label='select-date'
      onClick={() => onSelect?.(new Date('2026-04-24T00:00:00Z'))}
    />
  ),
}));

jest.mock('@/components/ui/Checkbox', () => ({
  __esModule: true,
  Checkbox: ({
    checked = false,
    onCheckedChange,
  }: {
    checked?: boolean;
    onCheckedChange?: (checked: boolean) => void;
  }) => (
    <button
      type='button'
      role='checkbox'
      aria-label='checkbox'
      aria-checked={checked}
      onClick={() => onCheckedChange?.(!checked)}
    />
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
  Sheet: ({ children }: any) => <div>{children}</div>,
  SheetContent: ({ children }: any) => <div>{children}</div>,
  SheetHeader: ({ children }: any) => <div>{children}</div>,
  SheetTitle: ({ children }: any) => <div>{children}</div>,
  SheetDescription: ({ children }: any) => <div>{children}</div>,
}));

jest.mock('@/components/ui/Dialog', () => {
  const ReactModule = jest.requireActual('react') as typeof import('react');
  const MockDialogContent = ReactModule.forwardRef<HTMLDivElement, any>(
    ({ children }, ref) => <div ref={ref}>{children}</div>,
  );
  MockDialogContent.displayName = 'MockDialogContent';

  return {
    __esModule: true,
    Dialog: ({ open = true, onOpenChange, children }: any) =>
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
    DialogHeader: ({ children }: any) => <div>{children}</div>,
    DialogTitle: ({ children }: any) => <div>{children}</div>,
    DialogDescription: ({ children }: any) => <div>{children}</div>,
    DialogFooter: ({ children }: any) => <div>{children}</div>,
  };
});

jest.mock('@/components/ui/AlertDialog', () => ({
  __esModule: true,
  AlertDialog: ({ open = true, children }: any) =>
    open ? <div>{children}</div> : null,
  AlertDialogContent: ({ children }: any) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: any) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: any) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: any) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: any) => <div>{children}</div>,
  AlertDialogCancel: ({ children, onClick, disabled = false }: any) => (
    <button
      type='button'
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  ),
  AlertDialogAction: ({ children, onClick, disabled = false }: any) => (
    <button
      type='button'
      onClick={() => onClick?.({ preventDefault: () => undefined })}
      disabled={disabled}
    >
      {children}
    </button>
  ),
}));

jest.mock('@/components/ui/DropdownMenu', () => ({
  __esModule: true,
  DropdownMenu: ({ children }: any) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: any) => <>{children}</>,
  DropdownMenuContent: ({ children }: any) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick }: any) => (
    <button
      type='button'
      onClick={onClick}
    >
      {children}
    </button>
  ),
}));

jest.mock('@/components/ui/Select', () => {
  const ReactModule = jest.requireActual('react') as typeof import('react');
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
    Select: ({ value, onValueChange, disabled = false, children }: any) => (
      <SelectContext.Provider value={{ value, onValueChange, disabled }}>
        <div>{children}</div>
      </SelectContext.Provider>
    ),
    SelectTrigger: ({ children }: any) => <div>{children}</div>,
    SelectValue: () => <span />,
    SelectContent: ({ children }: any) => <div>{children}</div>,
    SelectItem: ({ value, children }: any) => {
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
  const ReactModule = jest.requireActual('react') as typeof import('react');
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
      defaultValue = 'coupons',
      onValueChange,
      children,
    }: any) => {
      const [internalValue, setInternalValue] = ReactModule.useState(
        value || defaultValue,
      );
      const currentValue = value || internalValue;
      const handleValueChange = (nextValue: string) => {
        setInternalValue(nextValue);
        onValueChange?.(nextValue);
      };
      return (
        <TabsContext.Provider
          value={{ value: currentValue, onValueChange: handleValueChange }}
        >
          {children}
        </TabsContext.Provider>
      );
    },
    TabsList: ({ children }: any) => <div>{children}</div>,
    TabsTrigger: ({ value, children }: any) => {
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
    TabsContent: ({ value, children }: any) => {
      const context = ReactModule.useContext(TabsContext);
      return context.value === value ? <div>{children}</div> : null;
    },
  };
});

export const mockGetCoupons =
  api.getAdminOperationPromotionCoupons as jest.Mock;
export const mockGetCampaigns =
  api.getAdminOperationPromotionCampaigns as jest.Mock;
export const mockCreateCoupon =
  api.createAdminOperationPromotionCoupon as jest.Mock;
export const mockUpdateCoupon =
  api.updateAdminOperationPromotionCoupon as jest.Mock;
export const mockGetCouponDetail =
  api.getAdminOperationPromotionCouponDetail as jest.Mock;
export const mockGetCouponCodes =
  api.getAdminOperationPromotionCouponCodes as jest.Mock;
export const mockGetCouponUsages =
  api.getAdminOperationPromotionCouponUsages as jest.Mock;
export const mockUpdateCouponStatus =
  api.updateAdminOperationPromotionCouponStatus as jest.Mock;
export const mockCreateCampaign =
  api.createAdminOperationPromotionCampaign as jest.Mock;
export const mockUpdateCampaign =
  api.updateAdminOperationPromotionCampaign as jest.Mock;
export const mockGetCampaignDetail =
  api.getAdminOperationPromotionCampaignDetail as jest.Mock;
export const mockGetCampaignRedemptions =
  api.getAdminOperationPromotionCampaignRedemptions as jest.Mock;
export const mockUpdateCampaignStatus =
  api.updateAdminOperationPromotionCampaignStatus as jest.Mock;
export const mockGetReferralCampaigns =
  api.getAdminOperationPromotionReferralCampaigns as jest.Mock;
export const mockCreateReferralCampaign =
  api.createAdminOperationPromotionReferralCampaign as jest.Mock;
export const mockGetReferralCampaignDetail =
  api.getAdminOperationPromotionReferralCampaignDetail as jest.Mock;
export const mockUpdateReferralCampaign =
  api.updateAdminOperationPromotionReferralCampaign as jest.Mock;
export const mockUpdateReferralCampaignStatus =
  api.updateAdminOperationPromotionReferralCampaignStatus as jest.Mock;
export const mockGetReferralCampaignRelations =
  api.getAdminOperationPromotionReferralCampaignRelations as jest.Mock;
export const mockGetReferralCampaignInvitations =
  api.getAdminOperationPromotionReferralCampaignInvitations as jest.Mock;
export const mockGetPackageCampaignProductOptions =
  api.getAdminBillingCampaignProductOptions as jest.Mock;
export const mockGetPackageCampaigns =
  api.getAdminBillingCampaigns as jest.Mock;
export const mockCreatePackageCampaign =
  api.createAdminBillingCampaign as jest.Mock;
export const mockGetPackageCampaignDetail =
  api.getAdminBillingCampaignDetail as jest.Mock;
export const mockUpdatePackageCampaign =
  api.updateAdminBillingCampaign as jest.Mock;
export const mockUpdatePackageCampaignStatus =
  api.updateAdminBillingCampaignStatus as jest.Mock;
export const mockPublishPackageCampaignProviderDiscounts =
  api.publishAdminBillingCampaign as jest.Mock;
export const mockRetryPackageCampaignProviderDiscounts =
  api.retryPublishAdminBillingCampaign as jest.Mock;
export const mockRetirePackageCampaignProviderDiscounts =
  api.retireAdminBillingCampaign as jest.Mock;

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
  mockCreateCampaign.mockReset();
  mockUpdateCampaign.mockReset();
  mockGetCampaignDetail.mockReset();
  mockGetCampaignRedemptions.mockReset();
  mockUpdateCampaignStatus.mockReset();
  mockGetReferralCampaigns.mockReset();
  mockCreateReferralCampaign.mockReset();
  mockGetReferralCampaignDetail.mockReset();
  mockUpdateReferralCampaign.mockReset();
  mockUpdateReferralCampaignStatus.mockReset();
  mockGetReferralCampaignRelations.mockReset();
  mockGetReferralCampaignInvitations.mockReset();
  mockGetPackageCampaignProductOptions.mockReset();
  mockGetPackageCampaigns.mockReset();
  mockCreatePackageCampaign.mockReset();
  mockGetPackageCampaignDetail.mockReset();
  mockUpdatePackageCampaign.mockReset();
  mockUpdatePackageCampaignStatus.mockReset();
  mockPublishPackageCampaignProviderDiscounts.mockReset();
  mockRetryPackageCampaignProviderDiscounts.mockReset();
  mockRetirePackageCampaignProviderDiscounts.mockReset();
  mockCreateCoupon.mockResolvedValue({ coupon_bid: 'created-coupon' });
  mockUpdateCoupon.mockResolvedValue({ coupon_bid: 'coupon-1' });
  mockCreateCampaign.mockResolvedValue({ promo_bid: 'created-campaign' });
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
        created_user_bid: 'operator-1',
        created_user_name: 'Operator',
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
        created_user_bid: 'operator-1',
        created_user_name: 'Operator',
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
  mockGetReferralCampaigns.mockResolvedValue({
    summary: {
      total: 1,
      active: 1,
      relation_count: 14,
      reward_count: 12,
      invite_code_count: 8,
      invite_event_count: 21,
    },
    items: [
      {
        campaign_bid: 'ref-campaign-1',
        campaign_code: 'domestic_creator_invite_202606',
        campaign_name: 'Domestic Creator Invite',
        campaign_status: 7802,
        computed_status: 'active',
        enabled: true,
        feature_flag_key: 'referral.invite.enabled',
        starts_at: '2026-06-01T00:00:00Z',
        ends_at: '2026-08-01T00:00:00Z',
        invite_route_template: '/invite/{invite_code}',
        inviter_eligibility: {},
        invitee_eligibility: {},
        invitee_benefit_policy: 'existing_trial_only',
        rules_copy_i18n_key: 'module.referral.rules.default',
        reward_rule_bid: 'reward-rule-1',
        rule_code: 'domestic_creator_invite_202606_invited_registration',
        rule_status: 7812,
        reward_product_code: 'creator-plan-monthly',
        reward_cycle_count: 1,
        reward_credit_amount: '1000.0000000000',
        reward_credit_validity_days: 30,
        reward_cap_scope: 'per_inviter',
        reward_cap_count: 12,
        reward_timing_policy: 'immediate_extend_or_defer',
        priority: 10,
        relation_count: 14,
        reward_count: 12,
        invite_code_count: 8,
        invite_event_count: 21,
        latest_invite_event_at: '2026-06-12T08:00:00Z',
        created_at: '2026-06-01T00:00:00Z',
        updated_at: '2026-06-11T09:00:00Z',
      },
    ],
    page: 1,
    page_count: 1,
    page_size: 20,
    total: 1,
  });
  mockCreateReferralCampaign.mockResolvedValue({
    campaign_bid: 'ref-campaign-created',
  });
  mockGetReferralCampaignDetail.mockResolvedValue({
    campaign: {
      campaign_bid: 'ref-campaign-1',
      campaign_code: 'domestic_creator_invite_202606',
      campaign_name: 'Domestic Creator Invite',
      campaign_status: 7802,
      computed_status: 'active',
      enabled: true,
      feature_flag_key: 'referral.invite.enabled',
      starts_at: '2026-06-01T00:00:00Z',
      ends_at: '2026-08-01T00:00:00Z',
      invite_route_template: '/invite/{invite_code}',
      inviter_eligibility: { country: 'CN' },
      invitee_eligibility: {},
      invitee_benefit_policy: 'existing_trial_only',
      rules_copy_i18n_key: 'module.referral.rules.default',
      reward_rule_bid: 'reward-rule-1',
      rule_code: 'domestic_creator_invite_202606_invited_registration',
      rule_status: 7812,
      reward_product_code: 'creator-plan-monthly',
      reward_cycle_count: 1,
      reward_credit_amount: '1000.0000000000',
      reward_credit_validity_days: 30,
      reward_cap_scope: 'per_inviter',
      reward_cap_count: 12,
      reward_timing_policy: 'immediate_extend_or_defer',
      priority: 10,
      relation_count: 14,
      reward_count: 12,
      invite_code_count: 8,
      invite_event_count: 21,
      latest_invite_event_at: '2026-06-12T08:00:00Z',
      created_at: '2026-06-01T00:00:00Z',
      updated_at: '2026-06-11T09:00:00Z',
    },
  });
  mockGetReferralCampaignRelations.mockResolvedValue({
    items: [],
    page_index: 1,
    page_size: 20,
    total: 0,
    page_count: 0,
  });
  mockGetReferralCampaignInvitations.mockResolvedValue({
    items: [
      {
        invite_code_bid: 'invite-code-1',
        campaign_bid: 'ref-campaign-1',
        invite_code: 'ABC12345',
        inviter_user_bid: 'inviter-1',
        inviter: { identifier: '13800000000' },
        status: 7821,
        generated_at: '2026-06-12T07:00:00Z',
        event_counts: {},
        link_clicked_count: 3,
        registration_page_viewed_count: 2,
        code_entered_count: 1,
        registration_submitted_count: 1,
        total_event_count: 7,
        successful_relation_count: 1,
        latest_event_at: '2026-06-12T08:00:00Z',
      },
    ],
    page_index: 1,
    page_size: 20,
    total: 1,
    page_count: 1,
  });
  mockUpdateReferralCampaign.mockResolvedValue({
    campaign_bid: 'ref-campaign-1',
  });
  mockUpdateReferralCampaignStatus.mockResolvedValue({
    campaign_bid: 'ref-campaign-1',
    enabled: false,
  });
  mockGetPackageCampaignProductOptions.mockResolvedValue({
    plans: [
      {
        product_bid: 'plan-trial',
        product_code: 'creator-plan-trial',
        product_type: 'plan',
        display_name: 'module.billing.catalog.plans.trial.title',
        description: 'module.billing.catalog.plans.trial.description',
        currency: 'CNY',
        price_amount: 0,
        credit_amount: 0,
        billing_interval: 'day',
        billing_interval_count: 7,
        campaign_discount_type: null,
        campaign_discount_amount: 0,
        campaign_discount_percent: 0,
        campaign_price_amount: 0,
        campaign_bonus_credit_amount: 0,
      },
      {
        product_bid: 'plan-1',
        product_code: 'creator-plan-monthly',
        product_type: 'plan',
        display_name: 'module.billing.catalog.plans.creatorMonthly.title',
        description: 'module.billing.catalog.plans.creatorMonthly.description',
        currency: 'CNY',
        price_amount: 9900,
        credit_amount: 100,
        billing_interval: 'month',
        billing_interval_count: 1,
        campaign_discount_type: null,
        campaign_discount_amount: 0,
        campaign_discount_percent: 0,
        campaign_price_amount: 0,
        campaign_bonus_credit_amount: 0,
      },
    ],
    topups: [
      {
        product_bid: 'topup-1',
        product_code: 'creator-topup-basic',
        product_type: 'topup',
        display_name: 'module.billing.catalog.topups.default.title',
        description: 'module.billing.catalog.topups.default.description',
        currency: 'CNY',
        price_amount: 1990,
        credit_amount: 30,
        billing_interval: 'none',
        billing_interval_count: 0,
        campaign_discount_type: null,
        campaign_discount_amount: 0,
        campaign_discount_percent: 0,
        campaign_price_amount: 0,
        campaign_bonus_credit_amount: 0,
      },
    ],
  });
  mockGetPackageCampaigns.mockResolvedValue({
    items: [
      {
        campaign_bid: 'campaign-1',
        name: 'Spring Package Promo',
        note: 'Plan-only promotion',
        benefit_type: 'discount',
        discount_type: 'percent',
        discount_amount: 0,
        discount_percent: 20,
        bonus_credit_amount: 0,
        product_count: 1,
        product_types: ['plan'],
        product_names: ['module.billing.catalog.plans.creatorMonthly.title'],
        has_custom_product_rules: false,
        computed_status: 'active',
        hit_order_count: 2,
        start_at: '2026-04-24T10:00:00Z',
        end_at: '2026-05-24T10:00:00Z',
        enabled: true,
        created_at: '2026-04-24T10:00:00Z',
        updated_at: '2026-04-24T11:00:00Z',
      },
    ],
    page: 1,
    page_count: 1,
    page_size: 20,
    total: 1,
  });
  mockCreatePackageCampaign.mockResolvedValue({
    campaign: { campaign_bid: 'campaign-created' },
    products: [],
    created_user_bid: 'operator-1',
    updated_user_bid: 'operator-1',
  });
  mockGetPackageCampaignDetail.mockResolvedValue({
    campaign: {
      campaign_bid: 'campaign-1',
      name: 'Spring Package Promo',
      note: 'Plan-only promotion',
      benefit_type: 'discount',
      discount_type: 'percent',
      discount_amount: 0,
      discount_percent: 20,
      bonus_credit_amount: 0,
      product_count: 1,
      product_types: ['plan'],
      product_names: ['module.billing.catalog.plans.creatorMonthly.title'],
      has_custom_product_rules: false,
      computed_status: 'active',
      hit_order_count: 2,
      start_at: '2026-04-24T10:00:00Z',
      end_at: '2026-05-24T10:00:00Z',
      enabled: true,
      created_at: '2026-04-24T10:00:00Z',
      updated_at: '2026-04-24T11:00:00Z',
    },
    products: [
      {
        product_bid: 'plan-1',
        product_code: 'creator-plan-monthly',
        product_type: 'plan',
        display_name: 'module.billing.catalog.plans.creatorMonthly.title',
        description: 'module.billing.catalog.plans.creatorMonthly.description',
        currency: 'CNY',
        price_amount: 9900,
        credit_amount: 100,
        billing_interval: 'month',
        billing_interval_count: 1,
        campaign_discount_type: 'percent',
        campaign_discount_amount: 1980,
        campaign_discount_percent: 20,
        campaign_price_amount: 7920,
        campaign_bonus_credit_amount: 0,
      },
    ],
    created_user_bid: 'operator-1',
    updated_user_bid: 'operator-1',
  });
  mockUpdatePackageCampaign.mockResolvedValue({
    campaign: { campaign_bid: 'campaign-1' },
    products: [],
    created_user_bid: 'operator-1',
    updated_user_bid: 'operator-1',
  });
  mockUpdatePackageCampaignStatus.mockResolvedValue({
    campaign: { campaign_bid: 'campaign-1', enabled: false },
    products: [],
    created_user_bid: 'operator-1',
    updated_user_bid: 'operator-1',
  });
  mockPublishPackageCampaignProviderDiscounts.mockResolvedValue({ items: [] });
  mockRetryPackageCampaignProviderDiscounts.mockResolvedValue({ items: [] });
  mockRetirePackageCampaignProviderDiscounts.mockResolvedValue({ items: [] });
});
