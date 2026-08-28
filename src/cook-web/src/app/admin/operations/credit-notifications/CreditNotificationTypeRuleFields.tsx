import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Switch } from '@/components/ui/Switch';
import type {
  AdminOperationCreditNotificationPolicy,
  CreditNotificationEstimatedDaysThreshold,
  CreditNotificationFixedThreshold,
} from '../operation-credit-notification-types';
import { CreditNotificationFormField as FormField } from './CreditNotificationFormPrimitives';
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

export function CreditNotificationTypeRuleFields({
  type,
  policy,
  fixedLowBalanceThresholds,
  estimatedDaysThreshold,
  updatePolicy,
  getListInputValue,
  updateListInput,
  finishListInput,
  getIntegerInputValue,
  updateIntegerInput,
  finishIntegerInput,
}: {
  type: KnownNotificationType;
  policy: AdminOperationCreditNotificationPolicy;
  fixedLowBalanceThresholds: CreditNotificationFixedThreshold[];
  estimatedDaysThreshold: CreditNotificationEstimatedDaysThreshold | null;
  updatePolicy: UpdatePolicy;
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
}) {
  const { t } = useTranslation();

  if (type === 'credit_granted') {
    return (
      <div className='rounded-lg border border-dashed border-border bg-muted/20 px-3 py-2 text-xs leading-5 text-muted-foreground'>
        {t(
          'module.operationsCreditNotifications.config.typeTable.rules.creditGranted',
        )}
      </div>
    );
  }

  if (type === 'credit_expiring') {
    return (
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
              checked={policy.types.credit_expiring.merge_same_creator || false}
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
    );
  }

  if (type !== 'low_balance') {
    return null;
  }

  return (
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
            finishListInput('low_balance.thresholds', event.currentTarget.value)
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
  );
}
