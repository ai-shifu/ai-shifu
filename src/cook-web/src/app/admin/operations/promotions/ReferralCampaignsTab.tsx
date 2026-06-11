import React from 'react';
import { Plus } from 'lucide-react';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminRowActions from '@/app/admin/components/AdminRowActions';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import type {
  AdminBillingCampaignProductOptions,
  AdminReferralCampaignItem,
} from '@/app/admin/operations/operation-promotion-types';
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
import { formatBillingCreditAmount } from '@/lib/billing';
import { cn } from '@/lib/utils';
import {
  EMPTY_VALUE,
  type ErrorState,
  REFERRAL_CAMPAIGN_DEFAULT_COLUMN_WIDTHS,
  type ReferralCampaignColumnKey,
  type ReferralCampaignFilters,
  renderPromotionStatusBadge,
  renderTimeRange,
  renderTooltipText,
  resolvePackageCampaignOptionTitle,
  SectionCard,
  shouldShowReferralCampaignStatusToggle,
  TABLE_ACTION_CELL_CLASS,
  TABLE_ACTION_HEAD_CLASS,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
} from './promotionPageShared';

type Translation = (key: string, options?: Record<string, unknown>) => string;

type ReferralCampaignsTabProps = {
  t: Translation;
  tPromotion: Translation;
  filterItems: React.ComponentProps<typeof AdminFilter>['items'];
  filtersExpanded: boolean;
  onFiltersExpandedChange: (expanded: boolean) => void;
  onReset: () => void;
  onSearch: () => void;
  onCreate: () => void;
  error: ErrorState;
  loading: boolean;
  campaigns: AdminReferralCampaignItem[];
  page: number;
  pageCount: number;
  filters: ReferralCampaignFilters;
  fetchCampaigns: (
    pageIndex: number,
    filters: ReferralCampaignFilters,
  ) => Promise<void>;
  productOptions: AdminBillingCampaignProductOptions | null;
  getColumnStyle: (key: ReferralCampaignColumnKey) => React.CSSProperties;
  renderResizeHandle: (key: ReferralCampaignColumnKey) => React.ReactNode;
  onEdit: (item: AdminReferralCampaignItem) => void | Promise<void>;
  onToggleStatus: (item: AdminReferralCampaignItem) => void | Promise<void>;
};

const resolveRewardProductName = (
  t: Translation,
  productOptions: AdminBillingCampaignProductOptions | null,
  productCode: string,
) => {
  const option = (productOptions?.plans || []).find(
    item => item.product_code === productCode,
  );
  return option ? resolvePackageCampaignOptionTitle(t, option) : productCode;
};

const resolveCapLabel = (
  tPromotion: Translation,
  item: AdminReferralCampaignItem,
) => {
  if (item.reward_cap_scope === 'none') {
    return tPromotion('referralCampaign.capScopeNone');
  }
  if (!item.reward_cap_count) {
    return EMPTY_VALUE;
  }
  const scopeKey =
    item.reward_cap_scope === 'per_campaign'
      ? 'referralCampaign.capScopePerCampaign'
      : 'referralCampaign.capScopePerInviter';
  return tPromotion('referralCampaign.capSummary', {
    scope: tPromotion(scopeKey),
    count: item.reward_cap_count,
  });
};

export default function ReferralCampaignsTab({
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
  productOptions,
  getColumnStyle,
  renderResizeHandle,
  onEdit,
  onToggleStatus,
}: ReferralCampaignsTabProps) {
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
            {tPromotion('actions.createReferralCampaign')}
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
          collapsedCount={3}
          className='bg-transparent'
          contentClassName='min-w-0'
          labelClassName='w-24 text-right'
          collapsedGridClassName='gap-x-5 xl:grid-cols-3'
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
        emptyContent={tPromotion('messages.emptyReferralCampaigns')}
        stickyActionEmpty={{
          contentColSpan:
            Object.keys(REFERRAL_CAMPAIGN_DEFAULT_COLUMN_WIDTHS).length - 1,
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
                  {tPromotion('referralCampaign.name')}
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
                  style={getColumnStyle('code')}
                >
                  {tPromotion('referralCampaign.code')}
                  {renderResizeHandle('code')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('rewardProduct')}
                >
                  {tPromotion('referralCampaign.rewardProduct')}
                  {renderResizeHandle('rewardProduct')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('rewardCredits')}
                >
                  {tPromotion('referralCampaign.rewardCredits')}
                  {renderResizeHandle('rewardCredits')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('rewardValidity')}
                >
                  {tPromotion('referralCampaign.validityDays')}
                  {renderResizeHandle('rewardValidity')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('rewardCap')}
                >
                  {tPromotion('referralCampaign.cap')}
                  {renderResizeHandle('rewardCap')}
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
                  style={getColumnStyle('relationCount')}
                >
                  {tPromotion('referralCampaign.relationCount')}
                  {renderResizeHandle('relationCount')}
                </TableHead>
                <TableHead
                  className={TABLE_HEAD_CLASS}
                  style={getColumnStyle('rewardCount')}
                >
                  {tPromotion('referralCampaign.rewardCount')}
                  {renderResizeHandle('rewardCount')}
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
                    {renderTooltipText(item.campaign_name)}
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
                    style={getColumnStyle('code')}
                  >
                    {renderTooltipText(item.campaign_code)}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('rewardProduct')}
                  >
                    {renderTooltipText(
                      resolveRewardProductName(
                        t,
                        productOptions,
                        item.reward_product_code,
                      ),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('rewardCredits')}
                  >
                    {renderTooltipText(
                      formatBillingCreditAmount(
                        Number(item.reward_credit_amount || 0),
                      ),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('rewardValidity')}
                  >
                    {renderTooltipText(
                      tPromotion('referralCampaign.validityDaysValue', {
                        count: item.reward_credit_validity_days || 0,
                      }),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('rewardCap')}
                  >
                    {renderTooltipText(resolveCapLabel(tPromotion, item))}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('campaignTime')}
                  >
                    {renderTooltipText(
                      renderTimeRange(item.starts_at, item.ends_at),
                    )}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('relationCount')}
                  >
                    {renderTooltipText(String(item.relation_count || 0))}
                  </TableCell>
                  <TableCell
                    className={TABLE_CELL_CLASS}
                    style={getColumnStyle('rewardCount')}
                  >
                    {renderTooltipText(String(item.reward_count || 0))}
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
                              !shouldShowReferralCampaignStatusToggle(item),
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
