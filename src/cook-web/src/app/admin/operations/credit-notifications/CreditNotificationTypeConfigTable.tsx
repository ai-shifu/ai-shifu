import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/Badge';
import type { ContactMode } from '@/lib/resolve-contact-mode';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Switch } from '@/components/ui/Switch';
import {
  CreditNotificationTypeConfigCard,
  getTemplateOptionsForType,
  type CreditNotificationTypeConfigCardProps,
} from './CreditNotificationTypeConfigCard';
import {
  CreditNotificationConfigOverviewTable,
  type CreditNotificationConfigOverviewColumn,
} from './CreditNotificationConfigOverviewTable';
import {
  isEstimatedDaysThreshold,
  isFixedThreshold,
  type KnownNotificationType,
  NOTIFICATION_TYPES,
} from './creditNotificationUtils';

type CreditNotificationTypeConfigTableProps = Omit<
  CreditNotificationTypeConfigCardProps,
  'type' | 'recommendedTemplate'
> & {
  contactMode: ContactMode;
};

type TypeConfigRow = {
  key: KnownNotificationType;
  type: KnownNotificationType;
  typePolicy: CreditNotificationTypeConfigTableProps['policy']['types'][KnownNotificationType];
  recommendedTemplate?: ReturnType<typeof getTemplateOptionsForType>[number];
  templateName: string;
  syncStatus: string;
  ruleSummary: string;
};

