import React from 'react';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type {
  AdminBillingCampaignDetail,
  AdminBillingCampaignItem,
  AdminBillingCampaignProductOption,
  AdminPromotionCampaignItem,
  AdminPromotionCampaignRedemptionItem,
  AdminPromotionCouponCodeItem,
  AdminPromotionCouponItem,
  AdminPromotionCouponUsageItem,
  AdminReferralCampaignDetail,
  AdminReferralCampaignItem,
} from '@/app/admin/operations/operation-promotion-types';
import { Badge } from '@/components/ui/Badge';
import { Label } from '@/components/ui/Label';
import { resolveBillingProductTitle } from '@/lib/billing';
import { cn } from '@/lib/utils';
import type { BillingPlan, BillingTopupProduct } from '@/types/billing';

export type PromotionTab =
  | 'coupons'
  | 'campaigns'
  | 'packageCampaigns'
  | 'referralCampaigns';

export type CouponFilters = {
  keyword: string;
  name: string;
  course_query: string;
  usage_type: string;
  ops_state: string;
  discount_type: string;
  status: string;
  start_time: string;
  end_time: string;
};

export type CampaignFilters = {
  keyword: string;
  course_query: string;
  apply_type: string;
  channel: string;
  discount_type: string;
  status: string;
  start_time: string;
  end_time: string;
};

export type PackageCampaignFilters = {
  keyword: string;
  product_type: string;
  benefit_type: string;
  status: string;
  start_time: string;
  end_time: string;
};

export type ReferralCampaignFilters = {
  keyword: string;
  status: string;
  start_time: string;
  end_time: string;
};

export type CouponFormState = {
  name: string;
  code: string;
  usage_type: string;
  discount_type: string;
  value: string;
  total_count: string;
  scope_type: string;
  shifu_bid: string;
  start_at: string;
  end_at: string;
  enabled: string;
};

export type CampaignFormState = {
  name: string;
  apply_type: string;
  shifu_bid: string;
  discount_type: string;
  value: string;
  start_at: string;
  end_at: string;
  description: string;
  channel: string;
  enabled: string;
};

export type PackageCampaignFormState = {
  name: string;
  note: string;
  product_type: string;
  product_bids: string[];
  benefit_type: string;
  discount_type: string;
  product_rules: Record<string, PackageCampaignProductRuleFormState>;
  start_at: string;
  end_at: string;
};

export type ReferralCampaignFormState = {
  campaign_code: string;
  campaign_name: string;
  enabled: string;
  starts_at: string;
  ends_at: string;
  reward_product_code: string;
  reward_cycle_count: string;
  reward_credit_amount: string;
  reward_credit_validity_days: string;
  reward_cap_scope: string;
  reward_cap_count: string;
  feature_flag_key: string;
  invite_route_template: string;
  inviter_eligibility_json: string;
  invitee_eligibility_json: string;
  invitee_benefit_policy: string;
  rules_copy_i18n_key: string;
  rule_code: string;
  priority: string;
};

export type PackageCampaignProductRuleFormState = {
  discount_type: string;
  campaign_price: string;
  discount_percent: string;
  bonus_credit_amount: string;
};

export type ErrorState = { message: string } | null;
export type PromotionStatusChangeTarget =
  | {
      entityType: 'coupon';
      enabling: boolean;
      item: AdminPromotionCouponItem;
    }
  | {
      entityType: 'campaign';
      enabling: boolean;
      item: AdminPromotionCampaignItem;
    }
  | {
      entityType: 'packageCampaign';
      enabling: boolean;
      item: AdminBillingCampaignItem;
    }
  | {
      entityType: 'referralCampaign';
      enabling: boolean;
      item: AdminReferralCampaignItem;
    };

export const PAGE_SIZE = 20;
export const EMPTY_VALUE = '--';
export const ALL_OPTION_VALUE = '__all__';
export const PROMOTION_EXPIRING_SOON_DAYS = 7;
export const COUPON_OPS_STATE_OPTIONS = [
  {
    value: 'expiring_soon',
    labelKey: 'opsState.expiringSoon',
  },
  {
    value: 'used_up',
    labelKey: 'opsState.usedUp',
  },
] as const;
export const COLUMN_MIN_WIDTH = 90;
export const COLUMN_MAX_WIDTH = 420;
export const COUPON_COLUMN_WIDTH_STORAGE_KEY =
  'adminPromotionCouponsColumnWidths';
export const CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY =
  'adminPromotionCampaignsColumnWidths';
