'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import ReferralRelationsPanel, {
  formatReferralText,
  REFERRAL_PAGE_SIZE,
  ReferralUserSummary,
} from '@/app/admin/operations/referrals/ReferralRelationsPanel';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { showErrorToast } from '@/hooks/useToast';
import type {
  AdminReferralCampaignInvitationItem,
  AdminReferralCampaignInvitationListResponse,
  AdminReferralListResponse,
} from '@/types/referral';
import {
  EMPTY_VALUE,
  SINGLE_SELECT_ITEM_CLASS,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
  TABLE_LAST_CELL_CLASS,
} from './promotionPageShared';

type InvitationFilters = {
  inviter_user_bid: string;
  invite_code: string;
  status: string;
  start_time: string;
  end_time: string;
};

const ALL_OPTION_VALUE = '__all__';
const INVITE_CODE_STATUS_ACTIVE = 7821;
const INVITE_CODE_STATUS_DISABLED = 7822;
const INVITATION_COLUMN_COUNT = 10;

const createEmptyInvitationFilters = (): InvitationFilters => ({
  inviter_user_bid: '',
  invite_code: '',
  status: '',
  start_time: '',
  end_time: '',
});

const normalizeCount = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) ? value : 0;

export default function ReferralCampaignRecordsDialog({
  open,
  onOpenChange,
  campaignBid,
  campaignName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignBid: string;
  campaignName: string;
}) {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const fetchCampaignRelations = React.useCallback(
    async (params: Record<string, string | number>) =>
      (await api.getAdminOperationPromotionReferralCampaignRelations({
        campaign_bid: campaignBid,
        ...params,
      })) as AdminReferralListResponse,
    [campaignBid],
  );

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-6xl'>
        <DialogHeader>
          <DialogTitle>
            {tPromotion('referralCampaign.records.title')}
          </DialogTitle>
          <DialogDescription className='sr-only'>
            {campaignName || campaignBid}
          </DialogDescription>
        </DialogHeader>
        <div className='flex max-h-[76vh] min-h-0 flex-col overflow-hidden'>
          <div className='mb-4 text-sm text-muted-foreground'>
            {campaignName || campaignBid}
          </div>
          <Tabs
            defaultValue='relations'
            className='flex min-h-0 flex-1 flex-col'
          >
            <TabsList className='h-9 w-fit'>
              <TabsTrigger value='relations'>
                {tPromotion('referralCampaign.records.relationsTab')}
              </TabsTrigger>
              <TabsTrigger value='invitations'>
                {tPromotion('referralCampaign.records.invitationsTab')}
              </TabsTrigger>
            </TabsList>
            <TabsContent
              value='relations'
              className='mt-4 min-h-0 flex-1 space-y-4 overflow-hidden'
            >
              <ReferralRelationsPanel
                key={campaignBid}
                enabled={open && Boolean(campaignBid)}
                fetchListApi={fetchCampaignRelations}
                includeCampaignFilter={false}
                filterSurface='plain'
                tableWrapperClassName='min-h-0 max-h-[44vh] overflow-auto'
              />
            </TabsContent>
            <TabsContent
              value='invitations'
              className='mt-4 min-h-0 flex-1 overflow-hidden'
            >
              <ReferralCampaignInvitationsPanel
                campaignBid={campaignBid}
                enabled={open && Boolean(campaignBid)}
                t={t}
                tPromotion={tPromotion}
              />
            </TabsContent>
          </Tabs>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ReferralCampaignInvitationsPanel({
  campaignBid,
  enabled,
  t,
  tPromotion,
}: {
  campaignBid: string;
  enabled: boolean;
  t: (key: string, values?: Record<string, unknown>) => string;
  tPromotion: (key: string, values?: Record<string, unknown>) => string;
}) {
  const [filters, setFilters] = React.useState<InvitationFilters>(
    createEmptyInvitationFilters,
  );
  const [appliedFilters, setAppliedFilters] = React.useState<InvitationFilters>(
    createEmptyInvitationFilters,
  );
  const [filtersExpanded, setFiltersExpanded] = React.useState(false);
  const [items, setItems] = React.useState<
    AdminReferralCampaignInvitationItem[]
  >([]);
  const [pageIndex, setPageIndex] = React.useState(1);
  const [pageCount, setPageCount] = React.useState(1);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(false);

  const fetchInvitations = React.useCallback(
    async (nextPageIndex = pageIndex) => {
      if (!enabled || !campaignBid) {
        return;
      }
      setLoading(true);
      try {
        const params: Record<string, string | number> = {
          campaign_bid: campaignBid,
          page_index: nextPageIndex,
          page_size: REFERRAL_PAGE_SIZE,
        };
        Object.entries(appliedFilters).forEach(([key, value]) => {
          if (value) {
            params[key] = value;
          }
        });
        const response =
          (await api.getAdminOperationPromotionReferralCampaignInvitations(
            params,
          )) as AdminReferralCampaignInvitationListResponse;
        setItems(response.items || []);
        setTotal(normalizeCount(response.total));
        setPageIndex(response.page_index || nextPageIndex);
        setPageCount(Math.max(1, normalizeCount(response.page_count) || 1));
      } catch (error) {
        setItems([]);
        setTotal(0);
        setPageCount(1);
        showErrorToast(
          (error as Error).message ||
            tPromotion('messages.loadReferralCampaignRecordsFailed'),
        );
      } finally {
        setLoading(false);
      }
    },
    [appliedFilters, campaignBid, enabled, pageIndex, tPromotion],
  );

  React.useEffect(() => {
    void fetchInvitations(pageIndex);
  }, [fetchInvitations, pageIndex]);

  const applySearch = () => {
    setPageIndex(1);
    setAppliedFilters({ ...filters });
  };

  const resetSearch = () => {
    const next = createEmptyInvitationFilters();
    setFilters(next);
    setAppliedFilters(next);
    setPageIndex(1);
  };

  const filterItems = [
    {
      key: 'inviter_user_bid',
      label: tPromotion('referralCampaign.records.inviterUserBid'),
      component: (
        <AdminClearableInput
          value={filters.inviter_user_bid}
          placeholder={tPromotion('referralCampaign.records.inviterUserBid')}
          onChange={value =>
            setFilters(current => ({ ...current, inviter_user_bid: value }))
          }
          clearLabel={t('common.core.close')}
        />
      ),
    },
    {
      key: 'invite_code',
      label: tPromotion('referralCampaign.records.inviteCode'),
      component: (
        <AdminClearableInput
          value={filters.invite_code}
          placeholder={tPromotion('referralCampaign.records.inviteCode')}
          onChange={value =>
            setFilters(current => ({ ...current, invite_code: value }))
          }
          clearLabel={t('common.core.close')}
        />
      ),
    },
    {
      key: 'status',
      label: tPromotion('referralCampaign.records.inviteCodeStatus'),
      component: (
        <Select
          value={filters.status || ALL_OPTION_VALUE}
          onValueChange={value =>
            setFilters(current => ({
              ...current,
              status: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              value={ALL_OPTION_VALUE}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {t('common.core.all')}
            </SelectItem>
            <SelectItem
              value={String(INVITE_CODE_STATUS_ACTIVE)}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('referralCampaign.records.inviteCodeStatusActive')}
            </SelectItem>
            <SelectItem
              value={String(INVITE_CODE_STATUS_DISABLED)}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {tPromotion('referralCampaign.records.inviteCodeStatusDisabled')}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'generated_at',
      label: tPromotion('referralCampaign.records.generatedAt'),
      component: (
        <AdminDateRangeFilter
          startValue={filters.start_time}
          endValue={filters.end_time}
          onChange={range =>
            setFilters(current => ({
              ...current,
              start_time: range.start,
              end_time: range.end,
            }))
          }
          placeholder={tPromotion('referralCampaign.records.generatedAt')}
          resetLabel={t('module.order.filters.reset')}
          clearLabel={t('common.core.close')}
        />
      ),
    },
  ];

  return (
    <div className='flex min-h-0 flex-col space-y-4'>
      <AdminFilter
        items={filterItems}
        expanded={filtersExpanded}
        onExpandedChange={setFiltersExpanded}
        onReset={resetSearch}
        onSearch={applySearch}
        resetLabel={t('module.order.filters.reset')}
        searchLabel={t('module.order.filters.search')}
        expandLabel={t('common.core.expand')}
        collapseLabel={t('common.core.collapse')}
        collapsedCount={3}
        surface='plain'
        layoutPreset='operations'
      />
      <AdminTableShell
        loading={loading}
        isEmpty={!items.length}
        emptyContent={tPromotion('messages.emptyReferralCampaignRecords')}
        emptyColSpan={INVITATION_COLUMN_COUNT}
        withTooltipProvider
        tableWrapperClassName='min-h-0 max-h-[44vh] overflow-auto'
        table={emptyRow => (
          <Table containerClassName='overflow-visible max-h-none'>
            <TableHeader>
              <TableRow>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {tPromotion('referralCampaign.records.inviteCode')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {tPromotion('referralCampaign.records.inviter')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {tPromotion('referralCampaign.records.generatedAt')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {tPromotion('referralCampaign.records.linkClicked')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {tPromotion('referralCampaign.records.pageViewed')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {tPromotion('referralCampaign.records.codeEntered')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {tPromotion('referralCampaign.records.submitted')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {tPromotion('referralCampaign.records.successfulRelations')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {tPromotion('referralCampaign.records.totalEvents')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {tPromotion('referralCampaign.records.latestEventAt')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {emptyRow}
              {items.map(item => (
                <TableRow key={item.invite_code_bid || item.invite_code}>
                  <TableCell className={`${TABLE_CELL_CLASS} font-mono`}>
                    {formatReferralText(item.invite_code)}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    <ReferralUserSummary
                      userBid={item.inviter_user_bid}
                      identifier={item.inviter?.identifier}
                    />
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {formatAdminUtcDateTime(item.generated_at || '') ||
                      EMPTY_VALUE}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {item.link_clicked_count}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {item.registration_page_viewed_count}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {item.code_entered_count}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {item.registration_submitted_count}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {item.successful_relation_count}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {item.total_event_count}
                  </TableCell>
                  <TableCell className={TABLE_LAST_CELL_CLASS}>
                    {formatAdminUtcDateTime(item.latest_event_at || '') ||
                      EMPTY_VALUE}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        footnote={tPromotion('referralCampaign.records.total', { total })}
        pagination={{
          pageIndex,
          pageCount,
          onPageChange: setPageIndex,
          prevLabel: t('module.order.paginationPrev'),
          nextLabel: t('module.order.paginationNext'),
          prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
          nextAriaLabel: t('module.order.paginationNextAriaLabel'),
          hideWhenSinglePage: true,
        }}
        footerClassName='mt-3'
      />
    </div>
  );
}
