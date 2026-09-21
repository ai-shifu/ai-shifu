'use client';

import React from 'react';
import useSWR from 'swr';
import { Star } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useTracking } from '@/hooks/useTracking';
import {
  BillingStripeRedirectOverlay,
  type BillingStripeRedirectPhase,
} from '@/components/billing/BillingStripeRedirectOverlay';
import { TopupCard } from '@/components/billing/BillingOverviewCards';
import { BillingOverviewFootnote } from '@/components/billing/BillingOverviewFootnote';
import styles from '@/components/billing/BillingPlanComparisonTable.module.scss';
import { Skeleton } from '@/components/ui/Skeleton';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { toast } from '@/hooks/useToast';
import { useBillingOverview } from '@/hooks/useBillingData';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import {
  buildBillingSwrKey,
  formatBillingCredits,
  formatBillingPlanInterval,
  formatBillingPrice,
  getBillingProductCampaignBonusCredits,
  hasBillingProductBonusCampaign,
  hasBillingProductDiscountCampaign,
  openBillingCheckoutUrl,
  resolveBillingProductPayableAmount,
} from '@/lib/billing';
import {
  buildCreatorBillingAttemptAnalytics,
  buildCreatorBillingResultAnalytics,
  buildCreatorBillingStatusAnalytics,
  CREATOR_BILLING_ANALYTICS_EVENTS,
  trackCreatorBillingEventSafely,
  type CreatorBillingAnalyticsBaseInput,
  type CreatorBillingFailureCategory,
} from '@/lib/billingAnalytics';
import { rememberStripeBillingOrderForAnalytics } from '@/lib/stripe-storage';
import { formatBillingLearningTime } from '@/lib/billingLearningTime';
import { cn } from '@/lib/utils';
import type {
  BillingCheckoutResult,
  BillingPlan,
  BillingSubscription,
  BillingSubscriptionCheckoutAction,
  BillingTopupProduct,
} from '@/types/billing';

type BillingCatalogResponse = {
  plans: BillingPlan[];
  topups: BillingTopupProduct[];
};

type GlobalBillingProduct = BillingPlan | BillingTopupProduct;
type BillingCycle = 'monthly' | 'annual';
type PricingTab = 'plans' | 'credit_packs';
type PlanTier = 'studio' | 'growth' | 'business' | 'scale';

type ExpectedProductSpec = {
  productType: 'plan' | 'topup';
  priceAmount: number;
  billingInterval?: 'month' | 'year';
};

export const GLOBAL_BILLING_PRODUCT_CODES = {
  studioMonthly: 'creator-global-studio-monthly',
  growthMonthly: 'creator-global-growth-monthly',
  growthAnnual: 'creator-global-growth-yearly',
  businessMonthly: 'creator-global-business-monthly',
  businessAnnual: 'creator-global-business-yearly',
  scaleMonthly: 'creator-global-scale-monthly',
  scaleAnnual: 'creator-global-scale-yearly',
  credits250: 'creator-global-credits-250',
  credits3000: 'creator-global-credits-3000',
} as const;

const EXPECTED_GLOBAL_PRODUCTS: Record<string, ExpectedProductSpec> = {
  [GLOBAL_BILLING_PRODUCT_CODES.studioMonthly]: {
    productType: 'plan',
    billingInterval: 'month',
    priceAmount: 5900,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.growthMonthly]: {
    productType: 'plan',
    billingInterval: 'month',
    priceAmount: 22900,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.growthAnnual]: {
    productType: 'plan',
    billingInterval: 'year',
    priceAmount: 219900,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.businessMonthly]: {
    productType: 'plan',
    billingInterval: 'month',
    priceAmount: 41900,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.businessAnnual]: {
    productType: 'plan',
    billingInterval: 'year',
    priceAmount: 399900,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.scaleMonthly]: {
    productType: 'plan',
    billingInterval: 'month',
    priceAmount: 83900,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.scaleAnnual]: {
    productType: 'plan',
    billingInterval: 'year',
    priceAmount: 799900,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.credits250]: {
    productType: 'topup',
    priceAmount: 2900,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.credits3000]: {
    productType: 'topup',
    priceAmount: 27900,
  },
};

