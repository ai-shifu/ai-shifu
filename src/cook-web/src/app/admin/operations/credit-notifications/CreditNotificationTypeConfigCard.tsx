import { Dispatch, SetStateAction, useEffect, useRef } from 'react';
import { ChevronDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Switch } from '@/components/ui/Switch';
import type {
  AdminOperationCreditNotificationPolicy,
  AdminOperationCreditNotificationTemplateOption,
  AdminOperationCreditNotificationTemplateSyncResponse,
  CreditNotificationEstimatedDaysThreshold,
  CreditNotificationFixedThreshold,
} from '../operation-credit-notification-types';
import {
  CreditNotificationFormField as FormField,
  CreditNotificationHelpTooltip as HelpTooltip,
} from './CreditNotificationFormPrimitives';
import {
  CreditNotificationPlaceholderGuide,
  CreditNotificationTemplateSyncResult,
} from './CreditNotificationTemplateSyncPanel';
import {
  isEstimatedDaysThreshold,
  type KnownNotificationType,
  parseListInput,
  parseThresholdInput,
  readPositiveNumber,
  removeEstimatedDaysThreshold,
  setEstimatedDaysThreshold,
} from './creditNotificationUtils';

type UpdatePolicy = (
  updater: (draft: AdminOperationCreditNotificationPolicy) => void,
) => void;

type CreditNotificationTypeConfigCardProps = {
  type: KnownNotificationType;
  policy: AdminOperationCreditNotificationPolicy;
  fixedLowBalanceThresholds: CreditNotificationFixedThreshold[];
  estimatedDaysThreshold: CreditNotificationEstimatedDaysThreshold | null;
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
  recommendedTemplate?: AdminOperationCreditNotificationTemplateOption;
  openTemplatePicker: Partial<Record<KnownNotificationType, boolean>>;
  editingTemplateTypes: Partial<Record<KnownNotificationType, boolean>>;
  templateInputValues: Partial<Record<KnownNotificationType, string>>;
  updatePolicy: UpdatePolicy;
  syncTemplate: (
    notificationType: KnownNotificationType,
    templateCodeOverride?: string,
  ) => Promise<boolean>;
  clearTemplateSyncResult: (notificationType: KnownNotificationType) => void;
  resolveTypeLabel: (value: string) => string;
  getListInputValue: (key: string, value: string[]) => string;
  updateListInput: (
    key: string,
    value: string,
    commit: (normalized: string) => void,
  ) => void;
  finishListInput: (key: string, value: string) => void;
  getIntegerInputValue: (key: string, value: number) => string;
  updateIntegerInput: (
    key: string,
    value: string,
    fallback: number,
    commit: (value: number) => void,
  ) => void;
  finishIntegerInput: (key: string, value: number) => void;
  setOpenTemplatePicker: Dispatch<
    SetStateAction<Partial<Record<KnownNotificationType, boolean>>>
  >;
  setEditingTemplateTypes: Dispatch<
    SetStateAction<Partial<Record<KnownNotificationType, boolean>>>
  >;
  setTemplateInputValues: Dispatch<
    SetStateAction<Partial<Record<KnownNotificationType, string>>>
  >;
};

const TEMPLATE_TYPE_KEYWORDS: Record<
  KnownNotificationType,
  {
    code: string[];
    text: string[];
  }
> = {
  credit_expiring: {
    code: ['expire', 'expiring'],
    text: ['到期', '过期', 'expire', 'expiring'],
  },
  credit_granted: {
    code: ['grant', 'granted'],
    text: ['到账', '到帐', '发放', 'grant', 'granted'],
  },
  low_balance: {
    code: ['low_balance', 'low-balance', 'balance'],
    text: ['余额', '低余额', '不足', 'low balance', 'balance'],
  },
};

function scoreTemplateForType(
  option: AdminOperationCreditNotificationTemplateOption,
  type: KnownNotificationType,
) {
  const keywords = TEMPLATE_TYPE_KEYWORDS[type];
  const code = option.template_code.toLowerCase();
  const text = [
    option.template_name,
    option.template_content,
    option.template_code,
  ]
    .join(' ')
    .toLowerCase();
  const codeScore = keywords.code.some(keyword => code.includes(keyword))
    ? 10
    : 0;
  const textScore = keywords.text.some(keyword => text.includes(keyword))
    ? 5
    : 0;
  return codeScore + textScore;
}

const isTemplateCompatibleWithType = (
  option: AdminOperationCreditNotificationTemplateOption,
  type: KnownNotificationType,
) => {
  const compatibleTypes = option.compatible_notification_types;
  return !compatibleTypes || compatibleTypes.includes(type);
};

