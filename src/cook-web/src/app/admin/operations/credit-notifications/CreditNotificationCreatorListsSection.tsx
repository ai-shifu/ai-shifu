import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
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

  return (
    <ConfigSection
      title={t('module.operationsCreditNotifications.config.sections.lists')}
      description={t(
        'module.operationsCreditNotifications.config.sectionDescriptions.lists',
      )}
    >
      <div className='grid gap-3 lg:grid-cols-2'>
        <div className='lg:col-span-2 lg:max-w-[calc(50%-0.375rem)]'>
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
        <FormField
          htmlFor='credit-notification-blocked-creators-list'
          label={t(
            'module.operationsCreditNotifications.config.fields.blockedCreatorList',
          )}
          tooltip={t(
            'module.operationsCreditNotifications.config.fieldTips.blockedCreatorList',
          )}
        >
          <button
            id='credit-notification-blocked-creators-list'
            type='button'
            className='flex min-h-[76px] w-full items-center justify-between gap-3 rounded-lg border border-border bg-slate-50 px-4 py-3 text-left transition-colors hover:border-slate-300 hover:bg-slate-100/60'
            onClick={() => onOpenManagedListDialog('blocked')}
          >
            <span className='min-w-0'>
              <span className='block text-sm font-medium text-foreground'>
                {blockedCreatorIdentifiers.length > 0
                  ? t(resolveSummaryCountKey('blocked'), {
                      count: blockedCreatorIdentifiers.length,
                    })
                  : t(
                      'module.operationsCreditNotifications.config.emptyBlockedCreators',
                    )}
              </span>
              <span className='mt-1 block truncate text-xs text-muted-foreground'>
                {summarizeIdentifiers(
                  blockedCreatorIdentifiers,
                  t(
                    'module.operationsCreditNotifications.config.listDialog.emptyPreview',
                  ),
                )}
              </span>
            </span>
            <span className='ml-3 inline-flex h-8 shrink-0 items-center rounded-md border border-border bg-white px-3 text-xs font-medium text-muted-foreground shadow-sm'>
              {t(
                'module.operationsCreditNotifications.config.listDialog.manage',
              )}
            </span>
          </button>
        </FormField>
        <FormField
          htmlFor='credit-notification-opt-out-creators'
          label={t(
            'module.operationsCreditNotifications.config.fields.optedOutCreators',
          )}
          tooltip={t(
            'module.operationsCreditNotifications.config.fieldTips.optedOutCreators',
          )}
        >
          <button
            id='credit-notification-opt-out-creators'
            type='button'
            className='flex min-h-[76px] w-full items-center justify-between gap-3 rounded-lg border border-border bg-slate-50 px-4 py-3 text-left transition-colors hover:border-slate-300 hover:bg-slate-100/60'
            onClick={() => onOpenManagedListDialog('opted_out')}
          >
            <span className='min-w-0'>
              <span className='block text-sm font-medium text-foreground'>
                {optedOutCreatorIdentifiers.length > 0
                  ? t(resolveSummaryCountKey('opted_out'), {
                      count: optedOutCreatorIdentifiers.length,
                    })
                  : t(
                      'module.operationsCreditNotifications.config.emptyOptedOutCreators',
                    )}
              </span>
              <span className='mt-1 block truncate text-xs text-muted-foreground'>
                {summarizeIdentifiers(
                  optedOutCreatorIdentifiers,
                  t(
                    'module.operationsCreditNotifications.config.listDialog.emptyPreview',
                  ),
                )}
              </span>
            </span>
            <span className='ml-3 inline-flex h-8 shrink-0 items-center rounded-md border border-border bg-white px-3 text-xs font-medium text-muted-foreground shadow-sm'>
              {t('module.operationsCreditNotifications.config.listDialog.view')}
            </span>
          </button>
        </FormField>
      </div>
    </ConfigSection>
  );
}
