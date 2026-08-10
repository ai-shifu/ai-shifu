'use client';

import React from 'react';
import useSWR from 'swr';
import { Check, Star } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useTracking } from '@/c-common/hooks/useTracking';
import { TopupCard } from '@/components/billing/BillingOverviewCards';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from '@/components/ui/Card';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import {
  buildBillingSwrKey,
  formatBillingCredits,
  formatBillingPrice,
} from '@/lib/billing';
import type { BillingPlan, BillingTopupProduct } from '@/types/billing';

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
  creditAmount: number;
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
    creditAmount: 1000,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.growthMonthly]: {
    productType: 'plan',
    billingInterval: 'month',
    priceAmount: 22900,
    creditAmount: 4000,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.growthAnnual]: {
    productType: 'plan',
    billingInterval: 'year',
    priceAmount: 219900,
    creditAmount: 50000,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.businessMonthly]: {
    productType: 'plan',
    billingInterval: 'month',
    priceAmount: 41900,
    creditAmount: 8000,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.businessAnnual]: {
    productType: 'plan',
    billingInterval: 'year',
    priceAmount: 399900,
    creditAmount: 100000,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.scaleMonthly]: {
    productType: 'plan',
    billingInterval: 'month',
    priceAmount: 83900,
    creditAmount: 18000,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.scaleAnnual]: {
    productType: 'plan',
    billingInterval: 'year',
    priceAmount: 799900,
    creditAmount: 220000,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.credits250]: {
    productType: 'topup',
    priceAmount: 2900,
    creditAmount: 250,
  },
  [GLOBAL_BILLING_PRODUCT_CODES.credits3000]: {
    productType: 'topup',
    priceAmount: 27900,
    creditAmount: 3000,
  },
};

const PLAN_TIERS: Array<{
  tier: PlanTier;
  monthlyCode: string;
  annualCode?: string;
  annualMonthlyEquivalent?: number;
}> = [
  {
    tier: 'studio',
    monthlyCode: GLOBAL_BILLING_PRODUCT_CODES.studioMonthly,
  },
  {
    tier: 'growth',
    monthlyCode: GLOBAL_BILLING_PRODUCT_CODES.growthMonthly,
    annualCode: GLOBAL_BILLING_PRODUCT_CODES.growthAnnual,
    annualMonthlyEquivalent: 18300,
  },
  {
    tier: 'business',
    monthlyCode: GLOBAL_BILLING_PRODUCT_CODES.businessMonthly,
    annualCode: GLOBAL_BILLING_PRODUCT_CODES.businessAnnual,
    annualMonthlyEquivalent: 33300,
  },
  {
    tier: 'scale',
    monthlyCode: GLOBAL_BILLING_PRODUCT_CODES.scaleMonthly,
    annualCode: GLOBAL_BILLING_PRODUCT_CODES.scaleAnnual,
    annualMonthlyEquivalent: 66700,
  },
];

const PLAN_FEATURE_KEYS: Record<PlanTier, string[]> = {
  studio: ['coreTeaching'],
  growth: ['higherConcurrency'],
  business: ['customBranding', 'customDomain', 'prioritySupport'],
  scale: ['dedicatedSupport', 'exclusiveTraining'],
};

const PLAN_FEATURE_INCLUDE_KEYS: Partial<Record<PlanTier, string>> = {
  growth: 'module.billing.globalPricing.featuresIncludes.growth',
  business: 'module.billing.globalPricing.featuresIncludes.business',
  scale: 'module.billing.globalPricing.featuresIncludes.scale',
};

const CREDIT_PACK_CODES = [
  GLOBAL_BILLING_PRODUCT_CODES.credits250,
  GLOBAL_BILLING_PRODUCT_CODES.credits3000,
];

const BILLING_PASSIVE_REQUEST_CONFIG = { skipErrorToast: true } as const;
const LEARNER_ESTIMATE_MARKER = '①';
const CREDIT_VALIDITY_MARKER = '②';
const LEARNER_SESSIONS_PER_100_CREDITS = {
  minimum: 5,
  maximum: 15,
} as const;

function getLearnerSessionEstimate(creditAmount: number) {
  return {
    minimum: (creditAmount * LEARNER_SESSIONS_PER_100_CREDITS.minimum) / 100,
    maximum: (creditAmount * LEARNER_SESSIONS_PER_100_CREDITS.maximum) / 100,
  };
}

function useGlobalBillingTranslation() {
  const { t, i18n } = useTranslation();

  return { t, locale: i18n.resolvedLanguage || i18n.language || 'en-US' };
}

