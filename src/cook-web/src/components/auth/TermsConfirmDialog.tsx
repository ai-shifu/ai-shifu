'use client';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';
import { Trans, useTranslation } from 'react-i18next';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';

interface TermsConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  onCancel: () => void;
}

export function TermsConfirmDialog({
  open,
  onOpenChange,
  onConfirm,
  onCancel,
}: TermsConfirmDialogProps) {
  const { t, i18n } = useTranslation();
  const legalUrls = useEnvStore((state: EnvStoreState) => state.legalUrls);

  // Get current language URL with fallback
  const langKey = (i18n.language || 'en-US').startsWith('zh')
    ? 'zh-CN'
    : 'en-US';
  const agreementUrl =
    legalUrls?.agreement?.[langKey] || legalUrls?.agreement?.['en-US'] || '';
  const privacyUrl =
    legalUrls?.privacy?.[langKey] || legalUrls?.privacy?.['en-US'] || '';

  const handleConfirm = () => {
    onConfirm();
  };

  const handleCancel = () => {
    onCancel();
  };

  return (
    <AlertDialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className='text-center'>
            {t('module.auth.termsDialogTitle')}
          </AlertDialogTitle>
        </AlertDialogHeader>

        <div className='py-4 text-left'>
          <p className='text-sm text-muted-foreground'>
            {t('module.auth.termsDialogDescription')}{' '}
            <Trans
              i18nKey='module.auth.readAndAgreeLinks'
              components={{
                serviceAgreement: agreementUrl ? (
                  <a
                    href={agreementUrl}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='text-primary hover:underline mx-1 whitespace-nowrap'
                  />
                ) : (
                  <span className='mx-1' />
                ),
                privacyPolicy: privacyUrl ? (
                  <a
                    href={privacyUrl}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='text-primary hover:underline mx-1 whitespace-nowrap'
                  />
                ) : (
                  <span className='mx-1' />
                ),
              }}
              values={{
                serviceLabel: t('module.auth.serviceAgreement'),
                privacyLabel: t('module.auth.privacyPolicy'),
              }}
            />
          </p>
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel onClick={handleCancel}>
            {t('module.auth.disagree')}
          </AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm}>
            {t('module.auth.agree')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
