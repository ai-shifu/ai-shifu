import { useState } from 'react';
import useSWR, { mutate as mutateSWRCache } from 'swr';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import api from '@/api';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { toast } from '@/hooks/useToast';
import { useBillingPingxxPolling } from '@/hooks/useBillingPingxxPolling';
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
  BillingSyncResult,
  BillingSubscription,
  BillingSubscriptionCheckoutAction,
  BillingTopupProduct,
} from '@/types/billing';
import {
  buildBillingSwrKey,
  extractBillingPingxxQrCode,
  formatBillingCredits,
  formatBillingDateTime,
  formatBillingPrice,
  getBillingProductCampaignBonusCredits,
  hasBillingProductBonusCampaign,
  openBillingCheckoutUrl,
  resolveBillingProductPayableAmount,
  registerBillingTranslationUsage,
  resolveBillingPingxxChannelLabel,
  resolveBillingProductTitle,
  resolveBillingProviderLabel,
} from '@/lib/billing';
import { BillingAlertsBanner } from './BillingAlertsBanner';
import { BillingCheckoutDialog } from './BillingCheckoutDialog';
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
      action?: BillingSubscriptionCheckoutAction;
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
  expiresInSeconds?: number | null;
  productName: string;
  provider: BillingProvider;
  qrUrl: string;
  selectedChannel: BillingPingxxChannel;
  prepaidOffsetAmount?: number;
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

function resolveCheckoutChannelLabel(
  t: ReturnType<typeof useTranslation>['t'],
  target: CheckoutTarget,
  selectedPingxxChannel: BillingPingxxChannel,
): string {
  if (!target) {
    return '';
  }

  if (target.provider === 'pingxx') {
    return t('module.billing.catalog.labels.providerWithChannel', {
      provider: resolveBillingProviderLabel(t, target.provider),
      channel: resolveBillingPingxxChannelLabel(t, selectedPingxxChannel),
    });
  }

  if (target.provider === 'alipay') {
    return resolveBillingPingxxChannelLabel(t, 'alipay_qr');
  }

  if (target.provider === 'wechatpay') {
    return resolveBillingPingxxChannelLabel(t, 'wx_pub_qr');
  }

  return resolveBillingProviderLabel(t, target.provider);
}

