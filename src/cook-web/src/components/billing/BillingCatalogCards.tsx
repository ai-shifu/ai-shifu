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
  title: string;
  children: React.ReactNode;
};

function CatalogCardShell({
  badgeLabel,
  creditsLabel,
  description,
  priceLabel,
  title,
  children,
}: CatalogCardShellProps) {
  return (
    <Card className='h-full border-slate-200 bg-white/90 shadow-[0_12px_28px_rgba(15,23,42,0.06)]'>
      <CardHeader className='gap-4'>
        <div className='flex items-start justify-between gap-3'>
          <div className='space-y-2'>
            <CardTitle className='text-xl text-slate-900'>{title}</CardTitle>
            <CardDescription className='leading-6 text-slate-500'>
              {description}
            </CardDescription>
          </div>
          {badgeLabel ? (
            <Badge className='bg-amber-100 text-amber-800'>{badgeLabel}</Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className='space-y-5'>
        <div className='rounded-2xl bg-slate-50 p-4'>
          <div className='text-3xl font-semibold tracking-tight text-slate-900'>
            {priceLabel}
          </div>
          <div className='mt-2 text-sm font-medium text-slate-600'>
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
        <h4 className='text-base font-semibold text-slate-900'>{title}</h4>
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
    <div className='space-y-5'>
      <CatalogSection title={t('module.billing.catalog.sections.plans')}>
        <div className='grid gap-4 xl:grid-cols-2'>
          {plans.map(plan => {
            const checkoutKey = `plan:stripe:${plan.product_bid}`;
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
                creditsLabel={t(
                  'module.billing.catalog.labels.creditsPerCycle',
                  {
                    credits: formatBillingCredits(
                      plan.credit_amount,
                      i18n.language,
                    ),
                  },
                )}
                description={resolveBillingProductDescription(t, plan)}
                priceLabel={`${formatBillingPrice(
                  plan.price_amount,
                  plan.currency,
                  i18n.language,
                )} ${formatBillingPlanInterval(t, plan)}`}
                title={resolveBillingProductTitle(t, plan)}
              >
                <div className='flex gap-3'>
                  <Button
                    className='flex-1 rounded-xl'
                    disabled={
                      isCurrentPlan ||
                      !stripeAvailable ||
                      checkoutLoadingKey === checkoutKey
                    }
                    onClick={() => onCheckoutPlan(plan, 'stripe')}
                  >
                    {isCurrentPlan
                      ? t('module.billing.catalog.actions.currentPlan')
                      : checkoutLoadingKey === checkoutKey
                        ? t('module.billing.catalog.actions.processing')
                        : stripeAvailable
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
        <div className='grid gap-4 xl:grid-cols-2'>
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
                    className='rounded-xl'
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
                    className='rounded-xl'
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
