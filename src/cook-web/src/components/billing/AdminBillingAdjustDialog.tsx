'use client';

import React from 'react';
import { useSWRConfig } from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { toast } from '@/hooks/useToast';
import { formatBillingCreditBalance } from '@/lib/billing';
import type {
  AdminBillingLedgerAdjustPayload,
  AdminBillingLedgerAdjustResult,
} from '@/types/billing';
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
import { Textarea } from '@/components/ui/Textarea';
import {
  AdminBillingIdentityCell,
  setAdminBillingExceptionHandledState,
  type AdminBillingCreatorTarget,
  resolveAdminBillingCreatorPrimary,
} from './AdminBillingShared';

const DECIMAL_AMOUNT_PATTERN = /^[+-]?\d+(?:\.\d{1,2})?$/;
const ZERO_AMOUNT_PATTERN = /^[+-]?0+(?:\.0+)?$/;
const DECIMAL_AMOUNT_INPUT_PATTERN = /^[+-]?\d*(?:\.\d{0,2})?$/;

function isAdminBillingCacheKey(key: unknown): boolean {
  if (Array.isArray(key)) {
    return typeof key[0] === 'string' && key[0].startsWith('admin-billing-');
  }
  return typeof key === 'string' && key.startsWith('admin-billing-');
}

type AdminBillingAdjustDialogProps = {
  open: boolean;
  initialTarget?: AdminBillingCreatorTarget | null;
  onOpenChange: (open: boolean) => void;
};

