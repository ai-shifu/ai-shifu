'use client';

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useUiLayoutStore } from '@/c-store/useUiLayoutStore';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';

export default function MobileUnsupportedDialog() {
  const { t } = useTranslation();
  const inMobile = useUiLayoutStore(state => state.inMobile);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(inMobile);
  }, [inMobile]);

  if (!inMobile) {
    return null;
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={setOpen}
    >
      <AlertDialogContent className='w-[calc(100vw-32px)] max-w-md sm:max-w-md'>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {t('common.core.mobileUnsupportedTitle')}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {t('common.core.mobileUnsupportedDescription')}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogAction onClick={() => setOpen(false)}>
            {t('common.core.ok')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
