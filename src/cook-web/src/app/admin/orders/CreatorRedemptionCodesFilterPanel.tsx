'use client';

import { ChevronDown, ChevronUp } from 'lucide-react';
import { useMemo } from 'react';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import { Button } from '@/components/ui/Button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { cn } from '@/lib/utils';
import {
  FILTER_LABEL_CLASS,
  SINGLE_SELECT_INDICATOR_CLASS,
  SINGLE_SELECT_ITEM_CLASS,
  fromSelectValue,
  toSelectValue,
  type RedemptionCodeFilters,
  type RedemptionFilterItem,
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
      { value: 'ended', label: tPromotion('status.ended') },
    ],
    [t, tPromotion],
  );

  const filterItems: RedemptionFilterItem[] = [
    {
      key: 'name',
      label: tPromotion('filters.name'),
      component: (
        <AdminClearableInput
          value={filters.name}
          onChange={value => onFilterChange('name', value)}
          placeholder={tPromotion('filters.namePlaceholder')}
          clearLabel={t('common.core.close')}
        />
      ),
    },
    {
      key: 'course_query',
      label: tPromotion('filters.courseId'),
      component: (
        <AdminClearableInput
          value={filters.course_query}
          onChange={value => onFilterChange('course_query', value)}
          placeholder={tPromotion('filters.courseIdPlaceholder')}
          clearLabel={t('common.core.close')}
        />
      ),
    },
    {
      key: 'usage_type',
      label: tPromotion('filters.usageType'),
      component: (
        <Select
          value={toSelectValue(filters.usage_type)}
          onValueChange={value =>
            onFilterChange('usage_type', fromSelectValue(value))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue placeholder={tPromotion('filters.usageType')} />
          </SelectTrigger>
          <SelectContent>
            {usageTypeOptions.map(option => (
              <SelectItem
                key={option.value || 'all'}
                value={toSelectValue(option.value)}
                className={SINGLE_SELECT_ITEM_CLASS}
                indicatorClassName={SINGLE_SELECT_INDICATOR_CLASS}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'status',
      label: tPromotion('filters.status'),
      component: (
        <Select
          value={toSelectValue(filters.status)}
          onValueChange={value =>
            onFilterChange('status', fromSelectValue(value))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue placeholder={tPromotion('filters.status')} />
          </SelectTrigger>
          <SelectContent>
            {statusOptions.map(option => (
              <SelectItem
                key={option.value || 'all'}
                value={toSelectValue(option.value)}
                className={SINGLE_SELECT_ITEM_CLASS}
                indicatorClassName={SINGLE_SELECT_INDICATOR_CLASS}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'discount_type',
      label: tPromotion('filters.discountType'),
      component: (
        <Select
          value={toSelectValue(filters.discount_type)}
          onValueChange={value =>
            onFilterChange('discount_type', fromSelectValue(value))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue placeholder={tPromotion('filters.discountType')} />
          </SelectTrigger>
          <SelectContent>
            {discountTypeOptions.map(option => (
              <SelectItem
                key={option.value || 'all'}
                value={toSelectValue(option.value)}
                className={SINGLE_SELECT_ITEM_CLASS}
                indicatorClassName={SINGLE_SELECT_INDICATOR_CLASS}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'date_range',
      label: tPromotion('filters.activeTime'),
      component: (
        <AdminDateRangeFilter
          startValue={filters.start_time}
          endValue={filters.end_time}
          onChange={range => {
            onFilterChange('start_time', range.start);
            onFilterChange('end_time', range.end);
          }}
          placeholder={`${t('module.order.filters.startTime')} ~ ${t(
            'module.order.filters.endTime',
          )}`}
          resetLabel={t('module.order.filters.reset')}
          clearLabel={t('common.core.close')}
        />
      ),
    },
    {
      key: 'keyword',
      label: tPromotion('filters.keyword'),
      component: (
        <AdminClearableInput
          value={filters.keyword}
          onChange={value => onFilterChange('keyword', value)}
          placeholder={tPromotion('filters.keywordPlaceholder')}
          clearLabel={t('common.core.close')}
        />
      ),
    },
  ];
  const visibleFilterItems = expanded ? filterItems : filterItems.slice(0, 4);

  return (
    <div className='w-full bg-white'>
      <div className='grid min-w-0 grid-cols-1 gap-x-7 gap-y-4 xl:grid-cols-4'>
        {visibleFilterItems.map(item => (
          <div
            key={item.key}
            className='flex min-w-0 items-center gap-3 md:[&>span]:text-right'
          >
            <span className={cn(FILTER_LABEL_CLASS, 'w-24')}>{item.label}</span>
            <div className='min-w-0 flex-1'>{item.component}</div>
          </div>
        ))}
      </div>
      <div className='mt-5 flex items-center justify-end'>
        <div className='flex shrink-0 items-center justify-end'>
          <Button
            size='sm'
            type='button'
            variant='outline'
            className='px-4'
            onClick={onReset}
          >
            {t('module.order.filters.reset')}
          </Button>
          <Button
            size='sm'
            type='button'
            className='ml-2 px-4'
            onClick={onSearch}
          >
            {t('module.order.filters.search')}
          </Button>
          <Button
            size='sm'
            type='button'
            variant='ghost'
            className='ml-4 gap-1 px-2 text-[var(--base-foreground,#0A0A0A)] hover:text-[var(--base-foreground,#0A0A0A)]'
            onClick={() => onExpandedChange(!expanded)}
          >
            {expanded ? t('common.core.collapse') : t('common.core.expand')}
            {expanded ? (
              <ChevronUp className='h-4 w-4' />
            ) : (
              <ChevronDown className='h-4 w-4' />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
