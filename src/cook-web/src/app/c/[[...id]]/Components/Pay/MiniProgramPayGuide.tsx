import { memo, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import MainButtonM from '@/c-components/m/MainButtonM';

interface MiniProgramPayGuideProps {
  open: boolean;
  onClose: () => void;
}

const MiniProgramPayGuide = ({ open, onClose }: MiniProgramPayGuideProps) => {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const handleCopyLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = window.location.href;
      textArea.style.position = 'fixed';
      textArea.style.opacity = '0';
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, []);

  return (
    <Dialog
      open={open}
      onOpenChange={nextOpen => {
        if (!nextOpen) onClose();
      }}
    >
      <DialogContent className='w-full max-w-sm'>
        <DialogHeader>
          <DialogTitle>{t('module.pay.miniProgramNotSupported')}</DialogTitle>
        </DialogHeader>
        <div className='flex flex-col items-center gap-4 px-4 pb-4'>
          <p className='text-sm text-muted-foreground text-center'>
            {t('module.pay.miniProgramGuide')}
          </p>
          <MainButtonM
            className='w-full'
            onClick={handleCopyLink}
          >
            {copied ? t('module.pay.linkCopied') : t('module.pay.copyLink')}
          </MainButtonM>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default memo(MiniProgramPayGuide);
