'use client';

import { useTranslation } from 'react-i18next';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';

interface DraftConflictDialogProps {
  open: boolean;
  phone?: string;
  onRefresh: () => void;
}

const DraftConflictDialog = ({
  open,
  phone,
  onRefresh,
}: DraftConflictDialogProps) => {
  const { t } = useTranslation();
  const description = phone
    ? t('module.shifu.draftConflict.descriptionWithPhone', { phone })
    : t('module.shifu.draftConflict.description');

  return (
    <Dialog
      open={open}
      onOpenChange={() => {
        return;
      }}
    >
      <DialogContent className='sm:max-w-md [&>button]:hidden'>
        <DialogHeader>
          <DialogTitle>{t('module.shifu.draftConflict.title')}</DialogTitle>
        </DialogHeader>
        <DialogDescription>{description}</DialogDescription>
        <DialogFooter className='mt-4'>
          <Button
            type='button'
            onClick={onRefresh}
          >
            {t('module.shifu.draftConflict.refresh')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default DraftConflictDialog;
