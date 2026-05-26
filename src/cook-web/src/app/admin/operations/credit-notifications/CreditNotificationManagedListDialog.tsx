import { Search, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import type { AdminOperationCreditNotificationPolicyListItem } from '../operation-credit-notification-types';

export type CreditNotificationManagedListType = 'blocked' | 'opted_out';

export function CreditNotificationManagedListDialog({
  open,
  title,
  canDelete,
  contactMode,
  items,
  search,
  onSearchChange,
  onRemove,
  onClose,
}: {
  open: boolean;
  title: string;
  canDelete: boolean;
  contactMode: 'email' | 'phone';
  items: AdminOperationCreditNotificationPolicyListItem[];
  search: string;
  onSearchChange: (value: string) => void;
  onRemove: (identifier: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();

  return (
    <Dialog
      open={open}
      onOpenChange={nextOpen => {
        if (!nextOpen) {
          onClose();
        }
      }}
    >
      <DialogContent className='max-w-2xl'>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {t(
              canDelete
                ? 'module.operationsCreditNotifications.config.listDialog.blockedDescription'
                : 'module.operationsCreditNotifications.config.listDialog.optedOutDescription',
            )}
          </DialogDescription>
        </DialogHeader>
        <div className='space-y-3'>
          <div className='relative'>
            <Search className='pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' />
            <Input
              className='h-9 pl-9'
              value={search}
              placeholder={t(
                contactMode === 'email'
                  ? 'module.operationsCreditNotifications.config.listDialog.searchPlaceholderEmail'
                  : 'module.operationsCreditNotifications.config.listDialog.searchPlaceholderPhone',
              )}
              onChange={event => onSearchChange(event.target.value)}
            />
          </div>
          <div
            className={`grid max-h-[360px] grid-cols-1 gap-2 overflow-auto rounded-md border border-border p-2 ${
              canDelete ? 'md:grid-cols-2' : 'md:grid-cols-3'
            }`}
          >
            {items.length > 0 ? (
              items.map(item => {
                const contactValue =
                  contactMode === 'email'
                    ? item.email || item.identifier
                    : item.mobile || item.identifier;
                return (
                  <div
                    key={item.identifier}
                    className='group flex items-center justify-between gap-2 rounded-md bg-muted/30 px-3 py-2 transition-colors hover:bg-muted/50'
                  >
                    <div className='min-w-0'>
                      <p className='truncate text-sm font-medium text-foreground'>
                        {contactValue}
                      </p>
                      <p className='mt-0.5 truncate text-xs text-muted-foreground'>
                        {item.nickname ||
                          t(
                            'module.operationsCreditNotifications.config.listDialog.emptyNickname',
                          )}
                      </p>
                    </div>
                    {canDelete ? (
                      <button
                        type='button'
                        className='inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-white hover:text-slate-700'
                        onClick={() => onRemove(item.identifier)}
                        aria-label={t(
                          'module.operationsCreditNotifications.config.listDialog.delete',
                        )}
                      >
                        <X className='h-4 w-4' />
                      </button>
                    ) : null}
                  </div>
                );
              })
            ) : (
              <div
                className={`py-8 text-center text-sm text-muted-foreground ${
                  canDelete ? 'md:col-span-2' : 'md:col-span-3'
                }`}
              >
                {t(
                  'module.operationsCreditNotifications.config.listDialog.emptyResult',
                )}
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button
            type='button'
            onClick={onClose}
          >
            {t('common.core.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
