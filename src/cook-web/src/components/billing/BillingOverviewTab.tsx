import React, { useCallback, useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import { CheckIcon, InformationCircleIcon } from '@heroicons/react/24/outline';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import api from '@/api';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { toast } from '@/hooks/useToast';
import { rememberStripeCheckoutSession } from '@/lib/stripe-storage';
import { useBillingOverview } from '@/hooks/useBillingOverview';
import type {
  BillingAlert,
  BillingCheckoutResult,
  BillingPlan,
  BillingProvider,
  BillingSubscription,
  BillingTopupProduct,
} from '@/types/billing';
import {
  buildBillingStripeResultUrls,
  extractBillingPingxxQrUrl,
  formatBillingCredits,
  formatBillingDate,
  formatBillingPlanInterval,
  formatBillingPrice,
  openBillingCheckoutUrl,
  openBillingPaymentWindow,
  registerBillingTranslationUsage,
  resolveBillingPlanCreditsLabel,
  resolveBillingProductDescription,
  resolveBillingProductTitle,
  resolveBillingSubscriptionStatusLabel,
} from '@/lib/billing';
import { cn } from '@/lib/utils';
import { BillingAlertsBanner } from './BillingAlertsBanner';
import { BillingCheckoutDialog } from './BillingCheckoutDialog';

type BillingCatalogResponse = {
  plans: BillingPlan[];
  topups: BillingTopupProduct[];
};

type BillingOverviewTabProps = {
  onOpenOrdersTab?: () => void;
};

type ShowcaseTab = 'monthly' | 'yearly' | 'topup';

type CheckoutTarget =
  | {
      kind: 'plan';
      product: BillingPlan;
      provider: BillingProvider;
    }
  | {
      kind: 'topup';
      product: BillingTopupProduct;
      provider: BillingProvider;
    }
  | null;

function getPlanFeatureKeys(product: BillingPlan): string[] {
  const productHighlights = product.highlights?.filter(item => Boolean(item));
  if (productHighlights && productHighlights.length > 0) {
    return productHighlights;
  }
  if (product.billing_interval === 'year') {
    return [
      'module.billing.package.features.yearly.pro.branding',
      'module.billing.package.features.yearly.pro.domain',
      'module.billing.package.features.yearly.pro.priority',
      'module.billing.package.features.yearly.pro.analytics',
      'module.billing.package.features.yearly.pro.support',
    ];
  }
  return [
    'module.billing.package.features.monthly.publish',
    'module.billing.package.features.monthly.preview',
    'module.billing.package.features.monthly.support',
  ];
}

function getFreeFeatureKeys(): string[] {
  return [
    'module.billing.package.features.free.publish',
    'module.billing.package.features.free.preview',
  ];
}

function PlanFeatureList({ items }: { items: string[] }) {
  const { t } = useTranslation();
  return (
    <div className='space-y-3'>
      <p className='text-sm font-semibold text-slate-950'>
        {t('module.billing.package.featuresTitle')}
      </p>
      <ul className='space-y-3'>
        {items.map(item => (
          <li
            key={item}
            className='flex items-center justify-between gap-4 text-sm text-slate-600'
          >
            <div className='flex items-center gap-3'>
              <CheckIcon className='h-5 w-5 text-slate-950' />
              <span>{t(item)}</span>
            </div>
            <InformationCircleIcon className='h-4 w-4 shrink-0 text-slate-300' />
          </li>
        ))}
      </ul>
    </div>
  );
}

type PlanShowcaseCardProps = {
  actionLabel: string;
  actionLoading?: boolean;
  compact?: boolean;
  creditSummary: string;
  description: string;
  disabled?: boolean;
  featured?: boolean;
  footer: React.ReactNode;
  onAction?: () => void;
  priceLabel: string;
  priceMetaLabel?: string;
  testId: string;
  title: string;
};

function PlanShowcaseCard({
  actionLabel,
  actionLoading = false,
  compact = false,
  creditSummary,
  description,
  disabled = false,
  featured = false,
  footer,
  onAction,
  priceLabel,
  priceMetaLabel,
  testId,
  title,
}: PlanShowcaseCardProps) {
  return (
    <div
      className={cn(
        'flex h-full flex-col rounded-[34px] border bg-white p-7 shadow-[0_20px_56px_rgba(15,23,42,0.08)] transition-all',
        compact ? 'min-h-[260px]' : 'min-h-[620px]',
        featured
          ? 'border-[#1d5bd8] bg-[radial-gradient(circle_at_top,#eef5ff_0%,#ffffff_72%)] shadow-[0_24px_64px_rgba(29,91,216,0.18)]'
          : 'border-slate-200',
      )}
      data-testid={testId}
    >
      <div className='space-y-4'>
        <h3
          className={cn(
            'text-xl font-semibold leading-tight tracking-tight md:text-2xl',
            featured ? 'text-[#1d5bd8]' : 'text-slate-950',
          )}
        >
          {title}
        </h3>
        <p className='min-h-[52px] text-sm leading-6 text-slate-500 md:text-base'>
          {description}
        </p>
      </div>

      <div className='mt-8 flex flex-wrap items-end gap-x-2 gap-y-1'>
        <div className='text-3xl font-semibold leading-none tracking-tight text-slate-950 md:text-4xl'>
          {priceLabel}
        </div>
        {priceMetaLabel ? (
          <div className='text-sm font-medium leading-6 text-slate-500 md:text-base'>
            {priceMetaLabel}
          </div>
        ) : null}
      </div>

      <Button
        className={cn(
          'mt-8 h-12 rounded-2xl text-sm font-semibold md:text-base',
          featured
            ? 'bg-[#1d5bd8] text-white hover:bg-[#194fbc]'
            : 'bg-slate-100 text-slate-900 hover:bg-slate-200',
        )}
        data-testid={`${testId}-action`}
        disabled={disabled || actionLoading}
        onClick={onAction}
        type='button'
        variant={featured ? 'default' : 'secondary'}
      >
        {actionLoading ? '...' : actionLabel}
      </Button>

      <div className='mt-8 rounded-[24px] border border-slate-200 bg-white/90 p-5 shadow-sm'>
        <div className='text-lg font-semibold leading-tight text-slate-950 md:text-xl'>
          {creditSummary}
        </div>
      </div>

      <div className='mt-8 flex-1'>{footer}</div>
    </div>
  );
}

type TopupCardProps = {
  actionLabel: string;
  actionLoading?: boolean;
  creditsLabel: string;
  description: string;
  disabled?: boolean;
  featured?: boolean;
  onAction?: () => void;
  priceLabel: string;
  testId: string;
};

function TopupCard({
  actionLabel,
  actionLoading = false,
  creditsLabel,
  description,
  disabled = false,
  featured = false,
  onAction,
  priceLabel,
  testId,
}: TopupCardProps) {
  return (
    <div
      className={cn(
        'flex min-h-[250px] flex-col justify-between rounded-[30px] border bg-white p-8 shadow-[0_18px_48px_rgba(15,23,42,0.08)]',
        featured
          ? 'border-[#1d5bd8] shadow-[0_24px_60px_rgba(29,91,216,0.16)]'
          : 'border-slate-200',
      )}
      data-testid={testId}
    >
      <div className='space-y-3'>
        <div className='flex items-center gap-4'>
          <div className='flex h-11 w-11 items-center justify-center rounded-2xl bg-[#eef5ff] text-[#1d5bd8]'>
            <InformationCircleIcon className='h-6 w-6' />
          </div>
          <div>
            <div className='text-xl font-semibold leading-tight text-slate-950 md:text-2xl'>
              {creditsLabel}
            </div>
            <div className='text-sm leading-6 text-slate-500'>
              {description}
            </div>
          </div>
        </div>
      </div>

      <div className='mt-8 flex items-end justify-between gap-4'>
        <div className='text-2xl font-semibold leading-none tracking-tight text-slate-950 md:text-3xl'>
          {priceLabel}
        </div>
        <Button
          className='h-11 rounded-2xl px-6 text-sm font-semibold'
          data-testid={`${testId}-action`}
          disabled={disabled || actionLoading}
          onClick={onAction}
          type='button'
        >
          {actionLoading ? '...' : actionLabel}
        </Button>
      </div>
    </div>
  );
}

export function BillingOverviewTab({
  onOpenOrdersTab,
}: BillingOverviewTabProps = {}) {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const {
    data: overview,
    error: overviewError,
    isLoading: overviewLoading,
    mutate: mutateOverview,
  } = useBillingOverview();
  const {
    data: catalog,
    error: catalogError,
    isLoading: catalogLoading,
  } = useSWR<BillingCatalogResponse>(
    ['billing-catalog'],
    async () => (await api.getBillingCatalog({})) as BillingCatalogResponse,
    {
      revalidateOnFocus: false,
    },
  );
  const { paymentChannels, runtimeConfigLoaded, stripeEnabled } = useEnvStore(
    useShallow((state: EnvStoreState) => ({
      paymentChannels: state.paymentChannels,
      runtimeConfigLoaded: state.runtimeConfigLoaded,
      stripeEnabled: state.stripeEnabled,
    })),
  );

  const [showcaseTab, setShowcaseTab] = useState<ShowcaseTab>('monthly');
  const [checkoutTarget, setCheckoutTarget] = useState<CheckoutTarget>(null);
  const [checkoutLoadingKey, setCheckoutLoadingKey] = useState('');
  const [subscriptionActionLoading, setSubscriptionActionLoading] = useState<
    'cancel' | 'resume' | ''
  >('');

  const normalizedPaymentChannels = useMemo(
    () => (paymentChannels || []).map(channel => channel.trim().toLowerCase()),
    [paymentChannels],
  );

  const stripeAvailable = useMemo(() => {
    if (!normalizedPaymentChannels.includes('stripe')) {
      return false;
    }
    return stripeEnabled === 'true' || !runtimeConfigLoaded;
  }, [normalizedPaymentChannels, runtimeConfigLoaded, stripeEnabled]);
  const pingxxAvailable = normalizedPaymentChannels.includes('pingxx');

  const currentPlan = useMemo(() => {
    if (!catalog?.plans?.length || !overview?.subscription?.product_bid) {
      return null;
    }
    return (
      catalog.plans.find(
        item => item.product_bid === overview.subscription?.product_bid,
      ) || null
    );
  }, [catalog?.plans, overview?.subscription?.product_bid]);

  useEffect(() => {
    if (currentPlan?.billing_interval === 'year') {
      setShowcaseTab(currentTab =>
        currentTab === 'monthly' ? 'yearly' : currentTab,
      );
    }
  }, [currentPlan?.billing_interval]);

  const monthlyPlans = useMemo(
    () =>
      (catalog?.plans || []).filter(
        product => product.billing_interval === 'month',
      ),
    [catalog?.plans],
  );
  const yearlyPlans = useMemo(
    () =>
      (catalog?.plans || []).filter(
        product => product.billing_interval === 'year',
      ),
    [catalog?.plans],
  );
  const topups = useMemo(() => catalog?.topups || [], [catalog?.topups]);
  const hasActiveSubscription = Boolean(
    overview?.subscription &&
    !['canceled', 'expired', 'draft'].includes(overview.subscription.status),
  );
  const firstAvailableTopup = useMemo(() => {
    const firstTopup = topups[0] || null;
    if (!firstTopup) {
      return null;
    }
    if (stripeAvailable) {
      return { product: firstTopup, provider: 'stripe' as const };
    }
    if (pingxxAvailable) {
      return { product: firstTopup, provider: 'pingxx' as const };
    }
    return null;
  }, [pingxxAvailable, stripeAvailable, topups]);

  const renewalMessage = useMemo(() => {
    if (!overview?.subscription?.current_period_end_at) {
      return t('module.billing.overview.subscriptionEmptyDescription');
    }
    const cycleDate = formatBillingDate(
      overview.subscription.current_period_end_at,
      i18n.language,
    );
    if (overview.subscription.cancel_at_period_end) {
      return t('module.billing.overview.subscriptionEndsOn', {
        date: cycleDate,
      });
    }
    return t('module.billing.overview.subscriptionRenewsOn', {
      date: cycleDate,
    });
  }, [i18n.language, overview?.subscription, t]);

  const handleCheckout = useCallback(async () => {
    if (!checkoutTarget) {
      return;
    }

    const loadingKey = `${checkoutTarget.kind}:${checkoutTarget.provider}:${checkoutTarget.product.product_bid}`;
    setCheckoutLoadingKey(loadingKey);
    try {
      let result: BillingCheckoutResult;
      if (checkoutTarget.kind === 'plan') {
        const stripeUrls =
          checkoutTarget.provider === 'stripe'
            ? buildBillingStripeResultUrls(window.location.origin)
            : { cancelUrl: '', successUrl: '' };
        result = (await api.checkoutBillingSubscription({
          cancel_url: stripeUrls.cancelUrl || undefined,
          payment_provider: checkoutTarget.provider,
          product_bid: checkoutTarget.product.product_bid,
          success_url: stripeUrls.successUrl || undefined,
        })) as BillingCheckoutResult;
      } else {
        const stripeUrls =
          checkoutTarget.provider === 'stripe'
            ? buildBillingStripeResultUrls(window.location.origin)
            : { cancelUrl: '', successUrl: '' };
        result = (await api.checkoutBillingTopup({
          cancel_url: stripeUrls.cancelUrl || undefined,
          channel:
            checkoutTarget.provider === 'pingxx' ? 'alipay_qr' : undefined,
          payment_provider: checkoutTarget.provider,
          product_bid: checkoutTarget.product.product_bid,
          success_url: stripeUrls.successUrl || undefined,
        })) as BillingCheckoutResult;
      }

      if (result.status === 'unsupported') {
        toast({
          title: t('module.billing.checkout.unsupported'),
          variant: 'destructive',
        });
        setCheckoutTarget(null);
        return;
      }

      if (checkoutTarget.provider === 'stripe' && result.redirect_url) {
        if (result.checkout_session_id) {
          rememberStripeCheckoutSession(
            result.checkout_session_id,
            result.billing_order_bid,
          );
        }
        setCheckoutTarget(null);
        openBillingCheckoutUrl(result.redirect_url);
        return;
      }

      if (checkoutTarget.provider === 'pingxx') {
        const qrUrl = extractBillingPingxxQrUrl(result);
        if (!qrUrl) {
          toast({
            title: t('module.billing.checkout.unsupported'),
            variant: 'destructive',
          });
          return;
        }
        const opened = openBillingPaymentWindow(qrUrl);
        toast({
          title: opened
            ? t('module.billing.checkout.qrOpened')
            : t('module.billing.checkout.qrBlocked'),
          variant: opened ? 'default' : 'destructive',
        });
        if (opened) {
          setCheckoutTarget(null);
        }
      }
    } catch (error: any) {
      toast({
        title: error?.message || t('common.core.unknownError'),
        variant: 'destructive',
      });
    } finally {
      setCheckoutLoadingKey('');
    }
  }, [checkoutTarget, t]);

  const handleSubscriptionMutation = useCallback(
    async (action: 'cancel' | 'resume', subscription: BillingSubscription) => {
      setSubscriptionActionLoading(action);
      try {
        const nextSubscription =
          action === 'cancel'
            ? ((await api.cancelBillingSubscription({
                subscription_bid: subscription.subscription_bid,
              })) as BillingSubscription)
            : ((await api.resumeBillingSubscription({
                subscription_bid: subscription.subscription_bid,
              })) as BillingSubscription);

        await mutateOverview(currentOverview => {
          if (!currentOverview) {
            return currentOverview;
          }
          return {
            ...currentOverview,
            subscription: nextSubscription,
          };
        }, false);

        toast({
          title:
            action === 'cancel'
              ? t('module.billing.overview.feedback.cancelSuccess')
              : t('module.billing.overview.feedback.resumeSuccess'),
        });
      } catch (error: any) {
        toast({
          title: error?.message || t('common.core.unknownError'),
          variant: 'destructive',
        });
      } finally {
        setSubscriptionActionLoading('');
      }
    },
    [mutateOverview, t],
  );

  const handleAlertAction = useCallback(
    (alert: BillingAlert) => {
      if (alert.action_type === 'checkout_topup') {
        if (firstAvailableTopup) {
          setShowcaseTab('topup');
          setCheckoutTarget({
            kind: 'topup',
            product: firstAvailableTopup.product,
            provider: firstAvailableTopup.provider,
          });
        }
        return;
      }

      if (
        alert.action_type === 'resume_subscription' &&
        overview?.subscription
      ) {
        void handleSubscriptionMutation('resume', overview.subscription);
        return;
      }

      if (alert.action_type === 'open_orders') {
        onOpenOrdersTab?.();
      }
    },
    [
      firstAvailableTopup,
      handleSubscriptionMutation,
      onOpenOrdersTab,
      overview?.subscription,
    ],
  );

  const dialogPriceLabel = useMemo(() => {
    if (!checkoutTarget) {
      return '';
    }
    return formatBillingPrice(
      checkoutTarget.product.price_amount,
      checkoutTarget.product.currency,
      i18n.language,
    );
  }, [checkoutTarget, i18n.language]);

  const dialogCreditsLabel = useMemo(() => {
    if (!checkoutTarget) {
      return '';
    }
    return formatBillingCredits(
      checkoutTarget.product.credit_amount,
      i18n.language,
    );
  }, [checkoutTarget, i18n.language]);

  const dialogProviderLabel = checkoutTarget
    ? checkoutTarget.provider === 'stripe'
      ? t('module.billing.catalog.labels.providerStripe')
      : t('module.billing.catalog.labels.providerPingxx')
    : '';

  const loadError = overviewError || catalogError;

  const renderFreeCard = showcaseTab === 'monthly';

  return (
    <section
      className='space-y-8'
      data-testid='billing-overview-tab'
    >
      <div className='space-y-4 text-center'>
        <div className='space-y-2'>
          <h1 className='text-2xl font-semibold tracking-tight text-slate-950 md:text-3xl'>
            {t('module.billing.package.title')}
          </h1>
          <p className='mx-auto max-w-4xl text-sm leading-7 text-slate-500 md:text-base'>
            {t('module.billing.package.subtitle')}
          </p>
        </div>

        {overview?.subscription ? (
          <div className='mx-auto max-w-5xl rounded-[28px] border border-slate-200 bg-white px-6 py-5 text-left shadow-[0_18px_40px_rgba(15,23,42,0.06)]'>
            <div className='flex flex-col gap-4 md:flex-row md:items-center md:justify-between'>
              <div className='space-y-1'>
                <div className='text-sm font-medium uppercase tracking-[0.12em] text-slate-400'>
                  {t('module.billing.overview.subscriptionTitle')}
                </div>
                <div className='flex flex-wrap items-center gap-3'>
                  <div className='text-lg font-semibold text-slate-950 md:text-xl'>
                    {currentPlan
                      ? resolveBillingProductTitle(t, currentPlan)
                      : t('module.billing.overview.subscriptionEmptyTitle')}
                  </div>
                  <span className='rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-600'>
                    {resolveBillingSubscriptionStatusLabel(
                      t,
                      overview.subscription.status,
                    )}
                  </span>
                </div>
                <div className='text-sm text-slate-500'>{renewalMessage}</div>
              </div>

              <div className='flex flex-wrap gap-3'>
                {overview.subscription.cancel_at_period_end ||
                overview.subscription.status === 'paused' ? (
                  <Button
                    className='rounded-2xl'
                    disabled={subscriptionActionLoading === 'resume'}
                    onClick={() =>
                      void handleSubscriptionMutation(
                        'resume',
                        overview.subscription as BillingSubscription,
                      )
                    }
                    type='button'
                  >
                    {subscriptionActionLoading === 'resume'
                      ? t('module.billing.catalog.actions.processing')
                      : t('module.billing.overview.actions.resumeSubscription')}
                  </Button>
                ) : (
                  <Button
                    className='rounded-2xl'
                    disabled={subscriptionActionLoading === 'cancel'}
                    onClick={() =>
                      void handleSubscriptionMutation(
                        'cancel',
                        overview.subscription as BillingSubscription,
                      )
                    }
                    type='button'
                    variant='outline'
                  >
                    {subscriptionActionLoading === 'cancel'
                      ? t('module.billing.catalog.actions.processing')
                      : t('module.billing.overview.actions.cancelSubscription')}
                  </Button>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {loadError ? (
        <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
          {t('module.billing.overview.loadError')}
        </div>
      ) : null}

      <BillingAlertsBanner
        alerts={overview?.billing_alerts || []}
        actionLoading={
          subscriptionActionLoading === 'resume' ? 'resume_subscription' : ''
        }
        isActionDisabled={alert => {
          if (alert.action_type === 'checkout_topup') {
            return !firstAvailableTopup;
          }
          if (alert.action_type === 'resume_subscription') {
            return !overview?.subscription;
          }
          if (alert.action_type === 'open_orders') {
            return !onOpenOrdersTab;
          }
          return false;
        }}
        onAlertAction={handleAlertAction}
      />

      <div className='flex justify-center'>
        <Tabs
          className='w-full'
          onValueChange={value => setShowcaseTab(value as ShowcaseTab)}
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

      {overviewLoading || catalogLoading ? (
        <div className='grid gap-6 xl:grid-cols-3'>
          <Skeleton className='h-[620px] rounded-[34px]' />
          <Skeleton className='h-[620px] rounded-[34px]' />
          <Skeleton className='h-[620px] rounded-[34px]' />
        </div>
      ) : showcaseTab === 'topup' ? (
        <div className='grid gap-6 xl:grid-cols-2'>
          {topups.map(product => {
            const provider = stripeAvailable
              ? 'stripe'
              : pingxxAvailable
                ? 'pingxx'
                : null;
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
                  provider &&
                  setCheckoutTarget({
                    kind: 'topup',
                    product,
                    provider,
                  })
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
            renderFreeCard ? 'xl:grid-cols-3' : 'xl:grid-cols-2',
          )}
        >
          {renderFreeCard ? (
            <PlanShowcaseCard
              actionLabel={t(
                hasActiveSubscription
                  ? 'module.billing.package.actions.freeTrial'
                  : 'module.billing.package.actions.currentUsing',
              )}
              compact={false}
              creditSummary={t('module.billing.package.free.creditSummary')}
              description={t('module.billing.package.free.description')}
              disabled
              footer={<PlanFeatureList items={getFreeFeatureKeys()} />}
              priceLabel={t('module.billing.package.free.priceValue')}
              priceMetaLabel={t('module.billing.package.free.priceNote')}
              testId='billing-plan-card-free'
              title={t('module.billing.package.free.title')}
            />
          ) : null}

          {(showcaseTab === 'monthly' ? monthlyPlans : yearlyPlans).map(
            (plan, index) => {
              const provider = stripeAvailable
                ? 'stripe'
                : pingxxAvailable
                  ? 'pingxx'
                  : null;
              const isCurrentPlan =
                currentPlan?.product_bid === plan.product_bid;
              const isFeatured =
                isCurrentPlan ||
                (!hasActiveSubscription && index === 0) ||
                Boolean(plan.status_badge_key);
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
                  description={resolveBillingProductDescription(t, plan)}
                  disabled={!provider || isCurrentPlan}
                  featured={isFeatured}
                  footer={<PlanFeatureList items={getPlanFeatureKeys(plan)} />}
                  onAction={() =>
                    provider &&
                    setCheckoutTarget({
                      kind: 'plan',
                      product: plan,
                      provider,
                    })
                  }
                  priceLabel={`${formatBillingPrice(
                    plan.price_amount,
                    plan.currency,
                    i18n.language,
                  )} ${formatBillingPlanInterval(t, plan)}`}
                  testId={`billing-plan-card-${plan.product_bid}`}
                  title={resolveBillingProductTitle(t, plan)}
                />
              );
            },
          )}
        </div>
      )}

      <BillingCheckoutDialog
        creditsLabel={dialogCreditsLabel}
        description={t(
          checkoutTarget?.kind === 'plan'
            ? 'module.billing.checkout.planDescription'
            : 'module.billing.checkout.topupDescription',
        )}
        isLoading={Boolean(checkoutLoadingKey)}
        open={Boolean(checkoutTarget)}
        priceLabel={dialogPriceLabel}
        productName={
          checkoutTarget
            ? t(checkoutTarget.product.display_name)
            : t('module.billing.checkout.productLabel')
        }
        providerLabel={dialogProviderLabel}
        onConfirm={() => void handleCheckout()}
        onOpenChange={open => {
          if (!open) {
            setCheckoutTarget(null);
          }
        }}
      />
    </section>
  );
}
