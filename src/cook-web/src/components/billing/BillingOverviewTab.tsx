import { useEffect, useState } from 'react';
import useSWR, { mutate as mutateSWRCache } from 'swr';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import api from '@/api';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { toast } from '@/hooks/useToast';
import { useBillingPingxxPolling } from '@/hooks/useBillingPingxxPolling';
import { getBrowserTimeZone } from '@/lib/browser-timezone';
import { rememberStripeCheckoutSession } from '@/lib/stripe-storage';
import {
  BILLING_WALLET_BUCKETS_SWR_KEY,
  useBillingOverview,
} from '@/hooks/useBillingData';
import type {
  BillingAlert,
  BillingCheckoutResult,
  BillingPingxxChannel,
  BillingPlan,
  BillingProvider,
  BillingSubscription,
  BillingTopupProduct,
} from '@/types/billing';
import {
  buildBillingSwrKey,
  buildBillingStripeResultUrls,
  extractBillingPingxxQrCode,
  formatBillingCredits,
  formatBillingPrice,
  openBillingCheckoutUrl,
  registerBillingTranslationUsage,
  withBillingTimezone,
} from '@/lib/billing';
import { BillingAlertsBanner } from './BillingAlertsBanner';
import { BillingCheckoutDialog } from './BillingCheckoutDialog';
import { BillingOverviewHero } from './BillingOverviewHero';
import { BillingOverviewShowcase } from './BillingOverviewShowcase';
import { BillingPingxxQrDialog } from './BillingPingxxQrDialog';
import type { ShowcaseTab } from './BillingOverviewCards';

type BillingCatalogResponse = {
  plans: BillingPlan[];
  topups: BillingTopupProduct[];
};

