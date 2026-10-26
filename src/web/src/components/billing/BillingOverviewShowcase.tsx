import { useTranslation } from 'react-i18next';
import { Skeleton } from '@/components/ui/Skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import {
  formatBillingCreditAmount,
  formatBillingPrice,
  getBillingProductCampaignBonusCredits,
  hasBillingProductBonusCampaign,
  hasBillingProductDiscountCampaign,
  resolveBillingProductPayableAmount,
} from '@/lib/billing';
import type {
  BillingPlan,
  BillingProvider,
  BillingSubscription,
  BillingSubscriptionCheckoutAction,
  BillingTopupProduct,
  BillingTrialOffer,
} from '@/types/billing';
import { TopupCard } from './BillingOverviewCards';
import type { ShowcaseTab } from './BillingOverviewCards';
import { BillingOverviewFootnote } from './BillingOverviewFootnote';
import { BillingPlanComparisonTable } from './BillingPlanComparisonTable';
import styles from './BillingPlanComparisonTable.module.scss';

type BillingOverviewShowcaseProps = {
  checkoutLoadingKey: string;
  currentPlan: BillingPlan | null;
  currentSubscription: BillingSubscription | null;
  hasActiveSubscription: boolean;
  isTrialCurrentPlan: boolean;
  isLoading: boolean;
  monthlyPlans: BillingPlan[];
  orderedPlans: BillingPlan[];
  alipayAvailable: boolean;
  pingxxAvailable: boolean;
  renderFreeCard: boolean;
  showcaseTab: ShowcaseTab;
  stripeAvailable: boolean;
  topups: BillingTopupProduct[];
  trialOffer: BillingTrialOffer | null | undefined;
  wechatpayAvailable: boolean;
  yearlyPlans: BillingPlan[];
  onSelectPlanCheckout: (
    plan: BillingPlan,
    provider: BillingProvider,
    action?: BillingSubscriptionCheckoutAction,
  ) => void;
  onSelectTopupCheckout: (
    product: BillingTopupProduct,
    provider: BillingProvider,
  ) => void;
  onShowcaseTabChange: (tab: ShowcaseTab) => void;
};

function sortPlansByOrderedIndex(
  plans: BillingPlan[],
  ordered: BillingPlan[],
): BillingPlan[] {
  const indexOf = new Map<string, number>();
  ordered.forEach((plan, idx) => indexOf.set(plan.product_bid, idx));
  return [...plans].sort((a, b) => {
    const ai = indexOf.get(a.product_bid) ?? Number.MAX_SAFE_INTEGER;
    const bi = indexOf.get(b.product_bid) ?? Number.MAX_SAFE_INTEGER;
    return ai - bi;
  });
}

function resolveCheckoutProvider(
  stripeAvailable: boolean,
  pingxxAvailable: boolean,
  alipayAvailable: boolean,
  wechatpayAvailable: boolean,
): BillingProvider | null {
  if (stripeAvailable) {
    return 'stripe';
  }
  if (alipayAvailable) {
    return 'alipay';
  }
  if (wechatpayAvailable) {
    return 'wechatpay';
  }
  if (pingxxAvailable) {
    return 'pingxx';
  }
  return null;
}

