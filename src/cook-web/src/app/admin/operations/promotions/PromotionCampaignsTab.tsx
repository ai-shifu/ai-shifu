import React from 'react';
import { Plus } from 'lucide-react';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminRowActions from '@/app/admin/components/AdminRowActions';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type { AdminPromotionCampaignItem } from '@/app/admin/operations/operation-promotion-types';
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
  CAMPAIGN_DEFAULT_COLUMN_WIDTHS,
  type CampaignColumnKey,
  type CampaignFilters,
  type ErrorState,
  renderPromotionStatusBadge,
  renderRuleLabel,
  renderTimeRange,
  renderTooltipText,
  resolveCampaignApplyTypeLabel,
  SectionCard,
  shouldShowCampaignStatusToggle,
  TABLE_ACTION_CELL_CLASS,
  TABLE_ACTION_HEAD_CLASS,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
  TABLE_LAST_CELL_CLASS,
} from './promotionPageShared';

type Translation = (key: string) => string;

type PromotionCampaignsTabProps = {
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
  campaigns: AdminPromotionCampaignItem[];
  page: number;
  pageCount: number;
  filters: CampaignFilters;
  fetchCampaigns: (
    pageIndex: number,
    filters: CampaignFilters,
  ) => Promise<void>;
  getColumnStyle: (key: CampaignColumnKey) => React.CSSProperties;
  renderResizeHandle: (key: CampaignColumnKey) => React.ReactNode;
  onOpenRedemptions: (promoBid: string, promoName: string) => void;
  onEdit: (item: AdminPromotionCampaignItem) => void | Promise<void>;
  onToggleStatus: (item: AdminPromotionCampaignItem) => void | Promise<void>;
};

export default function PromotionCampaignsTab({
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
  campaigns,
  page,
  pageCount,
  filters,
  fetchCampaigns,
  getColumnStyle,
  renderResizeHandle,
  onOpenRedemptions,
  onEdit,
  onToggleStatus,
}: PromotionCampaignsTabProps) {
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
            {tPromotion('actions.createCampaign')}
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
        isEmpty={!campaigns.length}
        emptyContent={tPromotion('messages.emptyCampaigns')}
        stickyActionEmpty={{
          contentColSpan:
            Object.keys(CAMPAIGN_DEFAULT_COLUMN_WIDTHS).length - 1,
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
                  {tPromotion('table.campaignName')}
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
                  style={getColumnStyle('applyType')}
                >
                  {tPromotion('table.applyType')}
                  {renderResizeHandle('applyType')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('channel')}
                >
                  {tPromotion('table.channel')}
                  {renderResizeHandle('channel')}
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
                  style={getColumnStyle('discountRule')}
                >
                  {tPromotion('table.discountRule')}
                  {renderResizeHandle('discountRule')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('campaignTime')}
                >
                  {tPromotion('filters.campaignTime')}
                  {renderResizeHandle('campaignTime')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('appliedOrderCount')}
                >
                  {tPromotion('table.appliedOrderCount')}
                  {renderResizeHandle('appliedOrderCount')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('promoBid')}
                >
                  {tPromotion('table.promoBid')}
                  {renderResizeHandle('promoBid')}
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
              {campaigns.map(item => (
                <TableRow key={item.promo_bid}>
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
                    </div>
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('applyType')}
                  >
                    {renderTooltipText(
                      resolveCampaignApplyTypeLabel(
                        tPromotion,
                        item.apply_type,
                      ),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('channel')}
                  >
                    {renderTooltipText(item.channel)}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('course')}
                  >
                    {renderTooltipText(item.course_name || item.shifu_bid)}
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
                    style={getColumnStyle('campaignTime')}
                  >
                    {renderTooltipText(
                      renderTimeRange(item.start_at, item.end_at),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('appliedOrderCount')}
                  >
                    <button
                      type='button'
                      className='inline-flex min-w-[2.5rem] items-center justify-center rounded-sm text-sm font-medium text-primary underline-offset-2 transition-colors hover:text-primary/80 hover:underline focus-visible:outline-none'
                      onClick={() =>
                        onOpenRedemptions(item.promo_bid, item.name)
                      }
                      aria-label={`${tPromotion('actions.viewOrders')}: ${item.name || item.promo_bid}`}
                    >
                      {String(item.applied_order_count)}
                    </button>
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('promoBid')}
                  >
                    {renderTooltipText(item.promo_bid)}
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
                            key: 'toggle-status',
                            label:
                              item.computed_status === 'inactive'
                                ? tPromotion('actions.enable')
                                : tPromotion('actions.disable'),
                            hidden: !shouldShowCampaignStatusToggle(item),
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
          onPageChange: nextPage => void fetchCampaigns(nextPage, filters),
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
