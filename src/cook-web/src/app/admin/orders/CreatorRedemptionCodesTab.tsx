'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminRowActions from '@/app/admin/components/AdminRowActions';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type {
  AdminPromotionCouponDetail,
  AdminPromotionCouponCodeItem,
  AdminPromotionCouponItem,
  AdminPromotionCouponUsageItem,
  AdminPromotionListResponse,
} from '@/app/admin/operations/operation-promotion-types';
import {
  PromotionCouponCodesDialog,
  PromotionCouponUsageDialog,
} from '@/app/admin/operations/promotions/PromotionRecordDialogs';
import {
  ALL_OPTION_VALUE,
  downloadExcelCompatibleCodesFile,
  EMPTY_VALUE,
  renderCouponAttentionBadges,
  renderPromotionStatusBadge,
  renderRuleLabel,
  renderTimeRange,
  renderTooltipText,
  resolveCouponUsageTypeLabel,
  shouldShowCouponStatusToggle,
  TABLE_ACTION_CELL_CLASS,
  TABLE_ACTION_HEAD_CLASS,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
} from '@/app/admin/operations/promotions/promotionPageShared';
import PromotionStatusConfirmDialog from '@/app/admin/operations/promotions/PromotionStatusConfirmDialog';
import ErrorDisplay from '@/components/ErrorDisplay';
import { Button } from '@/components/ui/Button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import { showDefaultToast, showErrorToast } from '@/hooks/useToast';
import { cn } from '@/lib/utils';
import CreatorRedemptionCodeDialog from './CreatorRedemptionCodeDialog';

const PAGE_SIZE = 20;
const USAGE_PROGRESS_SEPARATOR = '/';
const SINGLE_SELECT_ITEM_CLASS =
  'pl-3 pr-8 data-[state=checked]:bg-muted data-[state=checked]:text-foreground';
const SINGLE_SELECT_INDICATOR_CLASS = 'left-auto right-2';
const FILTER_LABEL_CLASS =
  'shrink-0 whitespace-nowrap text-[length:var(--text-sm-font-size,14px)] not-italic font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]';

type RedemptionCodeFilters = {
  keyword: string;
  name: string;
  course_query: string;
  usage_type: string;
  discount_type: string;
  status: string;
  start_time: string;
  end_time: string;
};

type RedemptionFilterItem = {
  key: string;
  label: React.ReactNode;
  component: React.ReactNode;
};

const createDefaultFilters = (): RedemptionCodeFilters => ({
  keyword: '',
  name: '',
  course_query: '',
  usage_type: '',
  discount_type: '',
  status: '',
  start_time: '',
  end_time: '',
});

const toSelectValue = (value: string) => value || ALL_OPTION_VALUE;
const fromSelectValue = (value: string) =>
  value === ALL_OPTION_VALUE ? '' : value;