export function BillingOverviewShowcase({
  checkoutLoadingKey,
  currentPlan,
  currentSubscription,
  hasActiveSubscription,
  isTrialCurrentPlan,
  isLoading,
  monthlyPlans,
  orderedPlans,
  alipayAvailable,
  pingxxAvailable,
  renderFreeCard,
  showcaseTab,
  stripeAvailable,
  topups,
  trialOffer,
  wechatpayAvailable,
  yearlyPlans,
  onSelectPlanCheckout,
  onSelectTopupCheckout,
  onShowcaseTabChange,
}: BillingOverviewShowcaseProps) {
  const { t, i18n } = useTranslation();
  const paidPlans = sortPlansByOrderedIndex(
    [...monthlyPlans, ...yearlyPlans],
    orderedPlans,
  );

  return (
    <>
      <div className='mb-8 flex justify-center'>
        <Tabs
          className='flex justify-center'
          onValueChange={value => onShowcaseTabChange(value as ShowcaseTab)}
          value={showcaseTab}
        >
          <TabsList className={styles.showcaseTabsList}>
            <TabsTrigger
              className={styles.showcaseTabsTrigger}
              value='plans'
            >
              {t('module.billing.package.intervalTabs.plans')}
            </TabsTrigger>
            <TabsTrigger
              className={styles.showcaseTabsTrigger}
              value='topup'
            >
              {t('module.billing.package.intervalTabs.topup')}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {isLoading ? (
        <div
          className='grid gap-6 xl:grid-cols-3'
          role='status'
        >
          <span className='sr-only'>{t('module.billing.package.loading')}</span>
          <Skeleton
            className='h-[620px] rounded-[34px]'
            aria-hidden='true'
          />
          <Skeleton
            className='h-[620px] rounded-[34px]'
            aria-hidden='true'
          />
          <Skeleton
            className='h-[620px] rounded-[34px]'
            aria-hidden='true'
          />
        </div>
      ) : showcaseTab === 'topup' ? (
        <div className='space-y-6'>
          <div
            className='grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]'
            data-testid='billing-topup-grid'
          >
            {topups.map(product => {
              const hasDiscountCampaign =
                hasBillingProductDiscountCampaign(product);
              const hasBonusCampaign = hasBillingProductBonusCampaign(product);
              const bonusCreditAmount =
                getBillingProductCampaignBonusCredits(product);
              const provider = resolveCheckoutProvider(
                stripeAvailable,
                pingxxAvailable,
                alipayAvailable,
                wechatpayAvailable,
              );
              const checkoutKey = provider
                ? `topup:${provider}:${product.product_bid}`
                : '';

              return (
                <TopupCard
                  key={product.product_bid}
                  actionLabel={t('module.billing.package.actions.buyNow')}
                  actionLoading={checkoutLoadingKey === checkoutKey}
                  campaignLabel={
                    hasDiscountCampaign
                      ? t('module.billing.package.campaign.discountBadge')
                      : hasBonusCampaign
                        ? t('module.billing.package.campaign.bonusBadge', {
                            credits:
                              formatBillingCreditAmount(bonusCreditAmount),
                          })
                        : undefined
                  }
                  creditsLabel={t('module.billing.package.topup.creditLabel', {
                    credits: formatBillingCreditAmount(product.credit_amount),
                  })}
                  disabled={!provider}
                  featured={Boolean(product.status_badge_key)}
                  onAction={() =>
                    provider && onSelectTopupCheckout(product, provider)
                  }
                  originalPriceLabel={
                    hasDiscountCampaign
                      ? formatBillingPrice(
                          product.price_amount,
                          product.currency,
                          i18n.language,
                        )
                      : undefined
                  }
                  priceLabel={formatBillingPrice(
                    resolveBillingProductPayableAmount(product),
                    product.currency,
                    i18n.language,
                  )}
                  testId={`billing-topup-card-${product.product_bid}`}
                />
              );
            })}
          </div>

          <div
            className='text-[length:var(--text-sm-font-size,14px)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'
            data-testid='billing-topup-note'
          >
            <ul className='list-disc space-y-2 pl-5'>
              <li>{t('module.billing.package.topup.noteInstant')}</li>
              <li>{t('module.billing.package.topup.noteFrozen')}</li>
            </ul>
          </div>
        </div>
      ) : (
        <div className='space-y-6'>
          <BillingPlanComparisonTable
            checkoutLoadingKey={checkoutLoadingKey}
            currentPlan={currentPlan}
            currentSubscription={currentSubscription}
            alipayAvailable={alipayAvailable}
            hasActiveSubscription={hasActiveSubscription}
            isTrialCurrentPlan={isTrialCurrentPlan}
            orderedPlans={orderedPlans}
            paidPlans={paidPlans}
            pingxxAvailable={pingxxAvailable}
            renderFreeColumn={renderFreeCard}
            stripeAvailable={stripeAvailable}
            trialOffer={trialOffer}
            wechatpayAvailable={wechatpayAvailable}
            onSelectPlanCheckout={onSelectPlanCheckout}
          />
          <BillingOverviewFootnote
            hasDiscountCampaign={paidPlans.some(
              hasBillingProductDiscountCampaign,
            )}
          />
        </div>
      )}
    </>
  );
}
