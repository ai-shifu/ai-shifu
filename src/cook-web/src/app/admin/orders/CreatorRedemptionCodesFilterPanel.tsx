'use client';

import { useMemo } from 'react';
import type { AdminFilterItem } from '@/app/admin/components/AdminFilter';
import AdminFilter from '@/app/admin/components/AdminFilter';
import {
  createDateRangeFilterItem,
  createSelectFilterItem,
  createTextFilterItem,
} from '@/app/admin/components/adminFilterFieldBuilders';
import { COUPON_OPS_STATE_OPTIONS } from '@/app/admin/operations/promotions/promotionPageShared';
import {
  SINGLE_SELECT_INDICATOR_CLASS,
  SINGLE_SELECT_ITEM_CLASS,
  fromSelectValue,
  toSelectValue,
  type RedemptionCodeFilters,
} from './creatorRedemptionCodeShared';

type TranslationFn = (key: string, options?: Record<string, unknown>) => string;

export default function CreatorRedemptionCodesFilterPanel({
  expanded,
  filters,
  onExpandedChange,
  onFilterChange,
  onReset,
  onSearch,
  t,
  tPromotion,
}: {
  expanded: boolean;
  filters: RedemptionCodeFilters;
  onExpandedChange: (expanded: boolean) => void;
  onFilterChange: (key: keyof RedemptionCodeFilters, value: string) => void;
  onReset: () => void;
  onSearch: () => void;
  t: TranslationFn;
  tPromotion: TranslationFn;
}) {
  const usageTypeOptions = useMemo(
    () => [
      { value: '', label: t('module.order.filters.all') },
      { value: '801', label: tPromotion('usageType.generic') },
      { value: '802', label: tPromotion('usageType.singleUse') },
    ],
    [t, tPromotion],
  );

  const discountTypeOptions = useMemo(
    () => [
      { value: '', label: t('module.order.filters.all') },
      { value: '701', label: tPromotion('discountType.fixed') },
      { value: '702', label: tPromotion('discountType.percent') },
    ],
    [t, tPromotion],
  );

  const statusOptions = useMemo(
    () => [
      { value: '', label: t('module.order.filters.all') },
      { value: 'active', label: tPromotion('status.active') },
      { value: 'not_started', label: tPromotion('status.notStarted') },
      { value: 'inactive', label: tPromotion('status.inactive') },
      { value: 'expired', label: tPromotion('status.expired') },
    ],
    [t, tPromotion],
  );

  const opsStateOptions = useMemo(
    () => [
      { value: '', label: t('module.order.filters.all') },
      ...COUPON_OPS_STATE_OPTIONS.map(option => ({
        value: option.value,
        label: tPromotion(option.labelKey),
      })),
    ],
    [t, tPromotion],
  );

  const buildSelectItem = (
    key: keyof RedemptionCodeFilters,
    label: string,
    placeholder: string,
    value: string,
    options: Array<{ value: string; label: string }>,
  ): AdminFilterItem =>
    createSelectFilterItem({
      key,
      label,
      value: toSelectValue(value),
      onChange: nextValue => onFilterChange(key, fromSelectValue(nextValue)),
      placeholder,
      options: options.map(option => ({
        value: toSelectValue(option.value),
        label: option.label,
      })),
      selectItemClassName: SINGLE_SELECT_ITEM_CLASS,
      indicatorClassName: SINGLE_SELECT_INDICATOR_CLASS,
    });

  const filterItems: AdminFilterItem[] = [
    createTextFilterItem({
      key: 'name',
      label: tPromotion('filters.name'),
      value: filters.name,
      onChange: value => onFilterChange('name', value),
      placeholder: tPromotion('filters.namePlaceholder'),
      clearLabel: t('common.core.close'),
    }),
    createTextFilterItem({
      key: 'course_query',
      label: tPromotion('filters.courseId'),
      value: filters.course_query,
      onChange: value => onFilterChange('course_query', value),
      placeholder: tPromotion('filters.courseIdPlaceholder'),
      clearLabel: t('common.core.close'),
    }),
    buildSelectItem(
      'usage_type',
      tPromotion('filters.usageType'),
      tPromotion('filters.usageType'),
      filters.usage_type,
      usageTypeOptions,
    ),
    buildSelectItem(
      'status',
      tPromotion('filters.status'),
      tPromotion('filters.status'),
      filters.status,
      statusOptions,
    ),
    buildSelectItem(
      'ops_state',
      t('module.order.redemptionCodes.opsState'),
      t('module.order.redemptionCodes.opsState'),
      filters.ops_state,
      opsStateOptions,
    ),
    buildSelectItem(
      'discount_type',
      tPromotion('filters.discountType'),
      tPromotion('filters.discountType'),
      filters.discount_type,
      discountTypeOptions,
    ),
    createDateRangeFilterItem({
      key: 'date_range',
      label: tPromotion('filters.activeTime'),
      startValue: filters.start_time,
      endValue: filters.end_time,
      onChange: range => {
        onFilterChange('start_time', range.start);
        onFilterChange('end_time', range.end);
      },
      placeholder: t('module.order.filters.dateRangePlaceholder'),
      resetLabel: t('module.order.filters.reset'),
      clearLabel: t('common.core.close'),
    }),
    createTextFilterItem({
      key: 'keyword',
      label: tPromotion('filters.keyword'),
      value: filters.keyword,
      onChange: value => onFilterChange('keyword', value),
      placeholder: tPromotion('filters.keywordPlaceholder'),
      clearLabel: t('common.core.close'),
    }),
  ];

  return (
    <AdminFilter
      items={filterItems}
      expanded={expanded}
      onExpandedChange={onExpandedChange}
      onReset={onReset}
      onSearch={onSearch}
      resetLabel={t('module.order.filters.reset')}
      searchLabel={t('module.order.filters.search')}
      expandLabel={t('common.core.expand')}
      collapseLabel={t('common.core.collapse')}
      collapsedCount={4}
      labelClassName='w-24'
      contentClassName='min-w-0'
      collapsedGridClassName='gap-x-7 xl:grid-cols-4'
      expandedGridClassName='gap-x-7 xl:grid-cols-4'
      showToggle
    />
  );
}