export const PACKAGE_CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY =
  'adminPromotionPackageCampaignsColumnWidths';
export const REFERRAL_CAMPAIGN_COLUMN_WIDTH_STORAGE_KEY =
  'adminPromotionReferralCampaignsColumnWidths';
export const COUPON_DEFAULT_COLUMN_WIDTHS = {
  name: 200,
  status: 110,
  usageType: 120,
  discountRule: 120,
  code: 180,
  scope: 120,
  course: 240,
  activeTime: 260,
  usageProgress: 110,
  codesEntry: 110,
  couponBid: 220,
  creator: 160,
  updatedAt: 170,
  createdAt: 170,
  action: 120,
} as const;
export const CAMPAIGN_DEFAULT_COLUMN_WIDTHS = {
  name: 200,
  status: 110,
  applyType: 120,
  channel: 180,
  course: 240,
  discountRule: 120,
  campaignTime: 280,
  appliedOrderCount: 130,
  promoBid: 220,
  creator: 160,
  updatedAt: 170,
  createdAt: 170,
  action: 120,
} as const;
export const PACKAGE_CAMPAIGN_DEFAULT_COLUMN_WIDTHS = {
  name: 200,
  status: 110,
  products: 260,
  rule: 160,
  campaignTime: 280,
  benefitType: 120,
  productType: 120,
  hitOrderCount: 110,
  updatedAt: 170,
  action: 120,
} as const;
export const REFERRAL_CAMPAIGN_DEFAULT_COLUMN_WIDTHS = {
  name: 200,
  status: 110,
  code: 190,
  rewardProduct: 220,
  rewardCredits: 130,
  rewardValidity: 120,
  rewardCap: 140,
  campaignTime: 280,
  relationCount: 110,
  rewardCount: 110,
  updatedAt: 170,
  action: 120,
} as const;
export const BILLING_TRIAL_PLAN_PRODUCT_CODE = 'creator-plan-trial';
export const PROMOTION_CODE_DIALOG_COLUMN_COUNT = 4;
export const PACKAGE_CAMPAIGN_PRODUCT_DIALOG_COLUMN_COUNT = 5;
export const PROMOTION_REDEMPTION_DIALOG_COLUMN_COUNT = 4;
export const PROMOTION_USAGE_DIALOG_COLUMN_COUNT = {
  default: 4,
  withCourse: 5,
} as const;
export const SINGLE_SELECT_ITEM_CLASS =
  'pl-3 data-[state=checked]:bg-muted data-[state=checked]:text-foreground [&>span:first-child]:hidden';
export const TABLE_HEAD_CLASS = ADMIN_TABLE_HEADER_CELL_CENTER_CLASS;
export const TABLE_ACTION_HEAD_CLASS =
  getAdminStickyRightHeaderClass('text-center');
export const TABLE_CELL_CLASS =
  'border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center';
export const TABLE_LAST_CELL_CLASS =
  'whitespace-nowrap overflow-hidden text-ellipsis text-center';
export const TABLE_ACTION_CELL_CLASS = getAdminStickyRightCellClass(
  'whitespace-nowrap text-center',
);
export type CouponColumnKey = keyof typeof COUPON_DEFAULT_COLUMN_WIDTHS;
export type CampaignColumnKey = keyof typeof CAMPAIGN_DEFAULT_COLUMN_WIDTHS;
export type PackageCampaignColumnKey =
  keyof typeof PACKAGE_CAMPAIGN_DEFAULT_COLUMN_WIDTHS;
export type ReferralCampaignColumnKey =
  keyof typeof REFERRAL_CAMPAIGN_DEFAULT_COLUMN_WIDTHS;

export const createDefaultCouponFilters = (): CouponFilters => ({
  keyword: '',
  name: '',
  course_query: '',
  usage_type: '',
  ops_state: '',
  discount_type: '',
  status: '',
  start_time: '',
  end_time: '',
});

export const createDefaultCampaignFilters = (): CampaignFilters => ({
  keyword: '',
  course_query: '',
  apply_type: '',
  channel: '',
  discount_type: '',
  status: '',
  start_time: '',
  end_time: '',
});

export const createDefaultPackageCampaignFilters =
  (): PackageCampaignFilters => ({
    keyword: '',
    product_type: '',
    benefit_type: '',
    status: '',
    start_time: '',
    end_time: '',
  });

export const createDefaultReferralCampaignFilters =
  (): ReferralCampaignFilters => ({
    keyword: '',
    status: '',
    start_time: '',
    end_time: '',
  });

