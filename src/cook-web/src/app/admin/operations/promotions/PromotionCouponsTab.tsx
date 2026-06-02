import React from 'react';
import { Plus } from 'lucide-react';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminRowActions from '@/app/admin/components/AdminRowActions';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type { AdminPromotionCouponItem } from '@/app/admin/operations/operation-promotion-types';
import ErrorDisplay from '@/components/ErrorDisplay';
import { Button } from '@/components/ui/Button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { cn } from '@/lib/utils';
import {
  COUPON_DEFAULT_COLUMN_WIDTHS,
  type CouponColumnKey,
  type CouponFilters,
  EMPTY_VALUE,
  type ErrorState,
  renderCouponAttentionBadges,
  renderPromotionStatusBadge,
  renderRuleLabel,
  renderTimeRange,
  renderTooltipText,
  resolveCouponScopeLabel,
  resolveCouponUsageTypeLabel,
  SectionCard,
  shouldShowCouponStatusToggle,
  TABLE_ACTION_CELL_CLASS,
  TABLE_ACTION_HEAD_CLASS,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
  TABLE_LAST_CELL_CLASS,
} from './promotionPageShared';

type Translation = (key: string) => string;

const USAGE_PROGRESS_SEPARATOR = '/';

type PromotionCouponsTabProps = {
  t: Translation;
  tPromotion: Translation;
  currencySymbol: string;
  filterItems: React.ComponentProps<typeof AdminFilter>['items'];
  filtersExpanded: boolean;
  onFiltersExpandedChange: (expanded: boolean) => void;
  onReset: () => void;
  onSearch: () => void;
  onCreate: () => void;
  error: ErrorState;
  loading: boolean;
  coupons: AdminPromotionCouponItem[];
  page: number;
  pageCount: number;
  filters: CouponFilters;
  fetchCoupons: (pageIndex: number, filters: CouponFilters) => Promise<void>;
  getColumnStyle: (key: CouponColumnKey) => React.CSSProperties;
  renderResizeHandle: (key: CouponColumnKey) => React.ReactNode;
  onOpenUsage: (item: AdminPromotionCouponItem) => void;
  onOpenCodes: (item: AdminPromotionCouponItem) => void;
  onEdit: (item: AdminPromotionCouponItem) => void | Promise<void>;
  onExportCodes: (item: AdminPromotionCouponItem) => void | Promise<void>;
  onToggleStatus: (item: AdminPromotionCouponItem) => void | Promise<void>;
};

