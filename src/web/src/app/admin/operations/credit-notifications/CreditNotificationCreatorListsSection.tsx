import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import {
  CreditNotificationConfigSection as ConfigSection,
  CreditNotificationFormField as FormField,
} from './CreditNotificationFormPrimitives';
import type { CreditNotificationManagedListType } from './CreditNotificationManagedListDialog';
import { normalizeListInputCharacters } from './creditNotificationUtils';

const summarizeIdentifiers = (identifiers: string[], emptyText: string) => {
  if (identifiers.length === 0) {
    return emptyText;
  }
  const visibleItems = identifiers.slice(0, 3).join(', ');
  const restCount = identifiers.length - 3;
  return restCount > 0 ? `${visibleItems} +${restCount}` : visibleItems;
};

const resolveSummaryCountKey = (type: CreditNotificationManagedListType) =>
  type === 'blocked'
    ? 'module.operationsCreditNotifications.config.listDialog.blockedSummary'
    : 'module.operationsCreditNotifications.config.listDialog.optedOutSummary';

export function CreditNotificationCreatorListsSection({
  contactMode,
  blockedCreatorInput,
  blockedCreatorIdentifiers,
  optedOutCreatorIdentifiers,
  onBlockedCreatorInputChange,
  onAddBlockedCreators,
  onOpenManagedListDialog,
}: {
  contactMode: 'email' | 'phone';
  blockedCreatorInput: string;
  blockedCreatorIdentifiers: string[];
  optedOutCreatorIdentifiers: string[];
  onBlockedCreatorInputChange: (value: string) => void;
  onAddBlockedCreators: () => void;
  onOpenManagedListDialog: (
    listType: CreditNotificationManagedListType,
  ) => void;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const emptyPreview = t(
    'module.operationsCreditNotifications.config.listDialog.emptyPreview',
  );
  const openManagedListFromDialog = (
    listType: CreditNotificationManagedListType,
  ) => {
    setEditing(false);
    onOpenManagedListDialog(listType);
  };

  return (
    <>
      <ConfigSection
        title={t('module.operationsCreditNotifications.config.sections.lists')}
        description={t(
          'module.operationsCreditNotifications.config.sectionDescriptions.lists',
        )}
        action={
          <Button
            type='button'
            variant='outline'
            onClick={() => setEditing(true)}
          >
            {t(
              'module.operationsCreditNotifications.config.listDialog.manageLists',
            )}
          </Button>
        }
      >
        <div className='grid gap-3 lg:grid-cols-2'>
          <ListSummaryCard
            count={blockedCreatorIdentifiers.length}
            label={
              blockedCreatorIdentifiers.length > 0
                ? t(resolveSummaryCountKey('blocked'), {
                    count: blockedCreatorIdentifiers.length,
                  })
                : t(
                    'module.operationsCreditNotifications.config.emptyBlockedCreators',
                  )
            }
            preview={summarizeIdentifiers(
              blockedCreatorIdentifiers,
              emptyPreview,
            )}
            actionLabel={t(
              'module.operationsCreditNotifications.config.listDialog.manage',
            )}
            onClick={() => onOpenManagedListDialog('blocked')}
          />
          <ListSummaryCard
            count={optedOutCreatorIdentifiers.length}
            label={
              optedOutCreatorIdentifiers.length > 0
                ? t(resolveSummaryCountKey('opted_out'), {
                    count: optedOutCreatorIdentifiers.length,
                  })
                : t(
                    'module.operationsCreditNotifications.config.emptyOptedOutCreators',
                  )
            }
            preview={summarizeIdentifiers(
              optedOutCreatorIdentifiers,
              emptyPreview,
            )}
            actionLabel={t(
              'module.operationsCreditNotifications.config.listDialog.comingSoon',
            )}
            disabled
          />
        </div>
      </ConfigSection>

      <Dialog
        open={editing}
        onOpenChange={setEditing}
      >
        <DialogContent className='max-w-3xl'>
          <DialogHeader>
            <DialogTitle>
              {t(
                'module.operationsCreditNotifications.config.listDialog.manageLists',
              )}
            </DialogTitle>
            <DialogDescription>
              {t(
                'module.operationsCreditNotifications.config.listDialog.manageListsDescription',
              )}
            </DialogDescription>
          </DialogHeader>
          <div className='grid gap-3 lg:grid-cols-2'>
            <div className='lg:col-span-2'>
              <FormField
                htmlFor='credit-notification-blocked-creators'
                label={t(
                  'module.operationsCreditNotifications.config.fields.blockedCreators',
                )}
                tooltip={t(
                  contactMode === 'email'
                    ? 'module.operationsCreditNotifications.config.fieldTips.creatorIdentifierListEmail'
                    : 'module.operationsCreditNotifications.config.fieldTips.creatorIdentifierListPhone',
                )}
              >
                <div className='flex gap-2'>
                  <Input
                    id='credit-notification-blocked-creators'
                    className='h-9'
                    autoComplete='off'
                    spellCheck={false}
                    placeholder={t(
                      contactMode === 'email'
                        ? 'module.operationsCreditNotifications.config.inputPlaceholders.blockedCreatorsEmail'
                        : 'module.operationsCreditNotifications.config.inputPlaceholders.blockedCreatorsPhone',
                    )}
                    value={blockedCreatorInput}
                    onChange={event =>
                      onBlockedCreatorInputChange(
                        normalizeListInputCharacters(event.target.value),
                      )
                    }
                    onPaste={event => {
                      const pastedText = event.clipboardData.getData('text');
                      if (!pastedText) {
                        return;
                      }
                      event.preventDefault();
                      onBlockedCreatorInputChange(
                        normalizeListInputCharacters(pastedText),
                      );
                    }}
                    onKeyDown={event => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        onAddBlockedCreators();
                      }
                    }}
                    onBlur={onAddBlockedCreators}
                  />
                  <Button
                    type='button'
                    variant='outline'
                    className='h-9 shrink-0 border-border px-4 text-muted-foreground hover:bg-muted hover:text-slate-600'
                    onMouseDown={event => event.preventDefault()}
                    onClick={onAddBlockedCreators}
                  >
                    {t(
                      'module.operationsCreditNotifications.config.listDialog.add',
                    )}
                  </Button>
                </div>
              </FormField>
            </div>
            <ListSummaryCard
              count={blockedCreatorIdentifiers.length}
              label={t(
                'module.operationsCreditNotifications.config.fields.blockedCreatorList',
              )}
              preview={summarizeIdentifiers(
                blockedCreatorIdentifiers,
                emptyPreview,
              )}
              actionLabel={t(
                'module.operationsCreditNotifications.config.listDialog.manage',
              )}
              onClick={() => openManagedListFromDialog('blocked')}
            />
            <ListSummaryCard
              count={optedOutCreatorIdentifiers.length}
              label={t(
                'module.operationsCreditNotifications.config.fields.optedOutCreators',
              )}
              preview={summarizeIdentifiers(
                optedOutCreatorIdentifiers,
                emptyPreview,
              )}
              actionLabel={t(
                'module.operationsCreditNotifications.config.listDialog.comingSoon',
              )}
              disabled
            />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ListSummaryCard({
  count,
  label,
  preview,
  actionLabel,
  onClick,
  disabled = false,
}: {
  count: number;
  label: string;
  preview: string;
  actionLabel: string;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type='button'
      className='flex min-h-[86px] w-full items-center justify-between gap-4 rounded-xl border border-border bg-white px-4 py-3 text-left shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:bg-muted/20 disabled:opacity-70 disabled:hover:border-border'
      onClick={onClick}
      disabled={disabled}
    >
      <span className='flex min-w-0 items-center gap-3'>
        <span className='flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-muted text-base font-semibold text-slate-700'>
          {count}
        </span>
        <span className='min-w-0'>
          <span className='block text-sm font-medium text-foreground'>
            {label}
          </span>
          <span className='mt-1 block truncate text-xs text-muted-foreground'>
            {preview}
          </span>
        </span>
      </span>
      <span className='ml-3 inline-flex h-8 shrink-0 items-center rounded-md border border-border bg-white px-3 text-xs font-medium text-muted-foreground shadow-sm'>
        {actionLabel}
      </span>
    </button>
  );
}
