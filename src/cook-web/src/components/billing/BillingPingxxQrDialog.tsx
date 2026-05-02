import React, { useState, useEffect } from 'react';
import { LoaderIcon } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { useTranslation } from 'react-i18next';
import { getPaymentAgreementUrl } from '@/c-utils/urlUtils';
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
import { cn } from '@/lib/utils';
import {
  formatBillingPrice,
  resolveBillingPingxxChannelLabel,
} from '@/lib/billing';
import type { BillingPingxxChannel, BillingProvider } from '@/types/billing';

const BILLING_PINGXX_CHANNELS: BillingPingxxChannel[] = [
  'wx_pub_qr',
  'alipay_qr',
];

type BillingPingxxQrDialogProps = {
  amountInMinor: number;
  currency: string;
  description: string;
  isLoading?: boolean;
  open: boolean;
  productName: string;
  provider?: BillingProvider;
  qrUrl: string;
  selectedChannel: BillingPingxxChannel;
  onChannelChange: (channel: BillingPingxxChannel) => void;
  onOpenChange: (open: boolean) => void;
};

export function BillingPingxxQrDialog({
  amountInMinor,
  currency,
  description,
  isLoading = false,
  open,
  productName,
  provider = 'pingxx',
  qrUrl,
  selectedChannel,
  onChannelChange,
  onOpenChange,
}: BillingPingxxQrDialogProps) {
  const { t, i18n } = useTranslation();
  const [agreed, setAgreed] = useState(false);
  const agreementUrl = getPaymentAgreementUrl();
  const availableChannels =
    provider === 'alipay'
      ? (['alipay_qr'] as BillingPingxxChannel[])
      : provider === 'wechatpay'
        ? (['wx_pub_qr'] as BillingPingxxChannel[])
        : BILLING_PINGXX_CHANNELS;

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
            <span>{t('module.billing.checkout.priceLabel')}</span>
            <span className='text-right font-semibold text-slate-900'>
              {formatBillingPrice(amountInMinor, currency, i18n.language)}
            </span>
          </div>
        </div>

        <div className='grid gap-3'>
          <div className='grid grid-cols-2 gap-2'>
            {availableChannels.map(channel => (
              <Button
                key={channel}
                className='rounded-xl'
                data-testid={`billing-pingxx-channel-${channel}`}
                disabled={isLoading}
                onClick={() => {
                  if (channel !== selectedChannel) {
                    onChannelChange(channel);
                  }
                }}
                type='button'
                variant={channel === selectedChannel ? 'default' : 'outline'}
              >
                {resolveBillingPingxxChannelLabel(t, channel)}
              </Button>
            ))}
          </div>

          <div className='flex flex-col items-center gap-4 rounded-2xl border border-slate-200 bg-white px-4 py-5'>
            <div className='relative'>
              <QRCodeSVG
                data-testid='billing-pingxx-qr-code'
                level='M'
                size={192}
                value={qrUrl || 'billing-pingxx-qrcode-placeholder'}
              />
              {isLoading ? (
                <div className='absolute inset-0 flex items-center justify-center rounded-md bg-white/80'>
                  <LoaderIcon className='h-8 w-8 animate-spin text-slate-500' />
                </div>
              ) : null}
            </div>
            <p className='text-center text-sm text-slate-500'>
              {resolveBillingPingxxChannelLabel(t, selectedChannel)}
            </p>
          </div>
        </div>

        {agreementUrl ? (
          <div className='flex items-center gap-2 text-sm text-slate-600'>
            <Checkbox
              id='billing-pingxx-agreement'
              checked={agreed}
              onCheckedChange={checked => setAgreed(checked === true)}
            />
            <label
              htmlFor='billing-pingxx-agreement'
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
          >
            {t('module.billing.checkout.cancel')}
          </Button>
          <Button
            className={cn('sm:min-w-32')}
            disabled={isLoading || (agreementUrl !== null && !agreed)}
            onClick={() => onChannelChange(selectedChannel)}
            type='button'
            variant='secondary'
          >
            {isLoading
              ? t('module.billing.checkout.processing')
              : t('module.pay.clickRefresh')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
