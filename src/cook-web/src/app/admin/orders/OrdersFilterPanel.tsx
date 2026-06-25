'use client';

import { useMemo } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminFilter from '@/app/admin/components/AdminFilter';
import {
  createDateRangeFilterItem,
  createSelectFilterItem,
  createTextFilterItem,
} from '@/app/admin/components/adminFilterFieldBuilders';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/Popover';
import { ScrollArea } from '@/components/ui/ScrollArea';
import { cn } from '@/lib/utils';
import type { Shifu } from '@/types/shifu';
import type { OrderFilters } from './ordersPageShared';

const ALL_OPTION_VALUE = '__all__';
const SINGLE_SELECT_ITEM_CLASS =
  'pl-3 data-[state=checked]:bg-muted data-[state=checked]:text-foreground [&>span:first-child]:hidden';

type SelectOption = {
  value: string;
  label: string;
};

type OrdersFilterPanelProps = {
  filters: OrderFilters;
  courses: Shifu[];
  coursesLoading: boolean;
  coursesError: string | null;
  courseSearch: string;
  expanded: boolean;
  userBidPlaceholder: string;
  statusOptions: SelectOption[];
  channelOptions: SelectOption[];
  contentClassName: string;
  expandedLabelClassName: string;
  onCourseSearchChange: (value: string) => void;
  onExpandedChange: (expanded: boolean) => void;
  onFilterChange: (
    key: Exclude<keyof OrderFilters, 'shifu_bids'>,
    value: string,
  ) => void;
  onCourseToggle: (courseBid: string) => void;
  onReset: () => void;
  onSearch: () => void;
};

