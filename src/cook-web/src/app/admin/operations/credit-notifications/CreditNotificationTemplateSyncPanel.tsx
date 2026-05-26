import { ChevronDown, Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import type {
  AdminOperationCreditNotificationTemplateSyncResponse,
  CreditNotificationEstimatedDaysThreshold,
  CreditNotificationFixedThreshold,
} from '../operation-credit-notification-types';
import {
  buildPlaceholderGuideGroups,
  formatPlaceholderList,
  formatPlaceholderToken,
  formatValue,
  type KnownNotificationType,
} from './creditNotificationUtils';

export function CreditNotificationTemplateSyncResult({
  syncResult,
}: {
  syncResult: AdminOperationCreditNotificationTemplateSyncResponse;
}) {
  const { t } = useTranslation();

  return (
    <div
      className={cn(
        'rounded-lg border px-3 py-3 text-xs',
        syncResult.compatible
          ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
          : 'border-amber-200 bg-amber-50 text-amber-900',
      )}
    >
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <span className='font-medium'>
          {syncResult.compatible
            ? t(
                'module.operationsCreditNotifications.config.templateSync.compatible',
              )
            : t(
                'module.operationsCreditNotifications.config.templateSync.incompatible',
              )}
        </span>
        <Badge variant='secondary'>{formatValue(syncResult.sync_status)}</Badge>
      </div>
      <div className='mt-2 grid gap-2 lg:grid-cols-2'>
        {[
          {
            label:
              'module.operationsCreditNotifications.config.templateSync.content',
            value: formatValue(syncResult.template_content),
          },
          {
            label:
              'module.operationsCreditNotifications.config.templateSync.status',
            value: formatValue(syncResult.template_status),
          },
          {
            label:
              'module.operationsCreditNotifications.config.templateSync.variables',
            value: formatPlaceholderList(syncResult.placeholders),
          },
          {
            label:
              'module.operationsCreditNotifications.config.templateSync.unused',
            value: formatPlaceholderList(
              syncResult.unused_supported_placeholders,
            ),
          },
          {
            label:
              'module.operationsCreditNotifications.config.templateSync.unsupported',
            value: formatPlaceholderList(syncResult.unsupported_placeholders),
          },
          ...(syncResult.error_message
            ? [
                {
                  label:
                    'module.operationsCreditNotifications.config.templateSync.error',
                  value: syncResult.error_message,
                },
              ]
            : []),
        ].map(item => (
          <div
            key={item.label}
            className='min-w-0'
          >
            <div className='font-medium'>{t(item.label)}</div>
            <div className='mt-0.5 break-all'>{item.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function CreditNotificationPlaceholderGuide({
  type,
  fixedLowBalanceThresholds,
  estimatedDaysThreshold,
}: {
  type: KnownNotificationType;
  fixedLowBalanceThresholds: CreditNotificationFixedThreshold[];
  estimatedDaysThreshold: CreditNotificationEstimatedDaysThreshold | null;
}) {
  const { t } = useTranslation();
  const hasEstimatedLowBalance =
    type === 'low_balance' && Boolean(estimatedDaysThreshold);
  const hasEstimatedFallback =
    type === 'low_balance' &&
    Boolean(String(estimatedDaysThreshold?.fallback_fixed_value || '').trim());
  const hasFixedLowBalancePath =
    type === 'low_balance' &&
    (fixedLowBalanceThresholds.length > 0 || hasEstimatedFallback);
  const groups = buildPlaceholderGuideGroups({
    type,
    hasFixedLowBalancePath,
    hasEstimatedLowBalance,
  });
  const shouldShowGroupTitle = groups.length > 1;
  const noteKeys = [
    'module.operationsCreditNotifications.config.placeholders.tolerance',
    'module.operationsCreditNotifications.config.placeholders.notes.emptyVariables',
    'module.operationsCreditNotifications.config.placeholders.notes.unsupportedValidation',
    ...(hasEstimatedFallback
      ? [
          'module.operationsCreditNotifications.config.placeholders.notes.fallbackLowBalance',
        ]
      : []),
  ];

  return (
    <details className='group rounded-md border border-border bg-white px-3 py-2'>
      <summary className='flex cursor-pointer list-none items-center justify-between gap-3 text-xs font-medium text-muted-foreground marker:hidden'>
        <span className='flex min-w-0 items-center gap-2'>
          <Info className='h-3.5 w-3.5 shrink-0' />
          <span>
            {t(
              `module.operationsCreditNotifications.config.placeholders.guideTitle.${type}`,
            )}
          </span>
        </span>
        <span className='inline-flex shrink-0 items-center gap-1 text-[11px] font-normal text-primary'>
          <span className='group-open:hidden'>
            {t(
              'module.operationsCreditNotifications.config.placeholders.expand',
            )}
          </span>
          <span className='hidden group-open:inline'>
            {t(
              'module.operationsCreditNotifications.config.placeholders.collapse',
            )}
          </span>
          <ChevronDown className='h-3.5 w-3.5 transition-transform group-open:rotate-180' />
        </span>
      </summary>
      <p className='mt-1 text-[11px] text-muted-foreground group-open:hidden'>
        {t(
          'module.operationsCreditNotifications.config.placeholders.guideHint',
        )}
      </p>
      <div className='mt-2 space-y-2'>
        {groups.map(group => (
          <div
            key={group.id}
            className='rounded-md border border-border bg-muted/30 p-2'
          >
            {shouldShowGroupTitle ? (
              <div className='text-xs font-medium text-foreground'>
                {t(group.titleKey)}
              </div>
            ) : null}
            {group.descriptionKey ? (
              <p
                className={`text-xs leading-5 text-muted-foreground ${
                  shouldShowGroupTitle ? 'mt-1' : ''
                }`}
              >
                {t(group.descriptionKey)}
              </p>
            ) : null}
            <div className='mt-2 flex flex-wrap gap-1'>
              {group.placeholders.map(placeholder => (
                <span
                  key={`${group.id}-${placeholder}`}
                  className='inline-flex items-center gap-1 rounded border border-border bg-white px-2 py-1 text-xs text-muted-foreground'
                >
                  <code className='font-mono text-foreground'>
                    {formatPlaceholderToken(placeholder)}
                  </code>
                  <span>
                    {t(
                      `module.operationsCreditNotifications.config.placeholders.${placeholder}`,
                    )}
                  </span>
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
      <ul className='mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-muted-foreground'>
        {noteKeys.map(noteKey => (
          <li key={noteKey}>{t(noteKey)}</li>
        ))}
      </ul>
    </details>
  );
}