function resolvePlanCheckoutDescriptionKey(
  action?: BillingSubscriptionCheckoutAction,
  hasPrepaidOffset = false,
): string {
  if (action === 'preorder') {
    return 'module.billing.checkout.preorderDescription';
  }
  if (action === 'upgrade_immediate') {
    if (hasPrepaidOffset) {
      return 'module.billing.checkout.upgradeWithPreorderDescription';
    }
    return 'module.billing.checkout.upgradeDescription';
  }
  return 'module.billing.checkout.planDescription';
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
    buildBillingSwrKey('billing-catalog'),
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

  const [showcaseTab, setShowcaseTab] = useState<ShowcaseTab>('plans');
  const [checkoutTarget, setCheckoutTarget] = useState<CheckoutTarget>(null);
  const [checkoutLoadingKey, setCheckoutLoadingKey] = useState('');
  const [pingxxCheckout, setPingxxCheckout] =
    useState<PingxxCheckoutState | null>(null);
  const [selectedPingxxChannel, setSelectedPingxxChannel] =
    useState<BillingPingxxChannel>('wx_pub_qr');
  const [checkoutAgreed, setCheckoutAgreed] = useState(false);
  const [subscriptionActionLoading, setSubscriptionActionLoading] = useState<
    'cancel' | 'resume' | ''
  >('');

  useBillingPingxxPolling({
    open: Boolean(pingxxCheckout),
    billingOrderBid: pingxxCheckout?.billingOrderBid || '',
    onResolved: async result => {
      await refreshBillingData();
      if (result.status !== 'pending') {
        setPingxxCheckout(null);
        setCheckoutAgreed(false);
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
  const pendingPreorderPlan =
    plans.find(
      item => item.product_bid === overview?.subscription?.next_product_bid,
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

  async function refreshBillingData() {
    await Promise.all([
      mutateOverview(),
      mutateSWRCache(buildBillingSwrKey(BILLING_WALLET_BUCKETS_SWR_KEY)),
    ]);
  }

  async function handleCheckout() {
    if (!checkoutTarget) {
      return;
    }

    const loadingKey = `${checkoutTarget.kind}:${checkoutTarget.provider}:${checkoutTarget.product.product_bid}`;
    const planAction =
      checkoutTarget.kind === 'plan' ? checkoutTarget.action : undefined;
    const loadingKeyWithAction =
      checkoutTarget.kind === 'plan'
        ? `${loadingKey}:${planAction || 'subscription'}`
        : loadingKey;
    setCheckoutLoadingKey(loadingKeyWithAction);
    try {
      let result: BillingCheckoutResult;
      const checkoutChannel = isQrBillingProvider(checkoutTarget.provider)
        ? checkoutTarget.provider === 'pingxx'
          ? selectedPingxxChannel
          : resolveDefaultBillingQrChannel(checkoutTarget.provider)
        : undefined;

      if (checkoutTarget.kind === 'plan') {
        result = (await api.checkoutBillingSubscription({
          action: checkoutTarget.action,
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
        setCheckoutAgreed(false);
        return;
      }

      if (result.status === 'paid') {
        await refreshBillingData();
        toast({
          title: t('module.billing.checkout.completed'),
        });
        setCheckoutTarget(null);
        setCheckoutAgreed(false);
        return;
      }

      const resolvedProvider = result.provider;
      if (resolvedProvider === 'stripe' && result.redirect_url) {
        if (result.checkout_session_id) {
          rememberStripeCheckoutSession(
            result.checkout_session_id,
            result.bill_order_bid,
          );
        }
        setCheckoutTarget(null);
        setCheckoutAgreed(false);
        openBillingCheckoutUrl(result.redirect_url);
        return;
      }

      if (isQrBillingProvider(resolvedProvider)) {
        const preferredChannel =
          checkoutChannel ||
          (resolvedProvider === 'pingxx'
            ? selectedPingxxChannel
            : resolveDefaultBillingQrChannel(resolvedProvider));
        const qrCode = extractBillingPingxxQrCode(result, preferredChannel);
        if (!qrCode) {
          toast({
            title: t('module.billing.checkout.unsupported'),
            variant: 'destructive',
          });
          return;
        }

        setPingxxCheckout({
          amountInMinor:
            result.payable_amount ??
            resolveBillingProductPayableAmount(checkoutTarget.product),
          billingOrderBid: result.bill_order_bid,
          currency: result.currency || checkoutTarget.product.currency,
          description: t(
            checkoutTarget.kind === 'plan'
              ? resolvePlanCheckoutDescriptionKey(
                  checkoutTarget.action,
                  (result.prepaid_offset_amount || 0) > 0,
                )
              : 'module.billing.checkout.topupDescription',
          ),
          expiresInSeconds: result.expires_in_seconds,
          productName: resolveBillingProductTitle(t, checkoutTarget.product),
          provider: resolvedProvider,
          qrUrl: qrCode.url,
          selectedChannel: qrCode.channel,
          prepaidOffsetAmount: result.prepaid_offset_amount || 0,
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
      const syncResult = (await api.syncBillingOrder({
        bill_order_bid: pingxxCheckout.billingOrderBid,
      })) as BillingSyncResult;
      if (syncResult.status !== 'pending') {
        await refreshBillingData();
        if (syncResult.status === 'paid') {
          toast({
            title: t('module.billing.checkout.completed'),
          });
        }
        setPingxxCheckout(null);
        setCheckoutAgreed(false);
        return;
      }

      const result = (await api.checkoutBillingOrder({
        bill_order_bid: pingxxCheckout.billingOrderBid,
        channel,
      })) as BillingCheckoutResult;
      if (result.status === 'paid') {
        await refreshBillingData();
        toast({
          title: t('module.billing.checkout.completed'),
        });
        setPingxxCheckout(null);
        setCheckoutAgreed(false);
        return;
      }
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
              expiresInSeconds: result.expires_in_seconds,
              provider: result.provider,
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
        setCheckoutAgreed(false);
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
        resolveBillingProductPayableAmount(checkoutTarget.product),
        checkoutTarget.product.currency,
        i18n.language,
      )
    : '';
  const dialogCreditsLabel = checkoutTarget
    ? hasBillingProductBonusCampaign(checkoutTarget.product)
      ? t('module.billing.checkout.bonusCreditsLabel', {
          baseCredits: formatBillingCredits(
            checkoutTarget.product.credit_amount,
            i18n.language,
          ),
          bonusCredits: formatBillingCredits(
            getBillingProductCampaignBonusCredits(checkoutTarget.product),
            i18n.language,
          ),
        })
      : formatBillingCredits(
          checkoutTarget.product.credit_amount,
          i18n.language,
        )
    : '';
  const dialogProviderLabel = checkoutTarget
    ? resolveCheckoutChannelLabel(t, checkoutTarget, selectedPingxxChannel)
    : '';
  const dialogHasPrepaidOffset =
    checkoutTarget?.kind === 'plan' &&
    checkoutTarget.action === 'upgrade_immediate' &&
    Boolean(overview?.subscription?.next_product_bid);
  const dialogDescription = checkoutTarget
    ? t(
        checkoutTarget.kind === 'plan'
          ? resolvePlanCheckoutDescriptionKey(
              checkoutTarget.action,
              dialogHasPrepaidOffset,
            )
          : 'module.billing.checkout.topupDescription',
      )
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

      {overview?.subscription?.next_product_bid && pendingPreorderPlan ? (
        <div
          className='rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800'
          data-testid='billing-pending-preorder-banner'
        >
          {t('module.billing.package.preorder.pending', {
            plan: resolveBillingProductTitle(t, pendingPreorderPlan),
            date:
              formatBillingDateTime(
                overview.subscription.current_period_end_at,
                i18n.language,
              ) || t('module.billing.common.empty'),
          })}
        </div>
      ) : null}

      <BillingOverviewShowcase
        checkoutLoadingKey={checkoutLoadingKey}
        currentPlan={currentPlan}
        currentSubscription={overview?.subscription || null}
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
        onSelectPlanCheckout={(plan, provider, action) => {
          if (isQrBillingProvider(provider)) {
            setSelectedPingxxChannel(resolveDefaultBillingQrChannel(provider));
          }
          setCheckoutAgreed(false);
          setCheckoutTarget({
            kind: 'plan',
            product: plan,
            provider,
            action,
          });
        }}
        onSelectTopupCheckout={(product, provider) => {
          if (isQrBillingProvider(provider)) {
            setSelectedPingxxChannel(resolveDefaultBillingQrChannel(provider));
          }
          setCheckoutAgreed(false);
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
        description={dialogDescription}
        isLoading={Boolean(checkoutLoadingKey)}
        open={Boolean(checkoutTarget)}
        pingxxChannel={
          checkoutTarget?.provider === 'pingxx' ? selectedPingxxChannel : null
        }
        priceLabel={dialogPriceLabel}
        productName={
          checkoutTarget
            ? resolveBillingProductTitle(t, checkoutTarget.product)
            : t('module.billing.checkout.productLabel')
        }
        providerLabel={dialogProviderLabel}
        agreed={checkoutAgreed}
        onConfirm={() => void handleCheckout()}
        onAgreedChange={setCheckoutAgreed}
        onOpenChange={open => {
          if (!open) {
            setCheckoutTarget(null);
            setCheckoutAgreed(false);
          }
        }}
        onPingxxChannelChange={setSelectedPingxxChannel}
      />

      <BillingPingxxQrDialog
        amountInMinor={pingxxCheckout?.amountInMinor || 0}
        currency={pingxxCheckout?.currency || 'CNY'}
        description={pingxxCheckout?.description || ''}
        expiresInSeconds={pingxxCheckout?.expiresInSeconds ?? null}
        isLoading={Boolean(checkoutLoadingKey)}
        open={Boolean(pingxxCheckout)}
        productName={pingxxCheckout?.productName || ''}
        provider={pingxxCheckout?.provider || 'pingxx'}
        qrUrl={pingxxCheckout?.qrUrl || ''}
        selectedChannel={pingxxCheckout?.selectedChannel || 'wx_pub_qr'}
        prepaidOffsetAmount={pingxxCheckout?.prepaidOffsetAmount || 0}
        agreed={checkoutAgreed}
        onChannelChange={channel => void handlePingxxQrChannelChange(channel)}
        onAgreedChange={setCheckoutAgreed}
        onOpenChange={open => {
          if (!open) {
            void refreshBillingData();
            setPingxxCheckout(null);
            setCheckoutAgreed(false);
          }
        }}
      />
    </section>
  );
}
