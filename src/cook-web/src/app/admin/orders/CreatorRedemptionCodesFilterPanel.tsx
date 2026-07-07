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
import {
  ORDER_FILTER_CONTENT_CLASS,
  ORDER_FILTER_GRID_CLASS,
  type OrderFilterLabelWidth,
  getOrderFilterLabelClassName,
} from './orderFilterUiShared';

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
    labelWidth: OrderFilterLabelWidth = 'default',
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
      labelClassName: getOrderFilterLabelClassName(labelWidth),
      selectItemClassName: SINGLE_SELECT_ITEM_CLASS,
      indicatorClassName: SINGLE_SELECT_INDICATOR_CLASS,
    });

  const buildTextItem = (
    key: keyof RedemptionCodeFilters,
    label: string,
    placeholder: string,
    value: string,
    labelWidth: OrderFilterLabelWidth = 'default',
  ): AdminFilterItem =>
    createTextFilterItem({
      key,
      label,
      value,
      onChange: nextValue => onFilterChange(key, nextValue),
      placeholder,
      clearLabel: t('common.core.close'),
      labelClassName: getOrderFilterLabelClassName(labelWidth),
    });

  const filterItems: AdminFilterItem[] = [
    buildTextItem(
      'name',
      tPromotion('filters.name'),
      tPromotion('filters.namePlaceholder'),
      filters.name,
    ),
    buildTextItem(
      'course_query',
      tPromotion('filters.courseId'),
      tPromotion('filters.courseIdPlaceholder'),
      filters.course_query,
      'compact',
    ),
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
    buildTextItem(
      'keyword',
      tPromotion('filters.keyword'),
      tPromotion('filters.keywordPlaceholder'),
      filters.keyword,
    ),
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
      labelClassName={getOrderFilterLabelClassName()}
      contentClassName={ORDER_FILTER_CONTENT_CLASS}
      collapsedGridClassName={ORDER_FILTER_GRID_CLASS}
      expandedGridClassName={ORDER_FILTER_GRID_CLASS}
      showToggle
    />
  );
}
