import { useTranslation } from 'react-i18next';
import { AdminMetricCardGroup } from '@/app/admin/components/AdminMetricCard';
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
    <AdminMetricCardGroup
      items={overviewItems.map(item => ({
        ...item,
        onClick: () => applyOverviewFilter(item.key),
      }))}
      gridClassName='md:grid-cols-3 xl:grid-cols-5'
    />
  );
}
