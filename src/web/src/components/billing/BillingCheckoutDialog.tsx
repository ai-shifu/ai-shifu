import React from 'react';
import { useTranslation } from 'react-i18next';
import { getPaymentAgreementUrl } from '@/lib/url-utils';
import { Checkbox } from '@/components/ui/Checkbox';
import { Button } from '@/components/ui/Button';
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
  priceLabel: string;
  productName: string;
  providerLabel: string;
  agreed: boolean;
  onConfirm: () => void;
  onAgreedChange: (agreed: boolean) => void;
  onOpenChange: (open: boolean) => void;
};

export function BillingCheckoutDialog({
  creditsLabel,
  description,
  isLoading = false,
  open,
  priceLabel,
  productName,
  providerLabel,
  agreed,
  onConfirm,
  onAgreedChange,
  onOpenChange,
}: BillingCheckoutDialogProps) {
  const { t } = useTranslation();
  const agreementUrl = getPaymentAgreementUrl();

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
        {agreementUrl ? (
          <div className='flex items-center gap-2 text-sm text-slate-600'>
            <Checkbox
              id='billing-checkout-agreement'
              checked={agreed}
              onCheckedChange={checked => onAgreedChange(checked === true)}
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
