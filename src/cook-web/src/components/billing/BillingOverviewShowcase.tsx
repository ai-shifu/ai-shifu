import { useTranslation } from 'react-i18next';
import { Skeleton } from '@/components/ui/Skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import {
  formatBillingCreditAmount,
  formatBillingDate,
  formatBillingPlanInterval,
  formatBillingPrice,
  resolveBillingPlanCreditsLabel,
  resolveBillingPlanValidityLabel,
  resolveBillingProductDescription,
  resolveBillingProductTitle,
} from '@/lib/billing';
import type {
  BillingPlan,
  BillingProvider,
  BillingTopupProduct,
  BillingTrialOffer,
} from '@/types/billing';
import { cn } from '@/lib/utils';
import {
  getFreeFeatureData,
  getPlanFeatureData,
  getPlanScaleKeys,
  PlanFeatureList,
  PlanShowcaseCard,
  TopupCard,
} from './BillingOverviewCards';
import type { ShowcaseTab } from './BillingOverviewCards';

type BillingOverviewShowcaseProps = {
  checkoutLoadingKey: string;
  currentPlan: BillingPlan | null;
  dailyPlans: BillingPlan[];
  hasActiveSubscription: boolean;
  isTrialCurrentPlan: boolean;
  isLoading: boolean;
  monthlyPlans: BillingPlan[];
  orderedPlans: BillingPlan[];
  pingxxAvailable: boolean;
  renderFreeCard: boolean;
  showcaseTab: ShowcaseTab;
  stripeAvailable: boolean;
  topups: BillingTopupProduct[];
  trialOffer: BillingTrialOffer | null | undefined;
  yearlyPlans: BillingPlan[];
  onSelectPlanCheckout: (plan: BillingPlan, provider: BillingProvider) => void;
  onSelectTopupCheckout: (
    product: BillingTopupProduct,
    provider: BillingProvider,
  ) => void;
  onShowcaseTabChange: (tab: ShowcaseTab) => void;
};

function resolveCheckoutProvider(
  stripeAvailable: boolean,
  pingxxAvailable: boolean,
): BillingProvider | null {
  if (stripeAvailable) {
    return 'stripe';
  }
  if (pingxxAvailable) {
    return 'pingxx';
  }
  return null;
}

function resolvePlanRank(
  plans: BillingPlan[],
  productBid: string | null,
): number {
  if (!productBid) {
    return -1;
  }
  return plans.findIndex(plan => plan.product_bid === productBid);
}

