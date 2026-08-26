import { ExternalLink, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';

export type BillingStripeRedirectPhase = 'creating' | 'redirecting';

type BillingStripeRedirectOverlayProps = {
  open: boolean;
  phase: BillingStripeRedirectPhase;
  retryUrl?: string;
  onRetry?: () => void;
};

export function BillingStripeRedirectOverlay({
  open,
  phase,
  retryUrl = '',
  onRetry,
}: BillingStripeRedirectOverlayProps) {
  const { t } = useTranslation();

  if (!open) {
    return null;
  }

  const title =
    phase === 'redirecting'
      ? t('module.billing.checkout.redirect.openingStripe')
      : t('module.billing.checkout.redirect.creating');

  return (
    <div
      aria-live='polite'
      className='fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/55 px-4 backdrop-blur-sm'
      data-testid='billing-stripe-redirect-overlay'
      role='status'
    >
      <div className='w-full max-w-sm rounded-3xl border border-white/40 bg-white p-6 text-center shadow-2xl'>
        <div className='mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary'>
          <Loader2 className='h-6 w-6 animate-spin' />
        </div>
        <h2 className='mt-4 text-lg font-semibold text-slate-950'>{title}</h2>
        <p className='mt-2 text-sm leading-6 text-slate-600'>
          {t('module.billing.checkout.redirect.description')}
        </p>
        {phase === 'redirecting' && retryUrl ? (
          <Button
            className='mt-5 w-full gap-2'
            onClick={onRetry}
            type='button'
            variant='outline'
          >
            <ExternalLink className='h-4 w-4' />
            {t('module.billing.checkout.redirect.retry')}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
