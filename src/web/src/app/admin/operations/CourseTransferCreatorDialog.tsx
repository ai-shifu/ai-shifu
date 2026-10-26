import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import type { AdminOperationCourseItem } from './operation-course-types';
import {
  SINGLE_SELECT_ITEM_CLASS,
  type TransferContactType,
} from './operationCoursePageShared';

type ActorDisplay = {
  primary: string;
  secondary: string;
};

type CourseTransferCreatorDialogProps = {
  open: boolean;
  confirmOpen: boolean;
  loading: boolean;
  targetCourse: AdminOperationCourseItem | null;
  courseName: string;
  creatorDisplay: ActorDisplay;
  contactOptions: TransferContactType[];
  contactType: TransferContactType;
  identifier: string;
  identifierPlaceholder: string;
  error: string;
  currentCreatorText: string;
  targetCreatorText: string;
  hintText: string;
  onOpenChange: (open: boolean) => void;
  onConfirmOpenChange: (open: boolean) => void;
  onContactTypeChange: (value: TransferContactType) => void;
  onIdentifierChange: (value: string) => void;
  onSubmit: () => void;
  onConfirm: () => void;
};

export default function CourseTransferCreatorDialog({
  open,
  confirmOpen,
  loading,
  targetCourse,
  courseName,
  creatorDisplay,
  contactOptions,
  contactType,
  identifier,
  identifierPlaceholder,
  error,
  currentCreatorText,
  targetCreatorText,
  hintText,
  onOpenChange,
  onConfirmOpenChange,
  onContactTypeChange,
  onIdentifierChange,
  onSubmit,
  onConfirm,
}: CourseTransferCreatorDialogProps) {
  const { t } = useTranslation();
  const { t: tOperations } = useTranslation('module.operationsCourse');

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={onOpenChange}
      >
        <DialogContent className='overflow-hidden p-0 gap-0 sm:max-w-[440px]'>
          <DialogHeader className='border-b border-border px-6 pb-4 pt-6'>
            <DialogTitle>
              {tOperations('transferCreatorDialog.title')}
            </DialogTitle>
            <p className='mt-2 text-sm leading-6 text-muted-foreground'>
              {hintText}
            </p>
          </DialogHeader>

          <div className='space-y-5 px-6 py-5'>
            <div className='rounded-xl border border-border bg-muted/[0.18] p-3.5'>
              <div className='space-y-3'>
                <div className='space-y-1'>
                  <div className='text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground/90'>
                    {tOperations('table.courseName')}
                  </div>
                  <div className='text-[15px] font-medium leading-5 text-foreground'>
                    {courseName}
                  </div>
                </div>

                <div className='h-px bg-border/80' />

                <div className='space-y-1'>
                  <div className='text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground/90'>
                    {tOperations('transferCreatorDialog.currentCreator')}
                  </div>
                  <div className='text-[15px] font-medium leading-5 text-foreground'>
                    {creatorDisplay.secondary || creatorDisplay.primary || '--'}
                  </div>
                  {creatorDisplay.primary && creatorDisplay.secondary ? (
                    <div className='text-sm text-muted-foreground'>
                      {creatorDisplay.primary}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>

            <div className='space-y-2.5'>
              {contactOptions.length > 1 ? (
                <div className='space-y-2.5'>
                  <Label className='text-sm font-medium text-foreground'>
                    {tOperations('transferCreatorDialog.contactType')}
                  </Label>
                  <Select
                    value={contactType}
                    onValueChange={value =>
                      onContactTypeChange(value as TransferContactType)
                    }
                  >
                    <SelectTrigger className='h-11 rounded-lg'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem
                        value='email'
                        className={SINGLE_SELECT_ITEM_CLASS}
                      >
                        {tOperations('transferCreatorDialog.contactTypeEmail')}
                      </SelectItem>
                      <SelectItem
                        value='phone'
                        className={SINGLE_SELECT_ITEM_CLASS}
                      >
                        {tOperations('transferCreatorDialog.contactTypePhone')}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              ) : null}
              <Label
                htmlFor='transfer-identifier'
                className='text-sm font-medium text-foreground'
              >
                {tOperations('transferCreatorDialog.identifier')}
              </Label>
              <Input
                id='transfer-identifier'
                value={identifier}
                placeholder={identifierPlaceholder}
                className='h-11 rounded-lg'
                onChange={event => onIdentifierChange(event.target.value)}
                autoComplete='off'
              />
              {error ? (
                <p className='text-sm text-destructive'>{error}</p>
              ) : null}
            </div>
          </div>

          <DialogFooter className='gap-2 border-t border-border bg-background px-6 py-4'>
            <Button
              variant='outline'
              onClick={() => onOpenChange(false)}
              disabled={loading}
              className='min-w-24'
            >
              {t('common.core.cancel')}
            </Button>
            <Button
              onClick={onSubmit}
              disabled={loading || !targetCourse}
              className='min-w-28'
            >
              {tOperations('transferCreatorDialog.confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={confirmOpen}
        onOpenChange={onConfirmOpenChange}
      >
        <AlertDialogContent className='sm:max-w-[420px]'>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {tOperations('transferCreatorDialog.confirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              <span className='leading-8 text-muted-foreground'>
                {tOperations('transferCreatorDialog.confirmDescription', {
                  courseName,
                  currentCreator: currentCreatorText,
                  targetCreator: targetCreatorText,
                })}
              </span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={loading}>
              {t('common.core.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={onConfirm}
              disabled={loading}
            >
              {tOperations('transferCreatorDialog.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