export function CreditNotificationTypeConfigTable(
  props: CreditNotificationTypeConfigTableProps,
) {
  const { t } = useTranslation();
  const [editingType, setEditingType] = useState<KnownNotificationType | null>(
    null,
  );
  const editingTypeLabel = editingType
    ? props.resolveTypeLabel(editingType)
    : '';
  const rows = useMemo(
    () =>
      NOTIFICATION_TYPES.map(type => {
        const typePolicy = props.policy.types[type];
        const recommendedTemplate = typePolicy.template_code.trim()
          ? undefined
          : getTemplateOptionsForType(props.templateOptions, type)[0];
        const selectedTemplate = props.templateOptions.find(
          option => option.template_code === typePolicy.template_code,
        );
        const syncResult = props.templateSyncResults[type];
        return {
          key: type,
          type,
          typePolicy,
          recommendedTemplate,
          templateName:
            selectedTemplate?.template_name ||
            selectedTemplate?.template_code ||
            typePolicy.template_code,
          syncStatus: resolveTemplateStatusLabel({
            compatible: syncResult?.compatible,
            hasTemplate: Boolean(typePolicy.template_code.trim()),
            t,
          }),
          ruleSummary: buildRuleSummary(type, props.policy, t),
        };
      }),
    [props.policy, props.templateOptions, props.templateSyncResults, t],
  );
  const columns: CreditNotificationConfigOverviewColumn[] = useMemo(
    () => [
      {
        key: 'notificationType',
        header: t(
          'module.operationsCreditNotifications.config.typeTable.notificationType',
        ),
        className: 'min-w-[180px]',
      },
      {
        key: 'enabled',
        header: t(
          'module.operationsCreditNotifications.config.typeTable.enabled',
        ),
        className: 'w-[110px] text-center',
      },
      {
        key: 'channel',
        header: t(
          'module.operationsCreditNotifications.config.typeTable.channel',
        ),
        className: 'w-[138px]',
      },
      {
        key: 'template',
        header: t(
          'module.operationsCreditNotifications.config.typeTable.template',
        ),
        className: 'min-w-[180px]',
      },
      {
        key: 'templateStatus',
        header: t(
          'module.operationsCreditNotifications.config.typeTable.templateStatus',
        ),
        className: 'min-w-[150px]',
      },
      {
        key: 'rule',
        header: t('module.operationsCreditNotifications.config.typeTable.rule'),
        className: 'min-w-[220px]',
      },
      {
        key: 'actions',
        header: t(
          'module.operationsCreditNotifications.config.typeTable.actions',
        ),
        className: 'w-[120px] text-right',
      },
    ],
    [t],
  );

  const selectedRow = rows.find(row => row.type === editingType) || null;

  return (
    <>
      <CreditNotificationConfigOverviewTable
        columns={columns}
        rows={rows}
        renderCell={(row: TypeConfigRow, column) =>
          renderTypeConfigCell(row, column.key, {
            setEditingType,
            props,
            t,
          })
        }
      />

      <Dialog
        open={editingType !== null}
        onOpenChange={open => {
          if (!open) {
            setEditingType(null);
          }
        }}
      >
        <DialogContent className='max-h-[calc(100vh-48px)] max-w-5xl overflow-y-auto'>
          <DialogHeader>
            <DialogTitle>{editingTypeLabel}</DialogTitle>
            <DialogDescription>
              {t(
                'module.operationsCreditNotifications.config.typeTable.editDescription',
              )}
            </DialogDescription>
          </DialogHeader>
          {selectedRow ? (
            <CreditNotificationTypeConfigCard
              {...props}
              type={selectedRow.type}
              recommendedTemplate={selectedRow.recommendedTemplate}
            />
          ) : null}
          <DialogFooter className='border-t border-border pt-4 sm:items-center sm:justify-between'>
            <p className='text-xs leading-5 text-muted-foreground'>
              {t(
                'module.operationsCreditNotifications.config.typeEditor.draftHint',
              )}
            </p>
            <Button
              type='button'
              onClick={() => setEditingType(null)}
            >
              {t('module.operationsCreditNotifications.config.typeEditor.done')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

const renderTypeConfigCell = (
  row: TypeConfigRow,
  columnKey: string,
  {
    setEditingType,
    props,
    t,
  }: {
    setEditingType: (type: KnownNotificationType) => void;
    props: CreditNotificationTypeConfigTableProps;
    t: (key: string, options?: Record<string, unknown>) => string;
  },
) => {
  if (columnKey === 'notificationType') {
    return (
      <div className='space-y-1'>
        <div className='text-sm font-medium text-foreground'>
          {props.resolveTypeLabel(row.type)}
        </div>
        <div className='text-xs leading-5 text-muted-foreground'>
          {t(
            `module.operationsCreditNotifications.config.typeDescriptions.${row.type}`,
          )}
        </div>
      </div>
    );
  }

  if (columnKey === 'enabled') {
    return (
      <Switch
        checked={row.typePolicy.enabled}
        onCheckedChange={checked =>
          props.updatePolicy(draft => {
            draft.types[row.type].enabled = Boolean(checked);
          })
        }
        aria-label={props.resolveTypeLabel(row.type)}
      />
    );
  }

  if (columnKey === 'channel') {
    const channelLabel =
      props.contactMode === 'email'
        ? t(
            'module.operationsCreditNotifications.config.typeTable.emailChannelComingSoon',
          )
        : t(
            'module.operationsCreditNotifications.config.typeTable.smsChannelAvailable',
          );
    return (
      <Badge
        variant={props.contactMode === 'email' ? 'outline' : 'secondary'}
        className='whitespace-nowrap font-medium data-[mode=email]:text-muted-foreground'
        data-mode={props.contactMode}
      >
        {channelLabel}
      </Badge>
    );
  }

  if (columnKey === 'template') {
    return (
      <div className='max-w-[220px] truncate text-sm text-foreground'>
        {row.templateName ||
          t(
            'module.operationsCreditNotifications.config.typeTable.templateNotSet',
          )}
      </div>
    );
  }

  if (columnKey === 'templateStatus') {
    return (
      <span className='text-sm text-muted-foreground'>{row.syncStatus}</span>
    );
  }

  if (columnKey === 'rule') {
    return (
      <span className='text-sm leading-5 text-muted-foreground'>
        {row.ruleSummary}
      </span>
    );
  }

  return (
    <Button
      type='button'
      variant='outline'
      size='sm'
      onClick={() => setEditingType(row.type)}
    >
      {t('module.operationsCreditNotifications.config.typeTable.edit')}
    </Button>
  );
};

const resolveTemplateStatusLabel = ({
  compatible,
  hasTemplate,
  t,
}: {
  compatible?: boolean;
  hasTemplate: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
}) => {
  if (!hasTemplate) {
    return t(
      'module.operationsCreditNotifications.config.typeTable.templateNotSet',
    );
  }
  if (compatible === true) {
    return t(
      'module.operationsCreditNotifications.config.typeTable.statusCompatible',
    );
  }
  if (compatible === false) {
    return t(
      'module.operationsCreditNotifications.config.typeTable.statusIncompatible',
    );
  }
  return t(
    'module.operationsCreditNotifications.config.typeTable.statusUnknown',
  );
};

const buildRuleSummary = (
  type: KnownNotificationType,
  policy: CreditNotificationTypeConfigTableProps['policy'],
  t: (key: string, options?: Record<string, unknown>) => string,
) => {
  if (type === 'credit_expiring') {
    const windows = policy.types.credit_expiring.windows || [];
    return t(
      'module.operationsCreditNotifications.config.typeTable.rules.creditExpiring',
      { windows: windows.length > 0 ? windows.join(', ') : '--' },
    );
  }

  if (type === 'low_balance') {
    const thresholds = policy.types.low_balance.thresholds || [];
    const fixedValues = thresholds
      .filter(isFixedThreshold)
      .map(threshold => threshold.value)
      .filter(Boolean);
    const estimated = thresholds.find(isEstimatedDaysThreshold);
    if (estimated) {
      return t(
        'module.operationsCreditNotifications.config.typeTable.rules.lowBalanceEstimated',
        {
          thresholds: fixedValues.length > 0 ? fixedValues.join(', ') : '--',
          days: estimated.days,
        },
      );
    }
    return t(
      'module.operationsCreditNotifications.config.typeTable.rules.lowBalanceFixed',
      { thresholds: fixedValues.length > 0 ? fixedValues.join(', ') : '--' },
    );
  }

  return t(
    'module.operationsCreditNotifications.config.typeTable.rules.creditGranted',
  );
};
