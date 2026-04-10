import { useTranslation } from 'react-i18next';
import { Skeleton } from '@/components/ui/Skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import {
  formatBillingCredits,
  formatBillingDate,
  formatBillingPlanInterval,
  formatBillingPrice,
  resolveBillingPlanCreditsLabel,
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
  getFreeFeatureKeys,
  getPlanFeatureKeys,
  PlanFeatureList,
  PlanShowcaseCard,
  TopupCard,
} from './BillingOverviewCards';
import type { ShowcaseTab } from './BillingOverviewCards';

type BillingOverviewShowcaseProps = {
  checkoutLoadingKey: string;
  currentPlan: BillingPlan | null;
  hasActiveSubscription: boolean;
  isLoading: boolean;
  monthlyPlans: BillingPlan[];
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

export function BillingOverviewShowcase({
  checkoutLoadingKey,
  currentPlan,
  hasActiveSubscription,
  isLoading,
  monthlyPlans,
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
  const freeCreditSummary = t('module.billing.package.free.creditSummary', {
    credits: formatBillingCredits(
      trialOffer?.credit_amount || 0,
      i18n.language,
    ),
  });
  const freeCreditValidityLabel = t('module.billing.package.validity.free');

  let freePriceMetaLabel = '';
  if (trialOffer) {
    if (
      trialOffer.status === 'granted' &&
      trialOffer.granted_at &&
      trialOffer.expires_at
    ) {
      freePriceMetaLabel = t('module.billing.package.free.priceNoteGranted', {
        grantedAt: formatBillingDate(trialOffer.granted_at, i18n.language),
        expiresAt: formatBillingDate(trialOffer.expires_at, i18n.language),
      });
    } else {
      freePriceMetaLabel = t('module.billing.package.free.priceNote', {
        days: trialOffer.valid_days,
      });
    }
  }

  return (
    <>
      <div className='flex justify-center'>
        <Tabs
          className='w-full'
          onValueChange={value => onShowcaseTabChange(value as ShowcaseTab)}
          value={showcaseTab}
        >
          <TabsList className='mx-auto h-auto rounded-[24px] bg-slate-100 p-1.5 shadow-sm'>
            <TabsTrigger
              className='rounded-[18px] px-5 py-2 text-xs font-semibold text-slate-500 data-[state=active]:bg-white data-[state=active]:text-slate-950 md:text-sm'
              value='monthly'
            >
              {t('module.billing.package.intervalTabs.monthly')}
            </TabsTrigger>
            <TabsTrigger
              className='rounded-[18px] px-5 py-2 text-xs font-semibold text-slate-500 data-[state=active]:bg-white data-[state=active]:text-slate-950 md:text-sm'
              value='yearly'
            >
              {t('module.billing.package.intervalTabs.yearly')}
            </TabsTrigger>
            <TabsTrigger
              className='rounded-[18px] px-5 py-2 text-xs font-semibold text-slate-500 data-[state=active]:bg-white data-[state=active]:text-slate-950 md:text-sm'
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
        <div className='grid gap-6 xl:grid-cols-2'>
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
                  credits: formatBillingCredits(
                    product.credit_amount,
                    i18n.language,
                  ),
                })}
                description={resolveBillingProductDescription(t, product)}
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
      ) : (
        <div
          className={cn(
            'grid gap-6',
            showcaseTab === 'yearly'
              ? 'xl:grid-cols-3'
              : renderFreeCard
                ? 'xl:grid-cols-3'
                : 'xl:grid-cols-2',
          )}
          data-testid='billing-plan-grid'
        >
          {renderFreeCard ? (
            <PlanShowcaseCard
              actionLabel={t(
                !hasActiveSubscription || trialOffer?.status === 'granted'
                  ? 'module.billing.package.actions.currentUsing'
                  : 'module.billing.package.actions.freeTrial',
              )}
              creditSummary={freeCreditSummary}
              creditValidityLabel={freeCreditValidityLabel}
              description={t('module.billing.package.free.description')}
              disabled
              featured={!hasActiveSubscription}
              footer={<PlanFeatureList items={getFreeFeatureKeys()} />}
              priceLabel={t('module.billing.package.free.priceValue')}
              priceMetaLabel={freePriceMetaLabel}
              testId='billing-plan-card-free'
              title={t('module.billing.package.free.title')}
            />
          ) : null}

          {(showcaseTab === 'monthly' ? monthlyPlans : yearlyPlans).map(
            plan => {
              const provider = resolveCheckoutProvider(
                stripeAvailable,
                pingxxAvailable,
              );
              const isCurrentPlan =
                currentPlan?.product_bid === plan.product_bid;
              const isFeatured = isCurrentPlan;
              const checkoutKey = provider
                ? `plan:${provider}:${plan.product_bid}`
                : '';

              return (
                <PlanShowcaseCard
                  key={plan.product_bid}
                  actionLabel={
                    isCurrentPlan
                      ? t('module.billing.package.actions.currentSubscription')
                      : hasActiveSubscription
                        ? t('module.billing.package.actions.upgradeNow')
                        : t('module.billing.package.actions.subscribeNow')
                  }
                  actionLoading={checkoutLoadingKey === checkoutKey}
                  creditSummary={resolveBillingPlanCreditsLabel(
                    t,
                    plan,
                    i18n.language,
                  )}
                  creditValidityLabel={t(
                    plan.billing_interval === 'year'
                      ? 'module.billing.package.validity.yearly'
                      : 'module.billing.package.validity.monthly',
                  )}
                  description={resolveBillingProductDescription(t, plan)}
                  disabled={!provider || isCurrentPlan}
                  featured={isFeatured}
                  footer={<PlanFeatureList items={getPlanFeatureKeys(plan)} />}
                  onAction={() =>
                    provider && onSelectPlanCheckout(plan, provider)
                  }
                  priceLabel={formatBillingPrice(
                    plan.price_amount,
                    plan.currency,
                    i18n.language,
                  )}
                  priceMetaLabel={formatBillingPlanInterval(t, plan)}
                  testId={`billing-plan-card-${plan.product_bid}`}
                  title={resolveBillingProductTitle(t, plan)}
                />
              );
            },
          )}
        </div>
      )}
    </>
  );
}