const PLAN_TIERS: Array<{
  tier: PlanTier;
  monthlyCode: string;
  annualCode?: string;
}> = [
  {
    tier: 'studio',
    monthlyCode: GLOBAL_BILLING_PRODUCT_CODES.studioMonthly,
  },
  {
    tier: 'growth',
    monthlyCode: GLOBAL_BILLING_PRODUCT_CODES.growthMonthly,
    annualCode: GLOBAL_BILLING_PRODUCT_CODES.growthAnnual,
  },
  {
    tier: 'business',
    monthlyCode: GLOBAL_BILLING_PRODUCT_CODES.businessMonthly,
    annualCode: GLOBAL_BILLING_PRODUCT_CODES.businessAnnual,
  },
  {
    tier: 'scale',
    monthlyCode: GLOBAL_BILLING_PRODUCT_CODES.scaleMonthly,
    annualCode: GLOBAL_BILLING_PRODUCT_CODES.scaleAnnual,
  },
];

const PLAN_FEATURE_KEYS: Record<PlanTier, string[]> = {
  studio: ['module.billing.package.features.common.allTeachingAndLearning'],
  growth: ['module.billing.package.features.common.higherConcurrency'],
  business: [
    'module.billing.package.features.pro.branding',
    'module.billing.package.features.pro.customDomain',
    'module.billing.package.features.pro.techPriority',
  ],
  scale: [
    'module.billing.package.features.premium.dedicatedSupport',
    'module.billing.package.features.premium.onboarding',
  ],
};

const CREDIT_PACK_CODES = [
  GLOBAL_BILLING_PRODUCT_CODES.credits250,
  GLOBAL_BILLING_PRODUCT_CODES.credits3000,
];

const BILLING_PASSIVE_REQUEST_CONFIG = { skipErrorToast: true } as const;
const STRIPE_PAYMENT_PROVIDER = 'stripe' as const;
const LEARNING_TIME_ESTIMATE_MARKER = '*';
const INACTIVE_SUBSCRIPTION_STATUSES = new Set([
  'canceled',
  'expired',
  'draft',
]);
function resolveGlobalCampaignLabel(
  product: GlobalBillingProduct,
  t: ReturnType<typeof useTranslation>['t'],
  locale: string,
): string | undefined {
  if (hasBillingProductDiscountCampaign(product)) {
    return t('module.billing.package.campaign.discountBadge');
  }
  if (hasBillingProductBonusCampaign(product)) {
    return t('module.billing.package.campaign.bonusBadge', {
      credits: formatBillingCredits(
        getBillingProductCampaignBonusCredits(product),
        locale,
      ),
    });
  }
  return undefined;
}

function useGlobalBillingTranslation() {
  const { t, i18n } = useTranslation();

  return { t, locale: i18n.resolvedLanguage || i18n.language || 'en-US' };
}

function normalizeCurrency(currency: unknown): string {
  return typeof currency === 'string' ? currency.toUpperCase() : '';
}

function resolvePlanTierRank(productCode: string | null | undefined): number {
  const normalized = String(productCode || '').trim();

  return PLAN_TIERS.findIndex(
    tier =>
      tier.monthlyCode === normalized ||
      (tier.annualCode ? tier.annualCode === normalized : false),
  );
}

function isBillingSubscriptionActive(
  subscription: BillingSubscription | null | undefined,
): subscription is BillingSubscription {
  return (
    !!subscription && !INACTIVE_SUBSCRIPTION_STATUSES.has(subscription.status)
  );
}

function resolveGlobalProducts(
  catalog: BillingCatalogResponse | undefined,
): Map<string, GlobalBillingProduct> | null {
  if (!catalog) {
    return null;
  }

  const products = [...(catalog.plans || []), ...(catalog.topups || [])];
  const productsByCode = new Map(
    products.map(product => [product.product_code, product]),
  );

  for (const [productCode, expected] of Object.entries(
    EXPECTED_GLOBAL_PRODUCTS,
  )) {
    const product = productsByCode.get(productCode);
    if (
      !product ||
      product.product_type !== expected.productType ||
      normalizeCurrency(product.currency) !== 'USD' ||
      Number(product.price_amount) !== expected.priceAmount ||
      !Number.isFinite(Number(product.credit_amount)) ||
      Number(product.credit_amount) <= 0
    ) {
      return null;
    }
    if (
      product.product_type === 'plan' &&
      product.billing_interval !== expected.billingInterval
    ) {
      return null;
    }
  }

  return productsByCode;
}