export const createDefaultCouponForm = (): CouponFormState => ({
  name: '',
  code: '',
  usage_type: '',
  discount_type: '',
  value: '',
  total_count: '',
  scope_type: 'single_course',
  shifu_bid: '',
  start_at: '',
  end_at: '',
  enabled: 'true',
});

export const resolvePromotionEnabledFormValue = (item: {
  computed_status?: string;
  enabled?: boolean;
}) => {
  if (typeof item.enabled === 'boolean') {
    return String(item.enabled);
  }
  return item.computed_status === 'inactive' ? 'false' : 'true';
};

export function normalizePromotionFormDateTimeValue(value?: string) {
  const formatted = formatAdminUtcDateTime(value || '');
  return formatted || value || '';
}

export const createCouponFormFromItem = (
  item: AdminPromotionCouponItem,
): CouponFormState => ({
  name: item.name || '',
  code: item.code || '',
  usage_type: String(item.usage_type || ''),
  discount_type: String(item.discount_type || ''),
  value: item.value || '',
  total_count: String(item.total_count || ''),
  scope_type: item.scope_type || 'single_course',
  shifu_bid: item.shifu_bid || '',
  start_at: normalizePromotionFormDateTimeValue(item.start_at),
  end_at: normalizePromotionFormDateTimeValue(item.end_at),
  enabled: resolvePromotionEnabledFormValue(item),
});

export const createDefaultCampaignForm = (): CampaignFormState => ({
  name: '',
  apply_type: '',
  shifu_bid: '',
  discount_type: '',
  value: '',
  start_at: '',
  end_at: '',
  description: '',
  channel: '',
  enabled: 'true',
});

export const createDefaultPackageCampaignForm =
  (): PackageCampaignFormState => ({
    name: '',
    note: '',
    product_type: '',
    product_bids: [],
    benefit_type: '',
    discount_type: '',
    product_rules: {},
    start_at: '',
    end_at: '',
  });

export const createDefaultReferralCampaignForm =
  (): ReferralCampaignFormState => ({
    campaign_code: '',
    campaign_name: '',
    enabled: 'true',
    starts_at: '',
    ends_at: '',
    reward_product_code: '',
    reward_cycle_count: '1',
    reward_credit_amount: '1000',
    reward_credit_validity_days: '30',
    reward_cap_scope: 'per_inviter',
    reward_cap_count: '12',
    feature_flag_key: '',
    invite_route_template: '/invite/{invite_code}',
    inviter_eligibility_json: '{}',
    invitee_eligibility_json: '{}',
    invitee_benefit_policy: 'existing_trial_only',
    rules_copy_i18n_key: '',
    rule_code: '',
    priority: '0',
  });

export const formatCampaignPriceInput = (
  amountInMinor: number,
  currency: string,
) => {
  const safeAmount = Number(amountInMinor || 0);
  const resolvedCurrency = currency || 'CNY';
  const fractionDigits =
    new Intl.NumberFormat('zh-CN', {
      style: 'currency',
      currency: resolvedCurrency,
    }).resolvedOptions().maximumFractionDigits ?? 2;
  const majorAmount = safeAmount / 10 ** fractionDigits;
  return Number.isInteger(majorAmount)
    ? String(majorAmount)
    : majorAmount.toFixed(fractionDigits).replace(/\.?0+$/, '');
};

export const parseCampaignPriceInputToMinor = (
  value: string,
  currency: string,
) => {
  const normalizedValue = value.trim();
  if (!normalizedValue) {
    return null;
  }
  const numericValue = Number(normalizedValue);
  if (!Number.isFinite(numericValue) || numericValue < 0) {
    return null;
  }
  const resolvedCurrency = currency || 'CNY';
  const fractionDigits =
    new Intl.NumberFormat('zh-CN', {
      style: 'currency',
      currency: resolvedCurrency,
    }).resolvedOptions().maximumFractionDigits ?? 2;
  return Math.round(numericValue * 10 ** fractionDigits);
};

export const parsePositiveCampaignNumberInput = (value: string) => {
  const normalizedValue = value.trim();
  if (!normalizedValue) {
    return null;
  }
  const numericValue = Number(normalizedValue);
  return Number.isFinite(numericValue) && numericValue > 0
    ? numericValue
    : null;
};