export function AdminBillingAdjustDialog({
  open,
  initialTarget,
  onOpenChange,
}: AdminBillingAdjustDialogProps) {
  const { t } = useTranslation();
  const { mutate } = useSWRConfig();
  const [creatorMobile, setCreatorMobile] = React.useState('');
  const [amount, setAmount] = React.useState('');
  const [note, setNote] = React.useState('');
  const [submitting, setSubmitting] = React.useState(false);
  const initialCreatorBid = String(initialTarget?.creator_bid || '').trim();
  const initialCreatorMobile = String(
    initialTarget?.creator_mobile || '',
  ).trim();
  const initialCreatorNickname = String(
    initialTarget?.creator_nickname || '',
  ).trim();
  const resolvedCreatorLabel =
    creatorMobile.trim() ||
    initialCreatorMobile ||
    resolveAdminBillingCreatorPrimary(initialTarget || {});

  React.useEffect(() => {
    if (!open) {
      return;
    }
    setCreatorMobile(initialCreatorMobile);
    setAmount('');
    setNote('');
  }, [initialCreatorMobile, open]);

  const handleAmountChange = (nextValue: string) => {
    if (!nextValue || DECIMAL_AMOUNT_INPUT_PATTERN.test(nextValue.trim())) {
      setAmount(nextValue);
    }
  };

  const handleSubmit = async () => {
    const normalizedCreatorBid = initialCreatorBid;
    const normalizedCreatorMobile = creatorMobile.trim();
    const normalizedAmount = amount.trim();
    const normalizedNote = note.trim();

    if (!normalizedCreatorBid && !normalizedCreatorMobile) {
      toast({
        title: t('module.billing.admin.adjust.errors.creatorMobileRequired'),
        variant: 'destructive',
      });
      return;
    }

    if (
      !DECIMAL_AMOUNT_PATTERN.test(normalizedAmount) ||
      ZERO_AMOUNT_PATTERN.test(normalizedAmount)
    ) {
      toast({
        title: t('module.billing.admin.adjust.errors.amountInvalid'),
        variant: 'destructive',
      });
      return;
    }

    setSubmitting(true);
    try {
      const payload: AdminBillingLedgerAdjustPayload = {
        ...(normalizedCreatorBid
          ? { creator_bid: normalizedCreatorBid }
          : { creator_mobile: normalizedCreatorMobile }),
        amount: normalizedAmount,
        note: normalizedNote,
      };
      const result = (await api.adjustAdminBillingLedger(
        payload,
      )) as AdminBillingLedgerAdjustResult;

      const exceptionRowKey = String(
        initialTarget?.exception_row_key || '',
      ).trim();
      if (exceptionRowKey) {
        await setAdminBillingExceptionHandledState(exceptionRowKey, true);
      }

      await mutate(isAdminBillingCacheKey, undefined, { revalidate: true });
      onOpenChange(false);
      toast({
        title: t('module.billing.admin.adjust.success', {
          creator: resolvedCreatorLabel || result.creator_bid,
          availableCredits: formatBillingCreditBalance(
            result.wallet?.available_credits || 0,
          ),
        }),
      });
    } catch {
      // The shared request layer already surfaces backend errors.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={nextOpen => {
        if (!submitting) {
          onOpenChange(nextOpen);
        }
      }}
    >
      <DialogContent className='border-slate-200 bg-white sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{t('module.billing.admin.adjust.title')}</DialogTitle>
          <DialogDescription>
            {t('module.billing.admin.adjust.description')}
          </DialogDescription>
        </DialogHeader>

        <div className='grid gap-4 py-2'>
          {initialCreatorBid ? (
            <div className='rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3'>
              <div className='mb-2 text-xs font-medium uppercase tracking-[0.12em] text-slate-500'>
                {t('module.billing.admin.adjust.targetSummary')}
              </div>
              <AdminBillingIdentityCell
                primary={
                  initialCreatorMobile ||
                  resolveAdminBillingCreatorPrimary(initialTarget || {})
                }
                secondary={
                  initialCreatorNickname || t('module.user.defaultUserName')
                }
              />
            </div>
          ) : null}

          <div className='grid gap-2'>
            <label
              htmlFor='admin-billing-adjust-creator-mobile'
              className='text-sm font-medium text-slate-900'
            >
              {t('module.billing.admin.adjust.fields.creatorMobile')}
            </label>
            <Input
              id='admin-billing-adjust-creator-mobile'
              value={creatorMobile}
              disabled={Boolean(initialCreatorBid) || submitting}
              placeholder={t(
                'module.billing.admin.adjust.placeholders.creatorMobile',
              )}
              onChange={event => setCreatorMobile(event.target.value)}
            />
            {t('module.billing.admin.adjust.help.creatorMobile') ? (
              <p className='text-xs leading-5 text-slate-500'>
                {t('module.billing.admin.adjust.help.creatorMobile')}
              </p>
            ) : null}
          </div>

          <div className='grid gap-2'>
            <label
              htmlFor='admin-billing-adjust-amount'
              className='text-sm font-medium text-slate-900'
            >
              {t('module.billing.admin.adjust.fields.amount')}
            </label>
            <Input
              id='admin-billing-adjust-amount'
              value={amount}
              disabled={submitting}
              inputMode='decimal'
              placeholder={t('module.billing.admin.adjust.placeholders.amount')}
              onChange={event => handleAmountChange(event.target.value)}
            />
            {t('module.billing.admin.adjust.help.amount') ? (
              <p className='text-xs leading-5 text-slate-500'>
                {t('module.billing.admin.adjust.help.amount')}
              </p>
            ) : null}
          </div>

          <div className='grid gap-2'>
            <label
              htmlFor='admin-billing-adjust-note'
              className='text-sm font-medium text-slate-900'
            >
              {t('module.billing.admin.adjust.fields.note')}
            </label>
            <Textarea
              id='admin-billing-adjust-note'
              value={note}
              disabled={submitting}
              placeholder={t('module.billing.admin.adjust.placeholders.note')}
              onChange={event => setNote(event.target.value)}
            />
            <p className='text-xs leading-5 text-slate-500'>
              {t('module.billing.admin.adjust.help.note')}
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            disabled={submitting}
            onClick={() => onOpenChange(false)}
          >
            {t('module.billing.admin.adjust.cancel')}
          </Button>
          <Button
            type='button'
            disabled={submitting}
            onClick={handleSubmit}
          >
            {submitting
              ? t('module.billing.admin.adjust.submitting')
              : t('module.billing.admin.adjust.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
