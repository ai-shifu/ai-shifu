'use client';

import React from 'react';
import { Eye } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import {
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import { Label } from '@/components/ui/Label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { Textarea } from '@/components/ui/Textarea';
import { toast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import type {
  AdminReferralListResponse,
  AdminReferralRelation,
  AdminReferralRewardQueueItem,
  AdminReferralStatusPayload,
} from '@/types/referral';
import {
  REFERRAL_ABNORMAL_STATUS,
  REFERRAL_RELATION_STATUS,
  REFERRAL_REWARD_STATUS,
} from '@/types/referral';

export const REFERRAL_PAGE_SIZE = 20;
const ALL_OPTION_VALUE = '__all__';
const SINGLE_SELECT_ITEM_CLASS =
  'pl-3 data-[state=checked]:bg-muted data-[state=checked]:text-foreground [&>span:first-child]:hidden';
const TABLE_HEAD_CLASS = 'whitespace-nowrap';
const TABLE_CELL_CLASS = 'whitespace-nowrap';
const TABLE_ACTION_HEAD_CLASS = getAdminStickyRightHeaderClass('text-left');
const TABLE_ACTION_CELL_CLASS =
  getAdminStickyRightCellClass('whitespace-nowrap');

export type ReferralFilters = {
  campaign_bid: string;
  inviter_user_bid: string;
  invitee_user_bid: string;
  invite_code: string;
  relation_status: string;
  abnormal_status: string;
  start_time: string;
  end_time: string;
};

type ReferralRelationsFetch = (
  params: Record<string, string | number>,
) => Promise<AdminReferralListResponse>;

type ReferralRelationsPanelProps = {
  fetchListApi?: ReferralRelationsFetch;
  includeCampaignFilter?: boolean;
  enabled?: boolean;
  onStatusUpdated?: () => void | Promise<void>;
  className?: string;
  filterSurface?: 'plain' | 'card';
  tableWrapperClassName?: string;
  showFooterWhenLoading?: boolean;
};

const RELATION_STATUS_KEY_BY_VALUE: Record<number, string> = {
  [REFERRAL_RELATION_STATUS.registered]: 'registered',
  [REFERRAL_RELATION_STATUS.rewardGenerated]: 'rewardGenerated',
  [REFERRAL_RELATION_STATUS.rewardPendingEffective]: 'rewardPendingEffective',
  [REFERRAL_RELATION_STATUS.rewardActive]: 'rewardActive',
  [REFERRAL_RELATION_STATUS.rewardEnded]: 'rewardEnded',
  [REFERRAL_RELATION_STATUS.rewardSkippedCap]: 'rewardSkippedCap',
  [REFERRAL_RELATION_STATUS.abnormalReviewing]: 'abnormalReviewing',
  [REFERRAL_RELATION_STATUS.canceled]: 'canceled',
};

const ABNORMAL_STATUS_KEY_BY_VALUE: Record<number, string> = {
  [REFERRAL_ABNORMAL_STATUS.normal]: 'normal',
  [REFERRAL_ABNORMAL_STATUS.reviewing]: 'reviewing',
  [REFERRAL_ABNORMAL_STATUS.confirmedAbnormal]: 'confirmedAbnormal',
};

const REWARD_STATUS_KEY_BY_VALUE: Record<number, string> = {
  [REFERRAL_REWARD_STATUS.generated]: 'generated',
  [REFERRAL_REWARD_STATUS.pendingEffective]: 'pendingEffective',
  [REFERRAL_REWARD_STATUS.active]: 'active',
  [REFERRAL_REWARD_STATUS.expired]: 'expired',
  [REFERRAL_REWARD_STATUS.frozen]: 'frozen',
  [REFERRAL_REWARD_STATUS.canceled]: 'canceled',
  [REFERRAL_REWARD_STATUS.skippedCap]: 'skippedCap',
};

export const createEmptyReferralFilters = (): ReferralFilters => ({
  campaign_bid: '',
  inviter_user_bid: '',
  invitee_user_bid: '',
  invite_code: '',
  relation_status: '',
  abnormal_status: '',
  start_time: '',
  end_time: '',
});

export const formatReferralText = (value?: string | null) => {
  const normalized = String(value || '').trim();
  return normalized || '-';
};

const normalizeCount = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) ? value : 0;

export function ReferralUserSummary({
  userBid,
  identifier,
}: {
  userBid: string;
  identifier?: string;
}) {
  return (
    <div className='min-w-0'>
      <div className='truncate font-medium'>{formatReferralText(userBid)}</div>
      <div className='truncate text-xs text-muted-foreground'>
        {formatReferralText(identifier)}
      </div>
    </div>
  );
}

export default function ReferralRelationsPanel({
  fetchListApi = api.getAdminOperationReferrals as ReferralRelationsFetch,
  includeCampaignFilter = true,
  enabled = true,
  onStatusUpdated,
  className,
  filterSurface = 'card',
  tableWrapperClassName = 'max-h-[calc(100vh-23rem)] overflow-auto',
  showFooterWhenLoading = false,
}: ReferralRelationsPanelProps) {
  const { t } = useTranslation('module.referral');
  const { t: tCommon } = useTranslation();
  const [filters, setFilters] = React.useState<ReferralFilters>(
    createEmptyReferralFilters,
  );
  const [appliedFilters, setAppliedFilters] = React.useState<ReferralFilters>(
    createEmptyReferralFilters,
  );
  const [filtersExpanded, setFiltersExpanded] = React.useState(false);
  const [items, setItems] = React.useState<AdminReferralRelation[]>([]);
  const [pageIndex, setPageIndex] = React.useState(1);
  const [pageCount, setPageCount] = React.useState(1);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState('');
  const [detail, setDetail] = React.useState<AdminReferralRelation | null>(
    null,
  );
  const [detailOpen, setDetailOpen] = React.useState(false);
  const [detailLoading, setDetailLoading] = React.useState(false);
  const [statusLoading, setStatusLoading] = React.useState(false);
  const [operatorNote, setOperatorNote] = React.useState('');

  const relationStatusLabel = React.useCallback(
    (status: number) =>
      t(`relationStatus.${RELATION_STATUS_KEY_BY_VALUE[status] || 'unknown'}`),
    [t],
  );
  const abnormalStatusLabel = React.useCallback(
    (status: number) =>
      t(`abnormalStatus.${ABNORMAL_STATUS_KEY_BY_VALUE[status] || 'unknown'}`),
    [t],
  );
  const rewardStatusLabel = React.useCallback(
    (status?: number) =>
      t(
        `rewardStatus.${REWARD_STATUS_KEY_BY_VALUE[Number(status)] || 'unknown'}`,
      ),
    [t],
  );

  const buildListParams = React.useCallback(
    (nextPageIndex = pageIndex) => {
      const params: Record<string, string | number> = {
        page_index: nextPageIndex,
        page_size: REFERRAL_PAGE_SIZE,
      };
      Object.entries(appliedFilters).forEach(([key, value]) => {
        if (!includeCampaignFilter && key === 'campaign_bid') {
          return;
        }
        if (value) {
          params[key] = value;
        }
      });
      return params;
    },
    [appliedFilters, includeCampaignFilter, pageIndex],
  );

  const fetchList = React.useCallback(
    async (nextPageIndex = pageIndex) => {
      if (!enabled) {
        return;
      }
      setLoading(true);
      setError('');
      try {
        const response = await fetchListApi(buildListParams(nextPageIndex));
        const nextTotal = normalizeCount(response.total);
        setItems(response.items || []);
        setTotal(nextTotal);
        setPageCount(
          Math.max(
            1,
            normalizeCount(response.page_count) ||
              Math.ceil(nextTotal / REFERRAL_PAGE_SIZE),
          ),
        );
        setPageIndex(response.page_index || nextPageIndex);
      } catch (nextError) {
        const typedError = nextError as ErrorWithCode;
        setError(typedError.message || t('operator.loadFailed'));
        setItems([]);
        setTotal(0);
        setPageCount(1);
      } finally {
        setLoading(false);
      }
    },
    [buildListParams, enabled, fetchListApi, pageIndex, t],
  );

  React.useEffect(() => {
    void fetchList(pageIndex);
  }, [fetchList, pageIndex]);

  const applySearch = () => {
    setPageIndex(1);
    setAppliedFilters({ ...filters });
  };

  const resetSearch = () => {
    const next = createEmptyReferralFilters();
    setFilters(next);
    setAppliedFilters(next);
    setPageIndex(1);
  };

  const openDetail = async (relationBid: string) => {
    setDetailOpen(true);
    setDetailLoading(true);
    setOperatorNote('');
    try {
      const response = (await api.getAdminOperationReferralDetail({
        relation_bid: relationBid,
      })) as AdminReferralRelation;
      setDetail(response);
    } finally {
      setDetailLoading(false);
    }
  };

  const updateStatus = async (payload: AdminReferralStatusPayload) => {
    if (!detail?.relation_bid) {
      return;
    }
    setStatusLoading(true);
    try {
      const response = (await api.updateAdminOperationReferralStatus({
        relation_bid: detail.relation_bid,
        operator_note: operatorNote,
        ...payload,
      })) as AdminReferralRelation;
      setDetail(response);
      setItems(currentItems =>
        currentItems.map(item =>
          item.relation_bid === response.relation_bid ? response : item,
        ),
      );
      await onStatusUpdated?.();
      toast({ title: t('operator.statusUpdated') });
    } finally {
      setStatusLoading(false);
    }
  };

  const filterItems = buildFilterItems({
    t,
    tCommon,
    filters,
    setFilters,
    includeCampaignFilter,
    relationStatusLabel,
    abnormalStatusLabel,
  });

  return (
    <div className={className}>
      <AdminFilter
        items={filterItems}
        expanded={filtersExpanded}
        onExpandedChange={setFiltersExpanded}
        onReset={resetSearch}
        onSearch={applySearch}
        resetLabel={t('operator.actions.reset')}
        searchLabel={t('operator.actions.search')}
        expandLabel={tCommon('common.core.expand')}
        collapseLabel={tCommon('common.core.collapse')}
        collapsedCount={includeCampaignFilter ? 3 : 2}
        surface={filterSurface}
        layoutPreset='operations'
      />
      <AdminTableShell
        loading={loading}
        isEmpty={!items.length}
        emptyContent={t('operator.empty')}
        emptyColSpan={8}
        withTooltipProvider
        tableWrapperClassName={tableWrapperClassName}
        showFooterWhenLoading={showFooterWhenLoading}
        table={emptyRow => (
          <Table containerClassName='overflow-visible max-h-none'>
            <TableHeader>
              <TableRow>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {t('operator.table.campaign')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {t('operator.table.inviter')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {t('operator.table.invitee')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {t('operator.table.inviteCode')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {t('operator.table.relationStatus')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {t('operator.table.rewardStatus')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {t('operator.table.boundAt')}
                </TableHead>
                <TableHead className={TABLE_ACTION_HEAD_CLASS}>
                  {t('operator.table.action')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {emptyRow}
              {items.map(item => (
                <TableRow key={item.relation_bid}>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {formatReferralText(item.campaign_code)}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    <ReferralUserSummary
                      userBid={item.inviter_user_bid}
                      identifier={item.inviter?.identifier}
                    />
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    <ReferralUserSummary
                      userBid={item.invitee_user_bid}
                      identifier={
                        item.invitee_mobile_snapshot || item.invitee?.identifier
                      }
                    />
                  </TableCell>
                  <TableCell className={`${TABLE_CELL_CLASS} font-mono`}>
                    {formatReferralText(item.invite_code)}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {relationStatusLabel(item.relation_status)}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {item.reward
                      ? rewardStatusLabel(item.reward.reward_status)
                      : '-'}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {formatAdminUtcDateTime(item.bound_at || '') ||
                      formatReferralText(item.bound_at)}
                  </TableCell>
                  <TableCell className={TABLE_ACTION_CELL_CLASS}>
                    <Button
                      type='button'
                      variant='ghost'
                      size='sm'
                      className='h-auto justify-start gap-1 p-0 text-left font-normal text-primary hover:bg-transparent'
                      data-testid={`referral-detail-${item.relation_bid}`}
                      onClick={() => void openDetail(item.relation_bid)}
                    >
                      <Eye className='h-4 w-4' />
                      {t('operator.actions.detail')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        footnote={t('operator.total', { total })}
        pagination={{
          pageIndex,
          pageCount,
          onPageChange: setPageIndex,
          prevLabel: t('operator.pagination.prev'),
          nextLabel: t('operator.pagination.next'),
          prevAriaLabel: t('operator.pagination.prevAria'),
          nextAriaLabel: t('operator.pagination.nextAria'),
          jumpInputAriaLabel: t('operator.pagination.jumpInputAria'),
          hideWhenSinglePage: true,
        }}
        footerClassName='mt-4'
      />
      {error ? (
        <div className='mt-3 text-sm text-destructive'>{error}</div>
      ) : null}
      <ReferralDetailSheet
        open={detailOpen}
        onOpenChange={setDetailOpen}
        detail={detail}
        loading={detailLoading}
        statusLoading={statusLoading}
        operatorNote={operatorNote}
        onOperatorNoteChange={setOperatorNote}
        onUpdateStatus={updateStatus}
        relationStatusLabel={relationStatusLabel}
        abnormalStatusLabel={abnormalStatusLabel}
        rewardStatusLabel={rewardStatusLabel}
      />
    </div>
  );
}

function buildFilterItems({
  t,
  tCommon,
  filters,
  setFilters,
  includeCampaignFilter,
  relationStatusLabel,
  abnormalStatusLabel,
}: {
  t: (key: string, values?: Record<string, unknown>) => string;
  tCommon: (key: string, values?: Record<string, unknown>) => string;
  filters: ReferralFilters;
  setFilters: React.Dispatch<React.SetStateAction<ReferralFilters>>;
  includeCampaignFilter: boolean;
  relationStatusLabel: (status: number) => string;
  abnormalStatusLabel: (status: number) => string;
}) {
  const items = [
    includeCampaignFilter
      ? {
          key: 'campaign_bid',
          label: t('operator.filters.campaignBid'),
          component: (
            <AdminClearableInput
              value={filters.campaign_bid}
              placeholder={t('operator.filters.campaignBid')}
              onChange={value =>
                setFilters(current => ({ ...current, campaign_bid: value }))
              }
              clearLabel={tCommon('common.core.close')}
            />
          ),
        }
      : null,
    {
      key: 'inviter_user_bid',
      label: t('operator.filters.inviterUserBid'),
      component: (
        <AdminClearableInput
          value={filters.inviter_user_bid}
          placeholder={t('operator.filters.inviterUserBid')}
          onChange={value =>
            setFilters(current => ({ ...current, inviter_user_bid: value }))
          }
          clearLabel={tCommon('common.core.close')}
        />
      ),
    },
    {
      key: 'invitee_user_bid',
      label: t('operator.filters.inviteeUserBid'),
      component: (
        <AdminClearableInput
          value={filters.invitee_user_bid}
          placeholder={t('operator.filters.inviteeUserBid')}
          onChange={value =>
            setFilters(current => ({ ...current, invitee_user_bid: value }))
          }
          clearLabel={tCommon('common.core.close')}
        />
      ),
    },
    {
      key: 'invite_code',
      label: t('operator.filters.inviteCode'),
      component: (
        <AdminClearableInput
          value={filters.invite_code}
          placeholder={t('operator.filters.inviteCode')}
          onChange={value =>
            setFilters(current => ({ ...current, invite_code: value }))
          }
          clearLabel={tCommon('common.core.close')}
        />
      ),
    },
    {
      key: 'relation_status',
      label: t('operator.filters.relationStatus'),
      component: (
        <Select
          value={filters.relation_status || ALL_OPTION_VALUE}
          onValueChange={value =>
            setFilters(current => ({
              ...current,
              relation_status: value === ALL_OPTION_VALUE ? '' : value,
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
              {t('operator.filters.all')}
            </SelectItem>
            <SelectItem
              value={String(REFERRAL_RELATION_STATUS.rewardGenerated)}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {relationStatusLabel(REFERRAL_RELATION_STATUS.rewardGenerated)}
            </SelectItem>
            <SelectItem
              value={String(REFERRAL_RELATION_STATUS.rewardSkippedCap)}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {relationStatusLabel(REFERRAL_RELATION_STATUS.rewardSkippedCap)}
            </SelectItem>
            <SelectItem
              value={String(REFERRAL_RELATION_STATUS.canceled)}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {relationStatusLabel(REFERRAL_RELATION_STATUS.canceled)}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'abnormal_status',
      label: t('operator.filters.abnormalStatus'),
      component: (
        <Select
          value={filters.abnormal_status || ALL_OPTION_VALUE}
          onValueChange={value =>
            setFilters(current => ({
              ...current,
              abnormal_status: value === ALL_OPTION_VALUE ? '' : value,
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
              {t('operator.filters.all')}
            </SelectItem>
            <SelectItem
              value={String(REFERRAL_ABNORMAL_STATUS.normal)}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {abnormalStatusLabel(REFERRAL_ABNORMAL_STATUS.normal)}
            </SelectItem>
            <SelectItem
              value={String(REFERRAL_ABNORMAL_STATUS.reviewing)}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {abnormalStatusLabel(REFERRAL_ABNORMAL_STATUS.reviewing)}
            </SelectItem>
            <SelectItem
              value={String(REFERRAL_ABNORMAL_STATUS.confirmedAbnormal)}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {abnormalStatusLabel(REFERRAL_ABNORMAL_STATUS.confirmedAbnormal)}
            </SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'bound_at',
      label: t('operator.filters.boundAt'),
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
          placeholder={t('operator.filters.boundAt')}
          resetLabel={t('operator.actions.reset')}
          clearLabel={tCommon('common.core.close')}
        />
      ),
    },
  ];
  return items.filter(Boolean) as React.ComponentProps<
    typeof AdminFilter
  >['items'];
}

function ReferralDetailSheet({
  open,
  onOpenChange,
  detail,
  loading,
  statusLoading,
  operatorNote,
  onOperatorNoteChange,
  onUpdateStatus,
  relationStatusLabel,
  abnormalStatusLabel,
  rewardStatusLabel,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  detail: AdminReferralRelation | null;
  loading: boolean;
  statusLoading: boolean;
  operatorNote: string;
  onOperatorNoteChange: (value: string) => void;
  onUpdateStatus: (payload: AdminReferralStatusPayload) => void | Promise<void>;
  relationStatusLabel: (status: number) => string;
  abnormalStatusLabel: (status: number) => string;
  rewardStatusLabel: (status?: number) => string;
}) {
  const { t } = useTranslation('module.referral');
  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
    >
      <SheetContent className='w-full overflow-y-auto sm:max-w-2xl'>
        <SheetHeader>
          <SheetTitle>{t('operator.detail.title')}</SheetTitle>
          <SheetDescription>
            {detail?.relation_bid || t('operator.detail.loading')}
          </SheetDescription>
        </SheetHeader>
        {loading ? (
          <div className='flex h-40 items-center justify-center'>
            <Loading />
          </div>
        ) : detail ? (
          <div className='mt-6 space-y-5'>
            <DetailGrid
              rows={[
                [t('operator.detail.campaign'), detail.campaign_code],
                [t('operator.detail.inviter'), detail.inviter_user_bid],
                [t('operator.detail.invitee'), detail.invitee_user_bid],
                [
                  t('operator.detail.inviteeMobile'),
                  detail.invitee_mobile_snapshot,
                ],
                [t('operator.detail.inviteCode'), detail.invite_code],
                [
                  t('operator.detail.relationStatus'),
                  relationStatusLabel(detail.relation_status),
                ],
                [
                  t('operator.detail.abnormalStatus'),
                  abnormalStatusLabel(detail.abnormal_status),
                ],
                [
                  t('operator.detail.boundAt'),
                  formatAdminUtcDateTime(detail.bound_at || '') ||
                    formatReferralText(detail.bound_at),
                ],
              ]}
            />

            <DetailGrid
              title={t('operator.detail.reward')}
              rows={[
                [
                  t('operator.detail.rewardBid'),
                  detail.reward?.reward_bid || '-',
                ],
                [
                  t('operator.detail.rewardStatus'),
                  detail.reward
                    ? rewardStatusLabel(detail.reward.reward_status)
                    : '-',
                ],
                [
                  t('operator.detail.rewardProduct'),
                  detail.reward?.reward_product_code || '-',
                ],
                [
                  t('operator.detail.billOrder'),
                  String(
                    detail.reward?.billing_artifacts?.bill_order_bid || '-',
                  ),
                ],
                [
                  t('operator.detail.subscription'),
                  String(
                    detail.reward?.billing_artifacts
                      ?.billing_subscription_bid || '-',
                  ),
                ],
                [
                  t('operator.detail.walletBucket'),
                  String(
                    detail.reward?.billing_artifacts?.wallet_bucket_bid || '-',
                  ),
                ],
                [
                  t('operator.detail.ledger'),
                  String(detail.reward?.billing_artifacts?.ledger_bid || '-'),
                ],
              ]}
            />

            <RewardQueueTable
              items={detail.reward_queue || []}
              rewardStatusLabel={rewardStatusLabel}
            />

            <div className='space-y-2'>
              <Label htmlFor='operator-note'>
                {t('operator.detail.operatorNote')}
              </Label>
              <Textarea
                id='operator-note'
                value={operatorNote}
                onChange={event => onOperatorNoteChange(event.target.value)}
                placeholder={t('operator.detail.operatorNotePlaceholder')}
              />
            </div>
            <div className='grid gap-2 sm:grid-cols-2'>
              <Button
                type='button'
                variant='outline'
                disabled={statusLoading}
                onClick={() =>
                  void onUpdateStatus({ abnormal_status: 'reviewing' })
                }
              >
                {t('operator.actions.markReviewing')}
              </Button>
              <Button
                type='button'
                variant='outline'
                disabled={statusLoading}
                onClick={() =>
                  void onUpdateStatus({ abnormal_status: 'normal' })
                }
              >
                {t('operator.actions.markNormal')}
              </Button>
              <Button
                type='button'
                variant='outline'
                disabled={statusLoading}
                onClick={() =>
                  void onUpdateStatus({
                    relation_status: 'canceled',
                    reward_status: 'canceled',
                  })
                }
              >
                {t('operator.actions.cancelReward')}
              </Button>
              <Button
                type='button'
                variant='outline'
                disabled={statusLoading || !detail.reward}
                onClick={() => void onUpdateStatus({ reward_status: 'frozen' })}
              >
                {t('operator.actions.freezeReward')}
              </Button>
            </div>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function RewardQueueTable({
  items,
  rewardStatusLabel,
}: {
  items: AdminReferralRewardQueueItem[];
  rewardStatusLabel: (status?: number) => string;
}) {
  const { t } = useTranslation('module.referral');
  return (
    <section className='rounded-lg border border-border p-3'>
      <h3 className='mb-3 text-sm font-semibold text-foreground'>
        {t('operator.detail.rewardQueue.title')}
      </h3>
      <div className='overflow-x-auto'>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>
                {t('operator.detail.rewardQueue.columns.index')}
              </TableHead>
              <TableHead>
                {t('operator.detail.rewardQueue.columns.status')}
              </TableHead>
              <TableHead>
                {t('operator.detail.rewardQueue.columns.credits')}
              </TableHead>
              <TableHead>
                {t('operator.detail.rewardQueue.columns.invitee')}
              </TableHead>
              <TableHead>
                {t('operator.detail.rewardQueue.columns.effectiveAt')}
              </TableHead>
              <TableHead>
                {t('operator.detail.rewardQueue.columns.expiresAt')}
              </TableHead>
              <TableHead>
                {t('operator.detail.rewardQueue.columns.ledgerState')}
              </TableHead>
              <TableHead>
                {t('operator.detail.rewardQueue.columns.artifacts')}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length ? (
              items.map(item => (
                <TableRow key={`${item.reward_bid}:${item.queue_index}`}>
                  <TableCell>{item.queue_index}</TableCell>
                  <TableCell>{rewardStatusLabel(item.reward_status)}</TableCell>
                  <TableCell>
                    {formatReferralText(item.reward_credit_amount)}
                  </TableCell>
                  <TableCell>
                    <ReferralUserSummary
                      userBid={item.invitee_user_bid}
                      identifier={item.invitee_mobile_snapshot}
                    />
                  </TableCell>
                  <TableCell>
                    {formatAdminUtcDateTime(item.effective_at || '') ||
                      formatReferralText(item.effective_at)}
                  </TableCell>
                  <TableCell>
                    {formatAdminUtcDateTime(item.expires_at || '') ||
                      formatReferralText(item.expires_at)}
                  </TableCell>
                  <TableCell>
                    {formatReferralText(item.ledger_credit_state)}
                  </TableCell>
                  <TableCell>
                    <div className='space-y-1 text-xs'>
                      <ArtifactLine
                        label={t(
                          'operator.detail.rewardQueue.artifacts.reward',
                        )}
                        value={item.reward_bid}
                      />
                      <ArtifactLine
                        label={t('operator.detail.rewardQueue.artifacts.order')}
                        value={item.bill_order_bid}
                      />
                      <ArtifactLine
                        label={t(
                          'operator.detail.rewardQueue.artifacts.ledger',
                        )}
                        value={item.ledger_bid}
                      />
                    </div>
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={8}
                  className='px-4 py-8 text-center text-sm text-muted-foreground'
                >
                  {t('operator.detail.rewardQueue.empty')}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}

function ArtifactLine({ label, value }: { label: string; value: string }) {
  return (
    <div className='min-w-[160px]'>
      <span className='mr-1 text-muted-foreground'>{label}</span>
      <span className='font-mono text-foreground'>
        {formatReferralText(value)}
      </span>
    </div>
  );
}

function DetailGrid({
  title,
  rows,
}: {
  title?: string;
  rows: Array<[string, string]>;
}) {
  return (
    <section className='rounded-lg border border-border p-3'>
      {title ? (
        <h3 className='mb-3 text-sm font-semibold text-foreground'>{title}</h3>
      ) : null}
      <dl className='grid gap-3 sm:grid-cols-2'>
        {rows.map(([label, value]) => (
          <div
            key={label}
            className='min-w-0'
          >
            <dt className='text-xs text-muted-foreground'>{label}</dt>
            <dd className='mt-1 break-words text-sm text-foreground'>
              {formatReferralText(value)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