type BillingOverviewTabProps = {
  onOpenOrdersTab?: () => void;
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

type PingxxCheckoutState = {
  amountInMinor: number;
  billingOrderBid: string;
  currency: string;
  description: string;
  productName: string;
  qrUrl: string;
  selectedChannel: BillingPingxxChannel;
};

export function BillingOverviewTab({
  onOpenOrdersTab,
}: BillingOverviewTabProps = {}) {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const timezone = getBrowserTimeZone();

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
    buildBillingSwrKey('billing-catalog', timezone),
    async () =>
      (await api.getBillingCatalog(
        withBillingTimezone({}, timezone),
      )) as BillingCatalogResponse,
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
  const [pingxxCheckout, setPingxxCheckout] =
    useState<PingxxCheckoutState | null>(null);
  const [selectedPingxxChannel, setSelectedPingxxChannel] =
    useState<BillingPingxxChannel>('wx_pub_qr');
  const [subscriptionActionLoading, setSubscriptionActionLoading] = useState<
    'cancel' | 'resume' | ''
  >('');

  useBillingPingxxPolling({
    open: Boolean(pingxxCheckout),
    billingOrderBid: pingxxCheckout?.billingOrderBid || '',
    onResolved: async result => {
      await Promise.all([
        mutateOverview(),
        mutateSWRCache(
          buildBillingSwrKey(BILLING_WALLET_BUCKETS_SWR_KEY, timezone),
        ),
      ]);
      if (result.status !== 'pending') {
        setPingxxCheckout(null);
      }
    },
  });

  const normalizedPaymentChannels = (paymentChannels || []).map(channel =>
    channel.trim().toLowerCase(),
  );
  const stripeAvailable =
    normalizedPaymentChannels.includes('stripe') &&
    (stripeEnabled === 'true' || !runtimeConfigLoaded);
  const pingxxAvailable = normalizedPaymentChannels.includes('pingxx');
  const plans = catalog?.plans || [];
  const topups = catalog?.topups || [];
  const trialOffer = overview?.trial_offer;
  const currentPlan =
    plans.find(
      item => item.product_bid === overview?.subscription?.product_bid,
    ) || null;
  const dailyPlans = plans.filter(
    product => product.billing_interval === 'day',
  );
  const monthlyPlans = plans.filter(
    product => product.billing_interval === 'month',
  );
  const yearlyPlans = plans.filter(
    product => product.billing_interval === 'year',
  );
  const hasActiveSubscription = Boolean(
    overview?.subscription &&
    !['canceled', 'expired', 'draft'].includes(overview.subscription.status),
  );
  const isTrialCurrentPlan = Boolean(
    hasActiveSubscription &&
    trialOffer?.product_bid &&
    overview?.subscription?.product_bid === trialOffer.product_bid,
  );
  const firstAvailableTopup = topups[0]
    ? stripeAvailable
      ? { product: topups[0], provider: 'stripe' as const }
      : pingxxAvailable
        ? { product: topups[0], provider: 'pingxx' as const }
        : null
    : null;

  useEffect(() => {
    if (currentPlan?.billing_interval) {
      setShowcaseTab(currentTab => {
        if (currentTab === 'topup') {
          return currentTab;
        }
        if (currentPlan.billing_interval === 'day') {
          return 'daily';
        }
        if (currentPlan.billing_interval === 'year') {
          return 'yearly';
        }
        return 'monthly';
      });
    }
  }, [currentPlan?.billing_interval]);

  useEffect(() => {
    if (showcaseTab === 'daily' && dailyPlans.length === 0) {
      setShowcaseTab('monthly');
    }
  }, [dailyPlans.length, showcaseTab]);

  async function handleCheckout() {
    if (!checkoutTarget) {
      return;
    }

    const loadingKey = `${checkoutTarget.kind}:${checkoutTarget.provider}:${checkoutTarget.product.product_bid}`;
    setCheckoutLoadingKey(loadingKey);
    try {
      let result: BillingCheckoutResult;
      const stripeUrls =
        checkoutTarget.provider === 'stripe'
          ? buildBillingStripeResultUrls(window.location.origin)
          : { cancelUrl: '', successUrl: '' };

      if (checkoutTarget.kind === 'plan') {
        result = (await api.checkoutBillingSubscription({
          cancel_url: stripeUrls.cancelUrl || undefined,
          channel:
            checkoutTarget.provider === 'pingxx'
              ? selectedPingxxChannel
              : undefined,
          payment_provider: checkoutTarget.provider,
          product_bid: checkoutTarget.product.product_bid,
          success_url: stripeUrls.successUrl || undefined,
        })) as BillingCheckoutResult;
      } else {
        result = (await api.checkoutBillingTopup({
          cancel_url: stripeUrls.cancelUrl || undefined,
          channel:
            checkoutTarget.provider === 'pingxx'
              ? selectedPingxxChannel
              : undefined,
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
            result.bill_order_bid,
          );
        }
        setCheckoutTarget(null);
        openBillingCheckoutUrl(result.redirect_url);
        return;
      }

      if (checkoutTarget.provider === 'pingxx') {
        const qrCode = extractBillingPingxxQrCode(
          result,
          selectedPingxxChannel,
        );
        if (!qrCode) {
          toast({
            title: t('module.billing.checkout.unsupported'),
            variant: 'destructive',
          });
          return;
        }

        setPingxxCheckout({
          amountInMinor: checkoutTarget.product.price_amount,
          billingOrderBid: result.bill_order_bid,
          currency: checkoutTarget.product.currency,
          description: t(
            checkoutTarget.kind === 'plan'
              ? 'module.billing.checkout.planDescription'
              : 'module.billing.checkout.topupDescription',
          ),
          productName: t(checkoutTarget.product.display_name),
          qrUrl: qrCode.url,
          selectedChannel: qrCode.channel,
        });
        setSelectedPingxxChannel(qrCode.channel);
        setCheckoutTarget(null);
      }
    } catch (error: any) {
      toast({
        title: error?.message || t('common.core.unknownError'),
        variant: 'destructive',
      });
    } finally {
      setCheckoutLoadingKey('');
    }
  }

  async function handlePingxxQrChannelChange(channel: BillingPingxxChannel) {
    if (!pingxxCheckout) {
      return;
    }

    setCheckoutLoadingKey(
      `pingxx:${pingxxCheckout.billingOrderBid}:${channel}`,
    );
    try {
      const result = (await api.checkoutBillingOrder({
        bill_order_bid: pingxxCheckout.billingOrderBid,
        channel,
      })) as BillingCheckoutResult;
      const qrCode = extractBillingPingxxQrCode(result, channel);
      if (!qrCode) {
        toast({
          title: t('module.billing.checkout.unsupported'),
          variant: 'destructive',
        });
        return;
      }

      setPingxxCheckout(current =>
        current
          ? {
              ...current,
              qrUrl: qrCode.url,
              selectedChannel: qrCode.channel,
            }
          : current,
      );
      setSelectedPingxxChannel(qrCode.channel);
    } catch (error: any) {
      toast({
        title: error?.message || t('common.core.unknownError'),
        variant: 'destructive',
      });
    } finally {
      setCheckoutLoadingKey('');
    }
  }

  async function handleSubscriptionMutation(
    action: 'cancel' | 'resume',
    subscription: BillingSubscription,
  ) {
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
  }

  function handleAlertAction(alert: BillingAlert) {
    if (alert.action_type === 'checkout_topup') {
      if (firstAvailableTopup) {
        setShowcaseTab('topup');
        if (firstAvailableTopup.provider === 'pingxx') {
          setSelectedPingxxChannel('wx_pub_qr');
        }
        setCheckoutTarget({
          kind: 'topup',
          product: firstAvailableTopup.product,
          provider: firstAvailableTopup.provider,
        });
      }
      return;
    }

    if (alert.action_type === 'resume_subscription' && overview?.subscription) {
      void handleSubscriptionMutation('resume', overview.subscription);
      return;
    }

    if (alert.action_type === 'open_orders') {
      onOpenOrdersTab?.();
    }
  }

  const dialogPriceLabel = checkoutTarget
    ? formatBillingPrice(
        checkoutTarget.product.price_amount,
        checkoutTarget.product.currency,
        i18n.language,
      )
    : '';
  const dialogCreditsLabel = checkoutTarget
    ? formatBillingCredits(checkoutTarget.product.credit_amount, i18n.language)
    : '';
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
      <BillingOverviewHero />

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

      <BillingOverviewShowcase
        checkoutLoadingKey={checkoutLoadingKey}
        currentPlan={currentPlan}
        dailyPlans={dailyPlans}
        hasActiveSubscription={hasActiveSubscription}
        isTrialCurrentPlan={isTrialCurrentPlan}
        isLoading={overviewLoading || catalogLoading}
        monthlyPlans={monthlyPlans}
        orderedPlans={plans}
        pingxxAvailable={pingxxAvailable}
        renderFreeCard={renderFreeCard}
        showcaseTab={showcaseTab}
        stripeAvailable={stripeAvailable}
        topups={topups}
        trialOffer={trialOffer}
        yearlyPlans={yearlyPlans}
        onSelectPlanCheckout={(plan, provider) => {
          if (provider === 'pingxx') {
            setSelectedPingxxChannel('wx_pub_qr');
          }
          setCheckoutTarget({
            kind: 'plan',
            product: plan,
            provider,
          });
        }}
        onSelectTopupCheckout={(product, provider) => {
          if (provider === 'pingxx') {
            setSelectedPingxxChannel('wx_pub_qr');
          }
          setCheckoutTarget({
            kind: 'topup',
            product,
            provider,
          });
        }}
        onShowcaseTabChange={setShowcaseTab}
      />

      <BillingCheckoutDialog
        creditsLabel={dialogCreditsLabel}
        description={t(
          checkoutTarget?.kind === 'plan'
            ? 'module.billing.checkout.planDescription'
            : 'module.billing.checkout.topupDescription',
        )}
        isLoading={Boolean(checkoutLoadingKey)}
        open={Boolean(checkoutTarget)}
        pingxxChannel={
          checkoutTarget?.provider === 'pingxx' ? selectedPingxxChannel : null
        }
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
        onPingxxChannelChange={setSelectedPingxxChannel}
      />

      <BillingPingxxQrDialog
        amountInMinor={pingxxCheckout?.amountInMinor || 0}
        currency={pingxxCheckout?.currency || 'CNY'}
        description={pingxxCheckout?.description || ''}
        isLoading={Boolean(checkoutLoadingKey)}
        open={Boolean(pingxxCheckout)}
        productName={pingxxCheckout?.productName || ''}
        qrUrl={pingxxCheckout?.qrUrl || ''}
        selectedChannel={pingxxCheckout?.selectedChannel || 'wx_pub_qr'}
        onChannelChange={channel => void handlePingxxQrChannelChange(channel)}
        onOpenChange={open => {
          if (!open) {
            setPingxxCheckout(null);
          }
        }}
      />
    </section>
  );
}
