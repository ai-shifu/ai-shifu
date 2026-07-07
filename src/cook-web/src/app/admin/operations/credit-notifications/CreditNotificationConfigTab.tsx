import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { Switch } from '@/components/ui/Switch';
import AdminTimeSelect from '@/app/admin/components/AdminTimeSelect';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import type {
  AdminOperationCreditNotificationDryRunResponse,
  AdminOperationCreditNotificationPolicy,
  AdminOperationCreditNotificationPolicyResolvedLists,
  AdminOperationCreditNotificationTemplateOption,
  AdminOperationCreditNotificationTemplateSyncResponse,
} from '../operation-credit-notification-types';
import { CreditNotificationCreatorListsSection } from './CreditNotificationCreatorListsSection';
import { CreditNotificationDryRunPanel } from './CreditNotificationDryRunPanel';
import { CreditNotificationManagedListDialog } from './CreditNotificationManagedListDialog';
import {
  CreditNotificationTypeConfigCard,
  getTemplateOptionsForType,
} from './CreditNotificationTypeConfigCard';
import {
  CreditNotificationConfigSection as ConfigSection,
  CreditNotificationFormField as FormField,
  CreditNotificationHelpTooltip as HelpTooltip,
} from './CreditNotificationFormPrimitives';
import {
  isEstimatedDaysThreshold,
  isFixedThreshold,
  type KnownNotificationType,
  NOTIFICATION_TYPES,
} from './creditNotificationUtils';
import {
  type UpdatePolicy,
  useCreditNotificationConfigTabState,
} from './useCreditNotificationConfigTabState';

const TIMEZONE_OPTIONS = [
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Asia/Taipei',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Asia/Seoul',
  'UTC',
];

function ConfigCard({
  title,
  description,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className='space-y-4 rounded-lg border border-border bg-muted/20 p-3'>
      <div>
        <h3 className='text-sm font-medium text-foreground'>{title}</h3>
        {description ? (
          <p className='mt-1 text-xs leading-5 text-muted-foreground'>
            {description}
          </p>
        ) : null}
      </div>
      {children}
    </div>
  );
}