export const resolveCampaignPriceCurrencySymbol = (currency: string) => {
  try {
    const formatter = new Intl.NumberFormat('zh-CN', {
      style: 'currency',
      currency: currency || 'CNY',
    });
    const currencyPart = formatter
      .formatToParts(0)
      .find(part => part.type === 'currency');
    return currencyPart?.value || currency || 'CNY';
  } catch {
    return currency || 'CNY';
  }
};

export const createDefaultPackageCampaignProductRule = (
  discountType = 'fixed',
): PackageCampaignProductRuleFormState => ({
  discount_type: discountType,
  campaign_price: '',
  discount_percent: '',
  bonus_credit_amount: '',
});

export const createPackageCampaignFormFromDetail = (
  detail: AdminBillingCampaignDetail,
): PackageCampaignFormState => {
  const primaryProduct = detail.products[0];
  const productRules = Object.fromEntries(
    detail.products.map(product => [
      product.product_bid,
      {
        discount_type: product.campaign_discount_type || 'fixed',
        campaign_price:
          product.campaign_price_amount > 0
            ? formatCampaignPriceInput(
                product.campaign_price_amount,
                product.currency,
              )
            : '',
        discount_percent: product.campaign_discount_percent
          ? String(product.campaign_discount_percent)
          : '',
        bonus_credit_amount: product.campaign_bonus_credit_amount
          ? String(product.campaign_bonus_credit_amount)
          : '',
      } satisfies PackageCampaignProductRuleFormState,
    ]),
  );
  return {
    name: detail.campaign.name || '',
    note: detail.campaign.note || '',
    product_type: primaryProduct?.product_type || '',
    product_bids: detail.products.map(item => item.product_bid),
    benefit_type: detail.campaign.benefit_type || '',
    discount_type:
      detail.campaign.benefit_type === 'discount'
        ? detail.products[0]?.campaign_discount_type || 'fixed'
        : '',
    product_rules: productRules,
    start_at: normalizePromotionFormDateTimeValue(detail.campaign.start_at),
    end_at: normalizePromotionFormDateTimeValue(detail.campaign.end_at),
  };
};

export const stringifyReferralCampaignJson = (value: unknown) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return '{}';
  }
  return JSON.stringify(value, null, 2);
};

export const createReferralCampaignFormFromDetail = (
  detail: AdminReferralCampaignDetail,
): ReferralCampaignFormState => {
  const campaign = detail.campaign;
  return {
    campaign_code: campaign.campaign_code || '',
    campaign_name: campaign.campaign_name || '',
    enabled: resolvePromotionEnabledFormValue(campaign),
    starts_at: normalizePromotionFormDateTimeValue(campaign.starts_at),
    ends_at: normalizePromotionFormDateTimeValue(campaign.ends_at),
    reward_product_code: campaign.reward_product_code || '',
    reward_cycle_count: String(campaign.reward_cycle_count || ''),
    reward_credit_amount: campaign.reward_credit_amount || '',
    reward_credit_validity_days: String(
      campaign.reward_credit_validity_days || '',
    ),
    reward_cap_scope: campaign.reward_cap_scope || 'none',
    reward_cap_count:
      campaign.reward_cap_count === null ||
      typeof campaign.reward_cap_count === 'undefined'
        ? ''
        : String(campaign.reward_cap_count),
    feature_flag_key: campaign.feature_flag_key || '',
    invite_route_template: campaign.invite_route_template || '',
    inviter_eligibility_json: stringifyReferralCampaignJson(
      campaign.inviter_eligibility,
    ),
    invitee_eligibility_json: stringifyReferralCampaignJson(
      campaign.invitee_eligibility,
    ),
    invitee_benefit_policy: campaign.invitee_benefit_policy || '',
    rules_copy_i18n_key: campaign.rules_copy_i18n_key || '',
    rule_code: campaign.rule_code || '',
    priority: String(campaign.priority || 0),
  };
};

export const parseReferralCampaignJsonObjectInput = (value: string) => {
  const normalized = value.trim();
  if (!normalized) {
    return {};
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(normalized) as unknown;
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return null;
  }
  return parsed as Record<string, unknown>;
};

