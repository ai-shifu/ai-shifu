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
  mode?: 'other-user' | 'same-user';
  phone?: string;
  onRefresh: () => void;
}

const DraftConflictDialog = ({
  open,
  mode = 'other-user',
  phone,
  onRefresh,
}: DraftConflictDialogProps) => {
  const { t } = useTranslation();
  const displayPhone =
    phone || t('module.shifuSetting.draftConflictUnknownUser');
  const isOtherUserMode = mode === 'other-user';
  const title = isOtherUserMode
    ? t('module.shifuSetting.draftConflictTitle')
    : t('module.shifuSetting.draftSelfUpdateTitle');
  const description = isOtherUserMode
    ? t('module.shifuSetting.draftConflictDescription', {
        phone: displayPhone,
      })
    : t('module.shifuSetting.draftSelfUpdateDescription');

  return (
    <Dialog open={open}>
      <DialogContent
        className='sm:max-w-md'
        showClose={false}
        onEscapeKeyDown={event => event.preventDefault()}
        onInteractOutside={event => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className='text-sm text-gray-600'>{description}</div>
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