export default function OrdersFilterPanel({
  filters,
  courses,
  coursesLoading,
  coursesError,
  courseSearch,
  expanded,
  userBidPlaceholder,
  statusOptions,
  channelOptions,
  contentClassName,
  expandedLabelClassName,
  onCourseSearchChange,
  onExpandedChange,
  onFilterChange,
  onCourseToggle,
  onReset,
  onSearch,
}: OrdersFilterPanelProps) {
  const { t } = useTranslation();
  const displayStatusValue = filters.status || ALL_OPTION_VALUE;
  const displayChannelValue = filters.payment_channel || ALL_OPTION_VALUE;

  const courseNameMap = useMemo(() => {
    const map = new Map<string, string>();
    courses.forEach(course => {
      if (!course.bid) {
        return;
      }
      map.set(course.bid, course.name || course.bid);
    });
    return map;
  }, [courses]);

  const selectedCourseNames = useMemo(
    () => filters.shifu_bids.map(bid => courseNameMap.get(bid) || bid),
    [courseNameMap, filters.shifu_bids],
  );

  const selectedCourseLabel = useMemo(() => {
    if (selectedCourseNames.length === 0) {
      return t('module.order.filters.shifuBid');
    }
    if (selectedCourseNames.length <= 2) {
      return selectedCourseNames.join(', ');
    }
    const shortList = selectedCourseNames.slice(0, 2).join(', ');
    return `${shortList} +${selectedCourseNames.length - 2}`;
  }, [selectedCourseNames, t]);

  const filteredCourses = useMemo(() => {
    const keyword = courseSearch.trim().toLowerCase();
    if (!keyword) {
      return courses;
    }
    return courses.filter(course => {
      const name = (course.name || '').toLowerCase();
      const bid = (course.bid || '').toLowerCase();
      const matchesName = name.includes(keyword);
      const matchesBid = Boolean(bid && bid === keyword);
      return matchesName || matchesBid;
    });
  }, [courseSearch, courses]);

  const filterItems = [
    createTextFilterItem({
      key: 'user_bid',
      label: userBidPlaceholder,
      value: filters.user_bid,
      onChange: value => onFilterChange('user_bid', value),
      placeholder: userBidPlaceholder,
      clearLabel: t('common.core.close'),
    }),
    {
      key: 'shifu_bids',
      label: t('module.order.filters.shifuBid'),
      component: (
        <Popover>
          <PopoverTrigger asChild>
            <Button
              size='sm'
              variant='outline'
              type='button'
              className='h-9 w-full justify-between font-normal'
              title={selectedCourseNames.join(', ')}
            >
              <span
                className={cn(
                  'flex-1 truncate text-left',
                  filters.shifu_bids.length === 0
                    ? 'text-muted-foreground'
                    : 'text-foreground',
                )}
              >
                {selectedCourseLabel}
              </span>
              <ChevronDown className='h-4 w-4 text-muted-foreground' />
            </Button>
          </PopoverTrigger>
          <PopoverContent
            align='start'
            className='p-3'
            style={{
              width: 'var(--radix-popover-trigger-width)',
              maxWidth: 'var(--radix-popover-trigger-width)',
            }}
          >
            <AdminClearableInput
              value={courseSearch}
              onChange={onCourseSearchChange}
              placeholder={t('module.order.filters.searchCourseOrId')}
              clearLabel={t('common.core.close')}
            />
            <ScrollArea className='mt-3 h-48'>
              {coursesLoading ? (
                <div className='flex items-center justify-center py-4'>
                  <Loading className='h-5 w-5' />
                </div>
              ) : coursesError ? (
                <div className='px-2 py-3 text-xs text-destructive'>
                  {coursesError}
                </div>
              ) : filteredCourses.length === 0 ? (
                <div className='px-2 py-3 text-xs text-muted-foreground'>
                  {t('common.core.noShifus')}
                </div>
              ) : (
                <div className='space-y-1'>
                  {filteredCourses.map(course => {
                    const isSelected = filters.shifu_bids.includes(course.bid);
                    const courseName = course.name || course.bid;
                    return (
                      <button
                        key={course.bid}
                        type='button'
                        onClick={() => onCourseToggle(course.bid)}
                        className='flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent'
                        aria-pressed={isSelected}
                      >
                        <span
                          className={cn(
                            'mt-0.5 flex h-4 w-4 items-center justify-center rounded border',
                            isSelected
                              ? 'border-primary bg-primary text-primary-foreground'
                              : 'border-muted-foreground/40 text-transparent',
                          )}
                        >
                          <Check className='h-3 w-3' />
                        </span>
                        <span className='flex min-w-0 flex-col'>
                          <span className='truncate text-sm text-foreground'>
                            {courseName}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </ScrollArea>
          </PopoverContent>
        </Popover>
      ),
    },
    createSelectFilterItem({
      key: 'status',
      label: t('module.order.filters.status'),
      value: displayStatusValue,
      onChange: value =>
        onFilterChange('status', value === ALL_OPTION_VALUE ? '' : value),
      placeholder: t('module.order.filters.status'),
      options: statusOptions.map(option => ({
        value: option.value || ALL_OPTION_VALUE,
        label: option.label,
      })),
      selectItemClassName: SINGLE_SELECT_ITEM_CLASS,
    }),
    createSelectFilterItem({
      key: 'payment_channel',
      label: t('module.order.filters.channel'),
      value: displayChannelValue,
      onChange: value =>
        onFilterChange(
          'payment_channel',
          value === ALL_OPTION_VALUE ? '' : value,
        ),
      placeholder: t('module.order.filters.channel'),
      options: channelOptions.map(option => ({
        value: option.value || ALL_OPTION_VALUE,
        label: option.label,
      })),
      selectItemClassName: SINGLE_SELECT_ITEM_CLASS,
    }),
    createDateRangeFilterItem({
      key: 'date_range',
      label: t('module.order.table.createdAt'),
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
      key: 'order_bid',
      label: t('module.order.filters.orderBid'),
      value: filters.order_bid,
      onChange: value => onFilterChange('order_bid', value),
      placeholder: t('module.order.filters.orderBid'),
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
      collapsedCount={3}
      contentClassName={contentClassName}
      expandedLabelClassName={expandedLabelClassName}
    />
  );
}
