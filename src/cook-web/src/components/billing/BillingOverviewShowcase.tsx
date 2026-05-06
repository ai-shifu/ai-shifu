import { useTranslation } from 'react-i18next';
import { Skeleton } from '@/components/ui/Skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { formatBillingCreditAmount, formatBillingPrice } from '@/lib/billing';
import type {
  BillingPlan,
  BillingProvider,
  BillingTopupProduct,
  BillingTrialOffer,
} from '@/types/billing';
import { TopupCard } from './BillingOverviewCards';
import type { ShowcaseTab } from './BillingOverviewCards';
import { BillingPlanComparisonTable } from './BillingPlanComparisonTable';

type BillingOverviewShowcaseProps = {
  checkoutLoadingKey: string;
  currentPlan: BillingPlan | null;
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
  onSelectPlanCheckout: (plan: BillingPlan, provider: BillingProvider) => void;
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
          <TabsList className='h-[var(--height-h-9,36px)] rounded-[var(--border-radius-rounded-lg,10px)] bg-[var(--base-muted,#F5F5F5)] p-[3px]'>
            <TabsTrigger
              className='h-full rounded-[var(--border-radius-rounded-md,8px)] border border-transparent px-6 py-[var(--spacing-1,4px)] text-center text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)] data-[state=active]:border-[var(--custom-dark-input,rgba(255,255,255,0.00))] data-[state=active]:bg-[var(--custom-background-dark-input-30,#FFF)] data-[state=active]:shadow-[var(--shadow-sm-1-offset-x,0)_var(--shadow-sm-1-offset-y,1px)_var(--shadow-sm-1-blur-radius,3px)_var(--shadow-sm-1-spread-radius,0)_var(--shadow-sm-1-color,rgba(0,0,0,0.10)),var(--shadow-sm-2-offset-x,0)_var(--shadow-sm-2-offset-y,1px)_var(--shadow-sm-2-blur-radius,2px)_var(--shadow-sm-2-spread-radius,-1px)_var(--shadow-sm-2-color,rgba(0,0,0,0.10))]'
              value='plans'
            >
              {t('module.billing.package.intervalTabs.plans')}
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
            className='grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]'
            data-testid='billing-topup-grid'
          >
            {topups.map(product => {
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
        <BillingPlanComparisonTable
          checkoutLoadingKey={checkoutLoadingKey}
          currentPlan={currentPlan}
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
      )}
    </>
  );
}
