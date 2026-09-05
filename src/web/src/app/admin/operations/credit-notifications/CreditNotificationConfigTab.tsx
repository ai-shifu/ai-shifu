import { useTranslation } from 'react-i18next';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import { Label } from '@/components/ui/Label';
import { Switch } from '@/components/ui/Switch';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import type {
  AdminOperationCreditNotificationDryRunResponse,
  AdminOperationCreditNotificationPolicy,
  AdminOperationCreditNotificationPolicyResolvedLists,
  AdminOperationCreditNotificationTemplateOption,
} from '../operation-credit-notification-types';
import { CreditNotificationCreatorListsSection } from './CreditNotificationCreatorListsSection';
import { CreditNotificationDeliveryRulesSection } from './CreditNotificationDeliveryRulesSection';
import { CreditNotificationDryRunPanel } from './CreditNotificationDryRunPanel';
import { CreditNotificationManagedListDialog } from './CreditNotificationManagedListDialog';
import { CreditNotificationRuleManagementSection } from './CreditNotificationRuleManagementSection';
import {
  CreditNotificationConfigSection as ConfigSection,
  CreditNotificationHelpTooltip as HelpTooltip,
} from './CreditNotificationFormPrimitives';
import {
  type UpdatePolicy,
  useCreditNotificationConfigTabState,
} from './useCreditNotificationConfigTabState';

