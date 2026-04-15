'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Gift } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import type {
  BillingTrialOffer,
  CreatorBillingOverview,
} from '@/types/billing';

const DISMISSED_KEY = 'ai-shifu:welcome-trial-dismissed';

// TODO: remove after backend returns trial_offer with status 'eligible'
const FALLBACK_TRIAL_OFFER: BillingTrialOffer = {
  enabled: true,
  status: 'eligible',
  credit_amount: 100,
  valid_days: 15,
  starts_on_first_grant: true,
  granted_at: null,
  expires_at: null,
};

const APP_NAME_BY_LANG: Record<string, string> = {
  'zh-CN': 'AI 师傅',
  zh: 'AI 师傅',
};
const APP_NAME_DEFAULT = 'AI Shifu';

interface WelcomeTrialDialogProps {
  billingOverview: CreatorBillingOverview | undefined;
  menuReady: boolean;
}

export function WelcomeTrialDialog({
  billingOverview,
  menuReady,
}: WelcomeTrialDialogProps) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);

  // TODO: remove FALLBACK_TRIAL_OFFER after backend returns trial_offer with status 'eligible'
  const serverTrialOffer = billingOverview?.trial_offer;
  const trialOffer =
    serverTrialOffer?.status === 'eligible'
      ? serverTrialOffer
      : FALLBACK_TRIAL_OFFER;

  useEffect(() => {
    if (
      menuReady &&
      trialOffer.status === 'eligible' &&
      !localStorage.getItem(DISMISSED_KEY)
    ) {
      setOpen(true);
    }
  }, [menuReady, trialOffer.status]);

  const handleDismiss = useCallback(() => {
    localStorage.setItem(DISMISSED_KEY, '1');
    setOpen(false);
  }, []);

  const appName =
    APP_NAME_BY_LANG[i18n.language] ??
    APP_NAME_BY_LANG[i18n.language.split('-')[0]] ??
    APP_NAME_DEFAULT;

  return (
    <Dialog
      open={open}
      onOpenChange={val => !val && handleDismiss()}
    >
      <DialogContent
        className='max-w-md'
        showClose
      >
        <DialogHeader className='items-center text-center'>
          <div className='mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10'>
            <Gift className='h-7 w-7 text-primary' />
          </div>
          <DialogTitle className='text-xl'>
            {t('module.billing.welcomeTrial.title', { appName })}
          </DialogTitle>
          <DialogDescription className='mt-2 text-sm leading-relaxed'>
            {t('module.billing.welcomeTrial.description', {
              credits: trialOffer.credit_amount,
              days: trialOffer.valid_days,
            })}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className='mt-2 sm:justify-center'>
          <Button
            onClick={handleDismiss}
            className='min-w-[160px]'
          >
            {t('module.billing.welcomeTrial.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
