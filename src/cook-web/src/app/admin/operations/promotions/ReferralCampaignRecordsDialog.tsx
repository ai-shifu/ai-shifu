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
import { useEnvStore } from '@/c-store/envStore';
import type { EnvStoreState } from '@/c-types/store';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
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
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
  TABLE_LAST_CELL_CLASS,
} from './promotionPageShared';

type InvitationFilters = {
  inviter_user_bid: string;
  invite_code: string;
  start_time: string;
  end_time: string;
};

export type ReferralCampaignRecordsTab = 'relations' | 'invitations';

const INVITATION_COLUMN_COUNT = 9;

const createEmptyInvitationFilters = (): InvitationFilters => ({
  inviter_user_bid: '',
  invite_code: '',
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
  defaultTab = 'relations',
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignBid: string;
  campaignName: string;
  defaultTab?: ReferralCampaignRecordsTab;
}) {
  const { t } = useTranslation();
  const { t: tPromotion } = useTranslation('module.operationsPromotion');
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const defaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );
  const contactMode = React.useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
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
      <DialogContent className='overflow-hidden p-0 sm:max-w-6xl'>
        <DialogHeader className='border-b border-[var(--base-border,#E5E5E5)] bg-[linear-gradient(180deg,rgba(249,250,251,0.92)_0%,rgba(255,255,255,1)_100%)] px-6 py-3'>
          <DialogTitle>
            {tPromotion('referralCampaign.records.title')}
          </DialogTitle>
          <div className='text-sm text-[var(--base-muted-foreground,#737373)]'>
            {campaignName || campaignBid}
          </div>
          <DialogDescription className='sr-only'>
            {campaignName || campaignBid}
          </DialogDescription>
        </DialogHeader>
        <div className='flex max-h-[78vh] min-h-0 flex-col overflow-hidden px-6 py-2'>
          <Tabs
            key={`${campaignBid}:${defaultTab}`}
            defaultValue={defaultTab}
            className='flex min-h-0 flex-1 flex-col gap-1.5'
          >
            <TabsList className='h-auto w-fit gap-1 rounded-xl bg-[var(--base-muted,#F5F5F5)] p-1'>
              <TabsTrigger
                value='relations'
                className='rounded-lg px-4 py-2 text-sm data-[state=active]:bg-white data-[state=active]:shadow-sm'
              >
                {tPromotion('referralCampaign.records.relationsTab')}
              </TabsTrigger>
              <TabsTrigger
                value='invitations'
                className='rounded-lg px-4 py-2 text-sm data-[state=active]:bg-white data-[state=active]:shadow-sm'
              >
                {tPromotion('referralCampaign.records.invitationsTab')}
              </TabsTrigger>
            </TabsList>
            <TabsContent
              value='relations'
              className='mt-0 min-h-0 flex-1 overflow-hidden rounded-2xl border border-[var(--base-border,#E5E5E5)] bg-white p-4 shadow-sm'
            >
              <ReferralRelationsPanel
                key={campaignBid}
                enabled={open && Boolean(campaignBid)}
                fetchListApi={fetchCampaignRelations}
                includeCampaignFilter={false}
                className='flex min-h-0 h-full flex-col gap-4'
                filterSurface='card'
                tableWrapperClassName='min-h-0 flex-1 overflow-auto'
                showFooterWhenLoading
                expandedGridClassName='gap-x-5 xl:grid-cols-4'
                showDetailAction={false}
                showUserBidSecondary={false}
              />
            </TabsContent>
            <TabsContent
              value='invitations'
              className='mt-0 min-h-0 flex-1 overflow-hidden rounded-2xl border border-[var(--base-border,#E5E5E5)] bg-white p-4 shadow-sm'
            >
              <ReferralCampaignInvitationsPanel
                campaignBid={campaignBid}
                enabled={open && Boolean(campaignBid)}
                contactMode={contactMode}
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
  contactMode,
  t,
  tPromotion,
}: {
  campaignBid: string;
  enabled: boolean;
  contactMode: 'email' | 'phone';
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
  const inviterPlaceholder =
    contactMode === 'email'
      ? tPromotion('referralCampaign.records.inviterEmailPlaceholder')
      : tPromotion('referralCampaign.records.inviterMobilePlaceholder');

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
      label: tPromotion('referralCampaign.records.inviter'),
      component: (
        <AdminClearableInput
          value={filters.inviter_user_bid}
          placeholder={inviterPlaceholder}
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
    <div className='flex min-h-0 h-full flex-col gap-4'>
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
        showToggle={false}
        surface='card'
        layoutPreset='operations'
        className='rounded-2xl'
        contentClassName='max-w-[260px]'
        labelClassName='w-16 text-right'
        collapsedGridClassName='gap-x-5 xl:grid-cols-[repeat(3,minmax(0,240px))]'
        expandedGridClassName='gap-x-5 xl:grid-cols-[repeat(3,minmax(0,240px))]'
      />
      <AdminTableShell
        loading={loading}
        isEmpty={!items.length}
        emptyContent={tPromotion('messages.emptyReferralCampaignRecords')}
        emptyColSpan={INVITATION_COLUMN_COUNT}
        withTooltipProvider
        containerClassName='min-h-0 flex-1'
        tableWrapperClassName='min-h-0 flex-1 overflow-auto'
        showFooterWhenLoading
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
                  {tPromotion('referralCampaign.records.latestEventAt')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {tPromotion('referralCampaign.records.successfulRelations')}
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
                      primaryText={item.inviter?.identifier}
                      fallbackText={item.inviter_user_bid}
                    />
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {formatAdminUtcDateTime(item.generated_at || '') ||
                      EMPTY_VALUE}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {formatAdminUtcDateTime(item.latest_event_at || '') ||
                      EMPTY_VALUE}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {item.successful_relation_count}
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
                  <TableCell className={TABLE_LAST_CELL_CLASS}>
                    {item.registration_submitted_count}
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
