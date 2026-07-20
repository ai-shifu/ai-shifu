import React from 'react';
import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
import { ChevronDown } from 'lucide-react';
import useSWR from 'swr';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminTableShell from '@/components/admin/AdminTableShell';
import {
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/components/admin/adminTableStyles';
import { Button } from '@/components/ui/Button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  buildBillingSwrKey,
  formatBillingCredits,
  formatBillingDate,
  registerBillingTranslationUsage,
  resolveBillingEmptyLabel,
} from '@/lib/billing';
import {
  resolveAdminBillingCreatorPrimary,
  resolveAdminBillingCreatorSecondary,
} from '@/components/billing/AdminBillingShared';
import type {
  AdminBillingFocusTeacherItem,
  BillingPagedResponse,
} from '@/types/billing';

const ADMIN_REPORT_PAGE_SIZE = 10;
const BILLING_PASSIVE_REQUEST_CONFIG = { skipErrorToast: true } as const;
const REPORT_CARD_PLACEHOLDER = '--';
const REPORT_FILTERS = [
  'all',
  'rapid_growth',
  'debug_preview_heavy',
  'active_production',
] as const;
const REPORT_SORTS = ['credits_30d', 'growth', 'debug_ratio'] as const;

type ReportFilter = (typeof REPORT_FILTERS)[number];
type ReportSort = (typeof REPORT_SORTS)[number];

type ReportSectionProps = {
  title: string;
  description: string;
  loading: boolean;
  error?: unknown;
  emptyLabel: string;
  children: React.ReactNode;
};

function ReportCardPlaceholder() {
  return (
    <span
      className='text-base font-normal text-slate-400'
      aria-hidden='true'
    >
      {REPORT_CARD_PLACEHOLDER}
    </span>
  );
}