export const buildReferralCampaignPayload = (
  form: ReferralCampaignFormState,
  {
    includeCampaignCode,
  }: {
    includeCampaignCode: boolean;
  },
) => {
  const inviterEligibility = parseReferralCampaignJsonObjectInput(
    form.inviter_eligibility_json,
  );
  const inviteeEligibility = parseReferralCampaignJsonObjectInput(
    form.invitee_eligibility_json,
  );
  if (inviterEligibility === null || inviteeEligibility === null) {
    return null;
  }
  return {
    ...(includeCampaignCode
      ? { campaign_code: form.campaign_code.trim() }
      : {}),
    campaign_name: form.campaign_name.trim(),
    enabled: form.enabled === 'true',
    starts_at: form.starts_at,
    ends_at: form.ends_at,
    reward_product_code: form.reward_product_code.trim(),
    reward_cycle_count: Number(form.reward_cycle_count.trim()),
    reward_credit_amount: form.reward_credit_amount.trim(),
    reward_credit_validity_days: Number(
      form.reward_credit_validity_days.trim(),
    ),
    reward_cap_scope: form.reward_cap_scope,
    reward_cap_count:
      form.reward_cap_scope === 'none'
        ? null
        : Number(form.reward_cap_count.trim()),
    feature_flag_key: form.feature_flag_key.trim(),
    invite_route_template: form.invite_route_template.trim(),
    inviter_eligibility: inviterEligibility,
    invitee_eligibility: inviteeEligibility,
    invitee_benefit_policy: form.invitee_benefit_policy.trim(),
    rules_copy_i18n_key: form.rules_copy_i18n_key.trim(),
    rule_code: form.rule_code.trim(),
    priority: Number(form.priority.trim() || 0),
  };
};

export const buildPackageCampaignProductsPayload = (
  form: PackageCampaignFormState,
  productOptions: AdminBillingCampaignProductOption[],
) => {
  const optionByBid = new Map(
    productOptions.map(option => [option.product_bid, option]),
  );
  return form.product_bids
    .map(productBid => {
      const option = optionByBid.get(productBid);
      const productRule =
        form.product_rules[productBid] ||
        createDefaultPackageCampaignProductRule();
      if (!option) {
        return null;
      }
      const discountPercent = parsePositiveCampaignNumberInput(
        productRule.discount_percent,
      );
      const bonusCreditAmount = parsePositiveCampaignNumberInput(
        productRule.bonus_credit_amount,
      );
      if (form.benefit_type === 'discount') {
        const resolvedDiscountType = form.discount_type || 'fixed';
        return {
          product_bid: productBid,
          discount_type: resolvedDiscountType,
          campaign_price_amount:
            resolvedDiscountType === 'fixed'
              ? parseCampaignPriceInputToMinor(
                  productRule.campaign_price,
                  option.currency,
                ) || 0
              : 0,
          discount_percent:
            resolvedDiscountType === 'percent'
              ? String(discountPercent || '')
              : '',
          bonus_credit_amount: '',
        };
      }
      return {
        product_bid: productBid,
        discount_type: '',
        campaign_price_amount: 0,
        discount_percent: '',
        bonus_credit_amount: String(bonusCreditAmount || ''),
      };
    })
    .filter((item): item is NonNullable<typeof item> => item !== null);
};

export const createCampaignFormFromItem = (
  item: AdminPromotionCampaignItem,
  description: string,
): CampaignFormState => ({
  name: item.name || '',
  apply_type: String(item.apply_type || ''),
  shifu_bid: item.shifu_bid || '',
  discount_type: String(item.discount_type || ''),
  value: item.value || '',
  start_at: normalizePromotionFormDateTimeValue(item.start_at),
  end_at: normalizePromotionFormDateTimeValue(item.end_at),
  description: description || '',
  channel: item.channel || '',
  enabled: resolvePromotionEnabledFormValue(item),
});

export const SectionCard = ({
  title,
  action,
  children,
}: React.PropsWithChildren<{ title: string; action?: React.ReactNode }>) => (
  <div className='rounded-xl border border-border bg-white p-5 shadow-sm'>
    {title || action ? (
      <div
        className={cn(
          'mb-4 flex items-center gap-4',
          title ? 'justify-between' : 'justify-start',
        )}
      >
        {title ? (
          <h2 className='text-base font-semibold text-foreground'>{title}</h2>
        ) : null}
        {action}
      </div>
    ) : null}
    {children}
  </div>
);

export const renderTimeRange = (startAt?: string, endAt?: string) => {
  const start = formatAdminUtcDateTime(startAt || '');
  const end = formatAdminUtcDateTime(endAt || '');
  if (!start && !end) return EMPTY_VALUE;
  return `${start || EMPTY_VALUE} ~ ${end || EMPTY_VALUE}`;
};