function normalizeCurrency(currency: unknown): string {
  return typeof currency === 'string' ? currency.toUpperCase() : '';
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
      Number(product.credit_amount) !== expected.creditAmount
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
  const [comingSoonOpen, setComingSoonOpen] = React.useState(false);
  const { data, error, isLoading } = useSWR<BillingCatalogResponse>(
    buildBillingSwrKey('billing-catalog'),
    async () =>
      (await api.getBillingCatalog(
        {},
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingCatalogResponse,
    { revalidateOnFocus: false },
  );
  const globalProducts = React.useMemo(
    () => resolveGlobalProducts(data),
    [data],
  );

  const handlePaymentClick = React.useCallback(
    ({
      product,
      planName,
      billingInterval,
      sourceTab,
    }: {
      product: GlobalBillingProduct;
      planName: string;
      billingInterval: 'month' | 'year' | 'one_time';
      sourceTab: PricingTab;
    }) => {
      void trackEvent('creator_billing_checkout_click', {
        billing_market: 'global',
        product_type: product.product_type,
        product_code: product.product_code,
        plan_name: planName,
        billing_interval: billingInterval,
        price_amount: product.price_amount,
        currency: normalizeCurrency(product.currency),
        credit_amount: product.credit_amount,
        source_tab: sourceTab,
        checkout_status: 'coming_soon',
      });
      setComingSoonOpen(true);
    },
    [trackEvent],
  );

  return (
    <section
      className='mx-auto w-full max-w-[1440px] space-y-8'
      data-testid='global-billing-pricing'
    >
      <Tabs
        value={pricingTab}
        onValueChange={value => setPricingTab(value as PricingTab)}
        className='space-y-8'
      >
        <div className='flex flex-col items-center gap-2 px-4'>
          <TabsList className='h-11 rounded-[10px] p-[3px]'>
            <TabsTrigger
              value='plans'
              className='h-full rounded-lg px-5'
            >
              {t('module.billing.globalPricing.tabs.plans')}
            </TabsTrigger>
            <TabsTrigger
              value='credit_packs'
              className='h-full rounded-lg px-5'
            >
              {t('module.billing.globalPricing.tabs.creditPacks')}
            </TabsTrigger>
          </TabsList>
          <p className='text-center text-xs leading-5 text-muted-foreground'>
            {t('module.billing.globalPricing.comingSoon.inlineNotice')}
          </p>
        </div>

        <TabsContent
          value='plans'
          className='mt-0 space-y-6'
        >
          <div className='flex justify-center px-4'>
            <Tabs
              value={billingCycle}
              onValueChange={value => setBillingCycle(value as BillingCycle)}
            >
              <TabsList className='h-12 rounded-[10px] p-[3px]'>
                <TabsTrigger
                  value='monthly'
                  className='h-full rounded-lg px-5'
                >
                  {t('module.billing.globalPricing.cycles.monthly')}
                </TabsTrigger>
                <TabsTrigger
                  value='annual'
                  className='h-full gap-2 rounded-lg px-5'
                >
                  {t('module.billing.globalPricing.cycles.annual')}
                  <Badge className='border-0 bg-red-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white hover:bg-red-600'>
                    {t('module.billing.globalPricing.saveBadge')}
                  </Badge>
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          <CatalogState
            isLoading={isLoading}
            unavailable={Boolean(error) || (!isLoading && !globalProducts)}
          >
            {globalProducts ? (
              <div
                className='grid gap-5 px-1'
                style={{
                  gridTemplateColumns:
                    'repeat(auto-fit, minmax(min(100%, 260px), 1fr))',
                }}
              >
                {PLAN_TIERS.map(tierSpec => (
                  <PlanCard
                    key={tierSpec.tier}
                    tierSpec={tierSpec}
                    cycle={billingCycle}
                    products={globalProducts}
                    locale={locale}
                    onViewMonthly={() => setBillingCycle('monthly')}
                    onPaymentClick={handlePaymentClick}
                  />
                ))}
              </div>
            ) : null}
          </CatalogState>

          {globalProducts ? (
            <div className='mx-auto max-w-4xl space-y-4 rounded-xl border border-border bg-muted/40 px-5 py-4 text-sm leading-6 text-muted-foreground'>
              <p>
                <span className='mr-1 font-medium text-foreground'>
                  {LEARNER_ESTIMATE_MARKER}
                </span>
                {t('module.billing.globalPricing.footnote.intro')}
              </p>
              <ul className='list-disc space-y-1 pl-5'>
                <li>
                  {t('module.billing.package.footnote.learnerEstimateScale')}
                </li>
                <li>
                  {t('module.billing.package.footnote.learnerEstimateMode')}
                </li>
                <li>
                  {t('module.billing.package.footnote.learnerEstimateModel')}
                </li>
              </ul>
              <p>
                <span className='mr-1 font-medium text-foreground'>
                  {CREDIT_VALIDITY_MARKER}
                </span>
                {t('module.billing.globalPricing.footnote.validity')}
              </p>
            </div>
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
                  className='mx-auto grid max-w-3xl gap-4 px-1'
                  style={{
                    gridTemplateColumns:
                      'repeat(auto-fit, minmax(min(100%, 300px), 1fr))',
                  }}
                >
                  {CREDIT_PACK_CODES.map(code => {
                    const product = globalProducts.get(
                      code,
                    ) as BillingTopupProduct;
                    const packName = t(
                      'module.billing.globalPricing.creditPacks.packName',
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
                        actionClassName='min-h-11'
                        actionLabel={t(
                          'module.billing.globalPricing.actions.buyCredits',
                        )}
                        creditsLabel={packName}
                        onAction={() =>
                          handlePaymentClick({
                            product,
                            planName: packName,
                            billingInterval: 'one_time',
                            sourceTab: 'credit_packs',
                          })
                        }
                        priceLabel={formatBillingPrice(
                          product.price_amount,
                          product.currency,
                          locale,
                        )}
                        testId={`global-credit-pack-${product.credit_amount}`}
                      />
                    );
                  })}
                </div>
                <div className='mx-auto max-w-3xl text-sm leading-6 text-muted-foreground'>
                  <ul className='list-disc space-y-2 pl-5'>
                    <li>
                      {t(
                        'module.billing.globalPricing.creditPacks.instantAndPermanent',
                      )}
                    </li>
                    <li>
                      {t(
                        'module.billing.globalPricing.creditPacks.activeSubscriptionRequired',
                      )}
                    </li>
                  </ul>
                </div>
              </div>
            ) : null}
          </CatalogState>
        </TabsContent>
      </Tabs>

      <Dialog
        open={comingSoonOpen}
        onOpenChange={setComingSoonOpen}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t('module.billing.globalPricing.comingSoon.title')}
            </DialogTitle>
            <DialogDescription>
              {t('module.billing.globalPricing.comingSoon.description')}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button>
                {t('module.billing.globalPricing.comingSoon.close')}
              </Button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
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
      >
        {t('module.billing.globalPricing.states.loading')}
      </div>
    );
  }

  if (unavailable) {
    return (
      <div
        className='rounded-xl border border-border bg-card px-6 py-16 text-center'
        data-testid='global-billing-unavailable'
      >
        <h3 className='text-lg font-semibold text-foreground'>
          {t('module.billing.globalPricing.states.unavailableTitle')}
        </h3>
        <p className='mt-2 text-sm text-muted-foreground'>
          {t('module.billing.globalPricing.states.unavailableDescription')}
        </p>
      </div>
    );
  }

  return <>{children}</>;
}

