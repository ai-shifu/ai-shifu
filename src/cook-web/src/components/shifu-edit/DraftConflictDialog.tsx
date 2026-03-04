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
}

const DraftConflictDialog = ({
  open,
  phone,
  onRefresh,
}: DraftConflictDialogProps) => {
  const { t } = useTranslation();
  const displayPhone =
    phone || t('module.shifuSetting.draftConflictUnknownUser');

  return (
    <Dialog open={open}>
      <DialogContent
        className='sm:max-w-md'
        showClose={false}
        onEscapeKeyDown={event => event.preventDefault()}
        onInteractOutside={event => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>
            {t('module.shifuSetting.draftConflictTitle')}
          </DialogTitle>
        </DialogHeader>
        <div className='text-sm text-gray-600'>
          {t('module.shifuSetting.draftConflictDescription', {
            phone: displayPhone,
          })}
        </div>
        <DialogFooter>
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
