import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
import { useTranslation } from 'react-i18next';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { AdminOperationCreditNotificationOverview } from '../operation-credit-notification-types';
import type { NotificationOverviewCardKey } from './creditNotificationUtils';

export function CreditNotificationOverviewCards({
  overview,
  applyOverviewFilter,
}: {
  overview: AdminOperationCreditNotificationOverview;
  applyOverviewFilter: (cardKey: NotificationOverviewCardKey) => void;
}) {
  const { t } = useTranslation();
  const overviewItems = [
    {
      key: 'total' as const,
      label: t('module.operationsCreditNotifications.overview.total'),
      value: overview.total,
      tooltip: t('module.operationsCreditNotifications.overview.totalTooltip'),
    },
    {
      key: 'pending' as const,
      label: t('module.operationsCreditNotifications.overview.pending'),
      value: overview.pending,
      tooltip: t(
        'module.operationsCreditNotifications.overview.pendingTooltip',
      ),
    },
    {
      key: 'sent' as const,
      label: t('module.operationsCreditNotifications.overview.sent'),
      value: overview.sent,
      tooltip: t('module.operationsCreditNotifications.overview.sentTooltip'),
    },
    {
      key: 'failed' as const,
      label: t('module.operationsCreditNotifications.overview.failed'),
      value: overview.failed,
      tooltip: t('module.operationsCreditNotifications.overview.failedTooltip'),
    },
    {
      key: 'skipped' as const,
      label: t('module.operationsCreditNotifications.overview.skipped'),
      value: overview.skipped,
      tooltip: t(
        'module.operationsCreditNotifications.overview.skippedTooltip',
      ),
    },
  ];

  return (
    <TooltipProvider delayDuration={150}>
      <div className='grid gap-3 md:grid-cols-3 xl:grid-cols-5'>
        {overviewItems.map(item => (
          <div
            key={item.key}
            className='rounded-lg border border-border/70 bg-muted/20 p-4 transition-colors hover:border-primary/30 hover:bg-primary/[0.04]'
          >
            <div className='flex items-start justify-between gap-2'>
              <button
                type='button'
                aria-label={item.label}
                className='group min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2'
                onClick={() => applyOverviewFilter(item.key)}
              >
                <div className='text-sm text-muted-foreground'>
                  {item.label}
                </div>
                <div className='mt-3 text-2xl font-semibold text-foreground transition-colors group-hover:text-primary'>
                  {item.value}
                </div>
              </button>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type='button'
                    aria-label={item.tooltip}
                    className='inline-flex h-4 w-4 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2'
                  >
                    <QuestionMarkCircleIcon className='h-4 w-4' />
                  </button>
                </TooltipTrigger>
                <TooltipContent className='max-w-56 text-left leading-5'>
                  {item.tooltip}
                </TooltipContent>
              </Tooltip>
            </div>
          </div>
        ))}
      </div>
    </TooltipProvider>
  );
}
