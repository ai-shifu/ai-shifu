import React from 'react';
import { useTranslation } from 'react-i18next';
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
  onConfirm: () => void;
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
  onConfirm,
  onOpenChange,
}: BillingCheckoutDialogProps) {
  const { t } = useTranslation();

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
            disabled={isLoading}
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
