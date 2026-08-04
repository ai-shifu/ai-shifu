import React from 'react';
import { Plus } from 'lucide-react';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminRowActions from '@/app/admin/components/AdminRowActions';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type { AdminBillingCampaignItem } from '@/app/admin/operations/operation-promotion-types';
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
  type ErrorState,
  PACKAGE_CAMPAIGN_DEFAULT_COLUMN_WIDTHS,
  type PackageCampaignColumnKey,
  type PackageCampaignFilters,
  renderPromotionStatusBadge,
  renderTimeRange,
  renderTooltipText,
  resolvePackageCampaignBenefitTypeLabel,
  resolvePackageCampaignProductSummary,
  resolvePackageCampaignProductTypeLabel,
  resolvePackageCampaignRuleLabel,
  SectionCard,
  shouldShowPackageCampaignStatusToggle,
  TABLE_ACTION_CELL_CLASS,
  TABLE_ACTION_HEAD_CLASS,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
} from './promotionPageShared';

type Translation = (key: string) => string;

type PackageCampaignsTabProps = {
  t: Translation;
  tPromotion: Translation;
  filterItems: React.ComponentProps<typeof AdminFilter>['items'];
  filtersExpanded: boolean;
  onFiltersExpandedChange: (expanded: boolean) => void;
  onReset: () => void;
  onSearch: () => void;
  onCreate: () => void | Promise<void>;
  error: ErrorState;
  loading: boolean;
  campaigns: AdminBillingCampaignItem[];
  page: number;
  pageCount: number;
  filters: PackageCampaignFilters;
  fetchCampaigns: (
    pageIndex: number,
    filters: PackageCampaignFilters,
  ) => Promise<void>;
  getColumnStyle: (key: PackageCampaignColumnKey) => React.CSSProperties;
  renderResizeHandle: (key: PackageCampaignColumnKey) => React.ReactNode;
  onOpenProductDetails: (item: AdminBillingCampaignItem) => void;
  onEdit: (item: AdminBillingCampaignItem) => void | Promise<void>;
  onToggleStatus: (item: AdminBillingCampaignItem) => void | Promise<void>;
};

export default function PackageCampaignsTab({
  t,
  tPromotion,
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
  onOpenProductDetails,
  onEdit,
  onToggleStatus,
}: PackageCampaignsTabProps) {
  return (
    <>
      <SectionCard
        title=''
        action={
          <Button
            size='sm'
            variant='outline'
            onClick={() => void onCreate()}
          >
            <Plus className='mr-1 h-4 w-4' />
            {tPromotion('actions.createPackageCampaign')}
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
        emptyContent={tPromotion('messages.emptyPackageCampaigns')}
        stickyActionEmpty={{
          contentColSpan:
            Object.keys(PACKAGE_CAMPAIGN_DEFAULT_COLUMN_WIDTHS).length - 1,
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
                  {tPromotion('packageCampaign.name')}
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
                  style={getColumnStyle('products')}
                >
                  {tPromotion('packageCampaign.products')}
                  {renderResizeHandle('products')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('rule')}
                >
                  {tPromotion('packageCampaign.rule')}
                  {renderResizeHandle('rule')}
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
                  style={getColumnStyle('benefitType')}
                >
                  {tPromotion('packageCampaign.benefitType')}
                  {renderResizeHandle('benefitType')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('productType')}
                >
                  {tPromotion('packageCampaign.productType')}
                  {renderResizeHandle('productType')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('hitOrderCount')}
                >
                  {tPromotion('packageCampaign.hitOrderCount')}
                  {renderResizeHandle('hitOrderCount')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('updatedAt')}
                >
                  {tPromotion('table.updatedAt')}
                  {renderResizeHandle('updatedAt')}
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
                <TableRow key={item.campaign_bid}>
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
                        status: item.computed_status,
                      })}
                    </div>
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('products')}
                  >
                    <Button
                      type='button'
                      variant='link'
                      className='h-auto max-w-full justify-start p-0 text-left font-normal'
                      onClick={() => onOpenProductDetails(item)}
                    >
                      {renderTooltipText(
                        resolvePackageCampaignProductSummary(tPromotion, item),
                      )}
                    </Button>
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('rule')}
                  >
                    {renderTooltipText(
                      resolvePackageCampaignRuleLabel(t, item),
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
                    style={getColumnStyle('benefitType')}
                  >
                    {renderTooltipText(
                      resolvePackageCampaignBenefitTypeLabel(
                        tPromotion,
                        item.benefit_type,
                      ),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('productType')}
                  >
                    {renderTooltipText(
                      resolvePackageCampaignProductTypeLabel(
                        tPromotion,
                        item.product_types[0],
                      ),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('hitOrderCount')}
                  >
                    {renderTooltipText(String(item.hit_order_count || 0))}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('updatedAt')}
                  >
                    {renderTooltipText(formatAdminUtcDateTime(item.updated_at))}
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
                            hidden:
                              !shouldShowPackageCampaignStatusToggle(item),
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
