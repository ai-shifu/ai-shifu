'use client';

import React from 'react';
import { Eye, RefreshCcw, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import { AdminMetricCardGroup } from '@/app/admin/components/AdminMetricCard';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import AdminTitle from '@/app/admin/components/AdminTitle';
import useOperatorGuard from '@/app/admin/operations/useOperatorGuard';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
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
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import Loading from '@/components/loading';
import { Textarea } from '@/components/ui/Textarea';
import { toast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import type {
  AdminReferralListResponse,
  AdminReferralOverview,
  AdminReferralRelation,
  AdminReferralRewardQueueItem,
  AdminReferralStatusPayload,
} from '@/types/referral';
import {
  REFERRAL_ABNORMAL_STATUS,
  REFERRAL_RELATION_STATUS,
  REFERRAL_REWARD_STATUS,
} from '@/types/referral';

const PAGE_SIZE = 20;
const ALL_OPTION_VALUE = 'all';

/*
 * Translation usage markers for scripts/check_translation_usage.py:
 * t('module.referral.abnormalStatus.confirmedAbnormal')
 * t('module.referral.abnormalStatus.normal')
 * t('module.referral.abnormalStatus.reviewing')
 * t('module.referral.abnormalStatus.unknown')
 * t('module.referral.operator.actions.cancelReward')
 * t('module.referral.operator.actions.detail')
 * t('module.referral.operator.actions.freezeReward')
 * t('module.referral.operator.actions.markNormal')
 * t('module.referral.operator.actions.markReviewing')
 * t('module.referral.operator.actions.reset')
 * t('module.referral.operator.actions.search')
 * t('module.referral.operator.description')
 * t('module.referral.operator.detail.abnormalStatus')
 * t('module.referral.operator.detail.billOrder')
 * t('module.referral.operator.detail.boundAt')
 * t('module.referral.operator.detail.campaign')
 * t('module.referral.operator.detail.inviteCode')
 * t('module.referral.operator.detail.invitee')
 * t('module.referral.operator.detail.inviteeMobile')
 * t('module.referral.operator.detail.inviter')
 * t('module.referral.operator.detail.ledger')
 * t('module.referral.operator.detail.loading')
 * t('module.referral.operator.detail.operatorNote')
 * t('module.referral.operator.detail.operatorNotePlaceholder')
 * t('module.referral.operator.detail.relationStatus')
 * t('module.referral.operator.detail.reward')
 * t('module.referral.operator.detail.rewardBid')
 * t('module.referral.operator.detail.rewardQueue.artifacts.ledger')
 * t('module.referral.operator.detail.rewardQueue.artifacts.order')
 * t('module.referral.operator.detail.rewardQueue.artifacts.reward')
 * t('module.referral.operator.detail.rewardQueue.columns.artifacts')
 * t('module.referral.operator.detail.rewardQueue.columns.credits')
 * t('module.referral.operator.detail.rewardQueue.columns.effectiveAt')
 * t('module.referral.operator.detail.rewardQueue.columns.expiresAt')
 * t('module.referral.operator.detail.rewardQueue.columns.index')
 * t('module.referral.operator.detail.rewardQueue.columns.invitee')
 * t('module.referral.operator.detail.rewardQueue.columns.ledgerState')
 * t('module.referral.operator.detail.rewardQueue.columns.status')
 * t('module.referral.operator.detail.rewardQueue.empty')
 * t('module.referral.operator.detail.rewardQueue.title')
 * t('module.referral.operator.detail.rewardProduct')
 * t('module.referral.operator.detail.rewardStatus')
 * t('module.referral.operator.detail.subscription')
 * t('module.referral.operator.detail.title')
 * t('module.referral.operator.detail.walletBucket')
 * t('module.referral.operator.empty')
 * t('module.referral.operator.filters.abnormalStatus')
 * t('module.referral.operator.filters.all')
 * t('module.referral.operator.filters.campaignBid')
 * t('module.referral.operator.filters.inviteCode')
 * t('module.referral.operator.filters.inviteeUserBid')
 * t('module.referral.operator.filters.inviterUserBid')
 * t('module.referral.operator.filters.relationStatus')
 * t('module.referral.operator.loadFailed')
 * t('module.referral.operator.metrics.abnormalRelations')
 * t('module.referral.operator.metrics.generatedRewards')
 * t('module.referral.operator.metrics.totalRelations')
 * t('module.referral.operator.pagination.jumpInputAria')
 * t('module.referral.operator.pagination.next')
 * t('module.referral.operator.pagination.nextAria')
 * t('module.referral.operator.pagination.prev')
 * t('module.referral.operator.pagination.prevAria')
 * t('module.referral.operator.refresh')
 * t('module.referral.operator.statusUpdated')
 * t('module.referral.operator.table.action')
 * t('module.referral.operator.table.boundAt')
 * t('module.referral.operator.table.campaign')
 * t('module.referral.operator.table.inviteCode')
 * t('module.referral.operator.table.invitee')
 * t('module.referral.operator.table.inviter')
 * t('module.referral.operator.table.relationStatus')
 * t('module.referral.operator.table.rewardStatus')
 * t('module.referral.operator.title')
 * t('module.referral.operator.tooltips.abnormalRelations')
 * t('module.referral.operator.tooltips.generatedRewards')
 * t('module.referral.operator.tooltips.totalRelations')
 * t('module.referral.operator.total')
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

type ReferralFilters = {
  campaign_bid: string;
  inviter_user_bid: string;
  invitee_user_bid: string;
  invite_code: string;
  relation_status: string;
  abnormal_status: string;
};

const createEmptyFilters = (): ReferralFilters => ({
  campaign_bid: '',
  inviter_user_bid: '',
  invitee_user_bid: '',
  invite_code: '',
  relation_status: '',
  abnormal_status: '',
});

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

const formatText = (value?: string | null) => {
  const normalized = String(value || '').trim();
  return normalized || '-';
};

const normalizeCount = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) ? value : 0;

export default function AdminOperationReferralsPage() {
  const { t } = useTranslation('module.referral');
  const { isReady } = useOperatorGuard();
  const [filters, setFilters] =
    React.useState<ReferralFilters>(createEmptyFilters);
  const [appliedFilters, setAppliedFilters] =
    React.useState<ReferralFilters>(createEmptyFilters);
  const [items, setItems] = React.useState<AdminReferralRelation[]>([]);
  const [overview, setOverview] = React.useState<AdminReferralOverview>({
    total_relations: 0,
    abnormal_relations: 0,
    generated_rewards: 0,
  });
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
        page_size: PAGE_SIZE,
      };
      Object.entries(appliedFilters).forEach(([key, value]) => {
        if (value) {
          params[key] = value;
        }
      });
      return params;
    },
    [appliedFilters, pageIndex],
  );

  const fetchOverview = React.useCallback(async () => {
    const response = (await api.getAdminOperationReferralsOverview(
      {},
    )) as AdminReferralOverview;
    setOverview({
      total_relations: normalizeCount(response.total_relations),
      abnormal_relations: normalizeCount(response.abnormal_relations),
      generated_rewards: normalizeCount(response.generated_rewards),
    });
  }, []);

  const fetchList = React.useCallback(
    async (nextPageIndex = pageIndex) => {
      setLoading(true);
      setError('');
      try {
        const response = (await api.getAdminOperationReferrals(
          buildListParams(nextPageIndex),
        )) as AdminReferralListResponse;
        setItems(response.items || []);
        setTotal(normalizeCount(response.total));
        setPageCount(
          Math.max(1, Math.ceil(normalizeCount(response.total) / PAGE_SIZE)),
        );
      } catch (nextError) {
        const typedError = nextError as ErrorWithCode;
        setError(typedError.message || t('operator.loadFailed'));
      } finally {
        setLoading(false);
      }
    },
    [buildListParams, pageIndex, t],
  );

  React.useEffect(() => {
    if (!isReady) {
      return;
    }
    void fetchOverview();
    void fetchList(pageIndex);
  }, [fetchList, fetchOverview, isReady, pageIndex]);

  const applySearch = () => {
    setPageIndex(1);
    setAppliedFilters({ ...filters });
  };

  const resetSearch = () => {
    setFilters(createEmptyFilters());
    setAppliedFilters(createEmptyFilters());
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
      await fetchOverview();
      toast({ title: t('operator.statusUpdated') });
    } finally {
      setStatusLoading(false);
    }
  };

  if (!isReady) {
    return <Loading />;
  }

  return (
    <div className='flex min-h-0 flex-col'>
      <AdminBreadcrumb items={[{ label: t('operator.title') }]} />
      <AdminTitle
        title={t('operator.title')}
        description={t('operator.description')}
        actions={
          <Button
            type='button'
            variant='outline'
            className='gap-2'
            onClick={() => {
              void fetchOverview();
              void fetchList(pageIndex);
            }}
          >
            <RefreshCcw className='h-4 w-4' />
            {t('operator.refresh')}
          </Button>
        }
      />

      <AdminMetricCardGroup
        gridClassName='md:grid-cols-3'
        items={[
          {
            key: 'total-relations',
            label: t('operator.metrics.totalRelations'),
            value: overview.total_relations,
            tooltip: t('operator.tooltips.totalRelations'),
          },
          {
            key: 'generated-rewards',
            label: t('operator.metrics.generatedRewards'),
            value: overview.generated_rewards,
            tooltip: t('operator.tooltips.generatedRewards'),
          },
          {
            key: 'abnormal-relations',
            label: t('operator.metrics.abnormalRelations'),
            value: overview.abnormal_relations,
            tooltip: t('operator.tooltips.abnormalRelations'),
          },
        ]}
      />

      <section className='mt-5 rounded-lg border border-border bg-white p-4'>
        <div className='grid gap-3 md:grid-cols-3'>
          <FilterInput
            label={t('operator.filters.campaignBid')}
            value={filters.campaign_bid}
            onChange={value =>
              setFilters(current => ({ ...current, campaign_bid: value }))
            }
          />
          <FilterInput
            label={t('operator.filters.inviterUserBid')}
            value={filters.inviter_user_bid}
            onChange={value =>
              setFilters(current => ({ ...current, inviter_user_bid: value }))
            }
          />
          <FilterInput
            label={t('operator.filters.inviteeUserBid')}
            value={filters.invitee_user_bid}
            onChange={value =>
              setFilters(current => ({ ...current, invitee_user_bid: value }))
            }
          />
          <FilterInput
            label={t('operator.filters.inviteCode')}
            value={filters.invite_code}
            onChange={value =>
              setFilters(current => ({ ...current, invite_code: value }))
            }
          />
          <FilterSelect
            label={t('operator.filters.relationStatus')}
            value={filters.relation_status || ALL_OPTION_VALUE}
            allLabel={t('operator.filters.all')}
            options={[
              {
                value: String(REFERRAL_RELATION_STATUS.rewardGenerated),
                label: relationStatusLabel(
                  REFERRAL_RELATION_STATUS.rewardGenerated,
                ),
              },
              {
                value: String(REFERRAL_RELATION_STATUS.rewardSkippedCap),
                label: relationStatusLabel(
                  REFERRAL_RELATION_STATUS.rewardSkippedCap,
                ),
              },
              {
                value: String(REFERRAL_RELATION_STATUS.canceled),
                label: relationStatusLabel(REFERRAL_RELATION_STATUS.canceled),
              },
            ]}
            onChange={value =>
              setFilters(current => ({
                ...current,
                relation_status:
                  value === ALL_OPTION_VALUE ? '' : String(value),
              }))
            }
          />
          <FilterSelect
            label={t('operator.filters.abnormalStatus')}
            value={filters.abnormal_status || ALL_OPTION_VALUE}
            allLabel={t('operator.filters.all')}
            options={[
              {
                value: String(REFERRAL_ABNORMAL_STATUS.normal),
                label: abnormalStatusLabel(REFERRAL_ABNORMAL_STATUS.normal),
              },
              {
                value: String(REFERRAL_ABNORMAL_STATUS.reviewing),
                label: abnormalStatusLabel(REFERRAL_ABNORMAL_STATUS.reviewing),
              },
              {
                value: String(REFERRAL_ABNORMAL_STATUS.confirmedAbnormal),
                label: abnormalStatusLabel(
                  REFERRAL_ABNORMAL_STATUS.confirmedAbnormal,
                ),
              },
            ]}
            onChange={value =>
              setFilters(current => ({
                ...current,
                abnormal_status:
                  value === ALL_OPTION_VALUE ? '' : String(value),
              }))
            }
          />
        </div>
        <div className='mt-4 flex justify-end gap-2'>
          <Button
            type='button'
            variant='outline'
            onClick={resetSearch}
          >
            {t('operator.actions.reset')}
          </Button>
          <Button
            type='button'
            className='gap-2'
            onClick={applySearch}
          >
            <Search className='h-4 w-4' />
            {t('operator.actions.search')}
          </Button>
        </div>
      </section>

      <section className='mt-5 min-h-0 flex-1 rounded-lg border border-border bg-white'>
        {error ? (
          <div className='p-6 text-sm text-destructive'>{error}</div>
        ) : null}
        {loading ? (
          <div className='flex h-40 items-center justify-center'>
            <Loading />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('operator.table.campaign')}</TableHead>
                <TableHead>{t('operator.table.inviter')}</TableHead>
                <TableHead>{t('operator.table.invitee')}</TableHead>
                <TableHead>{t('operator.table.inviteCode')}</TableHead>
                <TableHead>{t('operator.table.relationStatus')}</TableHead>
                <TableHead>{t('operator.table.rewardStatus')}</TableHead>
                <TableHead>{t('operator.table.boundAt')}</TableHead>
                <TableHead className='text-right'>
                  {t('operator.table.action')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length ? (
                items.map(item => (
                  <TableRow key={item.relation_bid}>
                    <TableCell>{formatText(item.campaign_code)}</TableCell>
                    <TableCell>
                      <UserSummary
                        userBid={item.inviter_user_bid}
                        identifier={item.inviter?.identifier}
                      />
                    </TableCell>
                    <TableCell>
                      <UserSummary
                        userBid={item.invitee_user_bid}
                        identifier={
                          item.invitee_mobile_snapshot ||
                          item.invitee?.identifier
                        }
                      />
                    </TableCell>
                    <TableCell className='font-mono'>
                      {formatText(item.invite_code)}
                    </TableCell>
                    <TableCell>
                      {relationStatusLabel(item.relation_status)}
                    </TableCell>
                    <TableCell>
                      {item.reward
                        ? rewardStatusLabel(item.reward.reward_status)
                        : '-'}
                    </TableCell>
                    <TableCell>
                      {formatAdminUtcDateTime(item.bound_at) || '-'}
                    </TableCell>
                    <TableCell className='text-right'>
                      <Button
                        type='button'
                        variant='outline'
                        size='sm'
                        className='gap-2'
                        data-testid={`referral-detail-${item.relation_bid}`}
                        onClick={() => void openDetail(item.relation_bid)}
                      >
                        <Eye className='h-4 w-4' />
                        {t('operator.actions.detail')}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableEmpty colSpan={8}>{t('operator.empty')}</TableEmpty>
              )}
            </TableBody>
          </Table>
        )}
      </section>

      <div className='mt-4 flex items-center justify-between'>
        <div className='text-sm text-muted-foreground'>
          {t('operator.total', { total })}
        </div>
        <AdminPagination
          pageIndex={pageIndex}
          pageCount={pageCount}
          onPageChange={setPageIndex}
          prevLabel={t('operator.pagination.prev')}
          nextLabel={t('operator.pagination.next')}
          prevAriaLabel={t('operator.pagination.prevAria')}
          nextAriaLabel={t('operator.pagination.nextAria')}
          jumpInputAriaLabel={t('operator.pagination.jumpInputAria')}
          hideWhenSinglePage
        />
      </div>

      <Sheet
        open={detailOpen}
        onOpenChange={setDetailOpen}
      >
        <SheetContent className='w-full overflow-y-auto sm:max-w-2xl'>
          <SheetHeader>
            <SheetTitle>{t('operator.detail.title')}</SheetTitle>
            <SheetDescription>
              {detail?.relation_bid || t('operator.detail.loading')}
            </SheetDescription>
          </SheetHeader>
          {detailLoading ? (
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
                    formatAdminUtcDateTime(detail.bound_at) || '-',
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
                      detail.reward?.billing_artifacts?.wallet_bucket_bid ||
                        '-',
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
                t={t}
              />

              <div className='space-y-2'>
                <Label htmlFor='operator-note'>
                  {t('operator.detail.operatorNote')}
                </Label>
                <Textarea
                  id='operator-note'
                  value={operatorNote}
                  onChange={event => setOperatorNote(event.target.value)}
                  placeholder={t('operator.detail.operatorNotePlaceholder')}
                />
              </div>
              <div className='grid gap-2 sm:grid-cols-2'>
                <Button
                  type='button'
                  variant='outline'
                  disabled={statusLoading}
                  onClick={() =>
                    void updateStatus({ abnormal_status: 'reviewing' })
                  }
                >
                  {t('operator.actions.markReviewing')}
                </Button>
                <Button
                  type='button'
                  variant='outline'
                  disabled={statusLoading}
                  onClick={() =>
                    void updateStatus({ abnormal_status: 'normal' })
                  }
                >
                  {t('operator.actions.markNormal')}
                </Button>
                <Button
                  type='button'
                  variant='outline'
                  disabled={statusLoading}
                  onClick={() =>
                    void updateStatus({
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
                  onClick={() => void updateStatus({ reward_status: 'frozen' })}
                >
                  {t('operator.actions.freezeReward')}
                </Button>
              </div>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function RewardQueueTable({
  items,
  rewardStatusLabel,
  t,
}: {
  items: AdminReferralRewardQueueItem[];
  rewardStatusLabel: (status?: number) => string;
  t: (key: string, values?: Record<string, unknown>) => string;
}) {
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
                  <TableCell>{formatText(item.reward_credit_amount)}</TableCell>
                  <TableCell>
                    <UserSummary
                      userBid={item.invitee_user_bid}
                      identifier={item.invitee_mobile_snapshot}
                    />
                  </TableCell>
                  <TableCell>
                    {formatAdminUtcDateTime(item.effective_at) || '-'}
                  </TableCell>
                  <TableCell>
                    {formatAdminUtcDateTime(item.expires_at) || '-'}
                  </TableCell>
                  <TableCell>{formatText(item.ledger_credit_state)}</TableCell>
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
              <TableEmpty colSpan={8}>
                {t('operator.detail.rewardQueue.empty')}
              </TableEmpty>
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
      <span className='font-mono text-foreground'>{formatText(value)}</span>
    </div>
  );
}

function FilterInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className='space-y-2'>
      <Label>{label}</Label>
      <Input
        value={value}
        onChange={event => onChange(event.target.value)}
      />
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  allLabel,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  allLabel: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className='space-y-2'>
      <Label>{label}</Label>
      <Select
        value={value}
        onValueChange={onChange}
      >
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_OPTION_VALUE}>{allLabel}</SelectItem>
          {options.map(option => (
            <SelectItem
              key={option.value}
              value={option.value}
            >
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function UserSummary({
  userBid,
  identifier,
}: {
  userBid: string;
  identifier?: string;
}) {
  return (
    <div className='min-w-0'>
      <div className='truncate font-medium'>{formatText(userBid)}</div>
      <div className='truncate text-xs text-muted-foreground'>
        {formatText(identifier)}
      </div>
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
              {formatText(value)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
