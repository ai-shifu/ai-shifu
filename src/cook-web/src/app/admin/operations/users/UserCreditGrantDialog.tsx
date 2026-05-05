'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { v4 as uuidv4 } from 'uuid';
import api from '@/api';
import { useToast } from '@/hooks/useToast';
import { formatBillingCredits } from '@/lib/billing';
import { ErrorWithCode } from '@/lib/request';
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/RadioGroup';
import { Textarea } from '@/components/ui/Textarea';
import { formatOperatorUtcDateTime } from './dateTime';
import type {
  AdminOperationUserCreditGrantRequest,
  AdminOperationUserCreditGrantResponse,
  AdminOperationUserItem,
} from '../operation-user-types';

type UserCreditGrantDialogProps = {
  open: boolean;
  user: AdminOperationUserItem | null;
  onOpenChange: (open: boolean) => void;
  onGranted: (result: AdminOperationUserCreditGrantResponse) => void;
};

type FormState = {
  source: string;
  amount: string;
  validityPreset: string;
  note: string;
};

type FormErrors = Partial<
  Record<'source' | 'amount' | 'validityPreset' | 'submit', string>
>;

const BASE_FORM_STATE: Omit<FormState, 'validityPreset'> = {
  source: 'reward',
  amount: '',
  note: '',
};

const resolveDefaultValidityPreset = (
  hasActiveSubscription: boolean,
): FormState['validityPreset'] =>
  hasActiveSubscription ? 'align_subscription' : '1d';

