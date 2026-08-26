import { ExternalLink, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/Dialog';

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
    <Dialog open={open}>
      <DialogContent
        aria-describedby='billing-stripe-redirect-description'
        className='z-[111] w-full max-w-sm rounded-3xl border border-white/40 bg-white p-6 text-center shadow-2xl sm:rounded-3xl'
        data-testid='billing-stripe-redirect-overlay'
        onEscapeKeyDown={event => event.preventDefault()}
        onPointerDownOutside={event => event.preventDefault()}
        overlayClassName='z-[110] bg-slate-950/55 backdrop-blur-sm'
        showClose={false}
      >
        <div className='mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary'>
          <Loader2 className='h-6 w-6 animate-spin' />
        </div>
        <DialogTitle className='mt-4 text-lg font-semibold text-slate-950'>
          {title}
        </DialogTitle>
        <DialogDescription
          aria-live='polite'
          className='mt-2 text-sm leading-6 text-slate-600'
          id='billing-stripe-redirect-description'
          role='status'
        >
          {t('module.billing.checkout.redirect.description')}
        </DialogDescription>
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
      </DialogContent>
    </Dialog>
  );
}
