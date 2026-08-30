import { useRef, useState } from 'react';
import useSWR, { mutate as mutateSWRCache } from 'swr';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import api from '@/api';
import { useTracking } from '@/c-common/hooks/useTracking';
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
import {
  buildCreatorBillingAttemptAnalytics,
  buildCreatorBillingResultAnalytics,
  buildCreatorBillingStatusAnalytics,
  CREATOR_BILLING_ANALYTICS_EVENTS,
  trackCreatorBillingEventSafely,
  type CreatorBillingAnalyticsBaseInput,
  type CreatorBillingFailureCategory,
  type CreatorBillingStatus,
} from '@/lib/billingAnalytics';
import { BillingAlertsBanner } from './BillingAlertsBanner';
import { BillingCheckoutDialog } from './BillingCheckoutDialog';
import { BillingOverviewShowcase } from './BillingOverviewShowcase';
import { BillingPingxxQrDialog } from './BillingPingxxQrDialog';
import {
  BillingStripeRedirectOverlay,
  type BillingStripeRedirectPhase,
} from './BillingStripeRedirectOverlay';
import type { ShowcaseTab } from './BillingOverviewCards';

type BillingCatalogResponse = {
  plans: BillingPlan[];
  topups: BillingTopupProduct[];
};

const INACTIVE_SUBSCRIPTION_STATUSES = new Set([
  'canceled',
  'expired',
  'draft',
]);
const BILLING_PASSIVE_REQUEST_CONFIG = { skipErrorToast: true } as const;

