import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import AdminTimeSelect from '@/app/admin/components/AdminTimeSelect';
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
import { CreditNotificationFormField as FormField } from './CreditNotificationFormPrimitives';
import type { CreditNotificationDeliveryRulesSectionProps } from './CreditNotificationDeliveryRulesSection';

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

export function SoftlimitCard({
  policy,
  updatePolicy,
}: Pick<
  CreditNotificationDeliveryRulesSectionProps,
  'policy' | 'updatePolicy'
>) {
  const { t } = useTranslation();
  return (
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
              onCheckedChange={checked => field.update(Boolean(checked))}
            />
          </div>
        ))}
      </div>
    </ConfigCard>
  );
}

export function FrequencyCard({
  policy,
  updatePolicy,
  getIntegerInputValue,
  updateIntegerInput,
  finishIntegerInput,
}: CreditNotificationDeliveryRulesSectionProps) {
  const { t } = useTranslation();
  return (
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
                    draft.frequency.per_creator_per_type_per_day = value;
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
  );
}

export function QuietHoursCard({
  policy,
  updatePolicy,
}: Pick<
  CreditNotificationDeliveryRulesSectionProps,
  'policy' | 'updatePolicy'
>) {
  const { t } = useTranslation();
  return (
    <ConfigCard
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
                >
                  {timezone}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FormField>
      </div>
    </ConfigCard>
  );
}

export function BudgetCard({
  policy,
  updatePolicy,
  getIntegerInputValue,
  updateIntegerInput,
  finishIntegerInput,
}: CreditNotificationDeliveryRulesSectionProps) {
  const { t } = useTranslation();
  return (
    <ConfigCard
      title={t('module.operationsCreditNotifications.config.sections.budget')}
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
    </ConfigCard>
  );
}