export function CreditNotificationConfigTab({
  policy,
  configLoaded,
  configLoading,
  configError,
  dryRunResult,
  dryRunError,
  templateSyncError,
  templateSyncResults,
  templateSyncLoading,
  templateOptions,
  templateListSource,
  templateListError,
  resolvedLists,
  updatePolicy,
  syncTemplate,
  dryRun,
  saveConfig,
  clearTemplateSyncResult,
  resolveTypeLabel,
}: {
  policy: AdminOperationCreditNotificationPolicy;
  configLoaded: boolean;
  configLoading: boolean;
  configError: string;
  dryRunResult: AdminOperationCreditNotificationDryRunResponse | null;
  dryRunError: string;
  templateSyncError: string;
  templateSyncResults: Partial<
    Record<
      KnownNotificationType,
      AdminOperationCreditNotificationTemplateSyncResponse
    >
  >;
  templateSyncLoading: Partial<Record<KnownNotificationType, boolean>>;
  templateOptions: AdminOperationCreditNotificationTemplateOption[];
  templateListSource: 'provider' | 'local' | '';
  templateListError: string;
  resolvedLists: AdminOperationCreditNotificationPolicyResolvedLists;
  updatePolicy: UpdatePolicy;
  syncTemplate: (notificationType: KnownNotificationType) => Promise<boolean>;
  dryRun: () => void;
  saveConfig: () => Promise<boolean>;
  clearTemplateSyncResult: (notificationType: KnownNotificationType) => void;
  resolveTypeLabel: (value: string) => string;
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
    editingTemplateTypes,
    filteredManagedListDetails,
    finishIntegerInput,
    finishListInput,
    getIntegerInputValue,
    getListInputValue,
    managedListCanDelete,
    managedListDialog,
    managedListSearch,
    managedListTitle,
    openManagedListDialog,
    openTemplatePicker,
    optedOutCreatorIdentifiers,
    removeBlockedCreator,
    setBlockedCreatorInput,
    setEditingTemplateTypes,
    setManagedListSearch,
    setOpenTemplatePicker,
    setTemplateInputValues,
    templateInputValues,
    updateIntegerInput,
    updateListInput,
  } = useCreditNotificationConfigTabState({
    contactMode,
    policy,
    resolvedLists,
    updatePolicy,
    t,
  });
  const lowBalanceThresholds = policy.types.low_balance.thresholds || [];
  const fixedLowBalanceThresholds =
    lowBalanceThresholds.filter(isFixedThreshold);
  const estimatedDaysThreshold =
    lowBalanceThresholds.find(isEstimatedDaysThreshold) || null;

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
                    'module.operationsCreditNotifications.config.fields.enabled',
                  )}
                </Label>
                <HelpTooltip>
                  {t(
                    'module.operationsCreditNotifications.config.fieldTips.enabled',
                  )}
                </HelpTooltip>
              </div>
              <p className='mt-1 text-xs leading-5 text-muted-foreground'>
                {t(
                  'module.operationsCreditNotifications.config.masterSwitchDescription',
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

        <ConfigSection
          title={t(
            'module.operationsCreditNotifications.config.sections.types',
          )}
        >
          {templateSyncError ? (
            <div className='mb-3 rounded-md border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive'>
              {templateSyncError}
            </div>
          ) : null}
          <div className='space-y-3'>
            {NOTIFICATION_TYPES.map(type => (
              <CreditNotificationTypeConfigCard
                key={type}
                type={type}
                policy={policy}
                fixedLowBalanceThresholds={fixedLowBalanceThresholds}
                estimatedDaysThreshold={estimatedDaysThreshold}
                templateSyncResults={templateSyncResults}
                templateSyncLoading={templateSyncLoading}
                templateOptions={templateOptions}
                templateListSource={templateListSource}
                templateListError={templateListError}
                recommendedTemplate={
                  policy.types[type].template_code.trim()
                    ? undefined
                    : getTemplateOptionsForType(templateOptions, type)[0]
                }
                openTemplatePicker={openTemplatePicker}
                editingTemplateTypes={editingTemplateTypes}
                templateInputValues={templateInputValues}
                updatePolicy={updatePolicy}
                syncTemplate={syncTemplate}
                clearTemplateSyncResult={clearTemplateSyncResult}
                resolveTypeLabel={resolveTypeLabel}
                getListInputValue={getListInputValue}
                updateListInput={updateListInput}
                finishListInput={finishListInput}
                getIntegerInputValue={getIntegerInputValue}
                updateIntegerInput={updateIntegerInput}
                finishIntegerInput={finishIntegerInput}
                setOpenTemplatePicker={setOpenTemplatePicker}
                setEditingTemplateTypes={setEditingTemplateTypes}
                setTemplateInputValues={setTemplateInputValues}
              />
            ))}
          </div>
        </ConfigSection>

        <ConfigSection
          title={t(
            'module.operationsCreditNotifications.config.sections.deliveryPolicy',
          )}
        >
          <div className='grid gap-4 xl:grid-cols-2'>
            <ConfigCard
              title={t(
                'module.operationsCreditNotifications.config.sections.softlimit',
              )}
              description={t(
                'module.operationsCreditNotifications.config.sectionDescriptions.softlimit',
              )}
            >
              <div className='flex items-center justify-between gap-4 rounded-md border border-border bg-white p-3'>
                <Label
                  htmlFor='credit-notification-softlimit-enabled'
                  className='text-sm font-medium text-foreground'
                >
                  {t(
                    'module.operationsCreditNotifications.config.fields.softlimitEnabled',
                  )}
                </Label>
                <Switch
                  id='credit-notification-softlimit-enabled'
                  checked={policy.softlimit.enabled}
                  onCheckedChange={checked =>
                    updatePolicy(draft => {
                      draft.softlimit.enabled = Boolean(checked);
                    })
                  }
                />
              </div>
              <FormField
                htmlFor='credit-notification-softlimit-threshold'
                label={t(
                  'module.operationsCreditNotifications.config.fields.softlimitThreshold',
                )}
                tooltip={t(
                  'module.operationsCreditNotifications.config.fieldTips.softlimitThreshold',
                )}
              >
                <Input
                  id='credit-notification-softlimit-threshold'
                  className='h-9'
                  value={policy.softlimit.threshold.value}
                  onChange={event =>
                    updatePolicy(draft => {
                      draft.softlimit.threshold = {
                        kind: 'fixed',
                        value: event.target.value,
                      };
                    })
                  }
                />
              </FormField>
              <div className='grid gap-3 sm:grid-cols-3'>
                {[
                  {
                    id: 'credit-notification-teacher-page-alert',
                    label:
                      'module.operationsCreditNotifications.config.fields.teacherPageAlert',
                    checked: policy.softlimit.teacher_page_alert,
                    update: (checked: boolean) => {
                      updatePolicy(draft => {
                        draft.softlimit.teacher_page_alert = checked;
                      });
                    },
                  },
                  {
                    id: 'credit-notification-disable-debug',
                    label:
                      'module.operationsCreditNotifications.config.fields.disableDebug',
                    checked: policy.softlimit.disable_debug,
                    update: (checked: boolean) => {
                      updatePolicy(draft => {
                        draft.softlimit.disable_debug = checked;
                      });
                    },
                  },
                  {
                    id: 'credit-notification-softlimit-sms',
                    label:
                      'module.operationsCreditNotifications.config.fields.softlimitSms',
                    checked: policy.softlimit.sms_enabled,
                    update: (checked: boolean) => {
                      updatePolicy(draft => {
                        draft.softlimit.sms_enabled = checked;
                      });
                    },
                  },
                ].map(field => (
                  <div
                    key={field.id}
                    className='flex items-center justify-between gap-3 rounded-md border border-border bg-white p-2'
                  >
                    <Label
                      htmlFor={field.id}
                      className='text-xs font-medium text-muted-foreground'
                    >
                      {t(field.label)}
                    </Label>
                    <Switch
                      id={field.id}
                      checked={field.checked}
                      onCheckedChange={checked =>
                        field.update(Boolean(checked))
                      }
                    />
                  </div>
                ))}
              </div>
            </ConfigCard>

            <ConfigCard
              title={t(
                'module.operationsCreditNotifications.config.sections.frequency',
              )}
              description={t(
                'module.operationsCreditNotifications.config.sectionDescriptions.frequency',
              )}
            >
              <div className='grid gap-3 sm:grid-cols-2'>
                <FormField
                  htmlFor='credit-notification-per-mobile'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.perMobilePerDay',
                  )}
                  tooltip={t(
                    'module.operationsCreditNotifications.config.fieldTips.perMobilePerDay',
                  )}
                >
                  <Input
                    id='credit-notification-per-mobile'
                    className='h-9'
                    inputMode='numeric'
                    pattern='[0-9]*'
                    autoComplete='off'
                    value={getIntegerInputValue(
                      'frequency.per_mobile_per_day',
                      policy.frequency.per_mobile_per_day,
                    )}
                    onChange={event =>
                      updateIntegerInput(
                        'frequency.per_mobile_per_day',
                        event.target.value,
                        0,
                        value =>
                          updatePolicy(draft => {
                            draft.frequency.per_mobile_per_day = value;
                          }),
                      )
                    }
                    onBlur={() =>
                      finishIntegerInput(
                        'frequency.per_mobile_per_day',
                        policy.frequency.per_mobile_per_day,
                      )
                    }
                  />
                </FormField>
                <FormField
                  htmlFor='credit-notification-per-creator-type'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.perCreatorPerTypePerDay',
                  )}
                  tooltip={t(
                    'module.operationsCreditNotifications.config.fieldTips.perCreatorPerTypePerDay',
                  )}
                >
                  <Input
                    id='credit-notification-per-creator-type'
                    className='h-9'
                    inputMode='numeric'
                    pattern='[0-9]*'
                    autoComplete='off'
                    value={getIntegerInputValue(
                      'frequency.per_creator_per_type_per_day',
                      policy.frequency.per_creator_per_type_per_day,
                    )}
                    onChange={event =>
                      updateIntegerInput(
                        'frequency.per_creator_per_type_per_day',
                        event.target.value,
                        0,
                        value =>
                          updatePolicy(draft => {
                            draft.frequency.per_creator_per_type_per_day =
                              value;
                          }),
                      )
                    }
                    onBlur={() =>
                      finishIntegerInput(
                        'frequency.per_creator_per_type_per_day',
                        policy.frequency.per_creator_per_type_per_day,
                      )
                    }
                  />
                </FormField>
              </div>
            </ConfigCard>
          </div>
        </ConfigSection>

        <div className='grid gap-4 xl:grid-cols-2'>
          <ConfigSection
            title={t(
              'module.operationsCreditNotifications.config.sections.quietHours',
            )}
            description={t(
              'module.operationsCreditNotifications.config.sectionDescriptions.quietHours',
            )}
          >
            <div className='flex items-center justify-between gap-4 rounded-md border border-border bg-muted/20 p-3'>
              <Label
                htmlFor='credit-notification-quiet-hours-enabled'
                className='text-sm font-medium text-foreground'
              >
                {t(
                  'module.operationsCreditNotifications.config.fields.quietHoursEnabled',
                )}
              </Label>
              <Switch
                id='credit-notification-quiet-hours-enabled'
                checked={policy.quiet_hours.enabled}
                onCheckedChange={checked =>
                  updatePolicy(draft => {
                    draft.quiet_hours.enabled = Boolean(checked);
                  })
                }
              />
            </div>
            <div className='grid gap-3 sm:grid-cols-3'>
              <FormField
                htmlFor='credit-notification-quiet-start'
                label={t(
                  'module.operationsCreditNotifications.config.fields.quietStart',
                )}
                tooltip={t(
                  'module.operationsCreditNotifications.config.fieldTips.quietStart',
                )}
              >
                <AdminTimeSelect
                  id='credit-notification-quiet-start'
                  value={policy.quiet_hours.start}
                  onChange={value =>
                    updatePolicy(draft => {
                      draft.quiet_hours.start = value;
                    })
                  }
                />
              </FormField>
              <FormField
                htmlFor='credit-notification-quiet-end'
                label={t(
                  'module.operationsCreditNotifications.config.fields.quietEnd',
                )}
                tooltip={t(
                  'module.operationsCreditNotifications.config.fieldTips.quietEnd',
                )}
              >
                <AdminTimeSelect
                  id='credit-notification-quiet-end'
                  value={policy.quiet_hours.end}
                  onChange={value =>
                    updatePolicy(draft => {
                      draft.quiet_hours.end = value;
                    })
                  }
                />
              </FormField>
              <FormField
                htmlFor='credit-notification-timezone'
                label={t(
                  'module.operationsCreditNotifications.config.fields.timezone',
                )}
                tooltip={t(
                  'module.operationsCreditNotifications.config.fieldTips.timezone',
                )}
              >
                <Select
                  value={policy.quiet_hours.timezone || 'Asia/Shanghai'}
                  onValueChange={value =>
                    updatePolicy(draft => {
                      draft.quiet_hours.timezone = value;
                    })
                  }
                >
                  <SelectTrigger
                    id='credit-notification-timezone'
                    className='h-9'
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Array.from(
                      new Set([
                        policy.quiet_hours.timezone || 'Asia/Shanghai',
                        ...TIMEZONE_OPTIONS,
                      ]),
                    ).map(timezone => (
                      <SelectItem
                        key={timezone}
                        value={timezone}
                        className='pl-2 pr-8'
                        indicatorClassName='left-auto right-2'
                      >
                        {timezone}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FormField>
            </div>
          </ConfigSection>

          <ConfigSection
            title={t(
              'module.operationsCreditNotifications.config.sections.budget',
            )}
            description={t(
              'module.operationsCreditNotifications.config.sectionDescriptions.budget',
            )}
          >
            <div className='grid gap-3 sm:grid-cols-2'>
              <FormField
                htmlFor='credit-notification-daily-sms-limit'
                label={t(
                  'module.operationsCreditNotifications.config.fields.dailySmsLimit',
                )}
                tooltip={t(
                  'module.operationsCreditNotifications.config.fieldTips.dailySmsLimit',
                )}
              >
                <Input
                  id='credit-notification-daily-sms-limit'
                  className='h-9'
                  inputMode='numeric'
                  pattern='[0-9]*'
                  autoComplete='off'
                  value={getIntegerInputValue(
                    'budget.daily_sms_limit',
                    policy.budget.daily_sms_limit,
                  )}
                  onChange={event =>
                    updateIntegerInput(
                      'budget.daily_sms_limit',
                      event.target.value,
                      0,
                      value =>
                        updatePolicy(draft => {
                          draft.budget.daily_sms_limit = value;
                        }),
                    )
                  }
                  onBlur={() =>
                    finishIntegerInput(
                      'budget.daily_sms_limit',
                      policy.budget.daily_sms_limit,
                    )
                  }
                />
              </FormField>
              <FormField
                htmlFor='credit-notification-sms-unit-cost'
                label={t(
                  'module.operationsCreditNotifications.config.fields.smsUnitCost',
                )}
                tooltip={t(
                  'module.operationsCreditNotifications.config.fieldTips.smsUnitCost',
                )}
              >
                <Input
                  id='credit-notification-sms-unit-cost'
                  className='h-9'
                  value={policy.budget.sms_unit_cost}
                  onChange={event =>
                    updatePolicy(draft => {
                      draft.budget.sms_unit_cost = event.target.value;
                    })
                  }
                />
              </FormField>
            </div>
            <div className='flex items-center justify-between gap-4 rounded-md border border-border bg-muted/20 p-3'>
              <Label
                htmlFor='credit-notification-dry-run-required'
                className='text-xs font-medium text-muted-foreground'
              >
                {t(
                  'module.operationsCreditNotifications.config.fields.dryRunRequired',
                )}
              </Label>
              <Switch
                id='credit-notification-dry-run-required'
                checked={policy.budget.dry_run_required}
                onCheckedChange={checked =>
                  updatePolicy(draft => {
                    draft.budget.dry_run_required = Boolean(checked);
                  })
                }
              />
            </div>
          </ConfigSection>
        </div>

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
