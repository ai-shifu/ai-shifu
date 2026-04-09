import React, { useCallback, useMemo, useState } from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import api from '@/api';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { Skeleton } from '@/components/ui/Skeleton';
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
  formatBillingCredits,
  openBillingCheckoutUrl,
  openBillingPaymentWindow,
  registerBillingTranslationUsage,
  resolveBillingNextActionLabel,
  resolveBillingSubscriptionStatusLabel,
} from '@/lib/billing';
import { BillingAlertsBanner } from './BillingAlertsBanner';
import { BillingCatalogCards } from './BillingCatalogCards';
import { BillingCheckoutDialog } from './BillingCheckoutDialog';
import { BillingMetricCard } from './BillingMetricCard';
import { BillingSubscriptionCard } from './BillingSubscriptionCard';

type BillingCatalogResponse = {
  plans: BillingPlan[];
  topups: BillingTopupProduct[];
};

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

function extractPingxxQrUrl(result: BillingCheckoutResult): string {
  const credential =
    typeof result.payment_payload === 'object' && result.payment_payload
      ? (result.payment_payload as Record<string, unknown>).credential
      : null;
  if (!credential || typeof credential !== 'object') {
    return '';
  }
  const qrUrl = (credential as Record<string, unknown>).alipay_qr;
  return typeof qrUrl === 'string' ? qrUrl : '';
}

type BillingOverviewTabProps = {
  onOpenOrdersTab?: () => void;
};

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
  const firstAvailableTopup = useMemo(() => {
    const firstTopup = catalog?.topups?.[0] || null;
    if (!firstTopup) {
      return null;
    }
    if (stripeAvailable) {
      return {
        product: firstTopup,
        provider: 'stripe' as const,
      };
    }
    if (pingxxAvailable) {
      return {
        product: firstTopup,
        provider: 'pingxx' as const,
      };
    }
    return null;
  }, [catalog?.topups, pingxxAvailable, stripeAvailable]);

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

  const availableCredits = overview?.wallet.available_credits || 0;
  const availableCreditsLabel = overview
    ? formatBillingCredits(availableCredits, i18n.language)
    : t('module.billing.sidebar.placeholderValue');
  const subscriptionStatusLabel = overview
    ? resolveBillingSubscriptionStatusLabel(t, overview.subscription?.status)
    : t('module.billing.overview.pendingValue');
  const nextActionLabel = overview
    ? resolveBillingNextActionLabel(t, overview.subscription, availableCredits)
    : t('module.billing.overview.pendingValue');
  const loadError = overviewError || catalogError;

  const handleCheckout = useCallback(async () => {
    if (!checkoutTarget) {
      return;
    }

    const loadingKey = `${checkoutTarget.kind}:${checkoutTarget.provider}:${checkoutTarget.product.product_bid}`;
    setCheckoutLoadingKey(loadingKey);
    try {
      let result: BillingCheckoutResult;
      if (checkoutTarget.kind === 'plan') {
        const { cancelUrl, successUrl } = buildBillingStripeResultUrls(
          window.location.origin,
        );
        result = (await api.checkoutBillingSubscription({
          cancel_url: cancelUrl,
          payment_provider: checkoutTarget.provider,
          product_bid: checkoutTarget.product.product_bid,
          success_url: successUrl,
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
        const qrUrl = extractPingxxQrUrl(result);
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

  const openPlanCheckout = useCallback(
    (plan: BillingPlan, provider: BillingProvider) => {
      setCheckoutTarget({
        kind: 'plan',
        product: plan,
        provider,
      });
    },
    [],
  );

  const openTopupCheckout = useCallback(
    (topup: BillingTopupProduct, provider: BillingProvider) => {
      setCheckoutTarget({
        kind: 'topup',
        product: topup,
        provider,
      });
    },
    [],
  );

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
          openTopupCheckout(
            firstAvailableTopup.product,
            firstAvailableTopup.provider,
          );
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
      openTopupCheckout,
      overview?.subscription,
    ],
  );

  const dialogPriceLabel = useMemo(() => {
    if (!checkoutTarget) {
      return '';
    }
    return new Intl.NumberFormat(i18n.language, {
      style: 'currency',
      currency: checkoutTarget.product.currency || 'CNY',
      maximumFractionDigits: 2,
    }).format(Number(checkoutTarget.product.price_amount || 0) / 100);
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

  return (
    <div className='space-y-6'>
      <div>
        <h3 className='text-lg font-semibold text-slate-900'>
          {t('module.billing.overview.walletTitle')}
        </h3>
      </div>

      <div className='grid gap-4 md:grid-cols-3'>
        <BillingMetricCard
          label={t('module.billing.overview.availableCreditsLabel')}
          value={availableCreditsLabel}
        />
        <BillingMetricCard
          label={t('module.billing.overview.subscriptionStatusLabel')}
          value={subscriptionStatusLabel}
        />
        <BillingMetricCard
          label={t('module.billing.overview.nextActionLabel')}
          value={nextActionLabel}
        />
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

      {overviewLoading && catalogLoading ? (
        <div className='grid gap-4 xl:grid-cols-[0.92fr,1.08fr]'>
          <Skeleton className='h-[280px] rounded-[24px]' />
          <Skeleton className='h-[420px] rounded-[24px]' />
        </div>
      ) : (
        <div className='grid gap-4 xl:grid-cols-[0.92fr,1.08fr]'>
          <BillingSubscriptionCard
            currentPlan={currentPlan}
            subscription={overview?.subscription || null}
            actionLoading={subscriptionActionLoading}
            onCancelSubscription={subscription =>
              void handleSubscriptionMutation('cancel', subscription)
            }
            onResumeSubscription={subscription =>
              void handleSubscriptionMutation('resume', subscription)
            }
          />
          <BillingCatalogCards
            checkoutLoadingKey={checkoutLoadingKey}
            plans={catalog?.plans || []}
            stripeAvailable={stripeAvailable}
            subscription={overview?.subscription || null}
            topups={catalog?.topups || []}
            pingxxAvailable={pingxxAvailable}
            onCheckoutPlan={openPlanCheckout}
            onCheckoutTopup={openTopupCheckout}
          />
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
    </div>
  );
}
