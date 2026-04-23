'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyedMutator } from 'swr';
import { useTranslation } from 'react-i18next';
import { Gift } from 'lucide-react';
import api from '@/api';
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
  BillingTrialWelcomeAckResult,
  CreatorBillingOverview,
} from '@/types/billing';

const APP_NAME_BY_LANG: Record<string, string> = {
  'zh-CN': 'AI 师傅',
  zh: 'AI 师傅',
};
const APP_NAME_DEFAULT = 'AI Shifu';
const shownTrialGrantFingerprints = new Set<string>();

interface WelcomeTrialDialogProps {
  billingOverview: CreatorBillingOverview | undefined;
  menuReady: boolean;
  mutateBillingOverview: KeyedMutator<CreatorBillingOverview>;
}

export function WelcomeTrialDialog({
  billingOverview,
  menuReady,
  mutateBillingOverview,
}: WelcomeTrialDialogProps) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const dismissingRef = useRef(false);
  const trialOffer = billingOverview?.trial_offer;
  const creatorBid = billingOverview?.creator_bid || '';
  const grantFingerprint =
    creatorBid && trialOffer?.product_code && trialOffer.granted_at
      ? `${creatorBid}:${trialOffer.product_code}:${trialOffer.granted_at}`
      : '';

  useEffect(() => {
    if (
      !menuReady ||
      !trialOffer ||
      trialOffer.status !== 'granted' ||
      !trialOffer.granted_at ||
      trialOffer.welcome_dialog_acknowledged_at ||
      !grantFingerprint ||
      shownTrialGrantFingerprints.has(grantFingerprint)
    ) {
      return;
    }
    shownTrialGrantFingerprints.add(grantFingerprint);
    setOpen(true);
  }, [grantFingerprint, menuReady, trialOffer]);

  const handleDismiss = useCallback(() => {
    if (dismissingRef.current) {
      return;
    }
    dismissingRef.current = true;
    setOpen(false);
    if (
      !creatorBid ||
      !trialOffer ||
      trialOffer.status !== 'granted' ||
      trialOffer.welcome_dialog_acknowledged_at
    ) {
      dismissingRef.current = false;
      return;
    }
    void (async () => {
      try {
        const result = (await api.acknowledgeBillingTrialWelcome(
          {},
        )) as BillingTrialWelcomeAckResult;
        if (result.acknowledged) {
          const acknowledgedAt =
            result.acknowledged_at || new Date().toISOString();
          await mutateBillingOverview(
            currentOverview => {
              if (
                !currentOverview ||
                currentOverview.creator_bid !== creatorBid
              ) {
                return currentOverview;
              }
              return {
                ...currentOverview,
                trial_offer: {
                  ...currentOverview.trial_offer,
                  welcome_dialog_acknowledged_at: acknowledgedAt,
                },
              };
            },
            {
              revalidate: false,
            },
          );
        }
      } catch {
        // Ignore ack failures. The dialog is already closed and the next
        // admin mount can retry if the ack did not persist.
      } finally {
        dismissingRef.current = false;
      }
    })();
  }, [creatorBid, mutateBillingOverview, trialOffer]);

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
        data-testid='welcome-trial-dialog'
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
              credits: trialOffer?.credit_amount || 0,
              days: trialOffer?.valid_days || 0,
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
