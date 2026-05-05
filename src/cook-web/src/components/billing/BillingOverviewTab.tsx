import { useState } from 'react';
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
  extractBillingPingxxQrCode,
  formatBillingCredits,
  formatBillingPrice,
  openBillingCheckoutUrl,
  registerBillingTranslationUsage,
  resolveBillingProviderLabel,
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
  provider: BillingProvider;
  qrUrl: string;
  selectedChannel: BillingPingxxChannel;
};

const QR_BILLING_PROVIDERS = new Set<BillingProvider>([
  'pingxx',
  'alipay',
  'wechatpay',
]);

function isQrBillingProvider(provider: BillingProvider): boolean {
  return QR_BILLING_PROVIDERS.has(provider);
}

function resolveDefaultBillingQrChannel(
  provider: BillingProvider,
): BillingPingxxChannel {
  if (provider === 'wechatpay') {
    return 'wx_pub_qr';
  }
  if (provider === 'alipay') {
    return 'alipay_qr';
  }
  return 'wx_pub_qr';
}

function resolveFirstBillingProvider(
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

  const [showcaseTab, setShowcaseTab] = useState<ShowcaseTab>('plans');
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
  const alipayAvailable = normalizedPaymentChannels.includes('alipay');
  const wechatpayAvailable = normalizedPaymentChannels.includes('wechatpay');
  const plans = catalog?.plans || [];
  const topups = catalog?.topups || [];
  const trialOffer = overview?.trial_offer;
  const currentPlan =
    plans.find(
      item => item.product_bid === overview?.subscription?.product_bid,
    ) || null;
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
    ? (() => {
        const provider = resolveFirstBillingProvider(
          stripeAvailable,
          pingxxAvailable,
          alipayAvailable,
          wechatpayAvailable,
        );
        return provider ? { product: topups[0], provider } : null;
      })()
    : null;

  async function handleCheckout() {
    if (!checkoutTarget) {
      return;
    }

    const loadingKey = `${checkoutTarget.kind}:${checkoutTarget.provider}:${checkoutTarget.product.product_bid}`;
    setCheckoutLoadingKey(loadingKey);
    try {
      let result: BillingCheckoutResult;
      const checkoutChannel = isQrBillingProvider(checkoutTarget.provider)
        ? checkoutTarget.provider === 'pingxx'
          ? selectedPingxxChannel
          : resolveDefaultBillingQrChannel(checkoutTarget.provider)
        : undefined;

      if (checkoutTarget.kind === 'plan') {
        result = (await api.checkoutBillingSubscription({
          channel: checkoutChannel,
          payment_provider: checkoutTarget.provider,
          product_bid: checkoutTarget.product.product_bid,
        })) as BillingCheckoutResult;
      } else {
        result = (await api.checkoutBillingTopup({
          channel: checkoutChannel,
          payment_provider: checkoutTarget.provider,
          product_bid: checkoutTarget.product.product_bid,
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

      if (isQrBillingProvider(checkoutTarget.provider) && checkoutChannel) {
        const qrCode = extractBillingPingxxQrCode(result, checkoutChannel);
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
          provider: checkoutTarget.provider,
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
        if (isQrBillingProvider(firstAvailableTopup.provider)) {
          setSelectedPingxxChannel(
            resolveDefaultBillingQrChannel(firstAvailableTopup.provider),
          );
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
    ? resolveBillingProviderLabel(t, checkoutTarget.provider)
    : '';
  const loadError = overviewError || catalogError;
  // Trial column hidden in the comparison table; keep trial data wiring so the
  // 15-day basic-plan grant flow can re-enable rendering by flipping this flag.
  const renderFreeCard = false;

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
        hasActiveSubscription={hasActiveSubscription}
        isTrialCurrentPlan={isTrialCurrentPlan}
        isLoading={overviewLoading || catalogLoading}
        monthlyPlans={monthlyPlans}
        orderedPlans={plans}
        alipayAvailable={alipayAvailable}
        pingxxAvailable={pingxxAvailable}
        renderFreeCard={renderFreeCard}
        showcaseTab={showcaseTab}
        stripeAvailable={stripeAvailable}
        topups={topups}
        trialOffer={trialOffer}
        wechatpayAvailable={wechatpayAvailable}
        yearlyPlans={yearlyPlans}
        onSelectPlanCheckout={(plan, provider) => {
          if (isQrBillingProvider(provider)) {
            setSelectedPingxxChannel(resolveDefaultBillingQrChannel(provider));
          }
          setCheckoutTarget({
            kind: 'plan',
            product: plan,
            provider,
          });
        }}
        onSelectTopupCheckout={(product, provider) => {
          if (isQrBillingProvider(provider)) {
            setSelectedPingxxChannel(resolveDefaultBillingQrChannel(provider));
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
        provider={pingxxCheckout?.provider || 'pingxx'}
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