export const downloadExcelCompatibleCodesFile = (
  fileName: string,
  headerLabel: string,
  codes: string[],
) => {
  const tableRows = codes
    .map(
      code =>
        `<tr><td style="mso-number-format:'\\@';">${String(code)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')}</td></tr>`,
    )
    .join('');
  const html = `<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8" />
  </head>
  <body>
    <table>
      <thead>
        <tr><th>${headerLabel
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')}</th></tr>
      </thead>
      <tbody>${tableRows}</tbody>
    </table>
  </body>
</html>`;
  const blob = new Blob(['\ufeff', html], {
    type: 'application/vnd.ms-excel;charset=utf-8;',
  });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.URL.revokeObjectURL(url);
};

export const renderRuleLabel = (
  discountTypeKey: string,
  value: string,
  currencySymbol = '',
) => {
  if (discountTypeKey.endsWith('percent')) {
    return `${value}%`;
  }
  return `- ${currencySymbol}${value}`;
};

export const toPromotionRelativeKey = (key?: string) => {
  if (!key) {
    return '';
  }
  return key.startsWith('module.operationsPromotion.')
    ? key.replace('module.operationsPromotion.', '')
    : key;
};

export const resolveCouponUsageTypeLabel = (
  tPromotion: (key: string) => string,
  usageType: number | string,
  usageTypeKey?: string,
) => {
  if (usageTypeKey) {
    const translated = tPromotion(toPromotionRelativeKey(usageTypeKey));
    if (translated && translated !== usageTypeKey) {
      return translated;
    }
  }
  if (Number(usageType) === 801) {
    return tPromotion('usageType.generic');
  }
  if (Number(usageType) === 802) {
    return tPromotion('usageType.singleUse');
  }
  return EMPTY_VALUE;
};

export const resolveCouponScopeLabel = (
  tPromotion: (key: string) => string,
  scopeType?: string,
) => {
  if (scopeType === 'all_courses') {
    return tPromotion('scope.allCourses');
  }
  if (scopeType === 'single_course') {
    return tPromotion('scope.singleCourse');
  }
  return EMPTY_VALUE;
};

export const PROMOTION_STATUS_FALLBACK_KEYS: Record<string, string> = {
  active: 'status.active',
  ended: 'status.ended',
  expired: 'status.expired',
  inactive: 'status.inactive',
  not_started: 'status.notStarted',
  upcoming: 'status.notStarted',
};

export const resolvePromotionStatusLabel = (
  tPromotion: (key: string) => string,
  statusKey?: string,
  status?: string,
) => {
  const fallbackKey = status ? PROMOTION_STATUS_FALLBACK_KEYS[status] : '';
  const translationKey = statusKey
    ? toPromotionRelativeKey(statusKey)
    : fallbackKey;
  if (!translationKey) {
    return EMPTY_VALUE;
  }
  const translated = tPromotion(translationKey);
  return translated && translated !== translationKey ? translated : EMPTY_VALUE;
};

export const resolvePromotionStatusBadgeClassName = (status?: string) => {
  switch (status) {
    case 'active':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-50';
    case 'upcoming':
    case 'not_started':
      return 'border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-50';
    case 'inactive':
      return 'border-slate-200 bg-slate-100 text-slate-700 hover:bg-slate-100';
    case 'expired':
    case 'ended':
      return 'border-orange-200 bg-orange-50 text-orange-700 hover:bg-orange-50';
    default:
      return 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-50';
  }
};

export const renderPromotionStatusBadge = ({
  tPromotion,
  statusKey,
  status,
}: {
  tPromotion: (key: string) => string;
  statusKey?: string;
  status?: string;
}) => (
  <Badge
    variant='outline'
    className={cn(
      'rounded-full px-2 py-0.5 text-xs font-medium',
      resolvePromotionStatusBadgeClassName(status),
    )}
  >
    {resolvePromotionStatusLabel(tPromotion, statusKey, status)}
  </Badge>
);

export const resolvePackageCampaignBenefitTypeLabel = (
  tPromotion: (key: string) => string,
  benefitType?: string,
) => {
  if (benefitType === 'discount') {
    return tPromotion('packageCampaign.benefitTypeDiscount');
  }
  if (benefitType === 'bonus') {
    return tPromotion('packageCampaign.benefitTypeBonus');
  }
  return EMPTY_VALUE;
};

export const resolvePackageCampaignProductTypeLabel = (
  tPromotion: (key: string) => string,
  productType?: string,
) => {
  if (productType === 'plan') {
    return tPromotion('packageCampaign.productTypePlan');
  }
  if (productType === 'topup') {
    return tPromotion('packageCampaign.productTypeTopup');
  }
  return EMPTY_VALUE;
};