const buildDefaultFormState = (hasActiveSubscription: boolean): FormState => ({
  ...BASE_FORM_STATE,
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
  const defaultFormState = useMemo(
    () => buildDefaultFormState(hasActiveSubscription),
    [hasActiveSubscription],
  );
  const [formState, setFormState] = useState<FormState>(() => defaultFormState);
  const [formErrors, setFormErrors] = useState<FormErrors>({});
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [requestId, setRequestId] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setFormState(defaultFormState);
    setFormErrors({});
    setConfirmOpen(false);
    setRequestId(open ? uuidv4().replace(/-/g, '') : '');
    setSubmitting(false);
  }, [defaultFormState, open]);

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

  const sourceLabel =
    sourceOptions.find(option => option.value === formState.source)?.label ||
    '--';
  const validityLabel =
    validityOptions.find(option => option.value === formState.validityPreset)
      ?.label || '--';
  const accountLabel = user?.email || user?.mobile || user?.user_bid || '--';
  const currentExpiry = resolveCurrentExpiry(
    user,
    tOperationsUsers('credits.longTerm'),
  );

  const updateField = <K extends keyof FormState>(
    key: K,
    value: FormState[K],
  ) => {
    setFormState(current => ({ ...current, [key]: value }));
    setFormErrors(current => ({
      ...current,
      [key]: undefined,
      submit: undefined,
    }));
  };

  const validateForm = (): boolean => {
    const nextErrors: FormErrors = {};
    if (!formState.source) {
      nextErrors.source = tOperationsUsers(
        'grantDialog.validation.sourceRequired',
      );
    }
    if (!validatePositiveAmount(formState.amount)) {
      nextErrors.amount = tOperationsUsers(
        'grantDialog.validation.amountRequired',
      );
    }
    if (!formState.validityPreset) {
      nextErrors.validityPreset = tOperationsUsers(
        'grantDialog.validation.validityPresetRequired',
      );
    } else if (
      formState.validityPreset === 'align_subscription' &&
      !hasActiveSubscription
    ) {
      nextErrors.validityPreset = tOperationsUsers('grantDialog.validityHint');
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
    const payload: AdminOperationUserCreditGrantRequest = {
      request_id: requestId,
      amount: formState.amount.trim(),
      grant_source: formState.source,
      validity_preset: formState.validityPreset,
      note: formState.note.trim(),
    };
    setSubmitting(true);
    setFormErrors(current => ({ ...current, submit: undefined }));
    try {
      const result = (await api.grantAdminOperationUserCredits({
        user_bid: user.user_bid,
        ...payload,
      })) as AdminOperationUserCreditGrantResponse;
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
        <DialogContent className='flex max-h-[85vh] w-[calc(100vw-32px)] flex-col overflow-hidden gap-0 p-0 sm:max-w-[520px]'>
          <DialogHeader className='border-b border-border px-5 pb-3 pt-5'>
            <DialogTitle>{tOperationsUsers('grantDialog.title')}</DialogTitle>
            <DialogDescription>
              {tOperationsUsers('grantDialog.description')}
            </DialogDescription>
          </DialogHeader>

          <div className='min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4'>
            <div className='rounded-xl border border-border/70 bg-muted/[0.16] px-4 py-3'>
              <div className='grid gap-x-5 gap-y-3 sm:grid-cols-2'>
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
                  value={formatBillingCredits(
                    Number(user?.available_credits || 0),
                    i18n.language,
                  )}
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
                <div className='grid gap-2 sm:grid-cols-[56px_minmax(0,1fr)] sm:items-center'>
                  <div className='text-sm font-medium leading-none text-foreground'>
                    {tOperationsUsers('grantDialog.fields.source')}
                  </div>
                  <RadioGroup
                    value={formState.source}
                    onValueChange={value => updateField('source', value)}
                    className='flex flex-wrap items-center gap-x-4 gap-y-2'
                  >
                    {sourceOptions.map(option => {
                      const optionId = `grant-source-${option.value}`;
                      return (
                        <label
                          key={option.value}
                          htmlFor={optionId}
                          className='flex cursor-pointer items-center gap-2 text-sm text-foreground'
                        >
                          <RadioGroupItem
                            id={optionId}
                            value={option.value}
                          />
                          <span className='font-medium leading-none'>
                            {option.label}
                          </span>
                        </label>
                      );
                    })}
                  </RadioGroup>
                </div>
                {formErrors.source ? (
                  <div className='text-xs text-destructive'>
                    {formErrors.source}
                  </div>
                ) : null}
              </div>

              <div className='space-y-2'>
                <div className='grid gap-2 sm:grid-cols-[56px_minmax(0,1fr)] sm:items-center'>
                  <div className='text-sm font-medium leading-none text-foreground'>
                    {tOperationsUsers('grantDialog.fields.amount')}
                  </div>
                  <Input
                    type='text'
                    inputMode='decimal'
                    autoComplete='off'
                    value={formState.amount}
                    onChange={event =>
                      updateField(
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
                <div className='grid gap-2 sm:grid-cols-[56px_minmax(0,1fr)] sm:items-center'>
                  <div className='text-sm font-medium leading-none text-foreground'>
                    {tOperationsUsers('grantDialog.fields.validityPreset')}
                  </div>
                  <Select
                    value={formState.validityPreset}
                    onValueChange={value =>
                      updateField('validityPreset', value)
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
                <div className='pl-16 text-xs text-muted-foreground'>
                  {tOperationsUsers('grantDialog.validityHint')}
                </div>
                {formErrors.validityPreset ? (
                  <div className='text-xs text-destructive'>
                    {formErrors.validityPreset}
                  </div>
                ) : null}
              </div>

              <div className='space-y-2'>
                <div className='grid gap-2 sm:grid-cols-[56px_minmax(0,1fr)] sm:items-start'>
                  <div className='pt-2 text-sm font-medium leading-none text-foreground'>
                    {tOperationsUsers('grantDialog.fields.note')}
                  </div>
                  <Textarea
                    value={formState.note}
                    onChange={event => updateField('note', event.target.value)}
                    placeholder={tOperationsUsers(
                      'grantDialog.placeholders.note',
                    )}
                    rows={1}
                    className='min-h-[40px] resize-y'
                  />
                </div>
              </div>

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
        <AlertDialogContent className='sm:max-w-[460px]'>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {tOperationsUsers('grantDialog.confirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {tOperationsUsers('grantDialog.confirmDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>

          <div className='space-y-2 rounded-lg border border-border bg-muted/20 p-4 text-sm'>
            <ConfirmSummaryItem
              label={tOperationsUsers('grantDialog.confirmSummary.source')}
              value={sourceLabel}
            />
            <ConfirmSummaryItem
              label={tOperationsUsers('grantDialog.confirmSummary.amount')}
              value={formState.amount.trim() || '--'}
            />
            <ConfirmSummaryItem
              label={tOperationsUsers(
                'grantDialog.confirmSummary.validityPreset',
              )}
              value={validityLabel}
            />
            {formState.note.trim() ? (
              <ConfirmSummaryItem
                label={tOperationsUsers('grantDialog.confirmSummary.note')}
                value={formState.note.trim()}
              />
            ) : null}
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