export function BillingOverviewShowcase({
  checkoutLoadingKey,
  currentPlan,
  dailyPlans,
  hasActiveSubscription,
  isTrialCurrentPlan,
  isLoading,
  monthlyPlans,
  orderedPlans,
  pingxxAvailable,
  renderFreeCard,
  showcaseTab,
  stripeAvailable,
  topups,
  trialOffer,
  yearlyPlans,
  onSelectPlanCheckout,
  onSelectTopupCheckout,
  onShowcaseTabChange,
}: BillingOverviewShowcaseProps) {
  const { t, i18n } = useTranslation();
  const currentPlanRank = resolvePlanRank(
    orderedPlans,
    currentPlan?.product_bid || null,
  );
  const freeCreditSummary = t('module.billing.package.free.creditSummary', {
    credits: formatBillingCreditAmount(trialOffer?.credit_amount || 0),
  });
  const freeCreditValidityLabel = t('module.billing.package.validity.free');
  const freeFeatureData = getFreeFeatureData(trialOffer?.highlights);
  const freeCardFeatureKeys = freeFeatureData.items;
  const freeCardPriceLabel =
    trialOffer && trialOffer.currency
      ? formatBillingPrice(
          trialOffer.price_amount,
          trialOffer.currency,
          i18n.language,
        )
      : t('module.billing.package.free.priceValue');
  const freeCardTitle = resolveBillingProductTitle(
    t,
    trialOffer,
    t('module.billing.package.free.title'),
  );
  const freeCardDescription = resolveBillingProductDescription(
    t,
    trialOffer,
    t('module.billing.package.free.description'),
  );

  const freePriceMetaLabel = '';

  return (
    <>
      <div className='mb-8 flex justify-center'>
        <Tabs
          className='flex justify-center'
          onValueChange={value => onShowcaseTabChange(value as ShowcaseTab)}
          value={showcaseTab}
        >
          <TabsList className='h-[var(--height-h-9,36px)] rounded-[var(--border-radius-rounded-lg,10px)] bg-[var(--base-muted,#F5F5F5)] p-[3px]'>
            {dailyPlans.length > 0 ? (
              <TabsTrigger
                className='h-full rounded-[var(--border-radius-rounded-md,8px)] border border-transparent px-6 py-[var(--spacing-1,4px)] text-center text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)] data-[state=active]:border-[var(--custom-dark-input,rgba(255,255,255,0.00))] data-[state=active]:bg-[var(--custom-background-dark-input-30,#FFF)] data-[state=active]:shadow-[var(--shadow-sm-1-offset-x,0)_var(--shadow-sm-1-offset-y,1px)_var(--shadow-sm-1-blur-radius,3px)_var(--shadow-sm-1-spread-radius,0)_var(--shadow-sm-1-color,rgba(0,0,0,0.10)),var(--shadow-sm-2-offset-x,0)_var(--shadow-sm-2-offset-y,1px)_var(--shadow-sm-2-blur-radius,2px)_var(--shadow-sm-2-spread-radius,-1px)_var(--shadow-sm-2-color,rgba(0,0,0,0.10))]'
                value='daily'
              >
                {t('module.billing.package.intervalTabs.daily')}
              </TabsTrigger>
            ) : null}
            <TabsTrigger
              className='h-full rounded-[var(--border-radius-rounded-md,8px)] border border-transparent px-6 py-[var(--spacing-1,4px)] text-center text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)] data-[state=active]:border-[var(--custom-dark-input,rgba(255,255,255,0.00))] data-[state=active]:bg-[var(--custom-background-dark-input-30,#FFF)] data-[state=active]:shadow-[var(--shadow-sm-1-offset-x,0)_var(--shadow-sm-1-offset-y,1px)_var(--shadow-sm-1-blur-radius,3px)_var(--shadow-sm-1-spread-radius,0)_var(--shadow-sm-1-color,rgba(0,0,0,0.10)),var(--shadow-sm-2-offset-x,0)_var(--shadow-sm-2-offset-y,1px)_var(--shadow-sm-2-blur-radius,2px)_var(--shadow-sm-2-spread-radius,-1px)_var(--shadow-sm-2-color,rgba(0,0,0,0.10))]'
              value='monthly'
            >
              {t('module.billing.package.intervalTabs.monthly')}
            </TabsTrigger>
            <TabsTrigger
              className='h-full rounded-[var(--border-radius-rounded-md,8px)] border border-transparent px-6 py-[var(--spacing-1,4px)] text-center text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)] data-[state=active]:border-[var(--custom-dark-input,rgba(255,255,255,0.00))] data-[state=active]:bg-[var(--custom-background-dark-input-30,#FFF)] data-[state=active]:shadow-[var(--shadow-sm-1-offset-x,0)_var(--shadow-sm-1-offset-y,1px)_var(--shadow-sm-1-blur-radius,3px)_var(--shadow-sm-1-spread-radius,0)_var(--shadow-sm-1-color,rgba(0,0,0,0.10)),var(--shadow-sm-2-offset-x,0)_var(--shadow-sm-2-offset-y,1px)_var(--shadow-sm-2-blur-radius,2px)_var(--shadow-sm-2-spread-radius,-1px)_var(--shadow-sm-2-color,rgba(0,0,0,0.10))]'
              value='yearly'
            >
              {t('module.billing.package.intervalTabs.yearly')}
            </TabsTrigger>
            <TabsTrigger
              className='h-full rounded-[var(--border-radius-rounded-md,8px)] border border-transparent px-6 py-[var(--spacing-1,4px)] text-center text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)] data-[state=active]:border-[var(--custom-dark-input,rgba(255,255,255,0.00))] data-[state=active]:bg-[var(--custom-background-dark-input-30,#FFF)] data-[state=active]:shadow-[var(--shadow-sm-1-offset-x,0)_var(--shadow-sm-1-offset-y,1px)_var(--shadow-sm-1-blur-radius,3px)_var(--shadow-sm-1-spread-radius,0)_var(--shadow-sm-1-color,rgba(0,0,0,0.10)),var(--shadow-sm-2-offset-x,0)_var(--shadow-sm-2-offset-y,1px)_var(--shadow-sm-2-blur-radius,2px)_var(--shadow-sm-2-spread-radius,-1px)_var(--shadow-sm-2-color,rgba(0,0,0,0.10))]'
              value='topup'
            >
              {t('module.billing.package.intervalTabs.topup')}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {isLoading ? (
        <div className='grid gap-6 xl:grid-cols-3'>
          <Skeleton className='h-[620px] rounded-[34px]' />
          <Skeleton className='h-[620px] rounded-[34px]' />
          <Skeleton className='h-[620px] rounded-[34px]' />
        </div>
      ) : showcaseTab === 'topup' ? (
        <div className='space-y-4'>
          <div
            className='rounded-2xl border border-[rgba(0,82,217,0.12)] bg-[rgba(0,82,217,0.04)] px-5 py-4 text-sm leading-6 text-[var(--base-foreground,#0A0A0A)]'
            data-testid='billing-topup-note'
          >
            <div className='font-medium text-[var(--base-foreground,#0A0A0A)]'>
              {t('module.billing.package.topup.noteTitle')}
            </div>
            <ul className='mt-2 list-disc space-y-1 pl-5 text-[var(--base-muted-foreground,#525252)]'>
              <li>{t('module.billing.package.topup.noteInstant')}</li>
              <li>{t('module.billing.package.topup.noteFrozen')}</li>
            </ul>
          </div>

          <div
            className='grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(326px,1fr))]'
            data-testid='billing-topup-grid'
          >
            {topups.map(product => {
              const provider = resolveCheckoutProvider(
                stripeAvailable,
                pingxxAvailable,
              );
              const checkoutKey = provider
                ? `topup:${provider}:${product.product_bid}`
                : '';

              return (
                <TopupCard
                  key={product.product_bid}
                  actionLabel={t('module.billing.package.actions.buyNow')}
                  actionLoading={checkoutLoadingKey === checkoutKey}
                  creditsLabel={t('module.billing.package.topup.creditLabel', {
                    credits: formatBillingCreditAmount(product.credit_amount),
                  })}
                  disabled={!provider}
                  featured={Boolean(product.status_badge_key)}
                  onAction={() =>
                    provider && onSelectTopupCheckout(product, provider)
                  }
                  priceLabel={formatBillingPrice(
                    product.price_amount,
                    product.currency,
                    i18n.language,
                  )}
                  testId={`billing-topup-card-${product.product_bid}`}
                />
              );
            })}
          </div>
        </div>
      ) : (
        <div
          className='grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(326px,1fr))]'
          data-testid='billing-plan-grid'
        >
          {renderFreeCard
            ? (() => {
                const freeScale = getPlanScaleKeys(
                  trialOffer?.product_code || 'creator-plan-trial',
                );
                return (
                  <PlanShowcaseCard
                    actionLabel={t(
                      !hasActiveSubscription || isTrialCurrentPlan
                        ? 'module.billing.package.actions.currentUsing'
                        : 'module.billing.package.actions.freeTrial',
                    )}
                    actionTooltip={
                      !hasActiveSubscription
                        ? t('module.billing.package.actions.nonMemberTooltip')
                        : undefined
                    }
                    creditSummary={freeCreditSummary}
                    creditValidityLabel={freeCreditValidityLabel}
                    description={freeCardDescription}
                    disabled
                    featured={isTrialCurrentPlan || !hasActiveSubscription}
                    footer={<PlanFeatureList items={freeCardFeatureKeys} />}
                    priceLabel={freeCardPriceLabel}
                    priceMetaLabel={freePriceMetaLabel}
                    studentCapacity={
                      freeScale ? t(freeScale.students) : undefined
                    }
                    testId='billing-plan-card-free'
                    title={freeCardTitle}
                  />
                );
              })()
            : null}

          {(showcaseTab === 'daily'
            ? dailyPlans
            : showcaseTab === 'yearly'
              ? yearlyPlans
              : monthlyPlans
          ).map(plan => {
            const provider = resolveCheckoutProvider(
              stripeAvailable,
              pingxxAvailable,
            );
            const isCurrentPlan = currentPlan?.product_bid === plan.product_bid;
            const planRank = resolvePlanRank(orderedPlans, plan.product_bid);
            const isDowngradeLocked =
              hasActiveSubscription &&
              !isCurrentPlan &&
              currentPlanRank >= 0 &&
              planRank >= 0 &&
              planRank < currentPlanRank;
            const isFeatured = isCurrentPlan;
            const checkoutKey = provider
              ? `plan:${provider}:${plan.product_bid}`
              : '';
            const planScale = getPlanScaleKeys(plan.product_code);
            const planBadgeKey = plan.status_badge_key;
            const planFeatureData = getPlanFeatureData(plan);

            return (
              <PlanShowcaseCard
                key={plan.product_bid}
                actionLabel={
                  isCurrentPlan
                    ? t('module.billing.package.actions.currentSubscription')
                    : isDowngradeLocked
                      ? t('module.billing.package.actions.downgradeDisabled')
                      : hasActiveSubscription
                        ? t('module.billing.package.actions.upgradeNow')
                        : t('module.billing.package.actions.subscribeNow')
                }
                actionLoading={checkoutLoadingKey === checkoutKey}
                actionTooltip={
                  isDowngradeLocked
                    ? t('module.billing.package.actions.upgradeOnlyTooltip')
                    : undefined
                }
                badgeLabel={planBadgeKey ? t(planBadgeKey) : undefined}
                creditSummary={resolveBillingPlanCreditsLabel(t, plan)}
                creditValidityLabel={resolveBillingPlanValidityLabel(t, plan)}
                description={resolveBillingProductDescription(t, plan)}
                disabled={!provider || isCurrentPlan || isDowngradeLocked}
                featured={isFeatured}
                footer={
                  <PlanFeatureList
                    includesLabel={planFeatureData.includesLabel}
                    items={planFeatureData.items}
                  />
                }
                onAction={() =>
                  provider && onSelectPlanCheckout(plan, provider)
                }
                priceLabel={formatBillingPrice(
                  plan.price_amount,
                  plan.currency,
                  i18n.language,
                )}
                priceMetaLabel={formatBillingPlanInterval(t, plan)}
                studentCapacity={planScale ? t(planScale.students) : undefined}
                testId={`billing-plan-card-${plan.product_bid}`}
                title={resolveBillingProductTitle(t, plan)}
              />
            );
          })}
        </div>
      )}
    </>
  );
}