function ReportSection({
  title,
  description,
  loading,
  error,
  emptyLabel,
  children,
}: ReportSectionProps) {
  return (
    <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
      <CardHeader className='space-y-2 pb-4'>
        <div className='flex flex-wrap items-center justify-between gap-3'>
          <div className='space-y-1.5'>
            <CardTitle className='text-lg text-slate-900'>{title}</CardTitle>
            <CardDescription className='leading-6 text-slate-600'>
              {description}
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className='space-y-3'>
        {error ? (
          <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
            {emptyLabel}
          </div>
        ) : null}
        {loading ? (
          <div className='space-y-3'>
            <Skeleton className='h-14 rounded-2xl' />
            <Skeleton className='h-14 rounded-2xl' />
          </div>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}

function formatBillingPercent(value: number, language: string): string {
  return `${Math.round(Math.max(value || 0, 0) * 100).toLocaleString(language)}%`;
}

function resolveSummaryCardClassName(
  kind: 'focus' | 'credits' | 'active' | 'debug',
) {
  switch (kind) {
    case 'focus':
      return 'border-sky-200 bg-sky-50/80';
    case 'credits':
      return 'border-amber-200 bg-amber-50/80';
    case 'active':
      return 'border-emerald-200 bg-emerald-50/80';
    default:
      return 'border-violet-200 bg-violet-50/80';
  }
}

function SummaryHintTooltip({ content }: { content: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type='button'
          aria-label={content}
          className='inline-flex h-5 w-5 items-center justify-center rounded-full text-slate-400 transition-colors hover:text-slate-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300'
        >
          <QuestionMarkCircleIcon className='h-4 w-4' />
        </button>
      </TooltipTrigger>
      <TooltipContent className='max-w-56 text-left leading-5'>
        {content}
      </TooltipContent>
    </Tooltip>
  );
}

export function AdminBillingReportsPanel() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  registerBillingTranslationUsage(t);
  const [activeFilter, setActiveFilter] = React.useState<ReportFilter>('all');
  const [activeSort, setActiveSort] = React.useState<ReportSort>('credits_30d');
  const [pageIndex, setPageIndex] = React.useState(1);

  const { data: focusCountPage } = useSWR<
    BillingPagedResponse<AdminBillingFocusTeacherItem>
  >(
    buildBillingSwrKey('admin-billing-focus-teachers-count'),
    async () =>
      (await api.getAdminBillingFocusTeachers(
        {
          page_index: 1,
          page_size: 1,
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingPagedResponse<AdminBillingFocusTeacherItem>,
    {
      revalidateOnFocus: false,
    },
  );

  const focusTotal = Math.max(Number(focusCountPage?.total || 0), 0);
  const {
    data: focusTeachers,
    error: focusError,
    isLoading: focusLoading,
  } = useSWR<BillingPagedResponse<AdminBillingFocusTeacherItem>>(
    focusCountPage
      ? buildBillingSwrKey('admin-billing-focus-teachers-all', focusTotal)
      : null,
    async () =>
      (await api.getAdminBillingFocusTeachers(
        {
          page_index: 1,
          page_size: Math.max(focusTotal, 1),
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingPagedResponse<AdminBillingFocusTeacherItem>,
    {
      revalidateOnFocus: false,
    },
  );

  const focusRows = React.useMemo(
    () => focusTeachers?.items || [],
    [focusTeachers?.items],
  );
  const filteredRows = React.useMemo(() => {
    if (activeFilter === 'all') {
      return focusRows;
    }
    return focusRows.filter(item =>
      item.attention_reasons.includes(activeFilter),
    );
  }, [activeFilter, focusRows]);

  const sortedRows = React.useMemo(() => {
    const rows = [...filteredRows];
    rows.sort((left, right) => {
      if (activeSort === 'growth') {
        const leftGrowth = left.attention_reasons.includes('rapid_growth');
        const rightGrowth = right.attention_reasons.includes('rapid_growth');
        if (leftGrowth !== rightGrowth) {
          return leftGrowth ? -1 : 1;
        }
      }

      if (activeSort === 'debug_ratio') {
        const leftRatio =
          Number(left.total_credits_30d || 0) > 0
            ? Number(left.debug_preview_credits_30d || 0) /
              Number(left.total_credits_30d || 0)
            : 0;
        const rightRatio =
          Number(right.total_credits_30d || 0) > 0
            ? Number(right.debug_preview_credits_30d || 0) /
              Number(right.total_credits_30d || 0)
            : 0;
        if (leftRatio !== rightRatio) {
          return rightRatio - leftRatio;
        }
      }

      return Number(right.credits_30d || 0) - Number(left.credits_30d || 0);
    });
    return rows;
  }, [activeSort, filteredRows]);

  const totalCredits30d = focusRows.reduce(
    (sum, item) => sum + Number(item.credits_30d || 0),
    0,
  );
  const activeTeachers7d = focusRows.filter(
    item => item.active_days_7d > 0,
  ).length;
  const debugHeavyTeachers = focusRows.filter(item =>
    item.attention_reasons.includes('debug_preview_heavy'),
  ).length;
  const latestUsageAt = focusRows.reduce<string | null>((latest, item) => {
    const current = String(item.latest_usage_at || '').trim();
    if (!current) {
      return latest;
    }
    if (!latest || current > latest) {
      return current;
    }
    return latest;
  }, null);

  const pageCount = sortedRows.length
    ? Math.ceil(sortedRows.length / ADMIN_REPORT_PAGE_SIZE)
    : 1;
  const safePageIndex = Math.min(pageIndex, pageCount);
  const pagedRows = sortedRows.slice(
    (safePageIndex - 1) * ADMIN_REPORT_PAGE_SIZE,
    safePageIndex * ADMIN_REPORT_PAGE_SIZE,
  );

  React.useEffect(() => {
    setPageIndex(1);
  }, [activeFilter, activeSort]);

  React.useEffect(() => {
    if (pageIndex !== safePageIndex) {
      setPageIndex(safePageIndex);
    }
  }, [pageIndex, safePageIndex]);

  const handleViewOrders = React.useCallback(
    (item: AdminBillingFocusTeacherItem) => {
      const params = new URLSearchParams();
      params.set('tab', 'credits');
      if (item.creator_mobile) {
        params.set('creator_keyword', item.creator_mobile);
      }
      router.push(`/admin/operations/orders?${params.toString()}`);
    },
    [router],
  );

  return (
    <div className='space-y-4'>
      <Card className='border-slate-200 bg-[linear-gradient(135deg,#eff6ff_0%,#ffffff_60%,#f8fafc_100%)] shadow-[0_18px_50px_rgba(15,23,42,0.08)]'>
        <CardHeader className='space-y-2 pb-4'>
          <CardTitle className='text-lg text-slate-900'>
            {t('module.billing.admin.reports.title')}
          </CardTitle>
          <CardDescription className='leading-6 text-slate-600'>
            {t('module.billing.admin.reports.description')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <TooltipProvider delayDuration={150}>
            <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-4'>
              <div
                className={`rounded-xl border px-4 py-3.5 ${resolveSummaryCardClassName('focus')}`}
              >
                <div className='flex items-start justify-between gap-3'>
                  <div className='text-sm text-slate-500'>
                    {t('module.billing.admin.reports.summary.focusCount')}
                  </div>
                  <SummaryHintTooltip
                    content={t(
                      'module.billing.admin.reports.summary.focusCountHint',
                    )}
                  />
                </div>
                <div className='mt-2 text-2xl font-semibold text-slate-800'>
                  {focusRows.length.toLocaleString(i18n.language)}
                </div>
              </div>
              <div
                className={`rounded-xl border px-4 py-3.5 ${resolveSummaryCardClassName('credits')}`}
              >
                <div className='flex items-start justify-between gap-3'>
                  <div className='text-sm text-slate-500'>
                    {t('module.billing.admin.reports.summary.totalCredits')}
                  </div>
                  <SummaryHintTooltip
                    content={t(
                      'module.billing.admin.reports.summary.totalCreditsHint',
                    )}
                  />
                </div>
                <div className='mt-2 text-2xl font-semibold text-slate-800'>
                  {formatBillingCredits(totalCredits30d, i18n.language)}
                </div>
              </div>
              <div
                className={`rounded-xl border px-4 py-3.5 ${resolveSummaryCardClassName('active')}`}
              >
                <div className='flex items-start justify-between gap-3'>
                  <div className='text-sm text-slate-500'>
                    {t('module.billing.admin.reports.summary.activeTeachers7d')}
                  </div>
                  <SummaryHintTooltip
                    content={t(
                      'module.billing.admin.reports.summary.activeTeachers7dHint',
                    )}
                  />
                </div>
                <div className='mt-2 text-2xl font-semibold text-slate-800'>
                  {activeTeachers7d.toLocaleString(i18n.language)}
                </div>
              </div>
              <div
                className={`rounded-xl border px-4 py-3.5 ${resolveSummaryCardClassName('debug')}`}
              >
                <div className='flex items-start justify-between gap-3'>
                  <div className='text-sm text-slate-500'>
                    {t('module.billing.admin.reports.summary.debugHeavyCount')}
                  </div>
                  <SummaryHintTooltip
                    content={t(
                      'module.billing.admin.reports.summary.debugHeavyCountHint',
                    )}
                  />
                </div>
                <div className='mt-2 text-2xl font-semibold text-slate-800'>
                  {focusRows.length ? (
                    debugHeavyTeachers.toLocaleString(i18n.language)
                  ) : (
                    <ReportCardPlaceholder />
                  )}
                </div>
              </div>
            </div>
          </TooltipProvider>
        </CardContent>
      </Card>

      <ReportSection
        title={t('module.billing.admin.reports.sections.usage.title')}
        description={t(
          'module.billing.admin.reports.sections.usage.description',
        )}
        loading={focusLoading || focusCountPage === undefined}
        error={focusError}
        emptyLabel={t('module.billing.reports.loadError')}
      >
        <div className='flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50/70 px-3 py-3'>
          <div className='flex flex-wrap gap-2'>
            {REPORT_FILTERS.map(filter => (
              <Button
                key={filter}
                type='button'
                variant={activeFilter === filter ? 'secondary' : 'outline'}
                size='sm'
                className='h-8 rounded-full border-slate-200 bg-white px-3 text-xs text-slate-600 data-[state=active]:text-slate-900'
                onClick={() => setActiveFilter(filter)}
              >
                {t(`module.billing.admin.reports.filters.${filter}`)}
              </Button>
            ))}
          </div>
          <div className='flex flex-wrap items-center justify-end gap-2'>
            <span className='text-xs font-medium text-slate-500'>
              {t('module.billing.admin.reports.sort.label')}
            </span>
            {REPORT_SORTS.map(sort => (
              <Button
                key={sort}
                type='button'
                variant={activeSort === sort ? 'secondary' : 'ghost'}
                size='sm'
                className='h-8 rounded-full px-3 text-xs text-slate-600'
                onClick={() => setActiveSort(sort)}
              >
                {t(`module.billing.admin.reports.sort.options.${sort}`)}
              </Button>
            ))}
          </div>
        </div>
        <AdminTableShell
          loading={false}
          isEmpty={!sortedRows.length}
          emptyContent={
            <div className='space-y-1 py-2 text-center'>
              <div>{t('module.billing.admin.reports.empty')}</div>
              <div className='text-xs text-slate-500'>
                {t('module.billing.admin.reports.emptyHint')}
              </div>
            </div>
          }
          emptyColSpan={9}
          stickyActionEmpty={{
            contentColSpan: 8,
            actionClassName: getAdminStickyRightCellClass(
              'w-[92px] min-w-[92px]',
            ),
          }}
          pagination={{
            pageIndex: safePageIndex,
            pageCount,
            onPageChange: setPageIndex,
            prevLabel: t('module.dashboard.pagination.prev'),
            nextLabel: t('module.dashboard.pagination.next'),
            prevAriaLabel: t('module.dashboard.pagination.prev'),
            nextAriaLabel: t('module.dashboard.pagination.next'),
            hideWhenSinglePage: true,
          }}
          footerClassName='justify-end'
          table={emptyRow => (
            <Table className='min-w-[1180px]'>
              <TableHeader>
                <TableRow>
                  <TableHead className='min-w-[190px]'>
                    {t('module.billing.admin.reports.table.creator')}
                  </TableHead>
                  <TableHead className='min-w-[220px]'>
                    {t('module.billing.admin.reports.table.attentionReasons')}
                  </TableHead>
                  <TableHead className='min-w-[210px]'>
                    {t('module.billing.admin.reports.table.credits30d')}
                  </TableHead>
                  <TableHead className='w-[120px] text-right'>
                    {t('module.billing.admin.reports.table.credits7d')}
                  </TableHead>
                  <TableHead className='w-[112px]'>
                    {t('module.billing.admin.reports.table.recordCount7d')}
                  </TableHead>
                  <TableHead className='w-[112px]'>
                    {t('module.billing.admin.reports.table.activeDays7d')}
                  </TableHead>
                  <TableHead className='w-[132px]'>
                    {t('module.billing.admin.reports.table.productionRatio')}
                  </TableHead>
                  <TableHead className='min-w-[164px]'>
                    {t('module.billing.admin.reports.table.latestActivity')}
                  </TableHead>
                  <TableHead
                    className={getAdminStickyRightHeaderClass(
                      'w-[92px] min-w-[92px] text-center',
                    )}
                  >
                    {t('module.billing.admin.reports.table.actions')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {emptyRow}
                {pagedRows.map(item => (
                  <TableRow
                    key={item.creator_bid}
                    className='hover:bg-slate-50/70 [&>td]:py-3.5'
                  >
                    <TableCell className='font-medium text-slate-900'>
                      <div className='space-y-1'>
                        <div className='whitespace-nowrap'>
                          {resolveAdminBillingCreatorPrimary(item) ||
                            resolveBillingEmptyLabel(t)}
                        </div>
                        <div
                          className='max-w-[180px] truncate text-xs leading-5 text-slate-500'
                          title={resolveAdminBillingCreatorSecondary(t, item)}
                        >
                          {resolveAdminBillingCreatorSecondary(t, item)}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className='space-y-1'>
                        {item.attention_reasons.map(reason => (
                          <div
                            key={`${item.creator_bid}-${reason}`}
                            className='truncate text-xs font-medium leading-5 text-slate-700'
                          >
                            {t(
                              `module.billing.admin.reports.attentionReasons.${reason}`,
                            )}
                          </div>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className='space-y-1'>
                        <div className='font-medium text-slate-900'>
                          {formatBillingCredits(
                            item.credits_30d,
                            i18n.language,
                          )}
                        </div>
                        <div className='space-y-0.5 text-xs leading-5 text-slate-500'>
                          <div className='truncate whitespace-nowrap'>
                            {t(
                              'module.billing.admin.reports.table.credits30dProduction',
                              {
                                production: formatBillingCredits(
                                  item.production_credits_30d,
                                  i18n.language,
                                ),
                              },
                            )}
                          </div>
                          <div className='truncate whitespace-nowrap'>
                            {t(
                              'module.billing.admin.reports.table.credits30dDebugPreview',
                              {
                                debugPreview: formatBillingCredits(
                                  item.debug_preview_credits_30d,
                                  i18n.language,
                                ),
                              },
                            )}
                          </div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className='text-right font-medium text-slate-900'>
                      {formatBillingCredits(item.credits_7d, i18n.language)}
                    </TableCell>
                    <TableCell className='font-medium text-slate-900'>
                      {Number(item.record_count_7d || 0).toLocaleString(
                        i18n.language,
                      )}
                    </TableCell>
                    <TableCell className='font-medium text-slate-900'>
                      {Number(item.active_days_7d || 0).toLocaleString(
                        i18n.language,
                      )}
                    </TableCell>
                    <TableCell>
                      {Number(item.total_credits_30d || 0) > 0 ? (
                        <div className='space-y-2'>
                          <div className='font-medium text-slate-900'>
                            {formatBillingPercent(
                              Number(item.production_ratio_30d || 0),
                              i18n.language,
                            )}
                          </div>
                          <div className='h-2 overflow-hidden rounded-full bg-slate-100'>
                            <div
                              className='h-full rounded-full bg-emerald-500'
                              style={{
                                width: `${Math.max(
                                  Math.min(
                                    Number(item.production_ratio_30d || 0) *
                                      100,
                                    100,
                                  ),
                                  0,
                                )}%`,
                              }}
                            />
                          </div>
                        </div>
                      ) : (
                        resolveBillingEmptyLabel(t)
                      )}
                    </TableCell>
                    <TableCell>
                      {item.latest_usage_at ? (
                        <div className='space-y-1'>
                          <div className='whitespace-nowrap font-medium text-slate-900'>
                            {formatBillingDate(
                              item.latest_usage_at,
                              i18n.language,
                            )}
                          </div>
                          <div className='whitespace-nowrap text-xs text-slate-500'>
                            {t(
                              'module.billing.admin.reports.table.latestActivityHint',
                              {
                                days: Number(
                                  item.active_days_7d || 0,
                                ).toLocaleString(i18n.language),
                              },
                            )}
                          </div>
                        </div>
                      ) : latestUsageAt ? (
                        resolveBillingEmptyLabel(t)
                      ) : (
                        <ReportCardPlaceholder />
                      )}
                    </TableCell>
                    <TableCell
                      className={getAdminStickyRightCellClass(
                        'w-[92px] min-w-[92px] text-center',
                      )}
                    >
                      <div className='flex justify-start whitespace-nowrap'>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              type='button'
                              variant='ghost'
                              size='sm'
                              className='h-7 gap-1 px-1 text-[11px] text-slate-600'
                            >
                              {t('common.core.more')}
                              <ChevronDown className='h-3.5 w-3.5' />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent
                            align='end'
                            className='min-w-[132px]'
                          >
                            <DropdownMenuItem
                              onClick={() => handleViewOrders(item)}
                            >
                              {t(
                                'module.billing.admin.reports.actions.viewOrders',
                              )}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        />
      </ReportSection>
    </div>
  );
}
