import React, { useMemo } from 'react';
import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { Button } from '@/components/ui/Button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  useBillingOverview,
  useBillingWalletBuckets,
} from '@/hooks/useBillingData';
import { useTracking } from '@/hooks/useTracking';
import { toast } from '@/hooks/useToast';
import type {
  BillingBucketCategory,
  BillingWalletBucket,
} from '@/types/billing';
import {
  formatBillingCreditBalance,
  formatBillingCreditDetail,
  formatBillingCompactDateTime,
  parseBillingDateValue,
  registerBillingTranslationUsage,
  resolveBillingBucketCategoryLabel,
} from '@/lib/billing';
import type { BillingSubscription } from '@/types/billing';

type BillingCreditDetailsPanelProps = {
  onUpgrade?: () => void;
  showSubscriptionManagement?: boolean;
};

const SUBSCRIPTION_RENEWAL_EVENTS = {
  attempt: 'creator_subscription_renewal_attempt',
  result: 'creator_subscription_renewal_result',
} as const;

type CategorySummaryRow = {
  category: BillingBucketCategory;
  availableCredits: number;
  effectiveTo: string | null;
};

const CATEGORY_ORDER: BillingBucketCategory[] = ['subscription', 'topup'];
const SUBSCRIPTION_FREE_SOURCE_TYPES = new Set(['gift', 'manual']);

function isBucketInCurrentWindow(
  bucket: BillingWalletBucket,
  now: Date,
): boolean {
  const effectiveFrom = parseBillingDateValue(bucket.effective_from);
  const effectiveTo = parseBillingDateValue(bucket.effective_to);

  return (
    (!effectiveFrom || effectiveFrom <= now) &&
    (!effectiveTo || effectiveTo > now)
  );
}

function hasBucketStarted(bucket: BillingWalletBucket, now: Date): boolean {
  const effectiveFrom = parseBillingDateValue(bucket.effective_from);

  return !effectiveFrom || effectiveFrom <= now;
}

function bucketRequiresActiveSubscription(
  bucket: BillingWalletBucket,
): boolean {
  if (bucket.category === 'topup') {
    return true;
  }

  return !SUBSCRIPTION_FREE_SOURCE_TYPES.has(bucket.source_type);
}

function buildCategorySummary(
  buckets: BillingWalletBucket[],
  options: {
    hasActiveSubscription: boolean;
    activeSubscriptionEffectiveTo: string | null;
    now?: Date;
  },
): CategorySummaryRow[] {
  const { activeSubscriptionEffectiveTo, hasActiveSubscription } = options;
  const now = options.now || new Date();

  return CATEGORY_ORDER.flatMap<CategorySummaryRow>(category => {
    const activeBuckets = buckets.filter(
      bucket =>
        bucket.category === category &&
        bucket.status === 'active' &&
        Number(bucket.available_credits || 0) > 0 &&
        (category === 'topup'
          ? hasBucketStarted(bucket, now)
          : isBucketInCurrentWindow(bucket, now) &&
            (hasActiveSubscription ||
              !bucketRequiresActiveSubscription(bucket))),
    );

    if (activeBuckets.length === 0) {
      return [
        {
          category,
          availableCredits: 0,
          effectiveTo: null,
        },
      ];
    }

    if (category === 'subscription') {
      const manualGrantExpiry = activeBuckets
        .filter(
          bucket =>
            bucket.source_type === 'manual' &&
            Boolean(bucket.effective_to?.trim()),
        )
        .map(bucket => bucket.effective_to as string)
        .sort((left, right) => left.localeCompare(right))[0];

      return [
        {
          category,
          availableCredits: activeBuckets.reduce(
            (total, bucket) => total + Number(bucket.available_credits || 0),
            0,
          ),
          effectiveTo: hasActiveSubscription
            ? activeSubscriptionEffectiveTo
            : manualGrantExpiry || null,
        },
      ];
    }

    return [
      {
        category,
        availableCredits: activeBuckets.reduce(
          (total, bucket) => total + Number(bucket.available_credits || 0),
          0,
        ),
        effectiveTo: null,
      },
    ];
  });
}

