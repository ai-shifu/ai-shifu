import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import type { AdminOperationCreditNotificationDryRunResponse } from '../operation-credit-notification-types';
import { CreditNotificationConfigSection as ConfigSection } from './CreditNotificationFormPrimitives';

export function CreditNotificationDryRunPanel({
  dryRunResult,
  dryRunError,
  dryRun,
}: {
  dryRunResult: AdminOperationCreditNotificationDryRunResponse | null;
  dryRunError: string;
  dryRun: () => void;
}) {
  const { t } = useTranslation();
  const metricCards = dryRunResult
    ? [
        {
          key: 'candidate',
          label: t(
            'module.operationsCreditNotifications.dryRun.metrics.candidate',
          ),
          value: dryRunResult.candidate_count || 0,
        },
        {
          key: 'created',
          label: t(
            'module.operationsCreditNotifications.dryRun.metrics.created',
          ),
          value: dryRunResult.created_count || 0,
        },
        {
          key: 'cost',
          label: t('module.operationsCreditNotifications.dryRun.metrics.cost'),
          value: dryRunResult.estimated_sms_cost || '0',
        },
      ]
    : [];

  return (
    <ConfigSection
      title={t('module.operationsCreditNotifications.dryRun.title')}
      description={t('module.operationsCreditNotifications.dryRun.description')}
    >
      <div className='flex flex-col gap-4 rounded-md border border-border bg-muted/20 p-3 lg:flex-row lg:items-center lg:justify-between'>
        <div className='text-xs leading-5 text-muted-foreground'>
          {dryRunResult ? (
            <div className='grid gap-3 sm:grid-cols-3'>
              {metricCards.map(metric => (
                <div
                  key={metric.key}
                  className='rounded-md border border-border bg-white px-3 py-2'
                >
                  <div className='text-[11px] text-muted-foreground'>
                    {metric.label}
                  </div>
                  <div className='mt-1 text-base font-semibold text-foreground'>
                    {metric.value}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            t('module.operationsCreditNotifications.dryRun.empty')
          )}
        </div>
        <Button
          type='button'
          variant='outline'
          size='sm'
          onClick={dryRun}
        >
          {t('module.operationsCreditNotifications.actions.dryRun')}
        </Button>
      </div>
      {dryRunError ? (
        <div
          role='alert'
          className='rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive'
        >
          {dryRunError}
        </div>
      ) : null}
      {dryRunResult ? (
        <details className='rounded-md border border-border bg-white p-3 text-xs text-muted-foreground'>
          <summary className='cursor-pointer text-foreground'>
            {t('module.operationsCreditNotifications.dryRun.rawResult')}
          </summary>
          <pre className='mt-3 max-h-[220px] overflow-auto rounded-md bg-muted p-3'>
            {JSON.stringify(dryRunResult, null, 2)}
          </pre>
        </details>
      ) : null}
    </ConfigSection>
  );
}