export const canEnablePackageCampaignItem = (item: AdminBillingCampaignItem) =>
  item.computed_status !== 'ended';

export const shouldShowPackageCampaignStatusToggle = (
  item: AdminBillingCampaignItem,
) => item.computed_status !== 'inactive' || canEnablePackageCampaignItem(item);

export const canEnableReferralCampaignItem = (
  item: AdminReferralCampaignItem,
) => item.computed_status !== 'ended';

export const shouldShowReferralCampaignStatusToggle = (
  item: AdminReferralCampaignItem,
) => item.computed_status !== 'inactive' || canEnableReferralCampaignItem(item);

export const resolvePackageCampaignRuleLabel = (
  t: (key: string, options?: Record<string, unknown>) => string,
  item: Pick<
    AdminBillingCampaignItem,
    | 'benefit_type'
    | 'discount_type'
    | 'discount_amount'
    | 'discount_percent'
    | 'bonus_credit_amount'
    | 'has_custom_product_rules'
    | 'product_count'
  >,
) => {
  if (item.benefit_type === 'discount') {
    if (
      item.has_custom_product_rules ||
      item.discount_type === 'fixed' ||
      item.product_count > 1
    ) {
      return t('module.operationsPromotion.packageCampaign.rulePerProduct');
    }
    if (item.discount_type === 'percent') {
      return t('module.operationsPromotion.packageCampaign.rulePercent', {
        value: item.discount_percent,
      });
    }
  }
  if (item.benefit_type === 'bonus') {
    if (item.has_custom_product_rules || item.product_count > 1) {
      return t('module.operationsPromotion.packageCampaign.rulePerProduct');
    }
    return t('module.operationsPromotion.packageCampaign.ruleBonus', {
      value: item.bonus_credit_amount,
    });
  }
  return EMPTY_VALUE;
};

export const resolvePackageCampaignProductSummary = (
  tPromotion: (key: string) => string,
  item: Pick<AdminBillingCampaignItem, 'product_types' | 'product_count'>,
) => {
  if (!item.product_types.length) {
    return EMPTY_VALUE;
  }
  const labels = item.product_types
    .map(type => resolvePackageCampaignProductTypeLabel(tPromotion, type))
    .filter(label => label && label !== EMPTY_VALUE);
  if (!labels.length) {
    return EMPTY_VALUE;
  }
  return `${labels.join(' / ')} · ${item.product_count}`;
};

export const resolvePackageCampaignOptionTitle = (
  t: (key: string, options?: Record<string, unknown>) => string,
  option: AdminBillingCampaignProductOption,
) =>
  resolveBillingProductTitle(
    t,
    option as BillingPlan | BillingTopupProduct,
    option.product_code,
  );

export const isPackageCampaignTrialOption = (
  option: AdminBillingCampaignProductOption,
) =>
  option.product_type === 'plan' &&
  String(option.product_code || '').trim() === BILLING_TRIAL_PLAN_PRODUCT_CODE;

export const resolveCampaignApplyTypeLabel = (
  tPromotion: (key: string) => string,
  applyType: number | string,
) => {
  if (Number(applyType) === 2101) {
    return tPromotion('campaign.applyTypeAuto');
  }
  if (Number(applyType) === 2102) {
    return tPromotion('campaign.applyTypeEvent');
  }
  if (Number(applyType) === 2103) {
    return tPromotion('campaign.applyTypeManual');
  }
  return EMPTY_VALUE;
};

export const canEditCampaignStrategyFields = (
  item: AdminPromotionCampaignItem,
) => {
  const startAt = parseLocalDateTimeInput(item.start_at || '');
  if (!startAt) {
    return false;
  }
  return startAt.getTime() > Date.now() && !item.has_redemptions;
};

export const canEnableCouponItem = (item: AdminPromotionCouponItem) => {
  const endAt = parseDateValue(item.end_at || '');
  if (endAt && endAt.getTime() < Date.now()) {
    return false;
  }
  return Number(item.used_count || 0) < Number(item.total_count || 0);
};

export const canEnableCampaignItem = (item: AdminPromotionCampaignItem) => {
  const endAt = parseDateValue(item.end_at || '');
  return !endAt || endAt.getTime() >= Date.now();
};

export const shouldShowCouponStatusToggle = (item: AdminPromotionCouponItem) =>
  item.computed_status !== 'inactive' || canEnableCouponItem(item);

