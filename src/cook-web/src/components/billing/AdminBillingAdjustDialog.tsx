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

const DECIMAL_AMOUNT_PATTERN = /^[+-]?\d+(?:\.\d{1,10})?$/;
const ZERO_AMOUNT_PATTERN = /^[+-]?0+(?:\.0+)?$/;

function isAdminBillingCacheKey(key: unknown): boolean {
  if (Array.isArray(key)) {
    return typeof key[0] === 'string' && key[0].startsWith('admin-billing-');
  }
  return typeof key === 'string' && key.startsWith('admin-billing-');
}

type AdminBillingAdjustDialogProps = {
  open: boolean;
  initialCreatorBid?: string;
  onOpenChange: (open: boolean) => void;
};

export function AdminBillingAdjustDialog({
  open,
  initialCreatorBid = '',
  onOpenChange,
}: AdminBillingAdjustDialogProps) {
  const { t } = useTranslation();
  const { mutate } = useSWRConfig();
  const [creatorBid, setCreatorBid] = React.useState(initialCreatorBid);
  const [amount, setAmount] = React.useState('');
  const [note, setNote] = React.useState('');
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (!open) {
      return;
    }
    setCreatorBid(initialCreatorBid);
    setAmount('');
    setNote('');
  }, [initialCreatorBid, open]);

  const handleSubmit = async () => {
    const normalizedCreatorBid = creatorBid.trim();
    const normalizedAmount = amount.trim();
    const normalizedNote = note.trim();

    if (!normalizedCreatorBid) {
      toast({
        title: t('module.billing.admin.adjust.errors.creatorBidRequired'),
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
        creator_bid: normalizedCreatorBid,
        amount: normalizedAmount,
        note: normalizedNote,
      };
      const result = (await api.adjustAdminBillingLedger(
        payload,
      )) as AdminBillingLedgerAdjustResult;

      await mutate(isAdminBillingCacheKey, undefined, { revalidate: true });
      onOpenChange(false);
      toast({
        title: t('module.billing.admin.adjust.success', {
          creatorBid: result.creator_bid,
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
          <div className='grid gap-2'>
            <label
              htmlFor='admin-billing-adjust-creator-bid'
              className='text-sm font-medium text-slate-900'
            >
              {t('module.billing.admin.adjust.fields.creatorBid')}
            </label>
            <Input
              id='admin-billing-adjust-creator-bid'
              value={creatorBid}
              disabled={submitting}
              placeholder={t(
                'module.billing.admin.adjust.placeholders.creatorBid',
              )}
              onChange={event => setCreatorBid(event.target.value)}
            />
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
              onChange={event => setAmount(event.target.value)}
            />
            <p className='text-xs leading-5 text-slate-500'>
              {t('module.billing.admin.adjust.help.amount')}
            </p>
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