function isBillingSubscriptionActive(
  subscription: BillingSubscription | null | undefined,
): subscription is BillingSubscription {
  return (
    !!subscription && !INACTIVE_SUBSCRIPTION_STATUSES.has(subscription.status)
  );
}

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
  analyticsBase: CreatorBillingAnalyticsBaseInput;
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
  const { trackEvent } = useTracking();
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
    async () =>
      (await api.getBillingCatalog(
        {},
        BILLING_PASSIVE_REQUEST_CONFIG,
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
  const [checkoutAgreed, setCheckoutAgreed] = useState(false);
  const [stripeRedirect, setStripeRedirect] = useState<{
    phase: BillingStripeRedirectPhase;
    retryUrl?: string;
  } | null>(null);
  const [subscriptionActionLoading, setSubscriptionActionLoading] = useState<
    'cancel' | 'resume' | ''
  >('');
  const reportedAnalyticsKeysRef = useRef(new Set<string>());

  function reportCheckoutResult(
    analyticsBase: CreatorBillingAnalyticsBaseInput,
    outcome: 'success' | 'failed' | 'cancelled',
    failureCategory?: CreatorBillingFailureCategory,
  ) {
    const resultKey = analyticsBase.billOrderBid
      ? `result:${analyticsBase.billOrderBid}`
      : '';
    if (resultKey && reportedAnalyticsKeysRef.current.has(resultKey)) {
      return;
    }
    if (resultKey) {
      reportedAnalyticsKeysRef.current.add(resultKey);
    }
    trackCreatorBillingEventSafely(
      trackEvent,
      CREATOR_BILLING_ANALYTICS_EVENTS.result,
      buildCreatorBillingResultAnalytics({
        ...analyticsBase,
        outcome,
        failureCategory,
      }),
    );
  }

  function reportCheckoutStatus(
    analyticsBase: CreatorBillingAnalyticsBaseInput,
    status: CreatorBillingStatus,
  ) {
    const statusKey = analyticsBase.billOrderBid
      ? `status:${analyticsBase.billOrderBid}:${status}`
      : '';
    if (statusKey && reportedAnalyticsKeysRef.current.has(statusKey)) {
      return;
    }
    if (statusKey) {
      reportedAnalyticsKeysRef.current.add(statusKey);
    }
    trackCreatorBillingEventSafely(
      trackEvent,
      CREATOR_BILLING_ANALYTICS_EVENTS.status,
      buildCreatorBillingStatusAnalytics({
        ...analyticsBase,
        status,
      }),
    );
  }

  useBillingPingxxPolling({
    open: Boolean(pingxxCheckout),
    billingOrderBid: pingxxCheckout?.billingOrderBid || '',
    onResolved: async result => {
      if (pingxxCheckout?.analyticsBase) {
        const resolvedAnalyticsBase = {
          ...pingxxCheckout.analyticsBase,
          billOrderBid: result.bill_order_bid,
        };
        if (result.status === 'paid') {
          reportCheckoutResult(resolvedAnalyticsBase, 'success');
        } else if (result.status === 'canceled') {
          reportCheckoutResult(resolvedAnalyticsBase, 'cancelled');
        } else {
          reportCheckoutResult(
            resolvedAnalyticsBase,
            'failed',
            'payment_failed',
          );
        }
      }
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
  const activeSubscription = isBillingSubscriptionActive(overview?.subscription)
    ? overview.subscription
    : null;
  const currentPlan =
    plans.find(item => item.product_bid === activeSubscription?.product_bid) ||
    null;
  const pendingPreorderPlan =
    plans.find(
      item => item.product_bid === activeSubscription?.next_product_bid,
    ) || null;
  const monthlyPlans = plans.filter(
    product => product.billing_interval === 'month',
  );
  const yearlyPlans = plans.filter(
    product => product.billing_interval === 'year',
  );
  const hasActiveSubscription = Boolean(activeSubscription);
  const isTrialCurrentPlan = Boolean(
    hasActiveSubscription &&
    trialOffer?.product_bid &&
    activeSubscription?.product_bid === trialOffer.product_bid,
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

    const checkoutChannel = isQrBillingProvider(checkoutTarget.provider)
      ? checkoutTarget.provider === 'pingxx'
        ? selectedPingxxChannel
        : resolveDefaultBillingQrChannel(checkoutTarget.provider)
      : undefined;
    const analyticsBase: CreatorBillingAnalyticsBaseInput = {
      billingMarket: 'domestic',
      productType: checkoutTarget.kind,
      productBid: checkoutTarget.product.product_bid,
      productCode: checkoutTarget.product.product_code,
      billingInterval:
        checkoutTarget.kind === 'plan'
          ? checkoutTarget.product.billing_interval
          : 'one_time',
      priceAmount: resolveBillingProductPayableAmount(checkoutTarget.product),
      currency: checkoutTarget.product.currency,
      creditAmount: checkoutTarget.product.credit_amount,
      paymentProvider: checkoutTarget.provider,
      paymentChannel: checkoutChannel,
      checkoutAction:
        checkoutTarget.kind === 'topup'
          ? 'topup'
          : checkoutTarget.action || 'subscribe',
      sourceSurface: 'billing_overview',
      sourceTab: checkoutTarget.kind === 'plan' ? 'plans' : 'topup',
    };
    trackCreatorBillingEventSafely(
      trackEvent,
      CREATOR_BILLING_ANALYTICS_EVENTS.attempt,
      buildCreatorBillingAttemptAnalytics(analyticsBase),
    );

    const loadingKey = `${checkoutTarget.kind}:${checkoutTarget.provider}:${checkoutTarget.product.product_bid}`;
    const planAction =
      checkoutTarget.kind === 'plan' ? checkoutTarget.action : undefined;
    const loadingKeyWithAction =
      checkoutTarget.kind === 'plan'
        ? `${loadingKey}:${planAction || 'subscription'}`
        : loadingKey;
    const isStripeCheckout = checkoutTarget.provider === 'stripe';
    setCheckoutLoadingKey(loadingKeyWithAction);
    if (isStripeCheckout) {
      setStripeRedirect({ phase: 'creating' });
    }
    let catchFailureCategory: CreatorBillingFailureCategory =
      'checkout_request_failed';
    let catchAnalyticsBase = analyticsBase;
    let terminalResultReported = false;
    try {
      let result: BillingCheckoutResult;

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

      const resolvedAnalyticsBase: CreatorBillingAnalyticsBaseInput = {
        ...analyticsBase,
        paymentProvider: result.provider,
        billOrderBid: result.bill_order_bid,
      };
      catchAnalyticsBase = resolvedAnalyticsBase;

      if (result.status === 'unsupported') {
        reportCheckoutResult(resolvedAnalyticsBase, 'failed', 'unsupported');
        terminalResultReported = true;
        setStripeRedirect(null);
        toast({
          title: t('module.billing.checkout.unsupported'),
          variant: 'destructive',
        });
        setCheckoutTarget(null);
        setCheckoutAgreed(false);
        return;
      }

      if (result.status === 'paid') {
        reportCheckoutResult(resolvedAnalyticsBase, 'success');
        terminalResultReported = true;
        await refreshBillingData();
        setStripeRedirect(null);
        toast({
          title: t('module.billing.checkout.completed'),
        });
        setCheckoutTarget(null);
        setCheckoutAgreed(false);
        return;
      }
      if (result.status === 'failed') {
        reportCheckoutResult(resolvedAnalyticsBase, 'failed', 'payment_failed');
        terminalResultReported = true;
        setStripeRedirect(null);
        toast({
          title: t('module.billing.checkout.unsupported'),
          variant: 'destructive',
        });
        setCheckoutTarget(null);
        setCheckoutAgreed(false);
        return;
      }

      const resolvedProvider = result.provider;
      if (resolvedProvider === 'stripe' && result.redirect_url) {
        setStripeRedirect({
          phase: 'redirecting',
          retryUrl: result.redirect_url,
        });
        if (result.checkout_session_id) {
          rememberStripeCheckoutSession(
            result.checkout_session_id,
            result.bill_order_bid,
          );
        }
        setCheckoutTarget(null);
        setCheckoutAgreed(false);
        catchFailureCategory = 'redirect_failed';
        openBillingCheckoutUrl(result.redirect_url);
        reportCheckoutStatus(resolvedAnalyticsBase, 'pending');
        return;
      }
      if (resolvedProvider === 'stripe') {
        reportCheckoutResult(
          resolvedAnalyticsBase,
          'failed',
          'missing_redirect',
        );
        terminalResultReported = true;
        setStripeRedirect(null);
        toast({
          title: t('module.billing.checkout.unsupported'),
          variant: 'destructive',
        });
        setCheckoutTarget(null);
        setCheckoutAgreed(false);
        return;
      }

      if (isQrBillingProvider(resolvedProvider)) {
        setStripeRedirect(null);
        const preferredChannel =
          checkoutChannel ||
          (resolvedProvider === 'pingxx'
            ? selectedPingxxChannel
            : resolveDefaultBillingQrChannel(resolvedProvider));
        const qrCode = extractBillingPingxxQrCode(result, preferredChannel);
        if (!qrCode) {
          reportCheckoutStatus(
            {
              ...resolvedAnalyticsBase,
              paymentChannel: preferredChannel,
            },
            'confirmation_failed',
          );
          setStripeRedirect(null);
          toast({
            title: t('module.billing.checkout.unsupported'),
            variant: 'destructive',
          });
          return;
        }

        setPingxxCheckout({
          analyticsBase: {
            ...resolvedAnalyticsBase,
            paymentChannel: qrCode.channel,
          },
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
        reportCheckoutStatus(
          {
            ...resolvedAnalyticsBase,
            paymentChannel: qrCode.channel,
          },
          'pending',
        );
        setSelectedPingxxChannel(qrCode.channel);
        setCheckoutTarget(null);
        return;
      }

      reportCheckoutResult(resolvedAnalyticsBase, 'failed', 'unsupported');
      terminalResultReported = true;
      setStripeRedirect(null);
      toast({
        title: t('module.billing.checkout.unsupported'),
        variant: 'destructive',
      });
      setCheckoutTarget(null);
      setCheckoutAgreed(false);
    } catch (error: any) {
      if (!terminalResultReported) {
        reportCheckoutResult(
          catchAnalyticsBase,
          'failed',
          catchFailureCategory,
        );
      }
      setStripeRedirect(null);
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
    let terminalResultReported = false;
    try {
      const syncResult = (await api.syncBillingOrder({
        bill_order_bid: pingxxCheckout.billingOrderBid,
      })) as BillingSyncResult;
      if (syncResult.status !== 'pending') {
        const resolvedAnalyticsBase = {
          ...pingxxCheckout.analyticsBase,
          billOrderBid: syncResult.bill_order_bid,
        };
        if (syncResult.status === 'paid') {
          reportCheckoutResult(resolvedAnalyticsBase, 'success');
        } else if (syncResult.status === 'canceled') {
          reportCheckoutResult(resolvedAnalyticsBase, 'cancelled');
        } else {
          reportCheckoutResult(
            resolvedAnalyticsBase,
            'failed',
            'payment_failed',
          );
        }
        terminalResultReported = true;
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
        reportCheckoutResult(
          {
            ...pingxxCheckout.analyticsBase,
            paymentProvider: result.provider,
            paymentChannel: channel,
            billOrderBid: result.bill_order_bid,
          },
          'success',
        );
        terminalResultReported = true;
        await refreshBillingData();
        toast({
          title: t('module.billing.checkout.completed'),
        });
        setPingxxCheckout(null);
        setCheckoutAgreed(false);
        return;
      }
      const refreshedAnalyticsBase = {
        ...pingxxCheckout.analyticsBase,
        paymentProvider: result.provider,
        paymentChannel: channel,
        billOrderBid: result.bill_order_bid,
      };
      if (result.status === 'failed' || result.status === 'unsupported') {
        reportCheckoutResult(
          refreshedAnalyticsBase,
          'failed',
          result.status === 'failed' ? 'payment_failed' : 'unsupported',
        );
        terminalResultReported = true;
        toast({
          title: t('module.billing.checkout.unsupported'),
          variant: 'destructive',
        });
        return;
      }
      const qrCode = extractBillingPingxxQrCode(result, channel);
      if (!qrCode) {
        reportCheckoutStatus(refreshedAnalyticsBase, 'confirmation_failed');
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
              analyticsBase: {
                ...current.analyticsBase,
                paymentProvider: result.provider,
                paymentChannel: qrCode.channel,
                billOrderBid: result.bill_order_bid,
              },
              expiresInSeconds: result.expires_in_seconds,
              provider: result.provider,
              qrUrl: qrCode.url,
              selectedChannel: qrCode.channel,
            }
          : current,
      );
      reportCheckoutStatus(
        {
          ...pingxxCheckout.analyticsBase,
          paymentProvider: result.provider,
          paymentChannel: qrCode.channel,
          billOrderBid: result.bill_order_bid,
        },
        'pending',
      );
      setSelectedPingxxChannel(qrCode.channel);
    } catch (error: any) {
      if (!terminalResultReported) {
        reportCheckoutStatus(
          pingxxCheckout.analyticsBase,
          'confirmation_failed',
        );
      }
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

      {activeSubscription?.next_product_bid && pendingPreorderPlan ? (
        <div
          className='rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800'
          data-testid='billing-pending-preorder-banner'
        >
          {t('module.billing.package.preorder.pending', {
            plan: resolveBillingProductTitle(t, pendingPreorderPlan),
            date:
              formatBillingDateTime(
                activeSubscription.current_period_end_at,
                i18n.language,
              ) || t('module.billing.common.empty'),
          })}
        </div>
      ) : null}

      <BillingOverviewShowcase
        checkoutLoadingKey={checkoutLoadingKey}
        currentPlan={currentPlan}
        currentSubscription={activeSubscription}
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

      <BillingStripeRedirectOverlay
        open={Boolean(stripeRedirect)}
        phase={stripeRedirect?.phase || 'creating'}
        retryUrl={stripeRedirect?.retryUrl}
        onRetry={() => {
          if (stripeRedirect?.retryUrl) {
            openBillingCheckoutUrl(stripeRedirect.retryUrl);
          }
        }}
      />
    </section>
  );
}
