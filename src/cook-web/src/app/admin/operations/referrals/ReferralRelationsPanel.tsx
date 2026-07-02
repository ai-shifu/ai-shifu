'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { useEnvStore } from '@/c-store/envStore';
import type { EnvStoreState } from '@/c-types/store';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { ErrorWithCode } from '@/lib/request';
import type {
  AdminReferralListResponse,
  AdminReferralRelation,
} from '@/types/referral';
import {
  REFERRAL_RELATION_STATUS,
  REFERRAL_REWARD_STATUS,
} from '@/types/referral';

export const REFERRAL_PAGE_SIZE = 20;
const ALL_OPTION_VALUE = '__all__';
const SINGLE_SELECT_ITEM_CLASS =
  'pl-3 data-[state=checked]:bg-muted data-[state=checked]:text-foreground [&>span:first-child]:hidden';
const TABLE_HEAD_CLASS = 'whitespace-nowrap';
const TABLE_CELL_CLASS = 'whitespace-nowrap';

export type ReferralFilters = {
  campaign_bid: string;
  inviter_user_bid: string;
  invitee_user_bid: string;
  invite_code: string;
  relation_status: string;
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
  refreshToken?: number;
  className?: string;
  filterSurface?: 'plain' | 'card';
  tableWrapperClassName?: string;
  showFooterWhenLoading?: boolean;
  expandedGridClassName?: string;
  showUserBidSecondary?: boolean;
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

const REWARD_STATUS_KEY_BY_VALUE: Record<number, string> = {
  [REFERRAL_REWARD_STATUS.generated]: 'generated',
  [REFERRAL_REWARD_STATUS.pendingEffective]: 'pendingEffective',
  [REFERRAL_REWARD_STATUS.active]: 'active',
  [REFERRAL_REWARD_STATUS.expired]: 'expired',
  [REFERRAL_REWARD_STATUS.frozen]: 'frozen',
  [REFERRAL_REWARD_STATUS.canceled]: 'canceled',
  [REFERRAL_REWARD_STATUS.skippedCap]: 'skippedCap',
};

/*
 * Translation usage markers for scripts/check_translation_usage.py:
 * t('module.referral.relationStatus.abnormalReviewing')
 * t('module.referral.relationStatus.canceled')
 * t('module.referral.relationStatus.registered')
 * t('module.referral.relationStatus.rewardActive')
 * t('module.referral.relationStatus.rewardEnded')
 * t('module.referral.relationStatus.rewardGenerated')
 * t('module.referral.relationStatus.rewardPendingEffective')
 * t('module.referral.relationStatus.rewardSkippedCap')
 * t('module.referral.relationStatus.unknown')
 * t('module.referral.rewardStatus.active')
 * t('module.referral.rewardStatus.canceled')
 * t('module.referral.rewardStatus.expired')
 * t('module.referral.rewardStatus.frozen')
 * t('module.referral.rewardStatus.generated')
 * t('module.referral.rewardStatus.pendingEffective')
 * t('module.referral.rewardStatus.skippedCap')
 * t('module.referral.rewardStatus.unknown')
 */

export const createEmptyReferralFilters = (): ReferralFilters => ({
  campaign_bid: '',
  inviter_user_bid: '',
  invitee_user_bid: '',
  invite_code: '',
  relation_status: '',
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
  primaryText,
  fallbackText,
  secondaryText,
}: {
  primaryText?: string | null;
  fallbackText?: string | null;
  secondaryText?: string | null;
}) {
  const primary = formatReferralText(primaryText || fallbackText);
  const secondary = secondaryText ? formatReferralText(secondaryText) : '';

  return (
    <div className='min-w-0'>
      <div className='truncate font-medium'>{primary}</div>
      {secondary ? (
        <div className='truncate text-xs text-muted-foreground'>
          {secondary}
        </div>
      ) : null}
    </div>
  );
}

export default function ReferralRelationsPanel({
  fetchListApi = api.getAdminOperationReferrals as ReferralRelationsFetch,
  includeCampaignFilter = true,
  enabled = true,
  refreshToken = 0,
  className,
  filterSurface = 'card',
  tableWrapperClassName = 'max-h-[calc(100vh-23rem)] overflow-auto',
  showFooterWhenLoading = false,
  expandedGridClassName,
  showUserBidSecondary = true,
}: ReferralRelationsPanelProps) {
  const { t } = useTranslation('module.referral');
  const { t: tCommon } = useTranslation();
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

  const relationStatusLabel = React.useCallback(
    (status: number) =>
      t(`relationStatus.${RELATION_STATUS_KEY_BY_VALUE[status] || 'unknown'}`),
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
  }, [fetchList, pageIndex, refreshToken]);

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

  const filterItems = buildFilterItems({
    t,
    tCommon,
    filters,
    setFilters,
    includeCampaignFilter,
    relationStatusLabel,
    contactMode,
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
        collapsedCount={includeCampaignFilter ? 3 : 3}
        surface={filterSurface}
        layoutPreset='operations'
        expandedGridClassName={expandedGridClassName}
        expandedActionsInline
        expandedActionsClassName={
          includeCampaignFilter ? 'xl:col-start-3' : 'xl:col-start-4'
        }
      />
      <AdminTableShell
        loading={loading}
        isEmpty={!items.length}
        emptyContent={t('operator.empty')}
        emptyColSpan={6 + (includeCampaignFilter ? 1 : 0)}
        withTooltipProvider
        tableWrapperClassName={tableWrapperClassName}
        showFooterWhenLoading={showFooterWhenLoading}
        table={emptyRow => (
          <Table containerClassName='overflow-visible max-h-none'>
            <TableHeader>
              <TableRow>
                {includeCampaignFilter ? (
                  <TableHead className={TABLE_HEAD_CLASS}>
                    {t('operator.table.campaign')}
                  </TableHead>
                ) : null}
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
                  {t('operator.table.boundAt')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {t('operator.table.relationStatus')}
                </TableHead>
                <TableHead className={TABLE_HEAD_CLASS}>
                  {t('operator.table.rewardStatus')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {emptyRow}
              {items.map(item => (
                <TableRow key={item.relation_bid}>
                  {includeCampaignFilter ? (
                    <TableCell className={TABLE_CELL_CLASS}>
                      {formatReferralText(item.campaign_code)}
                    </TableCell>
                  ) : null}
                  <TableCell className={TABLE_CELL_CLASS}>
                    <ReferralUserSummary
                      primaryText={item.inviter?.identifier}
                      fallbackText={item.inviter_user_bid}
                      secondaryText={
                        showUserBidSecondary && item.inviter?.identifier
                          ? item.inviter_user_bid
                          : undefined
                      }
                    />
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    <ReferralUserSummary
                      primaryText={
                        item.invitee_mobile_snapshot || item.invitee?.identifier
                      }
                      fallbackText={item.invitee_user_bid}
                      secondaryText={
                        showUserBidSecondary &&
                        (item.invitee_mobile_snapshot ||
                          item.invitee?.identifier)
                          ? item.invitee_user_bid
                          : undefined
                      }
                    />
                  </TableCell>
                  <TableCell className={`${TABLE_CELL_CLASS} font-mono`}>
                    {formatReferralText(item.invite_code)}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {formatAdminUtcDateTime(item.bound_at || '') ||
                      formatReferralText(item.bound_at)}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {relationStatusLabel(item.relation_status)}
                  </TableCell>
                  <TableCell className={TABLE_CELL_CLASS}>
                    {item.reward
                      ? rewardStatusLabel(item.reward.reward_status)
                      : '-'}
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
  contactMode,
}: {
  t: (key: string, values?: Record<string, unknown>) => string;
  tCommon: (key: string, values?: Record<string, unknown>) => string;
  filters: ReferralFilters;
  setFilters: React.Dispatch<React.SetStateAction<ReferralFilters>>;
  includeCampaignFilter: boolean;
  relationStatusLabel: (status: number) => string;
  contactMode: 'email' | 'phone';
}) {
  const inviterPlaceholder =
    contactMode === 'email'
      ? t('operator.filters.inviterEmailPlaceholder')
      : t('operator.filters.inviterMobilePlaceholder');
  const inviteePlaceholder =
    contactMode === 'email'
      ? t('operator.filters.inviteeEmailPlaceholder')
      : t('operator.filters.inviteeMobilePlaceholder');
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
      label: t('operator.filters.inviter'),
      component: (
        <AdminClearableInput
          value={filters.inviter_user_bid}
          placeholder={inviterPlaceholder}
          onChange={value =>
            setFilters(current => ({ ...current, inviter_user_bid: value }))
          }
          clearLabel={tCommon('common.core.close')}
        />
      ),
    },
    {
      key: 'invitee_user_bid',
      label: t('operator.filters.invitee'),
      component: (
        <AdminClearableInput
          value={filters.invitee_user_bid}
          placeholder={inviteePlaceholder}
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
