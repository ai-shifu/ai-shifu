import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminFilter from '@/app/admin/components/AdminFilter';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  ALL_OPTION_VALUE,
  type NotificationFilters,
  type NotificationOverviewCardKey,
  NOTIFICATION_DELIVERY_STATUSES,
  NOTIFICATION_SOURCE_TYPES,
  NOTIFICATION_SKIP_REASONS,
  NOTIFICATION_TYPES,
} from './creditNotificationUtils';

const SELECT_ITEM_CLASS = 'pl-3 pr-8';
const SELECT_ITEM_INDICATOR_CLASS = 'left-auto right-2';

export function CreditNotificationRecordsFilter({
  draftFilters,
  updateDraftFilter,
  searchRecords,
  resetRecords,
  activeOverviewCardKey,
  activeOverviewLabel,
  clearOverviewFilter,
  resolveDeliveryStatusLabel,
  resolveSkipReasonLabel,
  resolveTypeLabel,
  resolveSourceTypeLabel,
}: {
  draftFilters: NotificationFilters;
  updateDraftFilter: (field: keyof NotificationFilters, value: string) => void;
  searchRecords: () => void;
  resetRecords: () => void;
  activeOverviewCardKey: NotificationOverviewCardKey | null;
  activeOverviewLabel: string;
  clearOverviewFilter: () => void;
  resolveDeliveryStatusLabel: (value: string) => string;
  resolveSkipReasonLabel: (value: string) => string;
  resolveTypeLabel: (value: string) => string;
  resolveSourceTypeLabel: (value: string) => string;
}) {
  const { t } = useTranslation();
  const [filtersExpanded, setFiltersExpanded] = useState(false);
  const clearLabel = t('common.core.close');

  const filterItems = useMemo(() => {
    const renderTypeSelect = () => (
      <Select
        value={draftFilters.notification_type || ALL_OPTION_VALUE}
        onValueChange={value =>
          updateDraftFilter(
            'notification_type',
            value === ALL_OPTION_VALUE ? '' : value,
          )
        }
      >
        <SelectTrigger className='h-9'>
          <SelectValue
            placeholder={t(
              'module.operationsCreditNotifications.filters.notificationType',
            )}
          />
        </SelectTrigger>
        <SelectContent>
          <SelectItem
            value={ALL_OPTION_VALUE}
            className={SELECT_ITEM_CLASS}
            indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
          >
            {t('module.operationsCreditNotifications.filters.all')}
          </SelectItem>
          {NOTIFICATION_TYPES.map(type => (
            <SelectItem
              key={type}
              value={type}
              className={SELECT_ITEM_CLASS}
              indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
            >
              {resolveTypeLabel(type)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );

    const renderStatusSelect = () => (
      <Select
        value={draftFilters.delivery_status || ALL_OPTION_VALUE}
        onValueChange={value => {
          const nextValue = value === ALL_OPTION_VALUE ? '' : value;
          updateDraftFilter('delivery_status', nextValue);
          if (nextValue !== 'not_sent') {
            updateDraftFilter('skip_reason', '');
          }
        }}
      >
        <SelectTrigger className='h-9'>
          <SelectValue
            placeholder={t(
              'module.operationsCreditNotifications.filters.status',
            )}
          />
        </SelectTrigger>
        <SelectContent>
          <SelectItem
            value={ALL_OPTION_VALUE}
            className={SELECT_ITEM_CLASS}
            indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
          >
            {t('module.operationsCreditNotifications.filters.all')}
          </SelectItem>
          {NOTIFICATION_DELIVERY_STATUSES.map(status => (
            <SelectItem
              key={status}
              value={status}
              className={SELECT_ITEM_CLASS}
              indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
            >
              {resolveDeliveryStatusLabel(status)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );

    const renderSkipReasonSelect = () => (
      <Select
        value={draftFilters.skip_reason || ALL_OPTION_VALUE}
        onValueChange={value =>
          updateDraftFilter(
            'skip_reason',
            value === ALL_OPTION_VALUE ? '' : value,
          )
        }
      >
        <SelectTrigger className='h-9'>
          <SelectValue
            placeholder={t(
              'module.operationsCreditNotifications.filters.skipReason',
            )}
          />
        </SelectTrigger>
        <SelectContent>
          <SelectItem
            value={ALL_OPTION_VALUE}
            className={SELECT_ITEM_CLASS}
            indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
          >
            {t('module.operationsCreditNotifications.filters.all')}
          </SelectItem>
          {NOTIFICATION_SKIP_REASONS.map(reason => (
            <SelectItem
              key={reason}
              value={reason}
              className={SELECT_ITEM_CLASS}
              indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
            >
              {resolveSkipReasonLabel(reason)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );

    const renderSourceTypeSelect = () => (
      <Select
        value={draftFilters.source_type || ALL_OPTION_VALUE}
        onValueChange={value =>
          updateDraftFilter(
            'source_type',
            value === ALL_OPTION_VALUE ? '' : value,
          )
        }
      >
        <SelectTrigger className='h-9'>
          <SelectValue
            placeholder={t(
              'module.operationsCreditNotifications.filters.sourceType',
            )}
          />
        </SelectTrigger>
        <SelectContent>
          <SelectItem
            value={ALL_OPTION_VALUE}
            className={SELECT_ITEM_CLASS}
            indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
          >
            {t('module.operationsCreditNotifications.filters.all')}
          </SelectItem>
          {NOTIFICATION_SOURCE_TYPES.map(sourceType => (
            <SelectItem
              key={sourceType}
              value={sourceType}
              className={SELECT_ITEM_CLASS}
              indicatorClassName={SELECT_ITEM_INDICATOR_CLASS}
            >
              {resolveSourceTypeLabel(sourceType)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );

    const renderCreatedAtRange = () => (
      <AdminDateRangeFilter
        startValue={draftFilters.start_time}
        endValue={draftFilters.end_time}
        onChange={range => {
          updateDraftFilter('start_time', range.start);
          updateDraftFilter('end_time', range.end);
        }}
        placeholder={t(
          'module.operationsCreditNotifications.filters.timeRangePlaceholder',
        )}
        resetLabel={t('module.operationsCreditNotifications.actions.reset')}
        clearLabel={clearLabel}
      />
    );

    const renderCreatorInput = () => (
      <AdminClearableInput
        value={draftFilters.creator_keyword}
        placeholder={t(
          'module.operationsCreditNotifications.filters.creatorPlaceholder',
        )}
        clearLabel={clearLabel}
        onChange={value => updateDraftFilter('creator_keyword', value)}
      />
    );

    return [
      {
        key: 'notification_type',
        label: t(
          'module.operationsCreditNotifications.filters.notificationType',
        ),
        component: renderTypeSelect(),
      },
      {
        key: 'status',
        label: t('module.operationsCreditNotifications.filters.status'),
        component: renderStatusSelect(),
      },
      ...(draftFilters.delivery_status === 'not_sent'
        ? [
            {
              key: 'skip_reason',
              label: t(
                'module.operationsCreditNotifications.filters.skipReason',
              ),
              component: renderSkipReasonSelect(),
            },
          ]
        : []),
      {
        key: 'creator_keyword',
        label: t('module.operationsCreditNotifications.filters.creator'),
        component: renderCreatorInput(),
      },
      {
        key: 'source_type',
        label: t('module.operationsCreditNotifications.filters.sourceType'),
        component: renderSourceTypeSelect(),
      },
      {
        key: 'created_at',
        label: t('module.operationsCreditNotifications.filters.createdTime'),
        component: renderCreatedAtRange(),
      },
    ];
  }, [
    clearLabel,
    draftFilters,
    resolveDeliveryStatusLabel,
    resolveSkipReasonLabel,
    resolveSourceTypeLabel,
    resolveTypeLabel,
    t,
    updateDraftFilter,
  ]);

  return (
    <AdminFilter
      items={filterItems}
      expanded={filtersExpanded}
      onExpandedChange={setFiltersExpanded}
      onReset={resetRecords}
      onSearch={searchRecords}
      resetLabel={t('module.operationsCreditNotifications.actions.reset')}
      searchLabel={t('module.operationsCreditNotifications.actions.search')}
      expandLabel={t('common.core.expand')}
      collapseLabel={t('common.core.collapse')}
      collapsedCount={3}
      surface='card'
      layoutPreset='operations'
      activeFilter={
        activeOverviewCardKey
          ? {
              label: t(
                'module.operationsCreditNotifications.overview.activeFilter',
              ),
              value: activeOverviewLabel,
              clearAriaLabel: `${activeOverviewLabel} ${clearLabel}`,
              onClear: clearOverviewFilter,
            }
          : null
      }
    />
  );
}