export default function PromotionCouponsTab({
  t,
  tPromotion,
  currencySymbol,
  filterItems,
  filtersExpanded,
  onFiltersExpandedChange,
  onReset,
  onSearch,
  onCreate,
  error,
  loading,
  coupons,
  page,
  pageCount,
  filters,
  fetchCoupons,
  getColumnStyle,
  renderResizeHandle,
  onOpenUsage,
  onOpenCodes,
  onEdit,
  onExportCodes,
  onToggleStatus,
}: PromotionCouponsTabProps) {
  return (
    <>
      <SectionCard
        title=''
        action={
          <Button
            size='sm'
            variant='outline'
            onClick={onCreate}
          >
            <Plus className='mr-1 h-4 w-4' />
            {tPromotion('actions.createCoupon')}
          </Button>
        }
      >
        <AdminFilter
          items={filterItems}
          expanded={filtersExpanded}
          onExpandedChange={onFiltersExpandedChange}
          onReset={onReset}
          onSearch={onSearch}
          resetLabel={t('module.order.filters.reset')}
          searchLabel={t('module.order.filters.search')}
          expandLabel={t('common.core.expand')}
          collapseLabel={t('common.core.collapse')}
          collapsedCount={4}
          className='bg-transparent'
          contentClassName='min-w-0'
          labelClassName='w-24 text-right'
          collapsedGridClassName='gap-x-5 xl:grid-cols-4'
          expandedGridClassName='gap-x-5 xl:grid-cols-3'
          labelColon
        />
      </SectionCard>
      {error ? (
        <ErrorDisplay
          errorMessage={error.message}
          errorCode={0}
        />
      ) : null}
      <AdminTableShell
        loading={loading}
        isEmpty={!coupons.length}
        emptyContent={tPromotion('messages.emptyCoupons')}
        stickyActionEmpty={{
          contentColSpan: Object.keys(COUPON_DEFAULT_COLUMN_WIDTHS).length - 1,
          actionClassName: TABLE_ACTION_CELL_CLASS,
          actionStyle: getColumnStyle('action'),
        }}
        withTooltipProvider
        tableWrapperClassName='max-h-[calc(100vh-18rem)] overflow-auto'
        table={emptyRow => (
          <Table containerClassName='overflow-visible max-h-none'>
            <TableHeader>
              <TableRow>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('name')}
                >
                  {tPromotion('table.name')}
                  {renderResizeHandle('name')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('status')}
                >
                  {tPromotion('table.status')}
                  {renderResizeHandle('status')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('usageType')}
                >
                  {tPromotion('table.usageType')}
                  {renderResizeHandle('usageType')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('discountRule')}
                >
                  {tPromotion('table.discountRule')}
                  {renderResizeHandle('discountRule')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('code')}
                >
                  {tPromotion('coupon.code')}
                  {renderResizeHandle('code')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('scope')}
                >
                  {tPromotion('table.scope')}
                  {renderResizeHandle('scope')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('course')}
                >
                  {tPromotion('table.course')}
                  {renderResizeHandle('course')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('activeTime')}
                >
                  {tPromotion('table.activeTime')}
                  {renderResizeHandle('activeTime')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('usageProgress')}
                >
                  {tPromotion('table.usageProgress')}
                  {renderResizeHandle('usageProgress')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('codesEntry')}
                >
                  {tPromotion('table.codesEntry')}
                  {renderResizeHandle('codesEntry')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('couponBid')}
                >
                  {tPromotion('table.couponBid')}
                  {renderResizeHandle('couponBid')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('creator')}
                >
                  {tPromotion('coupon.creator')}
                  {renderResizeHandle('creator')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('updatedAt')}
                >
                  {tPromotion('table.updatedAt')}
                  {renderResizeHandle('updatedAt')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('createdAt')}
                >
                  {tPromotion('table.createdAt')}
                  {renderResizeHandle('createdAt')}
                </TableHead>
                <TableHead
                  className={TABLE_ACTION_HEAD_CLASS}
                  style={getColumnStyle('action')}
                >
                  {tPromotion('table.actions')}
                  {renderResizeHandle('action')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {emptyRow}
              {coupons.map(item => (
                <TableRow key={item.coupon_bid}>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('name')}
                  >
                    {renderTooltipText(item.name)}
                  </TableCell>
                  <TableCell
                    className={cn(TABLE_CELL_CLASS, 'whitespace-normal')}
                    style={getColumnStyle('status')}
                  >
                    <div className='flex flex-wrap items-center justify-center gap-1'>
                      {renderPromotionStatusBadge({
                        tPromotion,
                        statusKey: item.computed_status_key,
                        status: item.computed_status,
                      })}
                      {renderCouponAttentionBadges(item, tPromotion)}
                    </div>
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('usageType')}
                  >
                    {renderTooltipText(
                      resolveCouponUsageTypeLabel(
                        tPromotion,
                        item.usage_type,
                        item.usage_type_key,
                      ),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('discountRule')}
                  >
                    {renderTooltipText(
                      renderRuleLabel(
                        item.discount_type_key,
                        item.value,
                        currencySymbol,
                      ),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('code')}
                  >
                    {renderTooltipText(item.code)}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('scope')}
                  >
                    {renderTooltipText(
                      resolveCouponScopeLabel(tPromotion, item.scope_type),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('course')}
                  >
                    {renderTooltipText(
                      item.course_name ||
                        item.shifu_bid ||
                        tPromotion('scope.allCourses'),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('activeTime')}
                  >
                    {renderTooltipText(
                      renderTimeRange(item.start_at, item.end_at),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('usageProgress')}
                  >
                    <button
                      type='button'
                      className='text-primary transition-colors hover:text-primary/80 hover:underline'
                      onClick={() => onOpenUsage(item)}
                    >
                      {String(item.used_count)}
                      {USAGE_PROGRESS_SEPARATOR}
                      {String(item.total_count)}
                    </button>
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('codesEntry')}
                  >
                    {Number(item.usage_type) === 802 ? (
                      <button
                        type='button'
                        className='text-primary transition-colors hover:text-primary/80 hover:underline'
                        onClick={() => onOpenCodes(item)}
                      >
                        {tPromotion('table.codesEntry')}
                      </button>
                    ) : (
                      EMPTY_VALUE
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('couponBid')}
                  >
                    {renderTooltipText(item.coupon_bid)}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('creator')}
                  >
                    {renderTooltipText(
                      item.created_user_name || item.created_user_bid,
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('updatedAt')}
                  >
                    {renderTooltipText(formatAdminUtcDateTime(item.updated_at))}
                  </TableCell>
                  <TableCell
                    className={TABLE_LAST_CELL_CLASS}
                    style={getColumnStyle('createdAt')}
                  >
                    {renderTooltipText(formatAdminUtcDateTime(item.created_at))}
                  </TableCell>
                  <TableCell
                    className={TABLE_ACTION_CELL_CLASS}
                    style={getColumnStyle('action')}
                  >
                    <div className='flex justify-center'>
                      <AdminRowActions
                        label={t('common.core.more')}
                        actions={[
                          {
                            key: 'edit',
                            label: tPromotion('actions.edit'),
                            onClick: () => void onEdit(item),
                          },
                          {
                            key: 'export-codes',
                            label: tPromotion('actions.exportCodes'),
                            hidden: Number(item.usage_type) !== 802,
                            onClick: () => void onExportCodes(item),
                          },
                          {
                            key: 'toggle-status',
                            label:
                              item.computed_status === 'inactive'
                                ? tPromotion('actions.enable')
                                : tPromotion('actions.disable'),
                            hidden: !shouldShowCouponStatusToggle(item),
                            onClick: () => void onToggleStatus(item),
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
        pagination={{
          pageIndex: page,
          pageCount,
          onPageChange: nextPage => void fetchCoupons(nextPage, filters),
          prevLabel: t('module.order.paginationPrev'),
          nextLabel: t('module.order.paginationNext'),
          prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
          nextAriaLabel: t('module.order.paginationNextAriaLabel'),
          hideWhenSinglePage: true,
        }}
        footerClassName='mt-3'
      />
    </>
  );
}