function CategoryValidityCell({
  availableCredits,
  category,
  effectiveTo,
  locale,
  emptyValidityLabel,
  neverExpiresLabel,
  topupAvailabilityLabel,
  topupAvailabilityTooltip,
}: {
  availableCredits: number;
  category: BillingBucketCategory;
  effectiveTo: string | null;
  locale: string;
  emptyValidityLabel: string;
  neverExpiresLabel: string;
  topupAvailabilityLabel: string;
  topupAvailabilityTooltip: string;
}) {
  if (category !== 'topup') {
    if (availableCredits <= 0) {
      return <>{emptyValidityLabel}</>;
    }

    if (effectiveTo) {
      return <>{formatBillingCompactDateTime(effectiveTo, locale)}</>;
    }

    return <>{neverExpiresLabel}</>;
  }

  return (
    <div className='flex items-center justify-end gap-1.5'>
      <span>{topupAvailabilityLabel}</span>
      <TooltipProvider delayDuration={0}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              aria-label={topupAvailabilityTooltip}
              className='inline-flex h-4 w-4 items-center justify-center text-muted-foreground transition-colors hover:text-foreground'
              data-testid='billing-topup-validity-tooltip-trigger'
              type='button'
            >
              <QuestionMarkCircleIcon className='h-4 w-4' />
            </button>
          </TooltipTrigger>
          <TooltipContent className='max-w-56 text-left leading-5'>
            {topupAvailabilityTooltip}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}

export function BillingCreditDetailsPanel({
  onUpgrade,
  showSubscriptionManagement = false,
}: BillingCreditDetailsPanelProps) {
  const { t, i18n } = useTranslation();
  const { trackEvent } = useTracking();
  const [pendingAction, setPendingAction] = React.useState<
    'cancel' | 'resume' | null
  >(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  registerBillingTranslationUsage(t);
  const {
    data: overview,
    error: overviewError,
    isLoading: overviewLoading,
    mutate: refreshOverview,
  } = useBillingOverview();
  const {
    data: bucketList,
    error: bucketsError,
    isLoading: bucketsLoading,
    mutate: refreshWalletBuckets,
  } = useBillingWalletBuckets();
  const subscriptionPeriodEnd = parseBillingDateValue(
    overview?.subscription?.current_period_end_at,
  );
  const hasActiveSubscription = Boolean(
    overview?.subscription &&
    !['canceled', 'expired', 'draft'].includes(overview.subscription.status) &&
    (!subscriptionPeriodEnd || subscriptionPeriodEnd > new Date()),
  );
  const activeSubscriptionEffectiveTo =
    hasActiveSubscription && overview?.subscription?.current_period_end_at
      ? String(overview.subscription.current_period_end_at)
      : null;

  React.useEffect(() => {
    if (overviewLoading || !overview?.creator_bid) {
      return;
    }

    void refreshWalletBuckets?.();
  }, [
    overview?.creator_bid,
    overview?.wallet?.available_credits,
    overview?.wallet?.reserved_credits,
    overview?.subscription?.status,
    overview?.subscription?.current_period_end_at,
    overviewLoading,
    refreshWalletBuckets,
  ]);

  const summaryRows = useMemo(
    () =>
      buildCategorySummary(bucketList?.items || [], {
        hasActiveSubscription,
        activeSubscriptionEffectiveTo,
      }),
    [activeSubscriptionEffectiveTo, bucketList?.items, hasActiveSubscription],
  );

  const totalCreditsLabel = formatBillingCreditBalance(
    overview?.wallet.available_credits || 0,
    i18n.language,
  );
  const emptyValidityLabel = t('module.billing.details.emptyValidityLabel');
  const neverExpiresLabel = t('module.billing.ledger.neverExpires');
  const topupAvailabilityLabel = t(
    'module.billing.details.topupAvailabilityLabel',
  );
  const topupAvailabilityTooltip = t(
    'module.billing.details.topupAvailabilityTooltip',
  );
  const loadError = overviewError || bucketsError;
  const subscription = overview?.subscription;
  const manageableSubscription =
    showSubscriptionManagement &&
    subscription?.billing_provider === 'stripe' &&
    hasActiveSubscription
      ? subscription
      : null;
  const currentPlanLabel = manageableSubscription?.product_name_key
    ? t(manageableSubscription.product_name_key)
    : t('module.billing.common.empty');
  const isPaused = manageableSubscription?.status === 'paused';
  const isResumeState = Boolean(
    manageableSubscription?.cancel_at_period_end ||
    manageableSubscription?.status === 'cancel_scheduled' ||
    manageableSubscription?.status === 'paused',
  );

  function reportRenewalEvent(
    eventName: (typeof SUBSCRIPTION_RENEWAL_EVENTS)[keyof typeof SUBSCRIPTION_RENEWAL_EVENTS],
    payload: Record<string, string>,
  ) {
    try {
      Promise.resolve(trackEvent(eventName, payload)).catch(() => {});
    } catch {
      // Analytics is best effort and must not alter subscription management.
    }
  }

  async function handleSubscriptionMutation() {
    if (!manageableSubscription || !pendingAction || isSubmitting) {
      return;
    }
    const action = pendingAction;
    const analyticsPayload = {
      action,
      source_surface: 'credit_details',
      payment_provider: 'stripe',
      subscription_bid: manageableSubscription.subscription_bid,
    };
    setIsSubmitting(true);
    try {
      reportRenewalEvent(SUBSCRIPTION_RENEWAL_EVENTS.attempt, analyticsPayload);
      const nextSubscription = (await (action === 'cancel'
        ? api.cancelBillingSubscription({
            subscription_bid: manageableSubscription.subscription_bid,
          })
        : api.resumeBillingSubscription({
            subscription_bid: manageableSubscription.subscription_bid,
          }))) as BillingSubscription;
      await refreshOverview?.(
        current =>
          current ? { ...current, subscription: nextSubscription } : current,
        false,
      );
      reportRenewalEvent(SUBSCRIPTION_RENEWAL_EVENTS.result, {
        ...analyticsPayload,
        outcome: 'success',
      });
      toast({
        title: t(
          action === 'cancel'
            ? 'module.billing.details.subscription.cancelSuccess'
            : 'module.billing.details.subscription.resumeSuccess',
        ),
      });
      setPendingAction(null);
    } catch {
      reportRenewalEvent(SUBSCRIPTION_RENEWAL_EVENTS.result, {
        ...analyticsPayload,
        outcome: 'failed',
      });
      toast({
        title: t('common.core.unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section
      className='space-y-6'
      data-testid='billing-credit-details-panel'
    >
      <Card className='gap-[var(--spacing-6,24px)] overflow-hidden rounded-[var(--border-radius-rounded-lg,10px)] border border-[var(--base-border,#E5E5E5)] bg-[#F6FAFF] shadow-[var(--shadow-xs-offset-x,0)_var(--shadow-xs-offset-y,1px)_var(--shadow-xs-blur-radius,2px)_var(--shadow-xs-spread-radius,0)_var(--shadow-xs-color,rgba(0,0,0,0.05))]'>
        <CardHeader className='gap-6 px-6 pb-0 pt-6 md:flex-row md:items-start md:justify-between'>
          <div className='space-y-1.5'>
            <div className='flex flex-wrap items-end gap-4'>
              <CardTitle className='text-[length:var(--text-2xl-font-size,24px)] font-[var(--font-weight-semibold,600)] leading-[var(--text-2xl-line-height,32px)] tracking-[var(--typography-components-h3-letter-spacing,-0.4px)] text-[var(--base-card-foreground,#0A0A0A)]'>
                {t('module.billing.details.totalCreditsLabel')}
              </CardTitle>
              {overviewLoading ? (
                <Skeleton className='h-12 w-36 rounded-xl' />
              ) : (
                <div className='text-[length:var(--text-2xl-font-size,24px)] font-[var(--font-weight-semibold,600)] leading-[var(--text-2xl-line-height,32px)] tracking-[var(--typography-components-h3-letter-spacing,-0.4px)] text-[var(--base-card-foreground,#0A0A0A)]'>
                  {totalCreditsLabel}
                </div>
              )}
            </div>
            <CardDescription className='max-w-3xl text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-normal,400)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'>
              {t('module.billing.details.totalCreditsDescription')}
            </CardDescription>
          </div>

          <Button
            className='h-[var(--height-h-9,36px)] gap-[var(--spacing-2,8px)] rounded-[var(--border-radius-rounded-md,8px)] bg-[var(--base-primary,#171717)] px-[var(--spacing-4,16px)] py-[var(--spacing-2,8px)] text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-primary-foreground,#FAFAFA)] shadow-[var(--shadow-xs-offset-x,0)_var(--shadow-xs-offset-y,1px)_var(--shadow-xs-blur-radius,2px)_var(--shadow-xs-spread-radius,0)_var(--shadow-xs-color,rgba(0,0,0,0.05))] hover:bg-[var(--base-primary,#171717)]'
            onClick={onUpgrade}
            type='button'
          >
            {t('module.billing.details.actions.upgradeNow')}
          </Button>
        </CardHeader>

        <CardContent className='px-6 pb-0 pt-5'>
          {loadError ? (
            <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
              {t('module.billing.ledger.loadError')}
            </div>
          ) : null}

          <div className='mt-0'>
            <div className='grid grid-cols-[1.4fr_0.7fr_0.9fr] border-b border-[var(--base-border,#E5E5E5)]'>
              <div className='flex h-[var(--height-h-10,40px)] min-w-[85px] items-center gap-2 px-[var(--spacing-2,8px)] text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'>
                <span>{t('module.billing.details.table.creditType')}</span>
              </div>
              <div className='flex h-[var(--height-h-10,40px)] min-w-[85px] items-center justify-end px-[var(--spacing-2,8px)] text-right text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'>
                {t('module.billing.details.table.balance')}
              </div>
              <div className='flex h-[var(--height-h-10,40px)] min-w-[85px] items-center justify-end px-[var(--spacing-2,8px)] text-right text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'>
                {t('module.billing.details.table.validUntil')}
              </div>
            </div>

            {bucketsLoading ? (
              <div className='space-y-4 px-2 py-4'>
                <Skeleton className='h-12 rounded-2xl' />
                <Skeleton className='h-12 rounded-2xl' />
                <Skeleton className='h-12 rounded-2xl' />
              </div>
            ) : (
              <div>
                {summaryRows.map(row => (
                  <div
                    key={`${row.category}:${row.effectiveTo || 'never-expires'}`}
                    className='grid grid-cols-[1.4fr_0.7fr_0.9fr] border-b border-[var(--base-border,#E5E5E5)] last:border-b-0'
                  >
                    <div className='px-[var(--spacing-2,8px)] py-4 text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                      {resolveBillingBucketCategoryLabel(t, row.category)}
                    </div>
                    <div className='px-[var(--spacing-2,8px)] py-4 text-right text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                      {formatBillingCreditDetail(
                        row.availableCredits,
                        i18n.language,
                      )}
                    </div>
                    <div className='px-[var(--spacing-2,8px)] py-4 text-right text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                      <CategoryValidityCell
                        availableCredits={row.availableCredits}
                        emptyValidityLabel={emptyValidityLabel}
                        category={row.category}
                        effectiveTo={row.effectiveTo}
                        locale={i18n.language}
                        neverExpiresLabel={neverExpiresLabel}
                        topupAvailabilityLabel={topupAvailabilityLabel}
                        topupAvailabilityTooltip={topupAvailabilityTooltip}
                      />
                    </div>
                  </div>
                ))}
                {manageableSubscription ? (
                  <div
                    className='flex flex-col gap-4 border-t border-[var(--base-border,#E5E5E5)] px-2 py-4 md:flex-row md:items-center md:justify-between'
                    data-testid='billing-subscription-management'
                  >
                    <div className='flex flex-wrap items-center gap-x-8 gap-y-2 text-sm leading-5'>
                      <div className='flex items-center gap-3'>
                        <span className='text-muted-foreground'>
                          {t('module.billing.details.subscription.currentPlan')}
                        </span>
                        <span className='font-medium text-foreground'>
                          {currentPlanLabel}
                        </span>
                      </div>
                      <div className='flex items-center gap-3'>
                        <span className='text-muted-foreground'>
                          {t(
                            'module.billing.details.subscription.renewalStatus',
                          )}
                        </span>
                        <span className='font-medium text-foreground'>
                          {t(
                            isPaused
                              ? 'module.billing.details.subscription.paused'
                              : isResumeState
                                ? 'module.billing.details.subscription.cancelScheduled'
                                : 'module.billing.details.subscription.autoRenew',
                          )}
                        </span>
                      </div>
                      <div className='flex items-center gap-3'>
                        <span className='text-muted-foreground'>
                          {t(
                            isResumeState
                              ? 'module.billing.details.subscription.accessUntil'
                              : 'module.billing.details.subscription.nextRenewal',
                          )}
                        </span>
                        <span className='font-medium text-foreground'>
                          {formatBillingCompactDateTime(
                            manageableSubscription.current_period_end_at,
                            i18n.language,
                          )}
                        </span>
                      </div>
                    </div>
                    <Button
                      className='shrink-0 self-start md:self-auto'
                      disabled={isSubmitting}
                      onClick={() =>
                        setPendingAction(isResumeState ? 'resume' : 'cancel')
                      }
                      type='button'
                      variant='outline'
                    >
                      {t(
                        isResumeState
                          ? 'module.billing.details.subscription.resumeAction'
                          : 'module.billing.details.subscription.cancelAction',
                      )}
                    </Button>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <AlertDialog
        open={pendingAction !== null}
        onOpenChange={open => {
          if (!open && !isSubmitting) {
            setPendingAction(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t(
                pendingAction === 'resume'
                  ? 'module.billing.details.subscription.resumeConfirmTitle'
                  : 'module.billing.details.subscription.cancelConfirmTitle',
              )}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t(
                pendingAction === 'resume'
                  ? 'module.billing.details.subscription.resumeConfirmDescription'
                  : 'module.billing.details.subscription.cancelConfirmDescription',
                {
                  date: formatBillingCompactDateTime(
                    manageableSubscription?.current_period_end_at,
                    i18n.language,
                  ),
                },
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isSubmitting}>
              {t('common.core.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={isSubmitting}
              onClick={event => {
                event.preventDefault();
                void handleSubscriptionMutation();
              }}
            >
              {t(
                pendingAction === 'resume'
                  ? 'module.billing.details.subscription.resumeConfirmAction'
                  : 'module.billing.details.subscription.cancelConfirmAction',
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