function PlanCard({
  tierSpec,
  cycle,
  products,
  locale,
  onViewMonthly,
  onPaymentClick,
}: {
  tierSpec: (typeof PLAN_TIERS)[number];
  cycle: BillingCycle;
  products: Map<string, GlobalBillingProduct>;
  locale: string;
  onViewMonthly: () => void;
  onPaymentClick: (payload: {
    product: GlobalBillingProduct;
    planName: string;
    billingInterval: 'month' | 'year' | 'one_time';
    sourceTab: PricingTab;
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
  const planName = t(
    `module.billing.globalPricing.plans.${tierSpec.tier}.name`,
  );
  const priceAmount =
    cycle === 'annual' && tierSpec.annualMonthlyEquivalent
      ? tierSpec.annualMonthlyEquivalent
      : product.price_amount;
  const learnerSessionEstimate = getLearnerSessionEstimate(
    Number(product.credit_amount),
  );
  const annualSavings = annualProduct
    ? monthlyProduct.price_amount * 12 - annualProduct.price_amount
    : 0;
  const annualSavingsPercent = annualProduct
    ? ((annualSavings / (monthlyProduct.price_amount * 12)) * 100).toFixed(1)
    : '0.0';
  const featureIncludeKey = PLAN_FEATURE_INCLUDE_KEYS[tierSpec.tier];

  return (
    <Card
      className='relative flex h-full flex-col overflow-hidden rounded-xl border-border shadow-sm'
      data-testid={`global-plan-${tierSpec.tier}`}
    >
      <CardHeader className='space-y-4 p-6 pb-4'>
        <div className='flex min-h-7 items-center justify-between gap-3'>
          <div className='flex min-w-0 flex-wrap items-center gap-2'>
            <h3 className='text-xl font-semibold text-foreground'>
              {planName}
            </h3>
            {tierSpec.tier === 'business' ? (
              <Badge className='gap-1 border-0 bg-red-600 px-2 py-0.5 text-[10px] font-semibold text-white hover:bg-red-600'>
                <Star className='h-3 w-3 fill-current' />
                {t('module.billing.globalPricing.mostPopular')}
              </Badge>
            ) : null}
          </div>
          {monthlyOnly ? (
            <Badge variant='secondary'>
              {t('module.billing.globalPricing.monthlyOnly')}
            </Badge>
          ) : null}
        </div>
        <div>
          <div className='flex items-end gap-1 text-foreground'>
            {cycle === 'annual' && annualProduct ? (
              <span className='pb-1 text-sm text-muted-foreground'>
                {t('module.billing.globalPricing.approximatePricePrefix')}
              </span>
            ) : null}
            <span className='text-4xl font-semibold tracking-tight'>
              {formatBillingPrice(priceAmount, product.currency, locale)}
            </span>
            <span className='pb-1 text-sm text-muted-foreground'>
              {t('module.billing.globalPricing.perMonth')}
            </span>
          </div>
          {cycle === 'annual' && annualProduct ? (
            <div className='mt-2 space-y-2'>
              <p className='text-sm text-muted-foreground'>
                {t('module.billing.globalPricing.billedAnnually', {
                  price: formatBillingPrice(
                    annualProduct.price_amount,
                    annualProduct.currency,
                    locale,
                  ),
                })}
              </p>
              <Badge className='border-0 bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-700 hover:bg-red-50'>
                {t('module.billing.globalPricing.annualSavings', {
                  amount: formatBillingPrice(
                    annualSavings,
                    annualProduct.currency,
                    locale,
                  ),
                  percent: annualSavingsPercent,
                })}
              </Badge>
            </div>
          ) : (
            <p className='mt-2 text-sm text-muted-foreground'>
              {t('module.billing.globalPricing.cancelAnytime')}
            </p>
          )}
        </div>

        <div className='rounded-lg border border-primary/10 bg-primary/5 p-3 text-foreground'>
          <p className='text-xs font-medium text-muted-foreground'>
            {t('module.billing.globalPricing.creditsLabel')}
          </p>
          <p className='mt-1 text-lg font-semibold'>
            {cycle === 'annual' && annualProduct
              ? t('module.billing.globalPricing.creditsPerYear', {
                  credits: formatBillingCredits(
                    annualProduct.credit_amount,
                    locale,
                  ),
                })
              : t('module.billing.globalPricing.creditsPerMonth', {
                  credits: formatBillingCredits(
                    monthlyProduct.credit_amount,
                    locale,
                  ),
                })}
          </p>
        </div>
      </CardHeader>

      <CardFooter className='px-6 pb-5 pt-0'>
        {monthlyOnly ? (
          <Button
            variant='outline'
            className='min-h-11 w-full'
            onClick={onViewMonthly}
          >
            {t('module.billing.globalPricing.actions.viewMonthly')}
          </Button>
        ) : (
          <Button
            className='min-h-11 w-full'
            onClick={() =>
              onPaymentClick({
                product,
                planName,
                billingInterval:
                  product.billing_interval === 'year' ? 'year' : 'month',
                sourceTab: 'plans',
              })
            }
          >
            {t('module.billing.globalPricing.actions.choosePlan')}
          </Button>
        )}
      </CardFooter>

      <CardContent className='flex-1 divide-y divide-border border-t border-border px-0 pb-0'>
        <div className='px-6 py-4'>
          <p className='text-xs font-medium text-muted-foreground'>
            {t('module.billing.globalPricing.audienceLabel')}
          </p>
          <p className='mt-1 text-sm leading-5 text-foreground'>
            {t(
              `module.billing.globalPricing.plans.${tierSpec.tier}.description`,
            )}
          </p>
        </div>

        <div className='px-6 py-4'>
          <p className='text-xs font-medium text-muted-foreground'>
            {t('module.billing.globalPricing.learnerEstimateLabel')}
            <span className='ml-1'>{LEARNER_ESTIMATE_MARKER}</span>
          </p>
          <p className='mt-1 text-sm text-foreground'>
            {t('module.billing.globalPricing.learnerEstimateValue', {
              minimum: formatBillingCredits(
                learnerSessionEstimate.minimum,
                locale,
              ),
              maximum: formatBillingCredits(
                learnerSessionEstimate.maximum,
                locale,
              ),
            })}
          </p>
        </div>

        <div className='px-6 py-4'>
          <p className='text-xs font-medium text-muted-foreground'>
            {featureIncludeKey
              ? t(featureIncludeKey)
              : t('module.billing.globalPricing.featuresLabel')}
          </p>
          <ul className='mt-3 space-y-3'>
            {PLAN_FEATURE_KEYS[tierSpec.tier].map(featureKey => (
              <li
                key={featureKey}
                className='flex gap-2 text-sm leading-5 text-muted-foreground'
              >
                <Check className='mt-0.5 h-4 w-4 shrink-0 text-primary' />
                <span>
                  {t(`module.billing.globalPricing.features.${featureKey}`)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}
