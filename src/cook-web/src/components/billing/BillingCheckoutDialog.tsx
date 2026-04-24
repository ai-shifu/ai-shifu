import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { getPaymentAgreementUrl } from '@/c-utils/urlUtils';
import { Checkbox } from '@/components/ui/Checkbox';
import { Button } from '@/components/ui/Button';
import { resolveBillingPingxxChannelLabel } from '@/lib/billing';
import type { BillingPingxxChannel } from '@/types/billing';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';

type BillingCheckoutDialogProps = {
  creditsLabel: string;
  description: string;
  isLoading?: boolean;
  open: boolean;
  pingxxChannel?: BillingPingxxChannel | null;
  priceLabel: string;
  productName: string;
  providerLabel: string;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
  onPingxxChannelChange?: (channel: BillingPingxxChannel) => void;
};

export function BillingCheckoutDialog({
  creditsLabel,
  description,
  isLoading = false,
  open,
  pingxxChannel = null,
  priceLabel,
  productName,
  providerLabel,
  onConfirm,
  onOpenChange,
  onPingxxChannelChange,
}: BillingCheckoutDialogProps) {
  const { t } = useTranslation();
  const [agreed, setAgreed] = useState(false);
  const agreementUrl = getPaymentAgreementUrl();

  useEffect(() => {
    if (!open) setAgreed(false);
  }, [open]);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='border-slate-200 bg-white sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{t('module.billing.checkout.title')}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className='grid gap-3 rounded-2xl bg-slate-50 p-4 text-sm text-slate-600'>
          <div className='flex items-center justify-between gap-3'>
            <span>{t('module.billing.checkout.productLabel')}</span>
            <span className='text-right font-semibold text-slate-900'>
              {productName}
            </span>
          </div>
          <div className='flex items-center justify-between gap-3'>
            <span>{t('module.billing.checkout.providerLabel')}</span>
            <span className='text-right font-semibold text-slate-900'>
              {providerLabel}
            </span>
          </div>
          <div className='flex items-center justify-between gap-3'>
            <span>{t('module.billing.checkout.priceLabel')}</span>
            <span className='text-right font-semibold text-slate-900'>
              {priceLabel}
            </span>
          </div>
          <div className='flex items-center justify-between gap-3'>
            <span>{t('module.billing.checkout.creditsLabel')}</span>
            <span className='text-right font-semibold text-slate-900'>
              {creditsLabel}
            </span>
          </div>
        </div>
        {pingxxChannel ? (
          <div className='grid grid-cols-2 gap-2'>
            {(['wx_pub_qr', 'alipay_qr'] as BillingPingxxChannel[]).map(
              channel => (
                <Button
                  key={channel}
                  className='rounded-xl'
                  data-testid={`billing-checkout-channel-${channel}`}
                  disabled={isLoading}
                  onClick={() => onPingxxChannelChange?.(channel)}
                  type='button'
                  variant={channel === pingxxChannel ? 'default' : 'outline'}
                >
                  {resolveBillingPingxxChannelLabel(t, channel)}
                </Button>
              ),
            )}
          </div>
        ) : null}
        {agreementUrl ? (
          <div className='flex items-center gap-2 text-sm text-slate-600'>
            <Checkbox
              id='billing-checkout-agreement'
              checked={agreed}
              onCheckedChange={checked => setAgreed(checked === true)}
            />
            <label
              htmlFor='billing-checkout-agreement'
              className='cursor-pointer leading-none'
            >
              {t('module.billing.checkout.agreementPrefix')}{' '}
              <a
                href={agreementUrl}
                target='_blank'
                rel='noopener noreferrer'
                className='text-primary underline underline-offset-2'
                onClick={e => e.stopPropagation()}
              >
                {t('module.billing.checkout.agreementLink')}
              </a>
            </label>
          </div>
        ) : null}
        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            onClick={() => onOpenChange(false)}
            disabled={isLoading}
          >
            {t('module.billing.checkout.cancel')}
          </Button>
          <Button
            type='button'
            onClick={onConfirm}
            disabled={isLoading || (agreementUrl !== null && !agreed)}
          >
            {isLoading
              ? t('module.billing.checkout.processing')
              : t('module.billing.checkout.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