export default function CreatorRedemptionCodesTab({
  reloadKey = 0,
}: {
  reloadKey?: number;
}) {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const currencySymbol = useEnvStore(
    (state: EnvStoreState) => state.currencySymbol,
  );
  const [filters, setFilters] = useState<RedemptionCodeFilters>(() =>
    createDefaultFilters(),
  );
  const filtersRef = useRef<RedemptionCodeFilters>(filters);
  const [expanded, setExpanded] = useState(false);
  const [items, setItems] = useState<AdminPromotionCouponItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ message: string } | null>(null);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(1);
  const [total, setTotal] = useState(0);
  const [usageDialogOpen, setUsageDialogOpen] = useState(false);
  const [codesDialogOpen, setCodesDialogOpen] = useState(false);
  const [selectedCouponBid, setSelectedCouponBid] = useState('');
  const [selectedCouponName, setSelectedCouponName] = useState('');
  const [editingCoupon, setEditingCoupon] =
    useState<AdminPromotionCouponItem | null>(null);
  const [statusTarget, setStatusTarget] =
    useState<AdminPromotionCouponItem | null>(null);
  const [statusSubmitting, setStatusSubmitting] = useState(false);

  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  const fetchCodes = useCallback(
    async (targetPage: number, nextFilters?: RedemptionCodeFilters) => {
      const resolvedFilters = nextFilters ?? filtersRef.current;
      setLoading(true);
      setError(null);
      try {
        const response = (await api.getCreatorCourseRedemptionCodes({
          page_index: targetPage,
          page_size: PAGE_SIZE,
          keyword: resolvedFilters.keyword.trim(),
          name: resolvedFilters.name.trim(),
          course_query: resolvedFilters.course_query.trim(),
          usage_type: resolvedFilters.usage_type,
          discount_type: resolvedFilters.discount_type,
          status: resolvedFilters.status,
          start_time: resolvedFilters.start_time,
          end_time: resolvedFilters.end_time,
        })) as AdminPromotionListResponse<AdminPromotionCouponItem>;

        setItems(response.items || []);
        setPageIndex(response.page || targetPage);
        setPageCount(response.page_count || 1);
        setTotal(response.total || 0);
      } catch (err) {
        setError({
          message:
            err instanceof Error
              ? err.message
              : t('module.order.redemptionCodes.loadFailed'),
        });
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void fetchCodes(1);
  }, [fetchCodes, reloadKey]);

  const handleFilterChange = (
    key: keyof RedemptionCodeFilters,
    value: string,
  ) => {
    setFilters(current => ({ ...current, [key]: value }));
  };

  const handleSearch = () => {
    void fetchCodes(1, filters);
  };

  const handleReset = () => {
    const cleared = createDefaultFilters();
    setFilters(cleared);
    void fetchCodes(1, cleared);
  };

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage > pageCount || nextPage === pageIndex) {
      return;
    }
    void fetchCodes(nextPage);
  };

  const handleOpenUsage = (item: AdminPromotionCouponItem) => {
    setSelectedCouponBid(item.coupon_bid);
    setSelectedCouponName(item.name);
    setUsageDialogOpen(true);
  };

  const handleOpenCodes = (item: AdminPromotionCouponItem) => {
    setSelectedCouponBid(item.coupon_bid);
    setSelectedCouponName(item.name);
    setCodesDialogOpen(true);
  };

  const handleStartEdit = async (item: AdminPromotionCouponItem) => {
    try {
      const detail = (await api.getCreatorCourseRedemptionCodeDetail({
        coupon_bid: item.coupon_bid,
      })) as AdminPromotionCouponDetail;
      setEditingCoupon(detail.coupon || item);
    } catch (err) {
      showErrorToast(
        (err as Error).message || tPromotion('messages.loadCouponDetailFailed'),
      );
    }
  };

  const handleStatusToggle = (item: AdminPromotionCouponItem) => {
    setStatusTarget(item);
  };

  const handleConfirmStatusToggle = async () => {
    if (!statusTarget) {
      return;
    }
    const enabling = statusTarget.computed_status === 'inactive';
    setStatusSubmitting(true);
    try {
      await api.updateCreatorCourseRedemptionCodeStatus({
        coupon_bid: statusTarget.coupon_bid,
        enabled: enabling,
      });
      showDefaultToast(
        enabling
          ? tPromotion('messages.couponEnabledSuccess')
          : tPromotion('messages.couponDisabledSuccess'),
      );
      setStatusTarget(null);
      await fetchCodes(pageIndex, filtersRef.current);
    } catch (err) {
      showErrorToast((err as Error).message || t('common.core.submitFailed'));
    } finally {
      setStatusSubmitting(false);
    }
  };

  const fetchCreatorUsages = useCallback(
    (params: { coupon_bid: string; page_index: number; page_size: number }) =>
      api.getCreatorCourseRedemptionCodeUsages(params) as Promise<
        AdminPromotionListResponse<AdminPromotionCouponUsageItem>
      >,
    [],
  );

  const fetchCreatorSubCodes = useCallback(
    (params: {
      coupon_bid: string;
      page_index: number;
      page_size: number;
      keyword?: string;
    }) =>
      api.getCreatorCourseRedemptionCodeCodes(params) as Promise<
        AdminPromotionListResponse<AdminPromotionCouponCodeItem>
      >,
    [],
  );

  const handleExportCodes = async (item: AdminPromotionCouponItem) => {
    if (Number(item.usage_type) !== 802) {
      return;
    }

    try {
      const allCodes: string[] = [];
      let nextPage = 1;
      let nextPageCount = 1;

      while (nextPage <= nextPageCount) {
        const response = await fetchCreatorSubCodes({
          coupon_bid: item.coupon_bid,
          page_index: nextPage,
          page_size: 100,
        });
        (response.items || []).forEach(codeItem => {
          if (codeItem.code) {
            allCodes.push(codeItem.code);
          }
        });
        nextPageCount = response.page_count || 0;
        nextPage += 1;
      }

      if (!allCodes.length) {
        showDefaultToast(tPromotion('messages.emptyCodes'));
        return;
      }

      const safeBaseName = (item.name || item.coupon_bid || 'coupon-codes')
        .trim()
        .replace(/[\\/:*?"<>|]+/g, '-');
      downloadExcelCompatibleCodesFile(
        `${safeBaseName}.xls`,
        tPromotion('coupon.code'),
        allCodes,
      );
      showDefaultToast(tPromotion('messages.exportSuccess'));
    } catch (err) {
      showErrorToast(
        (err as Error).message || tPromotion('messages.exportFailed'),
      );
    }
  };

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
          onChange={value => handleFilterChange('name', value)}
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
          onChange={value => handleFilterChange('course_query', value)}
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
            handleFilterChange('usage_type', fromSelectValue(value))
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
            handleFilterChange('status', fromSelectValue(value))
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
            handleFilterChange('discount_type', fromSelectValue(value))
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
            handleFilterChange('start_time', range.start);
            handleFilterChange('end_time', range.end);
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
          onChange={value => handleFilterChange('keyword', value)}
          placeholder={tPromotion('filters.keywordPlaceholder')}
          clearLabel={t('common.core.close')}
        />
      ),
    },
  ];
  const visibleFilterItems = expanded ? filterItems : filterItems.slice(0, 4);
  const renderFilterField = (item: RedemptionFilterItem) => (
    <div
      key={item.key}
      className='flex min-w-0 items-center gap-3 md:[&>span]:text-right'
    >
      <span className={cn(FILTER_LABEL_CLASS, 'w-24')}>{item.label}</span>
      <div className='min-w-0 flex-1'>{item.component}</div>
    </div>
  );

  return (
    <div className='flex h-full min-h-0 flex-col gap-5 pb-6'>
      <div className='w-full bg-white'>
        <div className='grid min-w-0 grid-cols-1 gap-x-7 gap-y-4 xl:grid-cols-4'>
          {visibleFilterItems.map(renderFilterField)}
        </div>
        <div className='mt-5 flex items-center justify-end'>
          <div className='flex shrink-0 items-center justify-end'>
            <Button
              size='sm'
              type='button'
              variant='outline'
              className='px-4'
              onClick={handleReset}
            >
              {t('module.order.filters.reset')}
            </Button>
            <Button
              size='sm'
              type='button'
              className='ml-2 px-4'
              onClick={handleSearch}
            >
              {t('module.order.filters.search')}
            </Button>
            <Button
              size='sm'
              type='button'
              variant='ghost'
              className='ml-4 gap-1 px-2 text-[var(--base-foreground,#0A0A0A)] hover:text-[var(--base-foreground,#0A0A0A)]'
              onClick={() => setExpanded(current => !current)}
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

      {error ? (
        <ErrorDisplay
          errorMessage={error.message}
          errorCode={0}
        />
      ) : null}

      <AdminTableShell
        loading={loading}
        isEmpty={items.length === 0}
        emptyContent={t('module.order.redemptionCodes.emptyList')}
        emptyColSpan={11}
        withTooltipProvider
        tableWrapperClassName='max-h-[calc(100vh-23rem)] overflow-auto'
        footnote={t('module.order.redemptionCodes.totalCount', {
          count: total,
        })}
        pagination={{
          pageIndex,
          pageCount,
          onPageChange: handlePageChange,
          prevLabel: t('module.order.paginationPrev'),
          nextLabel: t('module.order.paginationNext'),
          prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
          nextAriaLabel: t('module.order.paginationNextAriaLabel'),
          hideWhenSinglePage: true,
        }}
        table={emptyRow => (
          <Table className='min-w-[1340px] table-fixed'>
            <TableHeader>
              <TableRow>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={{ width: 180 }}
                >
                  {tPromotion('table.name')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={{ width: 200 }}
                >
                  {tPromotion('table.course')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={{ width: 110 }}
                >
                  {tPromotion('table.usageType')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={{ width: 160 }}
                >
                  {tPromotion('coupon.code')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={{ width: 120 }}
                >
                  {tPromotion('table.status')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={{ width: 110 }}
                >
                  {tPromotion('table.usageProgress')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={{ width: 110 }}
                >
                  {tPromotion('table.codesEntry')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={{ width: 120 }}
                >
                  {tPromotion('table.discountRule')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={{ width: 240 }}
                >
                  {tPromotion('table.activeTime')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={{ width: 170 }}
                >
                  {tPromotion('table.createdAt')}
                </TableHead>
                <TableHead
                  className={TABLE_ACTION_HEAD_CLASS}
                  style={{ width: 110 }}
                >
                  {tPromotion('table.actions')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {emptyRow}
              {items.map(item => (
                <TableRow key={item.coupon_bid}>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {renderTooltipText(item.name)}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {renderTooltipText(item.course_name || item.shifu_bid)}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {renderTooltipText(
                      resolveCouponUsageTypeLabel(
                        tPromotion,
                        item.usage_type,
                        item.usage_type_key,
                      ),
                    )}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {renderTooltipText(item.code || EMPTY_VALUE)}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    <div className='flex flex-wrap items-center justify-start gap-1'>
                      {renderPromotionStatusBadge({
                        tPromotion,
                        statusKey: item.computed_status_key,
                        status: item.computed_status,
                      })}
                      {renderCouponAttentionBadges(item, tPromotion)}
                    </div>
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    <button
                      type='button'
                      className='text-primary transition-colors hover:text-primary/80 hover:underline'
                      onClick={() => handleOpenUsage(item)}
                    >
                      {String(Number(item.used_count || 0))}
                      {USAGE_PROGRESS_SEPARATOR}
                      {String(Number(item.total_count || 0))}
                    </button>
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {Number(item.usage_type) === 802 ? (
                      <button
                        type='button'
                        className='text-primary transition-colors hover:text-primary/80 hover:underline'
                        onClick={() => handleOpenCodes(item)}
                      >
                        {tPromotion('table.codesEntry')}
                      </button>
                    ) : (
                      EMPTY_VALUE
                    )}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {renderTooltipText(
                      renderRuleLabel(
                        item.discount_type_key,
                        item.value,
                        currencySymbol || '',
                      ),
                    )}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {renderTooltipText(
                      renderTimeRange(item.start_at, item.end_at),
                    )}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {renderTooltipText(formatAdminUtcDateTime(item.created_at))}
                  </TableCell>
                  <TableCell className={TABLE_ACTION_CELL_CLASS}>
                    <div className='flex justify-start'>
                      <AdminRowActions
                        label={t('common.core.more')}
                        actions={[
                          {
                            key: 'edit',
                            label: tPromotion('actions.edit'),
                            onClick: () => void handleStartEdit(item),
                          },
                          {
                            key: 'export-codes',
                            label: tPromotion('actions.exportCodes'),
                            hidden: Number(item.usage_type) !== 802,
                            onClick: () => void handleExportCodes(item),
                          },
                          {
                            key: 'toggle-status',
                            label:
                              item.computed_status === 'inactive'
                                ? tPromotion('actions.enable')
                                : tPromotion('actions.disable'),
                            hidden: !shouldShowCouponStatusToggle(item),
                            onClick: () => handleStatusToggle(item),
                          },
                        ]}
                      />
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      />
      <PromotionCouponUsageDialog
        open={usageDialogOpen}
        onOpenChange={setUsageDialogOpen}
        couponBid={selectedCouponBid}
        couponName={selectedCouponName}
        showCourseColumn={false}
        fetchUsagesApi={fetchCreatorUsages}
      />
      <PromotionCouponCodesDialog
        open={codesDialogOpen}
        onOpenChange={setCodesDialogOpen}
        couponBid={selectedCouponBid}
        couponName={selectedCouponName}
        fetchCodesApi={fetchCreatorSubCodes}
      />
      <CreatorRedemptionCodeDialog
        open={Boolean(editingCoupon)}
        onOpenChange={open => {
          if (!open) {
            setEditingCoupon(null);
          }
        }}
        coupon={editingCoupon}
        onSuccess={() => fetchCodes(pageIndex, filtersRef.current)}
      />
      <PromotionStatusConfirmDialog
        changeTarget={
          statusTarget
            ? {
                entityType: 'coupon',
                enabling: statusTarget.computed_status === 'inactive',
                item: statusTarget,
              }
            : null
        }
        submitting={statusSubmitting}
        onOpenChange={open => {
          if (!open && !statusSubmitting) {
            setStatusTarget(null);
          }
        }}
        onConfirm={handleConfirmStatusToggle}
      />
    </div>
  );
}
