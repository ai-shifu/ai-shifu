'use client';

import AdminRowActions from '@/app/admin/components/AdminRowActions';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type { AdminPromotionCouponItem } from '@/app/admin/operations/operation-promotion-types';
import {
  EMPTY_VALUE,
  renderCouponAttentionBadges,
  renderPromotionStatusBadge,
  renderRuleLabel,
  renderTimeRange,
  renderTooltipText,
  resolveCouponUsageTypeLabel,
  TABLE_ACTION_CELL_CLASS,
  TABLE_ACTION_HEAD_CLASS,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
} from '@/app/admin/operations/promotions/promotionPageShared';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import {
  buildCreatorRedemptionRowActions,
  getCreatorRedemptionCodeDisplayCode,
  getCreatorRedemptionUsageProgress,
  shouldShowCreatorRedemptionCodesEntry,
} from './creatorRedemptionCodeViewModel';

type TranslationFn = (key: string, options?: Record<string, unknown>) => string;

export default function CreatorRedemptionCodesTable({
  currencySymbol,
  hasError,
  items,
  loading,
  onEdit,
  onExportCodes,
  onOpenCodes,
  onOpenUsage,
  onPageChange,
  onToggleStatus,
  pageCount,
  pageIndex,
  t,
  tPromotion,
  total,
}: {
  currencySymbol: string;
  hasError: boolean;
  items: AdminPromotionCouponItem[];
  loading: boolean;
  onEdit: (item: AdminPromotionCouponItem) => void;
  onExportCodes: (item: AdminPromotionCouponItem) => void;
  onOpenCodes: (item: AdminPromotionCouponItem) => void;
  onOpenUsage: (item: AdminPromotionCouponItem) => void;
  onPageChange: (page: number) => void;
  onToggleStatus: (item: AdminPromotionCouponItem) => void;
  pageCount: number;
  pageIndex: number;
  t: TranslationFn;
  tPromotion: TranslationFn;
  total: number;
}) {
  return (
    <AdminTableShell
      loading={loading}
      isEmpty={!loading && !hasError && items.length === 0}
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
        onPageChange,
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
                  {renderTooltipText(getCreatorRedemptionCodeDisplayCode(item))}
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
                    onClick={() => onOpenUsage(item)}
                  >
                    {getCreatorRedemptionUsageProgress(item)}
                  </button>
                </TableCell>
                <TableCell className={TABLE_CELL_CLASS}>
                  {shouldShowCreatorRedemptionCodesEntry(item) ? (
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
                      actions={buildCreatorRedemptionRowActions({
                        item,
                        onEdit,
                        onExportCodes,
                        onToggleStatus,
                        tPromotion,
                      })}
                    />
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    />
  );
}
