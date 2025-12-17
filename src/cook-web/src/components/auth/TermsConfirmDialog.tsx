'use client';

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
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

  // Get current language URL
  const currentLang = (i18n.language || 'en-US') as 'zh-CN' | 'en-US';
  const agreementUrl = legalUrls?.agreement?.[currentLang] || '';
  const privacyUrl = legalUrls?.privacy?.[currentLang] || '';

  const handleConfirm = () => {
    onConfirm();
    onOpenChange(false);
  };

  const handleCancel = () => {
    onCancel();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-center">
            {t('module.auth.termsDialogTitle')}
          </DialogTitle>
        </DialogHeader>
        
        <div className="py-4 text-center">
          <p className="text-sm text-muted-foreground mb-4">
            {t('module.auth.termsDialogDescription')}
          </p>
          
          <div className="text-sm">
            <Trans
              i18nKey="module.auth.readAndAgreeLinks"
              components={{
                serviceAgreement: agreementUrl ? (
                  <a
                    href={agreementUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline mx-1"
                  />
                ) : (
                  <span className="mx-1" />
                ),
                privacyPolicy: privacyUrl ? (
                  <a
                    href={privacyUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline mx-1"
                  />
                ) : (
                  <span className="mx-1" />
                ),
              }}
              values={{
                serviceLabel: t('module.auth.serviceAgreement'),
                privacyLabel: t('module.auth.privacyPolicy'),
              }}
            />
          </div>
        </div>

        <DialogFooter className="grid grid-cols-2 gap-2">
          <Button
            variant="outline"
            onClick={handleCancel}
            className="w-full"
          >
            {t('module.auth.disagree')}
          </Button>
          <Button
            onClick={handleConfirm}
            className="w-full"
          >
            {t('module.auth.agree')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}