import { Plus } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import AdminRowActions from '@/app/admin/components/AdminRowActions';
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
  DialogDescription,
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
import { Switch } from '@/components/ui/Switch';
import type {
  AdminOperationCreditNotificationPolicy,
  AdminOperationCreditNotificationTemplateOption,
  CreditNotificationRule,
  CreditNotificationThreshold,
} from '../operation-credit-notification-types';
import { CreditNotificationConfigOverviewTable } from './CreditNotificationConfigOverviewTable';
import { CreditNotificationConfigSection } from './CreditNotificationFormPrimitives';
import {
  type KnownNotificationType,
  NOTIFICATION_TYPES,
  formatListInput,
  parseListInput,
  parseThresholdInput,
  readPositiveNumber,
} from './creditNotificationUtils';
import type { UpdatePolicy } from './useCreditNotificationConfigTabState';

type RuleAction = 'created' | 'edited' | 'deleted' | 'toggled';

const createRuleBid = () =>
  `rule-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const createDraftRule = (): CreditNotificationRule => ({
  rule_bid: createRuleBid(),
  name: '',
  trigger_event: 'credit_granted',
  channel: 'sms',
  template_code: '',
  enabled: false,
  conditions: {},
});

const cloneRule = (rule: CreditNotificationRule): CreditNotificationRule =>
  JSON.parse(JSON.stringify(rule)) as CreditNotificationRule;

const canSaveRule = (rule: CreditNotificationRule | null) => {
  if (!rule?.name.trim() || (rule.enabled && !rule.template_code.trim())) {
    return false;
  }
  if (rule.trigger_event === 'credit_expiring' && !rule.legacy) {
    return Boolean(rule.conditions.windows?.length);
  }
  if (rule.trigger_event === 'low_balance' && rule.enabled) {
    return Boolean(rule.conditions.thresholds?.length);
  }
  return true;
};

const ruleConditionsSummary = (
  rule: CreditNotificationRule,
  t: (key: string) => string,
) => {
  if (rule.trigger_event === 'credit_expiring') {
    return (rule.conditions.windows || []).join(', ') || '--';
  }
  if (rule.trigger_event === 'low_balance') {
    return (
      (rule.conditions.thresholds || [])
        .map(threshold =>
          threshold.kind === 'fixed' ? threshold.value : `${threshold.days}d`,
        )
        .join(', ') || '--'
    );
  }
  return t('module.operationsCreditNotifications.ruleManagement.noConditions');
};

export function CreditNotificationRuleManagementSection({
  policy,
  templateOptions,
  resolveTypeLabel,
  updatePolicy,
  onRuleAction,
}: {
  policy: AdminOperationCreditNotificationPolicy;
  templateOptions: AdminOperationCreditNotificationTemplateOption[];
  resolveTypeLabel: (value: string) => string;
  updatePolicy: UpdatePolicy;
  onRuleAction: (
    action: RuleAction,
    triggerEvent: KnownNotificationType,
  ) => void;
}) {
  const { t } = useTranslation();
  const [editingRule, setEditingRule] = useState<CreditNotificationRule | null>(
    null,
  );
  const [isNewRule, setIsNewRule] = useState(false);
  const [deletingRule, setDeletingRule] =
    useState<CreditNotificationRule | null>(null);
  const rows = policy.rules;
  const columns = useMemo(
    () => [
      {
        key: 'name',
        header: t(
          'module.operationsCreditNotifications.ruleManagement.columns.name',
        ),
        className: 'min-w-[180px]',
      },
      {
        key: 'trigger',
        header: t(
          'module.operationsCreditNotifications.ruleManagement.columns.trigger',
        ),
        className: 'min-w-[150px]',
      },
      {
        key: 'template',
        header: t(
          'module.operationsCreditNotifications.ruleManagement.columns.template',
        ),
        className: 'min-w-[180px]',
      },
      {
        key: 'conditions',
        header: t(
          'module.operationsCreditNotifications.ruleManagement.columns.conditions',
        ),
        className: 'min-w-[180px]',
      },
      {
        key: 'enabled',
        header: t(
          'module.operationsCreditNotifications.ruleManagement.columns.enabled',
        ),
        className: 'w-[96px] text-center',
      },
      {
        key: 'actions',
        header: t(
          'module.operationsCreditNotifications.ruleManagement.columns.actions',
        ),
        className: 'w-[128px] text-right',
      },
    ],
    [t],
  );
  const openNewRule = () => {
    setEditingRule(createDraftRule());
    setIsNewRule(true);
  };
  const openEditRule = (rule: CreditNotificationRule) => {
    setEditingRule(cloneRule(rule));
    setIsNewRule(false);
  };
  const saveRule = () => {
    if (!editingRule) return;
    updatePolicy(draft => {
      const existingIndex = draft.rules.findIndex(
        rule => rule.rule_bid === editingRule.rule_bid,
      );
      if (existingIndex >= 0) draft.rules[existingIndex] = editingRule;
      else draft.rules.push(editingRule);
    });
    onRuleAction(isNewRule ? 'created' : 'edited', editingRule.trigger_event);
    setEditingRule(null);
  };
  const deleteRule = () => {
    if (!deletingRule) return;
    updatePolicy(draft => {
      draft.rules = draft.rules.filter(
        item => item.rule_bid !== deletingRule.rule_bid,
      );
    });
    onRuleAction('deleted', deletingRule.trigger_event);
    setDeletingRule(null);
  };

  return (
    <>
      <CreditNotificationConfigSection
        title={t('module.operationsCreditNotifications.ruleManagement.title')}
        description={t(
          'module.operationsCreditNotifications.ruleManagement.description',
        )}
        action={
          <Button
            type='button'
            size='sm'
            onClick={openNewRule}
          >
            <Plus className='mr-1.5 h-4 w-4' />
            {t('module.operationsCreditNotifications.ruleManagement.newRule')}
          </Button>
        }
      >
        {rows.length ? (
          <CreditNotificationConfigOverviewTable
            columns={columns}
            rows={rows.map(rule => ({ ...rule, key: rule.rule_bid }))}
            renderCell={(rule, column) => {
              if (column.key === 'name')
                return (
                  <span className='text-sm font-medium'>
                    {rule.legacy
                      ? resolveTypeLabel(rule.trigger_event)
                      : rule.name || '--'}
                  </span>
                );
              if (column.key === 'trigger')
                return (
                  <span className='text-sm'>
                    {resolveTypeLabel(rule.trigger_event)}
                  </span>
                );
              if (column.key === 'template')
                return (
                  <span className='block max-w-48 truncate text-sm'>
                    {rule.template_code || '--'}
                  </span>
                );
              if (column.key === 'conditions')
                return (
                  <span className='text-sm text-muted-foreground'>
                    {ruleConditionsSummary(rule, t)}
                  </span>
                );
              if (column.key === 'enabled')
                return (
                  <Switch
                    checked={rule.enabled}
                    disabled={
                      !rule.enabled && !canSaveRule({ ...rule, enabled: true })
                    }
                    onCheckedChange={checked => {
                      if (checked && !canSaveRule({ ...rule, enabled: true })) {
                        return;
                      }
                      updatePolicy(draft => {
                        const target = draft.rules.find(
                          item => item.rule_bid === rule.rule_bid,
                        );
                        if (target) target.enabled = Boolean(checked);
                      });
                      onRuleAction('toggled', rule.trigger_event);
                    }}
                    aria-label={
                      rule.name || resolveTypeLabel(rule.trigger_event)
                    }
                  />
                );
              return (
                <div className='flex justify-end'>
                  <AdminRowActions
                    label={t('common.core.more')}
                    className='whitespace-nowrap'
                    actions={[
                      {
                        key: 'edit',
                        label: t(
                          'module.operationsCreditNotifications.ruleManagement.edit',
                        ),
                        onClick: () => openEditRule(rule),
                      },
                      {
                        key: 'delete',
                        label: t(
                          'module.operationsCreditNotifications.ruleManagement.delete',
                        ),
                        onClick: () => setDeletingRule(rule),
                        disabled: Boolean(rule.legacy),
                      },
                    ]}
                  />
                </div>
              );
            }}
          />
        ) : (
          <div className='rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground'>
            {t('module.operationsCreditNotifications.ruleManagement.empty')}
          </div>
        )}
      </CreditNotificationConfigSection>
      <Dialog
        open={editingRule !== null}
        onOpenChange={open => !open && setEditingRule(null)}
      >
        <DialogContent className='max-w-2xl'>
          <DialogHeader>
            <DialogTitle>
              {isNewRule
                ? t(
                    'module.operationsCreditNotifications.ruleManagement.newRule',
                  )
                : t(
                    'module.operationsCreditNotifications.ruleManagement.editRule',
                  )}
            </DialogTitle>
            <DialogDescription>
              {t(
                'module.operationsCreditNotifications.ruleManagement.dialogDescription',
              )}
            </DialogDescription>
          </DialogHeader>
          {editingRule ? (
            <RuleEditor
              rule={editingRule}
              templateOptions={templateOptions}
              resolveTypeLabel={resolveTypeLabel}
              onChange={setEditingRule}
            />
          ) : null}
          <DialogFooter>
            <Button
              type='button'
              variant='outline'
              onClick={() => setEditingRule(null)}
            >
              {t('module.operationsCreditNotifications.ruleManagement.cancel')}
            </Button>
            <Button
              type='button'
              onClick={saveRule}
              disabled={!canSaveRule(editingRule)}
            >
              {t(
                'module.operationsCreditNotifications.ruleManagement.saveRule',
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <AlertDialog
        open={deletingRule !== null}
        onOpenChange={open => !open && setDeletingRule(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t(
                'module.operationsCreditNotifications.ruleManagement.deleteTitle',
              )}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t(
                'module.operationsCreditNotifications.ruleManagement.deleteDescription',
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t('module.operationsCreditNotifications.ruleManagement.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              className='bg-destructive text-destructive-foreground hover:bg-destructive/90'
              onClick={deleteRule}
            >
              {t('module.operationsCreditNotifications.ruleManagement.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function RuleEditor({
  rule,
  templateOptions,
  resolveTypeLabel,
  onChange,
}: {
  rule: CreditNotificationRule;
  templateOptions: AdminOperationCreditNotificationTemplateOption[];
  resolveTypeLabel: (value: string) => string;
  onChange: (rule: CreditNotificationRule) => void;
}) {
  const { t } = useTranslation();
  const [windowsInput, setWindowsInput] = useState(() =>
    formatListInput(rule.conditions.windows || []),
  );
  const [thresholdsInput, setThresholdsInput] = useState(() =>
    formatListInput(
      (rule.conditions.thresholds || [])
        .filter(
          (
            value,
          ): value is Extract<CreditNotificationThreshold, { kind: 'fixed' }> =>
            value.kind === 'fixed',
        )
        .map(value => value.value),
    ),
  );
  const update = (patch: Partial<CreditNotificationRule>) =>
    onChange({ ...rule, ...patch });
  useEffect(() => {
    setWindowsInput(formatListInput(rule.conditions.windows || []));
    setThresholdsInput(
      formatListInput(
        (rule.conditions.thresholds || [])
          .filter(
            (
              value,
            ): value is Extract<
              CreditNotificationThreshold,
              { kind: 'fixed' }
            > => value.kind === 'fixed',
          )
          .map(value => value.value),
      ),
    );
  }, [rule.rule_bid, rule.trigger_event]); // eslint-disable-line react-hooks/exhaustive-deps -- Keep partially typed list input until blur.
  const fixedThresholds = (rule.conditions.thresholds || []).filter(
    (value): value is Extract<CreditNotificationThreshold, { kind: 'fixed' }> =>
      value.kind === 'fixed',
  );
  const estimatedDaysThresholds = (rule.conditions.thresholds || []).filter(
    (
      value,
    ): value is Extract<
      CreditNotificationThreshold,
      { kind: 'estimated_days' }
    > => value.kind === 'estimated_days',
  );
  const estimatedDaysThreshold = estimatedDaysThresholds[0] || null;
  const updateEstimatedDaysThreshold = (
    patch: Partial<
      Extract<CreditNotificationThreshold, { kind: 'estimated_days' }>
    >,
  ) => {
    const base = estimatedDaysThreshold || {
      kind: 'estimated_days' as const,
      days: 7,
      lookback_days: 7,
      min_consumed_days: 2,
    };
    update({
      conditions: {
        thresholds: [
          ...fixedThresholds,
          { ...base, ...patch },
          ...estimatedDaysThresholds.slice(1),
        ],
      },
    });
  };
  return (
    <div className='grid gap-4 py-2 sm:grid-cols-2'>
      <div className='sm:col-span-2'>
        <Label htmlFor='notification-rule-name'>
          {t('module.operationsCreditNotifications.ruleManagement.fields.name')}
        </Label>
        <Input
          id='notification-rule-name'
          className='mt-1'
          value={rule.name}
          onChange={event => update({ name: event.target.value })}
        />
      </div>
      <div>
        <Label>
          {t(
            'module.operationsCreditNotifications.ruleManagement.fields.trigger',
          )}
        </Label>
        <Select
          value={rule.trigger_event}
          onValueChange={value =>
            update({
              trigger_event: value as KnownNotificationType,
              template_code: '',
              conditions:
                value === 'credit_expiring'
                  ? { windows: [] }
                  : value === 'low_balance'
                    ? { thresholds: [] }
                    : {},
            })
          }
        >
          <SelectTrigger className='mt-1'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {NOTIFICATION_TYPES.map(type => (
              <SelectItem
                key={type}
                value={type}
              >
                {resolveTypeLabel(type)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <RuleTemplateSelector
        rule={rule}
        templateOptions={templateOptions}
        onChange={template_code => update({ template_code })}
      />
      {rule.trigger_event === 'credit_expiring' ? (
        <div className='sm:col-span-2'>
          <Label htmlFor='notification-rule-windows'>
            {t(
              'module.operationsCreditNotifications.ruleManagement.fields.windows',
            )}
          </Label>
          <Input
            id='notification-rule-windows'
            className='mt-1'
            value={windowsInput}
            onChange={event => {
              setWindowsInput(event.target.value);
              update({
                conditions: {
                  windows: parseListInput(event.target.value),
                  merge_same_creator:
                    rule.conditions.merge_same_creator || false,
                },
              });
            }}
            onBlur={() =>
              setWindowsInput(formatListInput(parseListInput(windowsInput)))
            }
          />
          <div className='mt-3 flex items-center justify-between rounded-md border border-border px-3 py-2'>
            <Label htmlFor='notification-rule-merge-same-creator'>
              {t(
                'module.operationsCreditNotifications.config.fields.mergeSameCreator',
              )}
            </Label>
            <Switch
              id='notification-rule-merge-same-creator'
              checked={rule.conditions.merge_same_creator || false}
              onCheckedChange={merge_same_creator =>
                update({
                  conditions: {
                    windows: rule.conditions.windows || [],
                    merge_same_creator,
                  },
                })
              }
            />
          </div>
        </div>
      ) : null}
      {rule.trigger_event === 'low_balance' ? (
        <div className='space-y-3 sm:col-span-2'>
          <Label htmlFor='notification-rule-thresholds'>
            {t(
              'module.operationsCreditNotifications.ruleManagement.fields.thresholds',
            )}
          </Label>
          <Input
            id='notification-rule-thresholds'
            className='mt-1'
            value={thresholdsInput}
            onChange={event => {
              setThresholdsInput(event.target.value);
              update({
                conditions: {
                  thresholds: [
                    ...parseThresholdInput(event.target.value),
                    ...estimatedDaysThresholds,
                  ],
                },
              });
            }}
            onBlur={() =>
              setThresholdsInput(
                formatListInput(parseListInput(thresholdsInput)),
              )
            }
          />
          <div className='rounded-md border border-border px-3 py-2'>
            <div className='flex items-center justify-between gap-4'>
              <Label htmlFor='notification-rule-estimated-days-enabled'>
                {t(
                  'module.operationsCreditNotifications.config.fields.estimatedDaysEnabled',
                )}
              </Label>
              <Switch
                id='notification-rule-estimated-days-enabled'
                checked={Boolean(estimatedDaysThreshold)}
                onCheckedChange={checked => {
                  if (checked) {
                    updateEstimatedDaysThreshold({});
                    return;
                  }
                  update({
                    conditions: { thresholds: fixedThresholds },
                  });
                }}
              />
            </div>
            {estimatedDaysThreshold ? (
              <div className='mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4'>
                <RuleNumberInput
                  id='notification-rule-estimated-days'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.estimatedDays',
                  )}
                  value={estimatedDaysThreshold.days}
                  onChange={days => updateEstimatedDaysThreshold({ days })}
                />
                <RuleNumberInput
                  id='notification-rule-lookback-days'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.lookbackDays',
                  )}
                  value={estimatedDaysThreshold.lookback_days}
                  onChange={lookback_days =>
                    updateEstimatedDaysThreshold({ lookback_days })
                  }
                />
                <RuleNumberInput
                  id='notification-rule-min-consumed-days'
                  label={t(
                    'module.operationsCreditNotifications.config.fields.minConsumedDays',
                  )}
                  value={estimatedDaysThreshold.min_consumed_days}
                  onChange={min_consumed_days =>
                    updateEstimatedDaysThreshold({ min_consumed_days })
                  }
                />
                <div>
                  <Label htmlFor='notification-rule-fallback-fixed-value'>
                    {t(
                      'module.operationsCreditNotifications.config.fields.fallbackFixedValue',
                    )}
                  </Label>
                  <Input
                    id='notification-rule-fallback-fixed-value'
                    className='mt-1'
                    value={estimatedDaysThreshold.fallback_fixed_value || ''}
                    onChange={event =>
                      updateEstimatedDaysThreshold({
                        fallback_fixed_value:
                          event.target.value.trim() || undefined,
                      })
                    }
                  />
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
      <div className='flex items-center justify-between rounded-md border border-border px-3 py-2 sm:col-span-2'>
        <Label htmlFor='notification-rule-enabled'>
          {t(
            'module.operationsCreditNotifications.ruleManagement.fields.enabled',
          )}
        </Label>
        <Switch
          id='notification-rule-enabled'
          checked={rule.enabled}
          onCheckedChange={enabled => update({ enabled })}
        />
      </div>
    </div>
  );
}

function RuleTemplateSelector({
  rule,
  templateOptions,
  onChange,
}: {
  rule: CreditNotificationRule;
  templateOptions: AdminOperationCreditNotificationTemplateOption[];
  onChange: (templateCode: string) => void;
}) {
  const { t } = useTranslation();
  const compatibleTemplates = templateOptions.filter(
    option =>
      option.channel === 'sms' &&
      option.provider === 'aliyun' &&
      option.template_status === 'AUDIT_STATE_PASS' &&
      (!option.compatible_notification_types ||
        option.compatible_notification_types.includes(rule.trigger_event)),
  );

  return (
    <div>
      <Label>
        {t(
          'module.operationsCreditNotifications.ruleManagement.fields.template',
        )}
      </Label>
      <Select
        value={rule.template_code}
        onValueChange={onChange}
      >
        <SelectTrigger className='mt-1'>
          <SelectValue
            placeholder={t(
              'module.operationsCreditNotifications.ruleManagement.selectTemplate',
            )}
          />
        </SelectTrigger>
        <SelectContent>
          {compatibleTemplates.map(template => (
            <SelectItem
              key={template.template_code}
              value={template.template_code}
            >
              {template.template_name || template.template_code}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function RuleNumberInput({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        className='mt-1'
        inputMode='numeric'
        min={1}
        type='number'
        value={value}
        onChange={event => onChange(readPositiveNumber(event.target.value, 1))}
      />
    </div>
  );
}