const hasExplicitTemplateCompatibility = (
  option: AdminOperationCreditNotificationTemplateOption,
  type: KnownNotificationType,
) => (option.compatible_notification_types || []).includes(type);

export function getTemplateOptionsForType(
  templateOptions: AdminOperationCreditNotificationTemplateOption[],
  type: KnownNotificationType,
) {
  const scored = templateOptions
    .filter(option => isTemplateCompatibleWithType(option, type))
    .map(option => ({
      option,
      score: scoreTemplateForType(option, type),
    }))
    .filter(item => item.score > 0)
    .sort((left, right) => right.score - left.score);

  if (scored.length > 0) {
    return scored.map(item => item.option);
  }

  return templateOptions.filter(option =>
    hasExplicitTemplateCompatibility(option, type),
  );
}

export function CreditNotificationTypeConfigCard({
  type,
  policy,
  fixedLowBalanceThresholds,
  estimatedDaysThreshold,
  templateSyncResults,
  templateSyncLoading,
  templateOptions,
  templateListSource,
  templateListError,
  recommendedTemplate,
  openTemplatePicker,
  editingTemplateTypes,
  templateInputValues,
  updatePolicy,
  syncTemplate,
  clearTemplateSyncResult,
  resolveTypeLabel,
  getListInputValue,
  updateListInput,
  finishListInput,
  getIntegerInputValue,
  updateIntegerInput,
  finishIntegerInput,
  setOpenTemplatePicker,
  setEditingTemplateTypes,
  setTemplateInputValues,
}: CreditNotificationTypeConfigCardProps) {
  const { t } = useTranslation();
  const closePickerTimeoutRef = useRef<number | null>(null);
  const typePolicy = policy.types[type];
  const syncResult = templateSyncResults[type];
  const selectedTemplate = templateOptions.find(
    option => option.template_code === typePolicy.template_code,
  );
  const displayTemplate = selectedTemplate || recommendedTemplate;
  const templateInputValue =
    templateInputValues[type] ??
    displayTemplate?.template_name ??
    typePolicy.template_code;
  const filteredTemplateOptions = getTemplateOptionsForType(
    templateOptions,
    type,
  ).slice(0, 20);
  const templatePickerOpen =
    Boolean(openTemplatePicker[type]) && filteredTemplateOptions.length > 0;
  const isEditingTemplate =
    Boolean(editingTemplateTypes[type]) ||
    (!typePolicy.template_code.trim() && !recommendedTemplate);
  const appliedTemplateCode =
    typePolicy.template_code.trim() || recommendedTemplate?.template_code || '';
  useEffect(
    () => () => {
      if (closePickerTimeoutRef.current !== null) {
        window.clearTimeout(closePickerTimeoutRef.current);
      }
    },
    [],
  );
  return (
    <div
      key={type}
      className='space-y-4 rounded-lg border border-border bg-muted/20 p-4'
    >
      <div className='flex items-center justify-between gap-4'>
        <div>
          <Label
            htmlFor={`credit-notification-${type}-enabled`}
            className='text-sm font-medium text-foreground'
          >
            {resolveTypeLabel(type)}
          </Label>
          <p className='mt-1 text-xs text-muted-foreground'>
            {t(
              `module.operationsCreditNotifications.config.typeDescriptions.${type}`,
            )}
          </p>
        </div>
        <Switch
          id={`credit-notification-${type}-enabled`}
          checked={typePolicy.enabled}
          onCheckedChange={checked =>
            updatePolicy(draft => {
              draft.types[type].enabled = Boolean(checked);
            })
          }
        />
      </div>

      <div className='space-y-1'>
        <div className='grid gap-3 lg:grid-cols-[96px_minmax(0,1fr)_auto] lg:items-start'>
          <div className='flex h-9 items-center gap-1.5'>
            <Label
              htmlFor={`credit-notification-${type}-template`}
              className='text-xs font-medium text-muted-foreground'
            >
              {t(
                'module.operationsCreditNotifications.config.fields.templateCode',
              )}
            </Label>
            <HelpTooltip>
              {t(
                'module.operationsCreditNotifications.config.fieldTips.templateCode',
              )}
            </HelpTooltip>
          </div>
          {isEditingTemplate ? (
            <div className='relative'>
              <Input
                id={`credit-notification-${type}-template`}
                className='h-9 pr-10'
                placeholder={t(
                  'module.operationsCreditNotifications.config.templateList.editPlaceholder',
                )}
                value={templateInputValue}
                onFocus={() =>
                  setOpenTemplatePicker(current => ({
                    ...current,
                    [type]: true,
                  }))
                }
                onBlur={() => {
                  if (closePickerTimeoutRef.current !== null) {
                    window.clearTimeout(closePickerTimeoutRef.current);
                  }
                  closePickerTimeoutRef.current = window.setTimeout(() => {
                    setOpenTemplatePicker(current => ({
                      ...current,
                      [type]: false,
                    }));
                    closePickerTimeoutRef.current = null;
                  }, 120);
                }}
                onChange={event => {
                  const value = event.target.value;
                  setTemplateInputValues(current => ({
                    ...current,
                    [type]: value,
                  }));
                  clearTemplateSyncResult(type);
                  setOpenTemplatePicker(current => ({
                    ...current,
                    [type]: true,
                  }));
                  setEditingTemplateTypes(current => ({
                    ...current,
                    [type]: true,
                  }));
                }}
              />
              <button
                type='button'
                className='absolute right-2 top-0 flex h-9 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground'
                onMouseDown={event => {
                  event.preventDefault();
                  setTemplateInputValues(current => ({
                    ...current,
                    [type]:
                      displayTemplate?.template_name || appliedTemplateCode,
                  }));
                  setOpenTemplatePicker(current => ({
                    ...current,
                    [type]: !current[type],
                  }));
                }}
                aria-label={t(
                  'module.operationsCreditNotifications.config.templateList.editPlaceholder',
                )}
              >
                <ChevronDown className='h-4 w-4' />
              </button>
              {templatePickerOpen ? (
                <div className='absolute left-0 right-0 top-[calc(100%+6px)] z-[112] max-h-64 overflow-auto rounded-lg border border-border bg-white p-1 shadow-lg'>
                  {filteredTemplateOptions.map(option => (
                    <button
                      key={option.template_code}
                      type='button'
                      className='block w-full rounded-md px-3 py-2 text-left transition-colors hover:bg-muted focus:bg-muted focus:outline-none'
                      onMouseDown={event => {
                        event.preventDefault();
                        updatePolicy(draft => {
                          draft.types[type].template_code =
                            option.template_code;
                        });
                        setTemplateInputValues(current => ({
                          ...current,
                          [type]: option.template_name || option.template_code,
                        }));
                        clearTemplateSyncResult(type);
                        setOpenTemplatePicker(current => ({
                          ...current,
                          [type]: false,
                        }));
                        setEditingTemplateTypes(current => ({
                          ...current,
                          [type]: true,
                        }));
                      }}
                    >
                      <span className='block truncate text-sm font-medium text-foreground'>
                        {option.template_name || option.template_code}
                      </span>
                      <span className='mt-0.5 block truncate text-xs text-muted-foreground'>
                        {option.template_code}
                      </span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <div className='flex h-9 min-w-0 items-center rounded-md border border-border bg-white px-3 text-sm'>
              <span className='truncate text-foreground'>
                {displayTemplate?.template_name || typePolicy.template_code}
              </span>
            </div>
          )}
          <div className='flex items-center'>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='h-9 text-muted-foreground hover:text-foreground'
              disabled={
                Boolean(templateSyncLoading[type]) ||
                (isEditingTemplate && !templateInputValue.trim())
              }
              onClick={async () => {
                if (!isEditingTemplate) {
                  if (!typePolicy.template_code.trim() && recommendedTemplate) {
                    updatePolicy(draft => {
                      draft.types[type].template_code =
                        recommendedTemplate.template_code;
                    });
                  }
                  setTemplateInputValues(current => ({
                    ...current,
                    [type]:
                      displayTemplate?.template_name || appliedTemplateCode,
                  }));
                  setEditingTemplateTypes(current => ({
                    ...current,
                    [type]: true,
                  }));
                  return;
                }
                const normalizedTemplateInput = templateInputValue.trim();
                const matchedTemplate = templateOptions.find(
                  option =>
                    option.template_code === normalizedTemplateInput ||
                    option.template_name === normalizedTemplateInput,
                );
                const templateCodeToApply =
                  matchedTemplate?.template_code || normalizedTemplateInput;
                if (templateCodeToApply) {
                  updatePolicy(draft => {
                    draft.types[type].template_code = templateCodeToApply;
                  });
                  if (matchedTemplate) {
                    setTemplateInputValues(current => ({
                      ...current,
                      [type]:
                        matchedTemplate.template_name ||
                        matchedTemplate.template_code,
                    }));
                  }
                }
                const applied = await syncTemplate(type, templateCodeToApply);
                if (applied) {
                  setEditingTemplateTypes(current => ({
                    ...current,
                    [type]: false,
                  }));
                }
              }}
            >
              {templateSyncLoading[type]
                ? t(
                    'module.operationsCreditNotifications.actions.syncingTemplate',
                  )
                : isEditingTemplate
                  ? t(
                      'module.operationsCreditNotifications.actions.applyTemplate',
                    )
                  : t(
                      'module.operationsCreditNotifications.actions.changeTemplate',
                    )}
            </Button>
          </div>
        </div>
        <div className='text-[11px] leading-4 text-muted-foreground lg:ml-[108px]'>
          {templateListError
            ? t(
                filteredTemplateOptions.length > 0
                  ? 'module.operationsCreditNotifications.config.templateList.fallbackWithCache'
                  : 'module.operationsCreditNotifications.config.templateList.fallbackManual',
              )
            : t(
                `module.operationsCreditNotifications.config.templateList.source.${templateListSource || 'empty'}`,
              )}
        </div>
      </div>

      <CreditNotificationPlaceholderGuide
        type={type}
        fixedLowBalanceThresholds={fixedLowBalanceThresholds}
        estimatedDaysThreshold={estimatedDaysThreshold}
      />
      {syncResult ? (
        <CreditNotificationTemplateSyncResult syncResult={syncResult} />
      ) : null}

      {type === 'credit_expiring' ? (
        <div className='grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-start'>
          <FormField
            htmlFor='credit-notification-expiring-windows'
            label={t(
              'module.operationsCreditNotifications.config.fields.windows',
            )}
            description={t(
              'module.operationsCreditNotifications.config.fieldTips.windows',
            )}
          >
            <Input
              id='credit-notification-expiring-windows'
              className='h-9'
              autoComplete='off'
              spellCheck={false}
              value={getListInputValue(
                'credit_expiring.windows',
                policy.types.credit_expiring.windows || [],
              )}
              onChange={event =>
                updateListInput(
                  'credit_expiring.windows',
                  event.target.value,
                  normalized =>
                    updatePolicy(draft => {
                      draft.types.credit_expiring.windows =
                        parseListInput(normalized);
                    }),
                )
              }
              onBlur={event =>
                finishListInput(
                  'credit_expiring.windows',
                  event.currentTarget.value,
                )
              }
            />
          </FormField>
          <div className='pt-5'>
            <div className='flex h-9 w-full items-center justify-between gap-4 rounded-md border border-border bg-white px-3'>
              <Label
                htmlFor='credit-notification-merge-same-creator'
                className='text-xs font-medium text-muted-foreground'
              >
                {t(
                  'module.operationsCreditNotifications.config.fields.mergeSameCreator',
                )}
              </Label>
              <Switch
                id='credit-notification-merge-same-creator'
                checked={
                  policy.types.credit_expiring.merge_same_creator || false
                }
                onCheckedChange={checked =>
                  updatePolicy(draft => {
                    draft.types.credit_expiring.merge_same_creator =
                      Boolean(checked);
                  })
                }
              />
            </div>
          </div>
        </div>
      ) : null}

      {type === 'low_balance' ? (
        <div className='space-y-3'>
          <FormField
            htmlFor='credit-notification-low-balance-thresholds'
            label={t(
              'module.operationsCreditNotifications.config.fields.thresholds',
            )}
            description={t(
              'module.operationsCreditNotifications.config.fieldTips.thresholds',
            )}
          >
            <Input
              id='credit-notification-low-balance-thresholds'
              className='h-9'
              autoComplete='off'
              spellCheck={false}
              value={getListInputValue(
                'low_balance.thresholds',
                fixedLowBalanceThresholds.map(threshold => threshold.value),
              )}
              onChange={event =>
                updateListInput(
                  'low_balance.thresholds',
                  event.target.value,
                  normalized =>
                    updatePolicy(draft => {
                      const estimated = (
                        draft.types.low_balance.thresholds || []
                      ).find(isEstimatedDaysThreshold);
                      draft.types.low_balance.thresholds = [
                        ...parseThresholdInput(normalized),
                        ...(estimated ? [estimated] : []),
                      ];
                    }),
                )
              }
              onBlur={event =>
                finishListInput(
                  'low_balance.thresholds',
                  event.currentTarget.value,
                )
              }
            />
          </FormField>

          <div className='rounded-md border border-border bg-white p-3'>
            <div className='flex items-center justify-between gap-4'>
              <Label
                htmlFor='credit-notification-estimated-days-enabled'
                className='text-xs font-medium text-muted-foreground'
              >
                {t(
                  'module.operationsCreditNotifications.config.fields.estimatedDaysEnabled',
                )}
              </Label>
              <Switch
                id='credit-notification-estimated-days-enabled'
                checked={Boolean(estimatedDaysThreshold)}
                onCheckedChange={checked =>
                  updatePolicy(draft => {
                    if (checked) {
                      setEstimatedDaysThreshold(draft, {});
                      return;
                    }
                    removeEstimatedDaysThreshold(draft);
                  })
                }
              />
            </div>
            {estimatedDaysThreshold ? (
              <div className='mt-3 grid gap-3 lg:grid-cols-4'>
                <FormField
                  htmlFor='credit-notification-estimated-days'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.estimatedDays',
                  )}
                  tooltip={t(
                    'module.operationsCreditNotifications.config.fieldTips.estimatedDays',
                  )}
                >
                  <Input
                    id='credit-notification-estimated-days'
                    className='h-9'
                    inputMode='numeric'
                    pattern='[0-9]*'
                    autoComplete='off'
                    value={getIntegerInputValue(
                      'estimated_days.days',
                      estimatedDaysThreshold.days,
                    )}
                    onChange={event =>
                      updateIntegerInput(
                        'estimated_days.days',
                        event.target.value,
                        1,
                        value =>
                          updatePolicy(draft => {
                            setEstimatedDaysThreshold(draft, {
                              days: readPositiveNumber(value, 1),
                            });
                          }),
                      )
                    }
                    onBlur={() =>
                      finishIntegerInput(
                        'estimated_days.days',
                        estimatedDaysThreshold.days,
                      )
                    }
                  />
                </FormField>
                <FormField
                  htmlFor='credit-notification-lookback-days'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.lookbackDays',
                  )}
                  tooltip={t(
                    'module.operationsCreditNotifications.config.fieldTips.lookbackDays',
                  )}
                >
                  <Input
                    id='credit-notification-lookback-days'
                    className='h-9'
                    inputMode='numeric'
                    pattern='[0-9]*'
                    autoComplete='off'
                    value={getIntegerInputValue(
                      'estimated_days.lookback_days',
                      estimatedDaysThreshold.lookback_days,
                    )}
                    onChange={event =>
                      updateIntegerInput(
                        'estimated_days.lookback_days',
                        event.target.value,
                        1,
                        value =>
                          updatePolicy(draft => {
                            setEstimatedDaysThreshold(draft, {
                              lookback_days: readPositiveNumber(value, 1),
                            });
                          }),
                      )
                    }
                    onBlur={() =>
                      finishIntegerInput(
                        'estimated_days.lookback_days',
                        estimatedDaysThreshold.lookback_days,
                      )
                    }
                  />
                </FormField>
                <FormField
                  htmlFor='credit-notification-min-consumed-days'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.minConsumedDays',
                  )}
                  tooltip={t(
                    'module.operationsCreditNotifications.config.fieldTips.minConsumedDays',
                  )}
                >
                  <Input
                    id='credit-notification-min-consumed-days'
                    className='h-9'
                    inputMode='numeric'
                    pattern='[0-9]*'
                    autoComplete='off'
                    value={getIntegerInputValue(
                      'estimated_days.min_consumed_days',
                      estimatedDaysThreshold.min_consumed_days,
                    )}
                    onChange={event =>
                      updateIntegerInput(
                        'estimated_days.min_consumed_days',
                        event.target.value,
                        1,
                        value =>
                          updatePolicy(draft => {
                            setEstimatedDaysThreshold(draft, {
                              min_consumed_days: readPositiveNumber(value, 1),
                            });
                          }),
                      )
                    }
                    onBlur={() =>
                      finishIntegerInput(
                        'estimated_days.min_consumed_days',
                        estimatedDaysThreshold.min_consumed_days,
                      )
                    }
                  />
                </FormField>
                <FormField
                  htmlFor='credit-notification-fallback-fixed-value'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.fallbackFixedValue',
                  )}
                  tooltip={t(
                    'module.operationsCreditNotifications.config.fieldTips.fallbackFixedValue',
                  )}
                >
                  <Input
                    id='credit-notification-fallback-fixed-value'
                    className='h-9'
                    value={estimatedDaysThreshold.fallback_fixed_value || ''}
                    onChange={event =>
                      updatePolicy(draft => {
                        const normalized = event.target.value.trim();
                        setEstimatedDaysThreshold(draft, {
                          fallback_fixed_value: normalized || undefined,
                        });
                      })
                    }
                  />
                </FormField>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