export function GlobalBillingPricing() {
  const { t, locale } = useGlobalBillingTranslation();
  const { trackEvent } = useTracking();
  const [pricingTab, setPricingTab] = React.useState<PricingTab>('plans');
  const [billingCycle, setBillingCycle] =
    React.useState<BillingCycle>('annual');
  const [checkoutLoadingKey, setCheckoutLoadingKey] = React.useState('');
  const [stripeRedirect, setStripeRedirect] = React.useState<{
    phase: BillingStripeRedirectPhase;
    retryUrl?: string;
  } | null>(null);
  const { data, error, isLoading } = useSWR<BillingCatalogResponse>(
    buildBillingSwrKey('billing-catalog'),
    async () =>
      (await api.getBillingCatalog(
        {},
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingCatalogResponse,
    { revalidateOnFocus: true },
  );
  const { data: overview } = useBillingOverview();
  const hasResolvedOverview = overview !== undefined;
  const globalProducts = React.useMemo(
    () => resolveGlobalProducts(data),
    [data],
  );
  const activeSubscription = isBillingSubscriptionActive(overview?.subscription)
    ? overview.subscription
    : null;

  const handlePaymentClick = React.useCallback(
    async ({
      product,
      sourceTab,
      checkoutAction,
    }: {
      product: GlobalBillingProduct;
      sourceTab: PricingTab;
      checkoutAction?: BillingSubscriptionCheckoutAction;
    }) => {
      if (product.product_type === 'plan' && !hasResolvedOverview) {
        toast({
          title: t('common.core.requestFailed'),
          variant: 'destructive',
        });
        return;
      }

      const analyticsBase: CreatorBillingAnalyticsBaseInput = {
        billingMarket: 'global',
        productType: product.product_type,
        productBid: product.product_bid,
        productCode: product.product_code,
        billingInterval:
          product.product_type === 'plan'
            ? product.billing_interval
            : 'one_time',
        priceAmount: product.price_amount,
        currency: product.currency,
        creditAmount: product.credit_amount,
        paymentProvider: STRIPE_PAYMENT_PROVIDER,
        checkoutAction:
          product.product_type === 'topup'
            ? 'topup'
            : checkoutAction || 'subscribe',
        sourceSurface: 'global_pricing',
        sourceTab,
      };
      const attemptPayload = buildCreatorBillingAttemptAnalytics(analyticsBase);
      trackCreatorBillingEventSafely(
        trackEvent,
        CREATOR_BILLING_ANALYTICS_EVENTS.attempt,
        attemptPayload,
      );

      const loadingKey = buildCheckoutLoadingKey(product);
      setCheckoutLoadingKey(loadingKey);
      setStripeRedirect({ phase: 'creating' });
      let failureCategory: CreatorBillingFailureCategory =
        'checkout_request_failed';
      let catchAnalyticsBase = analyticsBase;
      let terminalResultReported = false;
      try {
        let result: BillingCheckoutResult;
        if (product.product_type === 'plan') {
          result = (await api.checkoutBillingSubscription({
            ...(checkoutAction ? { action: checkoutAction } : {}),
            payment_provider: STRIPE_PAYMENT_PROVIDER,
            product_bid: product.product_bid,
          })) as BillingCheckoutResult;
        } else {
          result = (await api.checkoutBillingTopup({
            payment_provider: STRIPE_PAYMENT_PROVIDER,
            product_bid: product.product_bid,
          })) as BillingCheckoutResult;
        }

        const resolvedAnalyticsBase = {
          ...analyticsBase,
          paymentProvider: result.provider,
          billOrderBid: result.bill_order_bid,
        };
        catchAnalyticsBase = resolvedAnalyticsBase;

        if (result.status === 'paid') {
          trackCreatorBillingEventSafely(
            trackEvent,
            CREATOR_BILLING_ANALYTICS_EVENTS.result,
            buildCreatorBillingResultAnalytics({
              ...resolvedAnalyticsBase,
              outcome: 'success',
            }),
          );
          terminalResultReported = true;
        } else if (
          result.status === 'unsupported' ||
          result.status === 'failed'
        ) {
          trackCreatorBillingEventSafely(
            trackEvent,
            CREATOR_BILLING_ANALYTICS_EVENTS.result,
            buildCreatorBillingResultAnalytics({
              ...resolvedAnalyticsBase,
              outcome: 'failed',
              failureCategory:
                result.status === 'unsupported'
                  ? 'unsupported'
                  : 'payment_failed',
            }),
          );
          terminalResultReported = true;
        } else if (!result.redirect_url) {
          trackCreatorBillingEventSafely(
            trackEvent,
            CREATOR_BILLING_ANALYTICS_EVENTS.result,
            buildCreatorBillingResultAnalytics({
              ...resolvedAnalyticsBase,
              outcome: 'failed',
              failureCategory: 'missing_redirect',
            }),
          );
          terminalResultReported = true;
        }

        if (result.status === 'unsupported' || !result.redirect_url) {
          setStripeRedirect(null);
          toast({
            title: t('module.billing.checkout.unsupported'),
            variant: 'destructive',
          });
          return;
        }

        setStripeRedirect({
          phase: 'redirecting',
          retryUrl: result.redirect_url,
        });
        if (result.provider === 'stripe') {
          rememberStripeBillingOrderForAnalytics(result.bill_order_bid);
        }
        failureCategory = 'redirect_failed';
        trackCreatorBillingEventSafely(
          trackEvent,
          CREATOR_BILLING_ANALYTICS_EVENTS.status,
          buildCreatorBillingStatusAnalytics({
            ...resolvedAnalyticsBase,
            status: 'pending',
          }),
        );
        openBillingCheckoutUrl(result.redirect_url);
      } catch (error: any) {
        if (!terminalResultReported) {
          trackCreatorBillingEventSafely(
            trackEvent,
            CREATOR_BILLING_ANALYTICS_EVENTS.result,
            buildCreatorBillingResultAnalytics({
              ...catchAnalyticsBase,
              outcome: 'failed',
              failureCategory,
            }),
          );
        }
        setStripeRedirect(null);
        toast({
          title: error?.message || t('common.core.requestFailed'),
          variant: 'destructive',
        });
      } finally {
        setCheckoutLoadingKey('');
      }
    },
    [hasResolvedOverview, t, trackEvent],
  );

  return (
    <section
      className='w-full space-y-8'
      data-testid='global-billing-pricing'
    >
      <BillingStripeRedirectOverlay
        open={Boolean(stripeRedirect)}
        phase={stripeRedirect?.phase || 'creating'}
        retryUrl={stripeRedirect?.retryUrl}
        onRetry={() => {
          if (stripeRedirect?.retryUrl) {
            openBillingCheckoutUrl(stripeRedirect.retryUrl);
          }
        }}
      />

      <Tabs
        value={pricingTab}
        onValueChange={value => setPricingTab(value as PricingTab)}
        className='space-y-8'
      >
        <div className='flex flex-col items-center gap-4'>
          <TabsList className={styles.showcaseTabsList}>
            <TabsTrigger
              value='plans'
              className={styles.showcaseTabsTrigger}
            >
              {t('module.billing.package.intervalTabs.plans')}
            </TabsTrigger>
            <TabsTrigger
              value='credit_packs'
              className={styles.showcaseTabsTrigger}
            >
              {t('module.billing.package.intervalTabs.topup')}
            </TabsTrigger>
          </TabsList>
          {pricingTab === 'plans' ? (
            <Tabs
              value={billingCycle}
              onValueChange={value => setBillingCycle(value as BillingCycle)}
            >
              <TabsList className={styles.showcaseTabsList}>
                <TabsTrigger
                  value='monthly'
                  className={styles.showcaseTabsTrigger}
                >
                  {t('module.billing.package.intervalTabs.monthly')}
                </TabsTrigger>
                <TabsTrigger
                  value='annual'
                  className={styles.showcaseTabsTrigger}
                >
                  {t('module.billing.package.intervalTabs.yearly')}
                </TabsTrigger>
              </TabsList>
            </Tabs>
          ) : null}
        </div>

        <TabsContent
          value='plans'
          className='mt-0 space-y-6'
        >
          <CatalogState
            isLoading={isLoading}
            unavailable={Boolean(error) || (!isLoading && !globalProducts)}
          >
            {globalProducts ? (
              <div className={styles.tableWrapper}>
                <div
                  className={styles.comparisonGrid}
                  data-testid='global-plan-grid'
                >
                  {PLAN_TIERS.map(tierSpec => (
                    <PlanColumn
                      key={tierSpec.tier}
                      tierSpec={tierSpec}
                      cycle={billingCycle}
                      products={globalProducts}
                      activeSubscription={activeSubscription}
                      hasResolvedOverview={hasResolvedOverview}
                      locale={locale}
                      onViewMonthly={() => setBillingCycle('monthly')}
                      checkoutLoadingKey={checkoutLoadingKey}
                      onPaymentClick={handlePaymentClick}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </CatalogState>

          {globalProducts ? (
            <BillingOverviewFootnote
              showValidity={false}
              hasDiscountCampaign={PLAN_TIERS.some(tier => {
                const code =
                  billingCycle === 'annual' && tier.annualCode
                    ? tier.annualCode
                    : tier.monthlyCode;
                return hasBillingProductDiscountCampaign(
                  globalProducts.get(code) as BillingPlan,
                );
              })}
            />
          ) : null}
        </TabsContent>

        <TabsContent
          value='credit_packs'
          className='mt-0 space-y-6'
        >
          <CatalogState
            isLoading={isLoading}
            unavailable={Boolean(error) || (!isLoading && !globalProducts)}
          >
            {globalProducts ? (
              <div className='space-y-6'>
                <div
                  className='grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]'
                  data-testid='global-credit-pack-grid'
                >
                  {CREDIT_PACK_CODES.map(code => {
                    const product = globalProducts.get(
                      code,
                    ) as BillingTopupProduct;
                    const packName = t(
                      'module.billing.package.topup.creditLabel',
                      {
                        credits: formatBillingCredits(
                          product.credit_amount,
                          locale,
                        ),
                      },
                    );
                    return (
                      <TopupCard
                        key={code}
                        actionLabel={t(
                          'module.billing.globalPricing.actions.buyCredits',
                        )}
                        actionLoading={
                          checkoutLoadingKey ===
                          buildCheckoutLoadingKey(product)
                        }
                        creditsLabel={packName}
                        disabled={Boolean(checkoutLoadingKey)}
                        campaignLabel={resolveGlobalCampaignLabel(
                          product,
                          t,
                          locale,
                        )}
                        onAction={() =>
                          handlePaymentClick({
                            product,
                            sourceTab: 'credit_packs',
                          })
                        }
                        originalPriceLabel={
                          hasBillingProductDiscountCampaign(product)
                            ? formatBillingPrice(
                                product.price_amount,
                                product.currency,
                                locale,
                              )
                            : undefined
                        }
                        priceLabel={formatBillingPrice(
                          resolveBillingProductPayableAmount(product),
                          product.currency,
                          locale,
                        )}
                        testId={`global-credit-pack-${product.credit_amount}`}
                      />
                    );
                  })}
                </div>
                <div className='text-[length:var(--text-sm-font-size,14px)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'>
                  <ul className='list-disc space-y-2 pl-5'>
                    <li>{t('module.billing.package.topup.noteInstant')}</li>
                    <li>{t('module.billing.package.topup.noteFrozen')}</li>
                  </ul>
                </div>
              </div>
            ) : null}
          </CatalogState>
        </TabsContent>
      </Tabs>
    </section>
  );
}

function buildCheckoutLoadingKey(product: GlobalBillingProduct): string {
  return `${product.product_type}:${product.product_bid}`;
}

function CatalogState({
  children,
  isLoading,
  unavailable,
}: {
  children: React.ReactNode;
  isLoading: boolean;
  unavailable: boolean;
}) {
  const { t } = useGlobalBillingTranslation();

  if (isLoading) {
    return (
      <div
        className='rounded-xl border border-border bg-card px-6 py-16 text-center text-muted-foreground'
        data-testid='global-billing-loading'
        role='status'
      >
        <span className='sr-only'>{t('module.billing.package.loading')}</span>
        <Skeleton
          className='mx-auto h-6 w-40'
          aria-hidden='true'
        />
      </div>
    );
  }

  if (unavailable) {
    return (
      <div
        className='rounded-xl border border-border bg-card px-6 py-16 text-center'
        data-testid='global-billing-unavailable'
      >
        <p className='text-sm text-muted-foreground'>
          {t('module.billing.overview.loadError')}
        </p>
      </div>
    );
  }

  return <>{children}</>;
}

function PlanColumn({
  tierSpec,
  cycle,
  products,
  activeSubscription,
  hasResolvedOverview,
  locale,
  onViewMonthly,
  checkoutLoadingKey,
  onPaymentClick,
}: {
  tierSpec: (typeof PLAN_TIERS)[number];
  cycle: BillingCycle;
  products: Map<string, GlobalBillingProduct>;
  activeSubscription: BillingSubscription | null;
  hasResolvedOverview: boolean;
  locale: string;
  onViewMonthly: () => void;
  checkoutLoadingKey: string;
  onPaymentClick: (payload: {
    product: GlobalBillingProduct;
    sourceTab: PricingTab;
    checkoutAction?: BillingSubscriptionCheckoutAction;
  }) => void;
}) {
  const { t } = useGlobalBillingTranslation();
  const monthlyProduct = products.get(tierSpec.monthlyCode) as BillingPlan;
  const annualProduct = tierSpec.annualCode
    ? (products.get(tierSpec.annualCode) as BillingPlan)
    : null;
  const monthlyOnly = cycle === 'annual' && !annualProduct;
  const product =
    cycle === 'annual' && annualProduct ? annualProduct : monthlyProduct;
  const activeSubscriptionProduct = activeSubscription
    ? (products.get(activeSubscription.product_code) as BillingPlan | undefined)
    : undefined;
  const isCurrentPlan = activeSubscription?.product_bid === product.product_bid;
  const currentTierRank = resolvePlanTierRank(activeSubscription?.product_code);
  const targetTierRank = resolvePlanTierRank(product.product_code);
  const legacyActiveSubscription = Boolean(
    activeSubscription && currentTierRank < 0,
  );
  const annualSubscriptionSwitchToMonthlyUnsupported =
    cycle === 'monthly' &&
    activeSubscriptionProduct?.billing_interval === 'year' &&
    !isCurrentPlan;
  const sameTierCycleSwitchUnsupported =
    cycle === 'annual' &&
    activeSubscriptionProduct?.billing_interval === 'month' &&
    currentTierRank >= 0 &&
    targetTierRank >= 0 &&
    targetTierRank === currentTierRank &&
    !isCurrentPlan;
  const downgradeUnsupported =
    !isCurrentPlan &&
    !monthlyOnly &&
    !annualSubscriptionSwitchToMonthlyUnsupported &&
    !sameTierCycleSwitchUnsupported &&
    !legacyActiveSubscription &&
    currentTierRank >= 0 &&
    targetTierRank >= 0 &&
    targetTierRank < currentTierRank;
  const supportedImmediateUpgrade =
    !activeSubscription ||
    legacyActiveSubscription ||
    (currentTierRank >= 0 &&
      targetTierRank >= 0 &&
      targetTierRank > currentTierRank);
  const unsupportedActivePlanTransition =
    Boolean(activeSubscription) &&
    !legacyActiveSubscription &&
    !isCurrentPlan &&
    !monthlyOnly &&
    !annualSubscriptionSwitchToMonthlyUnsupported &&
    !sameTierCycleSwitchUnsupported &&
    !downgradeUnsupported &&
    !supportedImmediateUpgrade;
  const checkoutAction: BillingSubscriptionCheckoutAction | undefined =
    activeSubscription && supportedImmediateUpgrade
      ? 'upgrade_immediate'
      : undefined;
  const isCheckingOut = Boolean(checkoutLoadingKey);
  const isCurrentCheckout =
    checkoutLoadingKey === buildCheckoutLoadingKey(product);
  const planName = t(
    `module.billing.globalPricing.plans.${tierSpec.tier}.name`,
  );
  const hasDiscountCampaign = hasBillingProductDiscountCampaign(product);
  const priceAmount = resolveBillingProductPayableAmount(product);
  const campaignLabel = resolveGlobalCampaignLabel(product, t, locale);
  const periodLabel = formatBillingPlanInterval(t, product)
    .replace(/^每\s*/, '')
    .replace(/^per\s*/i, '')
    .trim();
  const monthlyCostPerYear =
    (monthlyProduct.price_amount * 12) /
    Math.max(monthlyProduct.billing_interval_count || 0, 1);
  const annualSavings = annualProduct
    ? monthlyCostPerYear -
      annualProduct.price_amount /
        Math.max(annualProduct.billing_interval_count || 0, 1)
    : 0;
  const annualSavingsLabel =
    cycle === 'annual' && annualProduct && annualSavings > 0
      ? t('module.billing.globalPricing.annualSavings', {
          amount: formatBillingPrice(annualSavings, product.currency, locale),
        })
      : null;
  const featureKeys = PLAN_TIERS.slice(0, targetTierRank + 1).flatMap(
    tier => PLAN_FEATURE_KEYS[tier.tier],
  );
  const validityKey =
    product.billing_interval === 'year'
      ? 'module.billing.package.validityShort.yearly'
      : 'module.billing.package.validityShort.monthly';

  return (
    <div
      className={cn(
        styles.comparisonColumn,
        isCurrentPlan && styles.featuredColumn,
      )}
      data-testid={`global-plan-${tierSpec.tier}`}
      data-featured={isCurrentPlan ? 'true' : 'false'}
    >
      <div
        className={cn(styles.columnHead, styles.columnTitleHead)}
        data-testid={`global-plan-${tierSpec.tier}-title`}
      >
        <div className={styles.columnTitleRow}>
          <h3 className={styles.columnTitle}>{planName}</h3>
          {tierSpec.tier === 'business' ? (
            <span className={styles.columnBadge}>
              <Star className={styles.columnBadgeIcon} />
              {t('module.billing.catalog.badges.recommended')}
            </span>
          ) : null}
          {monthlyOnly ? (
            <Badge variant='secondary'>
              {t('module.billing.globalPricing.monthlyOnly')}
            </Badge>
          ) : null}
        </div>
      </div>

      <div
        className={cn(styles.columnHead, styles.columnPriceHead)}
        data-testid={`global-plan-${tierSpec.tier}-price`}
      >
        <div data-testid={`global-plan-${tierSpec.tier}-original-price-slot`}>
          {hasDiscountCampaign ? (
            <span className={styles.columnOriginalPrice}>
              {formatBillingPrice(
                product.price_amount,
                product.currency,
                locale,
              )}
            </span>
          ) : null}
        </div>
        <div className={styles.columnPrice}>
          <span>
            {formatBillingPrice(priceAmount, product.currency, locale)}
          </span>
          <span>{` / ${periodLabel}`}</span>
        </div>
        {campaignLabel ? (
          <div>
            <span className={styles.columnCampaignLabel}>{campaignLabel}</span>
          </div>
        ) : null}
        {hasDiscountCampaign ? (
          <p className={styles.columnPeriod}>
            {t('module.billing.globalPricing.renewalPrice', {
              price: formatBillingPrice(
                product.price_amount,
                product.currency,
                locale,
              ),
              period: periodLabel,
            })}
          </p>
        ) : null}
        {annualSavingsLabel ? (
          <p
            className='mt-2 text-xs font-medium leading-5 text-red-700'
            data-testid={`global-plan-${tierSpec.tier}-savings-slot`}
          >
            {annualSavingsLabel}
          </p>
        ) : null}
      </div>

      <div
        className={cn(styles.columnHead, styles.columnCreditsHead)}
        data-testid={`global-plan-${tierSpec.tier}-credits`}
      >
        <p className={styles.columnCreditAmount}>
          {t('module.billing.package.topup.creditLabel', {
            credits: formatBillingCredits(product.credit_amount, locale),
          })}
        </p>
      </div>

      <div
        className={cn(styles.columnHead, styles.columnActionHead)}
        data-testid={`global-plan-${tierSpec.tier}-action`}
      >
        {isCurrentPlan ? (
          <Button
            variant='default'
            className={cn(styles.columnAction, 'disabled:opacity-100')}
            disabled
          >
            {t('module.billing.package.actions.currentSubscription')}
          </Button>
        ) : annualSubscriptionSwitchToMonthlyUnsupported ? (
          <Button
            variant='secondary'
            className={styles.columnAction}
            disabled
          >
            {targetTierRank < currentTierRank
              ? t('module.billing.package.actions.downgradeDisabled')
              : t('module.billing.package.actions.monthlySwitchDisabled')}
          </Button>
        ) : sameTierCycleSwitchUnsupported ? (
          <Button
            variant='secondary'
            className={styles.columnAction}
            disabled
          >
            {t('module.billing.globalPricing.actions.cycleSwitchDisabled')}
          </Button>
        ) : downgradeUnsupported ? (
          <Button
            variant='secondary'
            className={styles.columnAction}
            disabled
          >
            {t('module.billing.package.actions.downgradeDisabled')}
          </Button>
        ) : unsupportedActivePlanTransition ? (
          <Button
            variant='secondary'
            className={styles.columnAction}
            disabled
          >
            {t('module.billing.package.actions.downgradeDisabled')}
          </Button>
        ) : monthlyOnly ? (
          <Button
            variant='outline'
            className={styles.columnAction}
            disabled={isCheckingOut}
            onClick={onViewMonthly}
          >
            {t('module.billing.globalPricing.actions.viewMonthly')}
          </Button>
        ) : (
          <Button
            className={styles.columnAction}
            disabled={!hasResolvedOverview || isCheckingOut}
            onClick={() =>
              onPaymentClick({
                product,
                sourceTab: 'plans',
                checkoutAction,
              })
            }
          >
            {isCurrentCheckout
              ? t('module.billing.globalPricing.actions.checkoutLoading')
              : activeSubscription
                ? t('module.billing.package.actions.upgradeNow')
                : t('module.billing.globalPricing.actions.choosePlan')}
          </Button>
        )}
      </div>

      <div
        className={styles.comparisonDataCell}
        data-testid={`global-plan-${tierSpec.tier}-estimate`}
      >
        <p className={styles.cellLabel}>
          {t('module.billing.package.learningTime.label')}
          <sup className='ml-1'>{LEARNING_TIME_ESTIMATE_MARKER}</sup>
        </p>
        <p className={styles.cellValue}>
          {formatBillingLearningTime(t, Number(product.credit_amount), locale)}
        </p>
      </div>

      <div
        className={styles.comparisonDataCell}
        data-testid={`global-plan-${tierSpec.tier}-validity`}
      >
        <p className={styles.cellLabel}>
          {t('module.billing.package.table.validityRowLabel')}
        </p>
        <p className={styles.cellValue}>
          {t(validityKey, {
            count: Math.max(product.billing_interval_count || 0, 1),
          })}
        </p>
      </div>

      <div
        className={styles.comparisonFeatureCell}
        data-testid={`global-plan-${tierSpec.tier}-benefits`}
      >
        <p className={styles.cellLabel}>
          {t('module.billing.package.table.featuresRowLabel')}
        </p>
        <ul className={styles.featureColumnList}>
          {featureKeys.map(featureKey => (
            <li
              key={featureKey}
              className={styles.featureColumnItem}
            >
              <span className={styles.featureColumnItemText}>
                {t(featureKey)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
