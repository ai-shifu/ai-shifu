import { useTranslation } from 'react-i18next';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';

interface DraftConflictDialogProps {
  open: boolean;
  phone?: string;
  onRefresh: () => void;
  onCancel: () => void;
}

const DraftConflictDialog = ({
  open,
  phone,
  onRefresh,
  onCancel,
}: DraftConflictDialogProps) => {
  const { t } = useTranslation();
  const displayPhone =
    phone || t('module.shifuSetting.draftConflictUnknownUser');

  return (
    <Dialog
      open={open}
      onOpenChange={nextOpen => {
        if (!nextOpen) {
          onCancel();
        }
      }}
    >
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{t('module.shifuSetting.draftConflictTitle')}</DialogTitle>
        </DialogHeader>
        <div className='text-sm text-gray-600'>
          {t('module.shifuSetting.draftConflictDescription', {
            phone: displayPhone,
          })}
        </div>
        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            onClick={onCancel}
            className='min-w-[120px]'
          >
            {t('module.shifuSetting.draftConflictCancel')}
          </Button>
          <Button
            type='button'
            onClick={onRefresh}
            className='min-w-[120px]'
          >
            {t('module.shifuSetting.draftConflictRefresh')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default DraftConflictDialog;
