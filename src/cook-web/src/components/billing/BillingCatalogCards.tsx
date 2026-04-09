import React from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { cn } from '@/lib/utils';
import type {
  BillingPlan,
  BillingProvider,
  BillingSubscription,
  BillingTopupProduct,
} from '@/types/billing';
import {
  formatBillingCredits,
  formatBillingPlanInterval,
  formatBillingPrice,
  resolveBillingPlanCreditsLabel,
  resolveBillingProductDescription,
  resolveBillingProductTitle,
} from '@/lib/billing';

type BillingCatalogCardsProps = {
  checkoutLoadingKey?: string;
  plans: BillingPlan[];
  stripeAvailable: boolean;
  subscription: BillingSubscription | null;
  topups: BillingTopupProduct[];
  pingxxAvailable: boolean;
  onCheckoutPlan: (plan: BillingPlan, provider: BillingProvider) => void;
  onCheckoutTopup: (
    topup: BillingTopupProduct,
    provider: BillingProvider,
  ) => void;
};

type CatalogCardShellProps = {
  badgeLabel?: string;
  creditsLabel: string;
  description: string;
  priceLabel: string;
  tone?: 'plan' | 'topup';
  title: string;
  children: React.ReactNode;
};

function CatalogCardShell({
  badgeLabel,
  creditsLabel,
  description,
  priceLabel,
  tone = 'plan',
  title,
  children,
}: CatalogCardShellProps) {
  return (
    <Card
      className={cn(
        'h-full overflow-hidden rounded-[28px] border-slate-200 shadow-[0_18px_40px_rgba(15,23,42,0.08)]',
        tone === 'plan'
          ? 'bg-[linear-gradient(180deg,#ffffff_0%,#f8fbff_100%)]'
          : 'bg-[linear-gradient(180deg,#ffffff_0%,#fffaf3_100%)]',
      )}
    >
      <CardHeader className='gap-5 pb-5'>
        <div className='flex items-start justify-between gap-3'>
          <div className='space-y-3'>
            <CardTitle className='text-xl leading-tight text-slate-950 md:text-2xl'>
              {title}
            </CardTitle>
            <CardDescription className='text-sm leading-6 text-slate-500 md:text-base md:leading-7'>
              {description}
            </CardDescription>
          </div>
          {badgeLabel ? (
            <Badge className='rounded-full bg-amber-100 px-3 py-1 text-amber-800'>
              {badgeLabel}
            </Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className='space-y-5'>
        <div className='rounded-[24px] border border-white/80 bg-white/90 p-5 shadow-sm'>
          <div className='text-2xl font-semibold tracking-tight text-slate-950 md:text-3xl'>
            {priceLabel}
          </div>
          <div className='mt-3 text-sm font-medium text-slate-600'>
            {creditsLabel}
          </div>
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

function CatalogSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className='space-y-3'>
      <div className='flex items-center justify-between gap-3'>
        <h4 className='text-lg font-semibold tracking-tight text-slate-950'>
          {title}
        </h4>
      </div>
      {children}
    </div>
  );
}

export function BillingCatalogCards({
  checkoutLoadingKey = '',
  plans,
  stripeAvailable,
  subscription,
  topups,
  pingxxAvailable,
  onCheckoutPlan,
  onCheckoutTopup,
}: BillingCatalogCardsProps) {
  const { t, i18n } = useTranslation();

  const currentProductBid = subscription?.product_bid || '';

  return (
    <div className='space-y-8'>
      <CatalogSection title={t('module.billing.catalog.sections.plans')}>
        <div className='grid gap-5 xl:grid-cols-2'>
          {plans.map(plan => {
            const provider = stripeAvailable
              ? 'stripe'
              : pingxxAvailable
                ? 'pingxx'
                : null;
            const checkoutKey = provider
              ? `plan:${provider}:${plan.product_bid}`
              : '';
            const isCurrentPlan =
              currentProductBid === plan.product_bid &&
              subscription?.status !== 'expired' &&
              subscription?.status !== 'canceled';

            return (
              <CatalogCardShell
                key={plan.product_bid}
                badgeLabel={
                  plan.status_badge_key ? t(plan.status_badge_key) : undefined
                }
                creditsLabel={resolveBillingPlanCreditsLabel(
                  t,
                  plan,
                  i18n.language,
                )}
                description={resolveBillingProductDescription(t, plan)}
                priceLabel={`${formatBillingPrice(
                  plan.price_amount,
                  plan.currency,
                  i18n.language,
                )} ${formatBillingPlanInterval(t, plan)}`}
                tone='plan'
                title={resolveBillingProductTitle(t, plan)}
              >
                <div className='flex gap-3'>
                  <Button
                    className='flex-1 rounded-full'
                    disabled={
                      isCurrentPlan ||
                      !provider ||
                      checkoutLoadingKey === checkoutKey
                    }
                    onClick={() => provider && onCheckoutPlan(plan, provider)}
                  >
                    {isCurrentPlan
                      ? t('module.billing.catalog.actions.currentPlan')
                      : checkoutLoadingKey === checkoutKey
                        ? t('module.billing.catalog.actions.processing')
                        : provider
                          ? t('module.billing.catalog.actions.subscribe')
                          : t('module.billing.catalog.actions.unavailable')}
                  </Button>
                </div>
              </CatalogCardShell>
            );
          })}
        </div>
      </CatalogSection>

      <CatalogSection title={t('module.billing.catalog.sections.topups')}>
        <div className='grid gap-5 xl:grid-cols-2'>
          {topups.map(product => {
            const stripeKey = `topup:stripe:${product.product_bid}`;
            const pingxxKey = `topup:pingxx:${product.product_bid}`;

            return (
              <CatalogCardShell
                key={product.product_bid}
                badgeLabel={
                  product.status_badge_key
                    ? t(product.status_badge_key)
                    : undefined
                }
                creditsLabel={t(
                  'module.billing.catalog.labels.creditsOneTime',
                  {
                    credits: formatBillingCredits(
                      product.credit_amount,
                      i18n.language,
                    ),
                  },
                )}
                description={resolveBillingProductDescription(t, product)}
                priceLabel={formatBillingPrice(
                  product.price_amount,
                  product.currency,
                  i18n.language,
                )}
                tone='topup'
                title={resolveBillingProductTitle(t, product)}
              >
                <div
                  className={cn(
                    'grid gap-3',
                    stripeAvailable && pingxxAvailable
                      ? 'sm:grid-cols-2'
                      : 'sm:grid-cols-1',
                  )}
                >
                  <Button
                    className='rounded-full'
                    disabled={
                      !stripeAvailable || checkoutLoadingKey === stripeKey
                    }
                    onClick={() => onCheckoutTopup(product, 'stripe')}
                    variant='default'
                  >
                    {checkoutLoadingKey === stripeKey
                      ? t('module.billing.catalog.actions.processing')
                      : stripeAvailable
                        ? t('module.billing.catalog.actions.buyWithStripe')
                        : t('module.billing.catalog.actions.unavailable')}
                  </Button>
                  <Button
                    className='rounded-full'
                    disabled={
                      !pingxxAvailable || checkoutLoadingKey === pingxxKey
                    }
                    onClick={() => onCheckoutTopup(product, 'pingxx')}
                    variant='outline'
                  >
                    {checkoutLoadingKey === pingxxKey
                      ? t('module.billing.catalog.actions.processing')
                      : pingxxAvailable
                        ? t('module.billing.catalog.actions.buyWithPingxx')
                        : t('module.billing.catalog.actions.unavailable')}
                  </Button>
                </div>
              </CatalogCardShell>
            );
          })}
        </div>
      </CatalogSection>
    </div>
  );
}
