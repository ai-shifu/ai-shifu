'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { v4 as uuidv4 } from 'uuid';
import api from '@/api';
import { formatAdminCredits } from '@/app/admin/lib/numberFormat';
import { Button } from '@/components/ui/Button';
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
import { useToast } from '@/hooks/useToast';
import { useTracking } from '@/hooks/useTracking';
import { ErrorWithCode } from '@/lib/request';
import { getTrackingIdentityGeneration } from '@/lib/tracking';
import type {
  AdminOperationUserCreditDeductionReason,
  AdminOperationUserCreditDeductionResponse,
  AdminOperationUserItem,
} from '../operation-user-types';

type Props = {
  open: boolean;
  user: AdminOperationUserItem | null;
  onOpenChange: (open: boolean) => void;
  onDeducted: (result: AdminOperationUserCreditDeductionResponse) => void;
};

const CREDIT_AMOUNT_PATTERN = /^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/;

export default function UserCreditDeductionDialog({
  open,
  user,
  onOpenChange,
  onDeducted,
}: Props) {
  const { t, i18n } = useTranslation('module.operationsUser');
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const [amount, setAmount] = useState('');
  const [reason, setReason] =
    useState<AdminOperationUserCreditDeductionReason>('account_correction');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const requestIdRef = useRef('');
  const submittingRef = useRef(false);
  const workflowRef = useRef('');
  const accountIdentifier =
    user?.mobile?.trim() || user?.email?.trim() || user?.user_bid || '';

  const trackDeduction = (
    eventName:
      | 'operator_credit_deduction_attempt'
      | 'operator_credit_deduction_result',
    outcome?: 'success' | 'failed',
  ) => {
    try {
      const properties = outcome
        ? { surface: 'operator_user_management', outcome }
        : { surface: 'operator_user_management' };
      void Promise.resolve(trackEvent(eventName, properties)).catch(() => {});
    } catch {
      // Analytics must never affect the deduction workflow.
    }
  };

  useEffect(() => {
    if (!open) return;
    if (submittingRef.current) return;
    setAmount('');
    setReason('account_correction');
    setNote('');
    setError('');
    setConfirming(false);
    setSubmitting(false);
    submittingRef.current = false;
    requestIdRef.current = uuidv4();
    workflowRef.current = `${user?.user_bid || ''}:${requestIdRef.current}`;
  }, [open, user?.user_bid]);

  const continueToConfirmation = () => {
    const normalizedAmount = amount.trim();
    if (
      !CREDIT_AMOUNT_PATTERN.test(normalizedAmount) ||
      Number(normalizedAmount) <= 0
    ) {
      setError(t('deductionDialog.errors.amount'));
      return;
    }
    setAmount(normalizedAmount);
    setError('');
    setConfirming(true);
  };

  const submit = async () => {
    if (!user || submittingRef.current) return;
    submittingRef.current = true;
    const workflowId = workflowRef.current;
    setSubmitting(true);
    setError('');
    const trackingIdentityGeneration = getTrackingIdentityGeneration();
    trackDeduction('operator_credit_deduction_attempt');
    try {
      const result = (await api.deductAdminOperationUserCredits({
        user_bid: user.user_bid,
        request_id: requestIdRef.current,
        amount,
        reason,
        note: note.trim(),
      })) as AdminOperationUserCreditDeductionResponse;
      if (workflowRef.current !== workflowId) return;
      if (getTrackingIdentityGeneration() === trackingIdentityGeneration) {
        trackDeduction('operator_credit_deduction_result', 'success');
      }
      toast({ title: t('deductionDialog.success') });
      onOpenChange(false);
      onDeducted(result);
    } catch (value) {
      if (workflowRef.current !== workflowId) return;
      if (getTrackingIdentityGeneration() === trackingIdentityGeneration) {
        trackDeduction('operator_credit_deduction_result', 'failed');
      }
      setError(
        (value as ErrorWithCode).message ||
          t('deductionDialog.errors.submitFailed'),
      );
      setConfirming(false);
    } finally {
      if (workflowRef.current === workflowId) {
        submittingRef.current = false;
        setSubmitting(false);
      }
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={nextOpen => {
        if (!nextOpen && submittingRef.current) return;
        onOpenChange(nextOpen);
      }}
    >
      <DialogContent className='gap-5 sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>
            {t(
              confirming
                ? 'deductionDialog.confirmTitle'
                : 'deductionDialog.title',
            )}
          </DialogTitle>
          <DialogDescription>
            {t(
              confirming
                ? 'deductionDialog.confirmDescription'
                : 'deductionDialog.description',
            )}
          </DialogDescription>
        </DialogHeader>

        {confirming ? (
          <dl className='grid grid-cols-[auto_1fr] gap-x-4 gap-y-3 rounded-lg border p-4 text-sm'>
            <dt className='text-muted-foreground'>
              {t('deductionDialog.account')}
            </dt>
            <dd className='break-all text-right'>{accountIdentifier}</dd>
            <dt className='text-muted-foreground'>
              {t('deductionDialog.currentBalance')}
            </dt>
            <dd className='text-right'>
              {formatAdminCredits(
                user?.available_credits || '0',
                i18n.language,
              )}
            </dd>
            <dt className='text-muted-foreground'>
              {t('deductionDialog.amount')}
            </dt>
            <dd className='text-right font-medium'>{amount}</dd>
            <dt className='text-muted-foreground'>
              {t('deductionDialog.reason')}
            </dt>
            <dd className='text-right'>
              {t(`deductionDialog.reasons.${reason}`)}
            </dd>
          </dl>
        ) : (
          <div className='space-y-5'>
            <div className='flex items-center justify-between rounded-lg border px-4 py-3 text-sm'>
              <span className='text-muted-foreground'>
                {t('deductionDialog.currentBalance')}
              </span>
              {formatAdminCredits(
                user?.available_credits || '0',
                i18n.language,
              )}
            </div>
            <div className='space-y-2'>
              <label
                htmlFor='credit-deduction-amount'
                className='text-sm font-medium'
              >
                {t('deductionDialog.amount')}
              </label>
              <Input
                id='credit-deduction-amount'
                inputMode='decimal'
                autoComplete='off'
                name='operator-credit-deduction-amount'
                value={amount}
                onChange={event => setAmount(event.target.value)}
                placeholder={t('deductionDialog.amountPlaceholder')}
              />
            </div>
            <div className='space-y-2'>
              <span className='text-sm font-medium'>
                {t('deductionDialog.reason')}
              </span>
              <Select
                value={reason}
                onValueChange={value =>
                  setReason(value as AdminOperationUserCreditDeductionReason)
                }
              >
                <SelectTrigger aria-label={t('deductionDialog.reason')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(
                    ['incorrect_grant', 'account_correction', 'other'] as const
                  ).map(value => (
                    <SelectItem
                      key={value}
                      value={value}
                    >
                      {t(`deductionDialog.reasons.${value}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='space-y-2'>
              <label
                htmlFor='credit-deduction-note'
                className='text-sm font-medium'
              >
                {t('deductionDialog.note')}
              </label>
              <Textarea
                id='credit-deduction-note'
                maxLength={255}
                value={note}
                onChange={event => setNote(event.target.value)}
                placeholder={t('deductionDialog.notePlaceholder')}
              />
            </div>
          </div>
        )}

        {error ? (
          <p
            role='alert'
            className='text-sm text-destructive'
          >
            {error}
          </p>
        ) : null}
        <DialogFooter>
          {confirming ? (
            <Button
              variant='outline'
              disabled={submitting}
              onClick={() => setConfirming(false)}
            >
              {t('deductionDialog.back')}
            </Button>
          ) : null}
          <Button
            disabled={submitting}
            onClick={confirming ? () => void submit() : continueToConfirmation}
          >
            {submitting
              ? t('deductionDialog.submitting')
              : t(
                  confirming
                    ? 'deductionDialog.confirmButton'
                    : 'deductionDialog.continueButton',
                )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