export const shouldShowCampaignStatusToggle = (
  item: AdminPromotionCampaignItem,
) => item.computed_status !== 'inactive' || canEnableCampaignItem(item);

export const renderUserLabel = (
  item:
    | AdminPromotionCouponUsageItem
    | AdminPromotionCouponCodeItem
    | AdminPromotionCampaignRedemptionItem,
) => {
  return item.user_mobile || item.user_email || item.user_bid || EMPTY_VALUE;
};

export const parseLocalDateTimeInput = (value: string) => {
  const normalized = String(value || '').trim();
  if (!normalized) {
    return null;
  }
  const parsed = new Date(
    normalized.includes(' ') ? normalized.replace(' ', 'T') : normalized,
  );
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
};

export const formatDateValue = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

export const formatTimeValue = (date: Date) => {
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${hours}:${minutes}`;
};

export const parseDateValue = (value: string) => {
  if (!value) {
    return undefined;
  }
  const parsed = new Date(
    String(value).includes(' ')
      ? String(value).replace(' ', 'T')
      : String(value),
  );
  if (Number.isNaN(parsed.getTime())) {
    return undefined;
  }
  return parsed;
};

export const resolveCouponOpsStates = (item: AdminPromotionCouponItem) =>
  Array.isArray(item.ops_states) ? item.ops_states : [];

export const couponHasOpsState = (
  item: AdminPromotionCouponItem,
  state: (typeof COUPON_OPS_STATE_OPTIONS)[number]['value'],
) => resolveCouponOpsStates(item).includes(state);

export const renderCouponAttentionBadges = (
  item: AdminPromotionCouponItem,
  tPromotion: (key: string) => string,
) => {
  if (item.computed_status !== 'active') {
    return [];
  }

  if (couponHasOpsState(item, 'used_up')) {
    return [
      <Badge
        key='used-up'
        variant='outline'
        className='rounded-full border-rose-200 bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700 hover:bg-rose-50'
      >
        {tPromotion('opsState.usedUp')}
      </Badge>,
    ];
  }

  if (couponHasOpsState(item, 'expiring_soon')) {
    return [
      <Badge
        key='expiring-soon'
        variant='outline'
        className='rounded-full border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 hover:bg-amber-50'
      >
        {tPromotion('opsState.expiringSoon')}
      </Badge>,
    ];
  }

  return [];
};

export const DEFAULT_START_TIME = '00:00';
export const DEFAULT_END_TIME = '23:59';

export const resolveDateTimeParts = (
  value: string,
  defaultTime: string,
): { date: string; time: string } => {
  const parsed = parseDateValue(value);
  if (!parsed) {
    return { date: '', time: defaultTime };
  }
  return {
    date: formatDateValue(parsed),
    time: formatTimeValue(parsed),
  };
};

export const combineDateAndTime = (dateValue: string, timeValue: string) => {
  const normalizedDate = String(dateValue || '').trim();
  if (!normalizedDate) {
    return '';
  }
  const normalizedTime = String(timeValue || '').trim() || DEFAULT_START_TIME;
  return `${normalizedDate} ${normalizedTime}:00`;
};

export const isPositiveIntegerString = (value: string) =>
  /^\d+$/.test(value.trim());

export const renderTooltipText = (text?: string, className?: string) => (
  <AdminTooltipText
    text={text}
    emptyValue={EMPTY_VALUE}
    className={className}
  />
);

export const FormField = ({
  label,
  children,
}: React.PropsWithChildren<{ label: React.ReactNode }>) => (
  <div className='space-y-2'>
    <Label className='text-sm font-medium text-foreground'>{label}</Label>
    {children}
  </div>
);

export const PackageCampaignInlineField = ({
  label,
  children,
  className,
}: React.PropsWithChildren<{
  label: string;
  className?: string;
}>) => (
  <div
    className={cn(
      'flex min-h-9 items-center gap-3 rounded-lg border border-border/80 bg-background px-3',
      className,
    )}
  >
    <span className='w-[5.5rem] shrink-0 text-sm font-medium text-foreground'>
      {label}
    </span>
    <div className='min-w-0 max-w-[13rem] flex-1'>{children}</div>
  </div>
);

export const PackageCampaignInlineValueField = ({
  label,
  value,
}: {
  label: string;
  value: string;
}) => (
  <PackageCampaignInlineField
    label={label}
    className='bg-muted/25'
  >
    <span className='block truncate text-sm text-muted-foreground'>
      {value}
    </span>
  </PackageCampaignInlineField>
);
