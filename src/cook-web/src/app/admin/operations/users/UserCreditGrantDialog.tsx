'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { v4 as uuidv4 } from 'uuid';
import api from '@/api';
import { formatAdminCredits } from '@/app/admin/lib/numberFormat';
import { useToast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import {
  formatBillingCompactDateTime,
  resolveBillingPlanValidityLabel,
} from '@/lib/billing';
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { Textarea } from '@/components/ui/Textarea';
import { formatOperatorUtcDateTime } from './dateTime';
import type {
  AdminOperationUserBenefitGrantResponse,
  AdminOperationUserCreditGrantRequest,
  AdminOperationUserCreditGrantResponse,
  AdminOperationUserGrantBootstrapResponse,
  AdminOperationUserItem,
  AdminOperationUserPackageGrantRequest,
  AdminOperationUserPackageGrantResponse,
} from '../operation-user-types';
import type { BillingPlan } from '@/types/billing';

type UserCreditGrantDialogProps = {
  open: boolean;
  user: AdminOperationUserItem | null;
  onOpenChange: (open: boolean) => void;
  onGranted: (result: AdminOperationUserBenefitGrantResponse) => void;
};

type GrantMode = 'credits' | 'package';

type CreditFormState = {
  source: string;
  amount: string;
  validityPreset: string;
  note: string;
};

type PackageFormState = {
  productBid: string;
  note: string;
};

type FormErrors = Partial<
  Record<
    | 'source'
    | 'amount'
    | 'validityPreset'
    | 'productBid'
    | 'bootstrap'
    | 'submit',
    string
  >
>;

const BASE_CREDIT_FORM_STATE: Omit<CreditFormState, 'validityPreset'> = {
  source: 'reward',
  amount: '',
  note: '',
};

const BASE_PACKAGE_FORM_STATE: PackageFormState = {
  productBid: '',
  note: '',
};

const resolveDefaultValidityPreset = (
  hasActiveSubscription: boolean,
): CreditFormState['validityPreset'] =>
  hasActiveSubscription ? 'align_subscription' : '1d';

const buildDefaultCreditFormState = (
  hasActiveSubscription: boolean,
): CreditFormState => ({
  ...BASE_CREDIT_FORM_STATE,
  validityPreset: resolveDefaultValidityPreset(hasActiveSubscription),
});

const resolveCurrentExpiry = (
  user: AdminOperationUserItem | null,
  longTermLabel: string,
): string => {
  if (!user) {
    return '--';
  }
  if (user.credits_expire_at) {
    return formatOperatorUtcDateTime(user.credits_expire_at);
  }
  if (Number(user.available_credits || 0) > 0) {
    return longTermLabel;
  }
  return '--';
};

const validatePositiveAmount = (value: string): boolean => {
  const normalized = value.trim();
  if (!normalized) {
    return false;
  }
  const parsed = Number(normalized);
  return Number.isFinite(parsed) && parsed > 0;
};

const sanitizePositiveDecimalInput = (value: string): string => {
  const sanitized = value.replace(/[^\d.]/g, '');
  const [integerPart, ...decimalParts] = sanitized.split('.');
  if (decimalParts.length === 0) {
    return sanitized;
  }
  return `${integerPart}.${decimalParts.join('')}`;
};

const addSelfManagedYears = (value: Date, years: number): Date => {
  const next = new Date(value.getTime());
  next.setFullYear(value.getFullYear() + years);
  return next;
};

const endOfDay = (value: Date): Date => {
  const next = new Date(value.getTime());
  next.setHours(23, 59, 59, 0);
  return next;
};

const resolveEstimatedPlanExpiry = (
  product: BillingPlan | null,
  grantedAt: Date | null,
): string => {
  if (!product || !grantedAt) {
    return '';
  }

  const intervalCount = Math.max(product.billing_interval_count || 0, 1);
  if (product.billing_interval === 'day') {
    const next = new Date(grantedAt.getTime());
    next.setDate(next.getDate() + intervalCount - 1);
    return endOfDay(next).toISOString();
  }
  if (product.billing_interval === 'month') {
    const next = new Date(grantedAt.getTime());
    next.setDate(next.getDate() + intervalCount * 30 - 1);
    return endOfDay(next).toISOString();
  }
  if (product.billing_interval === 'year') {
    return endOfDay(
      addSelfManagedYears(grantedAt, intervalCount),
    ).toISOString();
  }
  return '';
};

const stripValidityLabelPrefix = (value: string): string =>
  value.replace(/^[^:：]+[:：]\s*/, '').trim();

const SummaryField = ({
  label,
  value,
  className = '',
}: {
  label: string;
  value: string;
  className?: string;
}) => (
  <div className={className}>
    <div className='text-[11px] font-medium text-muted-foreground'>{label}</div>
    <div className='mt-1 break-all text-sm font-medium leading-5 text-foreground'>
      {value || '--'}
    </div>
  </div>
);

const ConfirmSummaryItem = ({
  label,
  value,
}: {
  label: string;
  value: string;
}) => (
  <div className='grid grid-cols-[96px_minmax(0,1fr)] gap-2'>
    <span className='text-muted-foreground'>{label}</span>
    <span className='break-all text-foreground'>{value}</span>
  </div>
);

const ChoiceChipGroup = ({
  value,
  options,
  onChange,
  compact = false,
}: {
  value: string;
  options: Array<{
    value: string;
    label: string;
    disabled?: boolean;
  }>;
  onChange: (value: string) => void;
  compact?: boolean;
}) => (
  <div className='flex flex-wrap gap-2'>
    {options.map(option => {
      const selected = option.value === value;
      return (
        <button
          key={option.value}
          type='button'
          disabled={option.disabled}
          aria-pressed={selected}
          onClick={() => {
            if (!option.disabled) {
              onChange(option.value);
            }
          }}
          className={[
            compact
              ? 'inline-flex min-w-[68px] items-center justify-center rounded-full border px-2.5 py-0.5 text-[13px] font-medium transition-colors'
              : 'inline-flex min-w-[84px] items-center justify-center rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors',
            selected
              ? 'border-primary/70 bg-primary/6 text-foreground shadow-[inset_0_0_0_1px_rgba(37,99,235,0.08)]'
              : 'border-border bg-background text-foreground hover:border-primary/25 hover:bg-muted/30',
            option.disabled
              ? 'cursor-not-allowed border-border/60 bg-muted/20 text-muted-foreground opacity-60'
              : '',
          ].join(' ')}
        >
          {option.label}
        </button>
      );
    })}
  </div>
);

export default function UserCreditGrantDialog({
  open,
  user,
  onOpenChange,
  onGranted,
}: UserCreditGrantDialogProps) {
  const { t, i18n } = useTranslation();
  const { t: tOperationsUsers } = useTranslation('module.operationsUser');
  const { toast } = useToast();
  const hasActiveSubscription = Boolean(user?.has_active_subscription);
  const defaultCreditFormState = useMemo(
    () => buildDefaultCreditFormState(hasActiveSubscription),
    [hasActiveSubscription],
  );
  const [grantMode, setGrantMode] = useState<GrantMode>('credits');
  const [creditFormState, setCreditFormState] = useState<CreditFormState>(
    defaultCreditFormState,
  );
  const [packageFormState, setPackageFormState] = useState<PackageFormState>(
    BASE_PACKAGE_FORM_STATE,
  );
  const [formErrors, setFormErrors] = useState<FormErrors>({});
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [requestId, setRequestId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [bootstrapLoading, setBootstrapLoading] = useState(false);
  const [bootstrapPayload, setBootstrapPayload] =
    useState<AdminOperationUserGrantBootstrapResponse | null>(null);
  const bootstrapRequestedUserBidRef = useRef('');
  const [grantedAt, setGrantedAt] = useState<Date | null>(null);
  const currentUserBid = user?.user_bid || '';

  useEffect(() => {
    setGrantMode('credits');
    setCreditFormState(defaultCreditFormState);
    setPackageFormState(BASE_PACKAGE_FORM_STATE);
    setFormErrors({});
    setConfirmOpen(false);
    setRequestId(open ? uuidv4().replace(/-/g, '') : '');
    setSubmitting(false);
    setGrantedAt(open ? new Date() : null);
  }, [defaultCreditFormState, open]);

  useEffect(() => {
    if (!open || !currentUserBid) {
      setBootstrapPayload(null);
      setBootstrapLoading(false);
      bootstrapRequestedUserBidRef.current = '';
      return;
    }

    setBootstrapPayload(null);
    setBootstrapLoading(false);
    bootstrapRequestedUserBidRef.current = '';
  }, [currentUserBid, open]);

  useEffect(() => {
    if (!open || !user) {
      return;
    }
    if (bootstrapPayload) {
      return;
    }
    if (bootstrapRequestedUserBidRef.current === user.user_bid) {
      return;
    }

    let active = true;
    bootstrapRequestedUserBidRef.current = user.user_bid;
    setBootstrapLoading(true);
    setFormErrors(current => ({
      ...current,
      bootstrap: undefined,
      submit: undefined,
    }));

    void api
      .getAdminOperationUserGrantBootstrap({
        user_bid: user.user_bid,
      })
      .then(result => {
        if (!active) {
          return;
        }
        setBootstrapPayload(result as AdminOperationUserGrantBootstrapResponse);
      })
      .catch(error => {
        if (!active) {
          return;
        }
        const resolvedError = error as ErrorWithCode;
        setBootstrapPayload(null);
        setFormErrors(current => ({
          ...current,
          bootstrap:
            resolvedError.message ||
            tOperationsUsers('grantDialog.bootstrapError'),
        }));
      })
      .finally(() => {
        if (active) {
          setBootstrapLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [bootstrapPayload, open, tOperationsUsers, user]);

  const sourceOptions = useMemo(
    () => [
      {
        value: 'reward',
        label: tOperationsUsers('grantDialog.sourceOptions.reward'),
      },
      {
        value: 'compensation',
        label: tOperationsUsers('grantDialog.sourceOptions.compensation'),
      },
    ],
    [tOperationsUsers],
  );

  const validityOptions = useMemo(
    () => [
      {
        value: 'align_subscription',
        label: tOperationsUsers(
          'grantDialog.validityOptions.alignSubscription',
        ),
        disabled: !hasActiveSubscription,
      },
      {
        value: '1d',
        label: tOperationsUsers('grantDialog.validityOptions.oneDay'),
        disabled: false,
      },
      {
        value: '7d',
        label: tOperationsUsers('grantDialog.validityOptions.sevenDays'),
        disabled: false,
      },
      {
        value: '1m',
        label: tOperationsUsers('grantDialog.validityOptions.oneMonth'),
        disabled: false,
      },
      {
        value: '3m',
        label: tOperationsUsers('grantDialog.validityOptions.threeMonths'),
        disabled: false,
      },
      {
        value: '1y',
        label: tOperationsUsers('grantDialog.validityOptions.oneYear'),
        disabled: false,
      },
    ],
    [hasActiveSubscription, tOperationsUsers],
  );

  const accountLabel = user?.email || user?.mobile || user?.user_bid || '--';
  const currentExpiry = resolveCurrentExpiry(
    user,
    tOperationsUsers('credits.longTerm'),
  );
  const selectedPlan =
    bootstrapPayload?.plans.find(
      plan => plan.product_bid === packageFormState.productBid,
    ) || null;
  const estimatedPlanExpiry = resolveEstimatedPlanExpiry(
    selectedPlan,
    grantedAt,
  );
  const packageName = selectedPlan ? t(selectedPlan.display_name) : '--';
  const packageCreditsLabel = selectedPlan
    ? formatAdminCredits(Number(selectedPlan.credit_amount || 0), i18n.language)
    : '--';
  const packageValidityLabel = selectedPlan
    ? stripValidityLabelPrefix(resolveBillingPlanValidityLabel(t, selectedPlan))
    : '--';
  const currentPackageLabel =
    bootstrapPayload?.current_subscription_product_display_name_i18n_key
      ? t(bootstrapPayload.current_subscription_product_display_name_i18n_key)
      : '--';
  const packageExpiryHint = selectedPlan
    ? tOperationsUsers('grantDialog.packageFields.expiryHintResolved', {
        dateTime: formatBillingCompactDateTime(
          estimatedPlanExpiry,
          i18n.language,
        ),
      })
    : tOperationsUsers('grantDialog.packageFields.expiryHintPending');

  const updateCreditField = <K extends keyof CreditFormState>(
    key: K,
    value: CreditFormState[K],
  ) => {
    setCreditFormState(current => ({ ...current, [key]: value }));
    setFormErrors(current => ({
      ...current,
      [key]: undefined,
      submit: undefined,
    }));
  };

  const updatePackageField = <K extends keyof PackageFormState>(
    key: K,
    value: PackageFormState[K],
  ) => {
    setPackageFormState(current => ({ ...current, [key]: value }));
    setFormErrors(current => ({
      ...current,
      productBid: key === 'productBid' ? undefined : current.productBid,
      submit: undefined,
    }));
  };

  const validateForm = (): boolean => {
    const nextErrors: FormErrors = {};

    if (grantMode === 'credits') {
      if (!creditFormState.source) {
        nextErrors.source = tOperationsUsers(
          'grantDialog.validation.sourceRequired',
        );
      }
      if (!validatePositiveAmount(creditFormState.amount)) {
        nextErrors.amount = tOperationsUsers(
          'grantDialog.validation.amountRequired',
        );
      }
      if (!creditFormState.validityPreset) {
        nextErrors.validityPreset = tOperationsUsers(
          'grantDialog.validation.validityPresetRequired',
        );
      } else if (
        creditFormState.validityPreset === 'align_subscription' &&
        !hasActiveSubscription
      ) {
        nextErrors.validityPreset = tOperationsUsers(
          'grantDialog.validityHint',
        );
      }
    } else {
      if (!packageFormState.productBid) {
        nextErrors.productBid = tOperationsUsers(
          'grantDialog.validation.productRequired',
        );
      }
      if (!bootstrapPayload?.plans.length && !bootstrapLoading) {
        nextErrors.bootstrap = tOperationsUsers('grantDialog.bootstrapError');
      }
    }

    setFormErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleOpenConfirm = () => {
    if (!validateForm()) {
      return;
    }
    setConfirmOpen(true);
  };

  const handleSubmit = async () => {
    if (!user || submitting) {
      return;
    }

    setSubmitting(true);
    setFormErrors(current => ({ ...current, submit: undefined }));

    try {
      let result:
        | AdminOperationUserCreditGrantResponse
        | AdminOperationUserPackageGrantResponse;
      if (grantMode === 'credits') {
        const payload: AdminOperationUserCreditGrantRequest = {
          request_id: requestId,
          amount: creditFormState.amount.trim(),
          grant_source: creditFormState.source,
          validity_preset: creditFormState.validityPreset,
          note: creditFormState.note.trim(),
        };
        result = (await api.grantAdminOperationUserCredits({
          user_bid: user.user_bid,
          ...payload,
        })) as AdminOperationUserCreditGrantResponse;
      } else {
        const payload: AdminOperationUserPackageGrantRequest = {
          request_id: requestId,
          product_bid: packageFormState.productBid,
          note: packageFormState.note.trim(),
        };
        result = (await api.grantAdminOperationUserPackage({
          user_bid: user.user_bid,
          ...payload,
        })) as AdminOperationUserPackageGrantResponse;
      }

      toast({
        title: tOperationsUsers('grantDialog.submitSuccess'),
      });
      setConfirmOpen(false);
      onOpenChange(false);
      onGranted(result);
    } catch (error) {
      const resolvedError = error as ErrorWithCode;
      setConfirmOpen(false);
      setFormErrors(current => ({
        ...current,
        submit: resolvedError.message || t('common.core.networkError'),
      }));
    } finally {
      setSubmitting(false);
    }
  };

  const confirmSummaryItems =
    grantMode === 'credits'
      ? [
          {
            id: 'mode',
            label: tOperationsUsers('grantDialog.confirmSummary.mode'),
            value: tOperationsUsers('grantDialog.modeOptions.credits'),
          },
          {
            id: 'source',
            label: tOperationsUsers('grantDialog.confirmSummary.source'),
            value:
              sourceOptions.find(
                option => option.value === creditFormState.source,
              )?.label || '--',
          },
          {
            id: 'amount',
            label: tOperationsUsers('grantDialog.confirmSummary.amount'),
            value: creditFormState.amount.trim() || '--',
          },
          {
            id: 'validityPreset',
            label: tOperationsUsers(
              'grantDialog.confirmSummary.validityPreset',
            ),
            value:
              validityOptions.find(
                option => option.value === creditFormState.validityPreset,
              )?.label || '--',
          },
          {
            id: 'note',
            label: tOperationsUsers('grantDialog.confirmSummary.note'),
            value: creditFormState.note.trim() || '--',
          },
        ]
      : [
          {
            id: 'mode',
            label: tOperationsUsers('grantDialog.confirmSummary.mode'),
            value: tOperationsUsers('grantDialog.modeOptions.package'),
          },
          {
            id: 'package',
            label: tOperationsUsers('grantDialog.confirmSummary.package'),
            value: packageName,
          },
          {
            id: 'packageCredits',
            label: tOperationsUsers(
              'grantDialog.confirmSummary.packageCredits',
            ),
            value: packageCreditsLabel,
          },
          {
            id: 'packageValidity',
            label: tOperationsUsers(
              'grantDialog.confirmSummary.packageValidity',
            ),
            value: packageValidityLabel,
          },
          {
            id: 'packageExpireAt',
            label: tOperationsUsers(
              'grantDialog.confirmSummary.packageExpireAt',
            ),
            value:
              formatBillingCompactDateTime(
                estimatedPlanExpiry,
                i18n.language,
              ) || '--',
          },
          {
            id: 'note',
            label: tOperationsUsers('grantDialog.confirmSummary.note'),
            value: packageFormState.note.trim() || '--',
          },
        ];

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={nextOpen => {
          if (!submitting) {
            onOpenChange(nextOpen);
          }
        }}
      >
        <DialogContent className='flex max-h-[85vh] w-[calc(100vw-32px)] flex-col gap-0 overflow-hidden p-0 sm:max-w-[520px]'>
          <DialogHeader className='border-b border-border px-5 pb-3 pt-5'>
            <DialogTitle>{tOperationsUsers('grantDialog.title')}</DialogTitle>
            <DialogDescription>
              {tOperationsUsers('grantDialog.description')}
            </DialogDescription>
          </DialogHeader>

          <div className='min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4'>
            <div className='rounded-xl border border-border/70 bg-muted/[0.16] px-4 py-3'>
              <div className='grid gap-x-5 gap-y-3 sm:grid-cols-3'>
                <SummaryField
                  label={tOperationsUsers('grantDialog.summary.account')}
                  value={accountLabel}
                />
                <SummaryField
                  label={tOperationsUsers('grantDialog.summary.nickname')}
                  value={user?.nickname || '--'}
                />
                <SummaryField
                  label={tOperationsUsers(
                    'grantDialog.summary.availableCredits',
                  )}
                  value={formatAdminCredits(
                    Number(user?.available_credits || 0),
                    i18n.language,
                  )}
                />
                <SummaryField
                  label={tOperationsUsers('grantDialog.summary.currentPackage')}
                  value={currentPackageLabel}
                />
                <SummaryField
                  label={tOperationsUsers(
                    'grantDialog.summary.currentExpireAt',
                  )}
                  value={currentExpiry}
                />
              </div>
            </div>

            <div className='space-y-3'>
              <div className='space-y-2'>
                <div className='grid gap-3 sm:grid-cols-[80px_minmax(0,1fr)] sm:items-center'>
                  <div className='text-sm font-semibold leading-9 text-foreground/90'>
                    {tOperationsUsers('grantDialog.fields.mode')}
                  </div>
                  <ChoiceChipGroup
                    value={grantMode}
                    onChange={value => {
                      setGrantMode(value as GrantMode);
                      setFormErrors(current => ({
                        ...current,
                        bootstrap: undefined,
                        productBid: undefined,
                        submit: undefined,
                      }));
                    }}
                    options={(['credits', 'package'] as const).map(option => ({
                      value: option,
                      label: tOperationsUsers(
                        `grantDialog.modeOptions.${option}`,
                      ),
                    }))}
                  />
                </div>
              </div>

              {grantMode === 'credits' ? (
                <>
                  <div className='space-y-2'>
                    <div className='grid gap-3 sm:grid-cols-[80px_minmax(0,1fr)] sm:items-center'>
                      <div className='text-sm font-medium leading-8 text-muted-foreground'>
                        {tOperationsUsers('grantDialog.fields.source')}
                      </div>
                      <div className='sm:pl-1'>
                        <ChoiceChipGroup
                          value={creditFormState.source}
                          onChange={value => updateCreditField('source', value)}
                          options={sourceOptions}
                          compact
                        />
                      </div>
                    </div>
                    {formErrors.source ? (
                      <div className='text-xs text-destructive'>
                        {formErrors.source}
                      </div>
                    ) : null}
                  </div>

                  <div className='space-y-2'>
                    <div className='grid gap-2 sm:grid-cols-[80px_minmax(0,1fr)] sm:items-center'>
                      <div className='text-sm font-semibold leading-10 text-foreground/90'>
                        {tOperationsUsers('grantDialog.fields.amount')}
                      </div>
                      <Input
                        type='text'
                        inputMode='decimal'
                        autoComplete='off'
                        value={creditFormState.amount}
                        onChange={event =>
                          updateCreditField(
                            'amount',
                            sanitizePositiveDecimalInput(event.target.value),
                          )
                        }
                        placeholder={tOperationsUsers(
                          'grantDialog.placeholders.amount',
                        )}
                        className='h-10'
                      />
                    </div>
                    {formErrors.amount ? (
                      <div className='text-xs text-destructive'>
                        {formErrors.amount}
                      </div>
                    ) : null}
                  </div>

                  <div className='space-y-2'>
                    <div className='grid gap-2 sm:grid-cols-[80px_minmax(0,1fr)] sm:items-center'>
                      <div className='text-sm font-semibold leading-10 text-foreground/90'>
                        {tOperationsUsers('grantDialog.fields.validityPreset')}
                      </div>
                      <Select
                        value={creditFormState.validityPreset}
                        onValueChange={value =>
                          updateCreditField('validityPreset', value)
                        }
                      >
                        <SelectTrigger>
                          <SelectValue
                            placeholder={tOperationsUsers(
                              'grantDialog.placeholders.validityPreset',
                            )}
                          />
                        </SelectTrigger>
                        <SelectContent>
                          {validityOptions.map(option => (
                            <SelectItem
                              key={option.value}
                              value={option.value}
                              disabled={option.disabled}
                            >
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className='pl-[92px] text-xs text-muted-foreground'>
                      {tOperationsUsers('grantDialog.validityHint')}
                    </div>
                    {formErrors.validityPreset ? (
                      <div className='text-xs text-destructive'>
                        {formErrors.validityPreset}
                      </div>
                    ) : null}
                  </div>

                  <div className='space-y-2'>
                    <div className='grid gap-2 sm:grid-cols-[80px_minmax(0,1fr)] sm:items-start'>
                      <div className='pt-2 text-sm font-semibold leading-none text-foreground/90'>
                        {tOperationsUsers('grantDialog.fields.note')}
                      </div>
                      <Textarea
                        value={creditFormState.note}
                        onChange={event =>
                          updateCreditField('note', event.target.value)
                        }
                        placeholder={tOperationsUsers(
                          'grantDialog.placeholders.note',
                        )}
                        rows={1}
                        className='min-h-[40px] resize-y'
                      />
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className='space-y-2'>
                    <div className='grid gap-2 sm:grid-cols-[80px_minmax(0,1fr)] sm:items-center'>
                      <div className='text-sm font-semibold leading-10 text-foreground/90'>
                        {tOperationsUsers('grantDialog.packageFields.product')}
                      </div>
                      <Select
                        value={packageFormState.productBid}
                        onValueChange={value =>
                          updatePackageField('productBid', value)
                        }
                      >
                        <SelectTrigger>
                          <SelectValue
                            placeholder={tOperationsUsers(
                              bootstrapLoading
                                ? 'grantDialog.placeholders.productLoading'
                                : 'grantDialog.placeholders.product',
                            )}
                          />
                        </SelectTrigger>
                        <SelectContent>
                          {bootstrapLoading &&
                          !(bootstrapPayload?.plans.length || 0) ? (
                            <SelectItem
                              value='__loading'
                              disabled
                            >
                              {tOperationsUsers(
                                'grantDialog.placeholders.productLoading',
                              )}
                            </SelectItem>
                          ) : (
                            (bootstrapPayload?.plans || []).map(plan => (
                              <SelectItem
                                key={plan.product_bid}
                                value={plan.product_bid}
                              >
                                {t(plan.display_name)}
                              </SelectItem>
                            ))
                          )}
                        </SelectContent>
                      </Select>
                    </div>
                    {formErrors.productBid ? (
                      <div className='text-xs text-destructive'>
                        {formErrors.productBid}
                      </div>
                    ) : null}
                    {formErrors.bootstrap ? (
                      <div className='text-xs text-destructive'>
                        {formErrors.bootstrap}
                      </div>
                    ) : null}
                  </div>

                  {selectedPlan ? (
                    <div className='rounded-xl border border-border/70 bg-muted/[0.12] px-4 py-3'>
                      <div className='grid gap-x-5 gap-y-3 sm:grid-cols-2'>
                        <SummaryField
                          label={tOperationsUsers(
                            'grantDialog.packageFields.packageName',
                          )}
                          value={packageName}
                        />
                        <SummaryField
                          label={tOperationsUsers(
                            'grantDialog.packageFields.credits',
                          )}
                          value={packageCreditsLabel}
                        />
                        <SummaryField
                          label={tOperationsUsers(
                            'grantDialog.packageFields.validity',
                          )}
                          value={packageValidityLabel}
                        />
                      </div>
                      <div className='mt-3 text-xs text-muted-foreground'>
                        {packageExpiryHint}
                      </div>
                    </div>
                  ) : null}

                  <div className='space-y-2'>
                    <div className='grid gap-2 sm:grid-cols-[80px_minmax(0,1fr)] sm:items-start'>
                      <div className='pt-2 text-sm font-semibold leading-none text-foreground/90'>
                        {tOperationsUsers('grantDialog.fields.note')}
                      </div>
                      <Textarea
                        value={packageFormState.note}
                        onChange={event =>
                          updatePackageField('note', event.target.value)
                        }
                        placeholder={tOperationsUsers(
                          'grantDialog.placeholders.note',
                        )}
                        rows={1}
                        className='min-h-[40px] resize-y'
                      />
                    </div>
                  </div>
                </>
              )}

              {formErrors.submit ? (
                <div className='rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive'>
                  {formErrors.submit}
                </div>
              ) : null}
            </div>
          </div>

          <DialogFooter className='gap-2 border-t border-border bg-background px-5 py-4'>
            <Button
              variant='outline'
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t('common.core.cancel')}
            </Button>
            <Button
              onClick={handleOpenConfirm}
              disabled={submitting}
            >
              {tOperationsUsers('grantDialog.confirmButton')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={confirmOpen}
        onOpenChange={nextOpen => {
          if (!submitting) {
            setConfirmOpen(nextOpen);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {grantMode === 'credits'
                ? tOperationsUsers('grantDialog.confirmTitle')
                : tOperationsUsers('grantDialog.packageConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {grantMode === 'credits'
                ? tOperationsUsers('grantDialog.confirmDescription')
                : tOperationsUsers('grantDialog.packageConfirmDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>

          <div className='space-y-3 text-sm'>
            <ConfirmSummaryItem
              label={tOperationsUsers('grantDialog.summary.account')}
              value={accountLabel}
            />
            <ConfirmSummaryItem
              label={tOperationsUsers('grantDialog.summary.nickname')}
              value={user?.nickname || '--'}
            />
            {confirmSummaryItems.map(item => (
              <ConfirmSummaryItem
                key={item.id}
                label={item.label}
                value={item.value}
              />
            ))}
          </div>

          <AlertDialogFooter>
            <AlertDialogCancel disabled={submitting}>
              {t('common.core.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={event => {
                event.preventDefault();
                void handleSubmit();
              }}
              disabled={submitting}
            >
              {tOperationsUsers('grantDialog.submitButton')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