export function CreditNotificationConfigTab({
  policy,
  configLoaded,
  configLoading,
  configError,
  dryRunResult,
  dryRunError,
  templateOptions,
  resolvedLists,
  updatePolicy,
  dryRun,
  saveConfig,
  resolveTypeLabel,
  onRuleAction,
  onLegacyRulesMigrated,
}: {
  policy: AdminOperationCreditNotificationPolicy;
  configLoaded: boolean;
  configLoading: boolean;
  configError: string;
  dryRunResult: AdminOperationCreditNotificationDryRunResponse | null;
  dryRunError: string;
  templateOptions: AdminOperationCreditNotificationTemplateOption[];
  resolvedLists: AdminOperationCreditNotificationPolicyResolvedLists;
  updatePolicy: UpdatePolicy;
  dryRun: () => void;
  saveConfig: () => Promise<boolean>;
  resolveTypeLabel: (value: string) => string;
  onRuleAction: (
    action: 'created' | 'edited' | 'deleted' | 'toggled',
    triggerEvent: 'credit_expiring' | 'credit_granted' | 'low_balance',
  ) => void;
  onLegacyRulesMigrated: () => void;
}) {
  const { t } = useTranslation();
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const defaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );
  const contactMode = resolveContactMode(
    loginMethodsEnabled,
    defaultLoginMethod,
  );
  const {
    addBlockedCreators,
    blockedCreatorIdentifiers,
    blockedCreatorInput,
    closeManagedListDialog,
    filteredManagedListDetails,
    finishIntegerInput,
    getIntegerInputValue,
    managedListCanDelete,
    managedListDialog,
    managedListSearch,
    managedListTitle,
    openManagedListDialog,
    optedOutCreatorIdentifiers,
    removeBlockedCreator,
    setBlockedCreatorInput,
    setManagedListSearch,
    updateIntegerInput,
  } = useCreditNotificationConfigTabState({
    contactMode,
    policy,
    resolvedLists,
    updatePolicy,
    t,
  });

  if (configLoading && !configLoaded) {
    return (
      <div className='flex h-full min-h-0 items-center justify-center'>
        <Loading />
      </div>
    );
  }

  return (
    <div className='flex h-full min-h-0 flex-col'>
      <div className='min-h-0 flex-1 space-y-4 overflow-auto pb-6 pr-1'>
        <ConfigSection
          title={t('module.operationsCreditNotifications.config.title')}
          description={t(
            'module.operationsCreditNotifications.config.description',
          )}
        >
          <div className='flex flex-col gap-4 rounded-lg border border-primary/20 bg-primary/[0.04] p-4 sm:flex-row sm:items-center sm:justify-between'>
            <div>
              <div className='flex items-center gap-1.5'>
                <Label
                  htmlFor='credit-notification-enabled'
                  className='text-sm font-medium text-foreground'
                >
                  {t(
                    contactMode === 'email'
                      ? 'module.operationsCreditNotifications.config.fields.enabledEmail'
                      : 'module.operationsCreditNotifications.config.fields.enabled',
                  )}
                </Label>
                <HelpTooltip>
                  {t(
                    contactMode === 'email'
                      ? 'module.operationsCreditNotifications.config.fieldTips.enabledEmail'
                      : 'module.operationsCreditNotifications.config.fieldTips.enabled',
                  )}
                </HelpTooltip>
              </div>
              <p className='mt-1 text-xs leading-5 text-muted-foreground'>
                {t(
                  contactMode === 'email'
                    ? 'module.operationsCreditNotifications.config.masterSwitchDescriptionEmail'
                    : 'module.operationsCreditNotifications.config.masterSwitchDescription',
                )}
              </p>
            </div>
            <Switch
              id='credit-notification-enabled'
              checked={policy.enabled}
              onCheckedChange={checked =>
                updatePolicy(draft => {
                  draft.enabled = Boolean(checked);
                })
              }
            />
          </div>
        </ConfigSection>

        <CreditNotificationRuleManagementSection
          contactMode={contactMode === 'email' ? 'email' : 'sms'}
          policy={policy}
          templateOptions={templateOptions}
          resolveTypeLabel={resolveTypeLabel}
          updatePolicy={updatePolicy}
          onRuleAction={onRuleAction}
          onLegacyRulesMigrated={onLegacyRulesMigrated}
        />

        <CreditNotificationDeliveryRulesSection
          contactMode={contactMode}
          policy={policy}
          updatePolicy={updatePolicy}
          getIntegerInputValue={getIntegerInputValue}
          updateIntegerInput={updateIntegerInput}
          finishIntegerInput={finishIntegerInput}
        />

        <CreditNotificationCreatorListsSection
          contactMode={contactMode}
          blockedCreatorInput={blockedCreatorInput}
          blockedCreatorIdentifiers={blockedCreatorIdentifiers}
          optedOutCreatorIdentifiers={optedOutCreatorIdentifiers}
          onBlockedCreatorInputChange={setBlockedCreatorInput}
          onAddBlockedCreators={addBlockedCreators}
          onOpenManagedListDialog={openManagedListDialog}
        />

        <CreditNotificationDryRunPanel
          contactMode={contactMode}
          dryRunResult={dryRunResult}
          dryRunError={dryRunError}
          dryRun={dryRun}
        />

        {configError ? (
          <ErrorDisplay
            errorCode={0}
            errorMessage={configError}
          />
        ) : null}

        <CreditNotificationManagedListDialog
          open={managedListDialog !== null}
          title={managedListTitle}
          canDelete={managedListCanDelete}
          contactMode={contactMode}
          items={filteredManagedListDetails}
          search={managedListSearch}
          onSearchChange={setManagedListSearch}
          onRemove={removeBlockedCreator}
          onClose={closeManagedListDialog}
        />
      </div>

      <div className='shrink-0 border-t border-border bg-white/95 px-4 py-3 shadow-[0_-8px_24px_rgba(15,23,42,0.08)] backdrop-blur'>
        <div className='flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between'>
          <p className='text-xs leading-5 text-muted-foreground'>
            {t('module.operationsCreditNotifications.config.saveStickyHint')}
          </p>
          <Button
            type='button'
            onClick={saveConfig}
            disabled={!configLoaded}
            className='w-full sm:w-auto'
          >
            {t('module.operationsCreditNotifications.actions.applyConfig')}
          </Button>
        </div>
      </div>
    </div>
  );
}
