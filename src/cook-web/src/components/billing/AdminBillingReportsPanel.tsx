import React from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { getBrowserTimeZone } from '@/lib/browser-timezone';
import { Badge } from '@/components/ui/Badge';
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
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import {
  buildBillingSwrKey,
  formatBillingCredits,
  formatBillingDate,
  formatBillingDateTime,
  registerBillingTranslationUsage,
  resolveBillingBucketSourceLabel,
  resolveBillingLedgerEntryLabel,
  resolveBillingMetricLabel,
  resolveBillingUsageSceneLabel,
  resolveBillingUsageTypeLabel,
  withBillingTimezone,
} from '@/lib/billing';
import type {
  AdminBillingDailyLedgerSummaryItem,
  AdminBillingDailyUsageMetricItem,
  BillingPagedResponse,
} from '@/types/billing';

const ADMIN_REPORT_PAGE_SIZE = 6;

type ReportSectionProps = {
  title: string;
  description: string;
  pageMeta?: string;
  loading: boolean;
  error?: unknown;
  emptyLabel: string;
  children: React.ReactNode;
};

function ReportSection({
  title,
  description,
  pageMeta,
  loading,
  error,
  emptyLabel,
  children,
}: ReportSectionProps) {
  return (
    <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
      <CardHeader className='space-y-3'>
        <div className='flex flex-wrap items-center justify-between gap-3'>
          <div className='space-y-2'>
            <CardTitle className='text-lg text-slate-900'>{title}</CardTitle>
            <CardDescription className='leading-6 text-slate-600'>
              {description}
            </CardDescription>
          </div>
          {pageMeta ? (
            <Badge
              variant='outline'
              className='border-slate-200 bg-slate-50 text-slate-600'
            >
              {pageMeta}
            </Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className='space-y-4'>
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

export function AdminBillingReportsPanel() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const timezone = getBrowserTimeZone();
  const {
    data: usageReports,
    error: usageError,
    isLoading: usageLoading,
  } = useSWR<BillingPagedResponse<AdminBillingDailyUsageMetricItem>>(
    buildBillingSwrKey('admin-billing-daily-usage-metrics', timezone),
    async () =>
      (await api.getAdminBillingDailyUsageMetrics({
        ...withBillingTimezone(
          {
            page_index: 1,
            page_size: ADMIN_REPORT_PAGE_SIZE,
          },
          timezone,
        ),
      })) as BillingPagedResponse<AdminBillingDailyUsageMetricItem>,
    {
      revalidateOnFocus: false,
    },
  );
  const {
    data: ledgerReports,
    error: ledgerError,
    isLoading: ledgerLoading,
  } = useSWR<BillingPagedResponse<AdminBillingDailyLedgerSummaryItem>>(
    buildBillingSwrKey('admin-billing-daily-ledger-summary', timezone),
    async () =>
      (await api.getAdminBillingDailyLedgerSummary({
        ...withBillingTimezone(
          {
            page_index: 1,
            page_size: ADMIN_REPORT_PAGE_SIZE,
          },
          timezone,
        ),
      })) as BillingPagedResponse<AdminBillingDailyLedgerSummaryItem>,
    {
      revalidateOnFocus: false,
    },
  );

  const usagePageMeta = usageReports
    ? t('module.billing.admin.pagination.page', {
        page: usageReports.page,
        pageCount: usageReports.page_count,
        total: usageReports.total,
      })
    : '';
  const ledgerPageMeta = ledgerReports
    ? t('module.billing.admin.pagination.page', {
        page: ledgerReports.page,
        pageCount: ledgerReports.page_count,
        total: ledgerReports.total,
      })
    : '';

  return (
    <div className='space-y-4'>
      <Card className='border-slate-200 bg-[linear-gradient(135deg,#eff6ff_0%,#ffffff_60%,#f8fafc_100%)] shadow-[0_18px_50px_rgba(15,23,42,0.08)]'>
        <CardHeader className='space-y-3'>
          <CardTitle className='text-lg text-slate-900'>
            {t('module.billing.admin.reports.title')}
          </CardTitle>
          <CardDescription className='leading-6 text-slate-600'>
            {t('module.billing.admin.reports.description')}
          </CardDescription>
        </CardHeader>
      </Card>

      <ReportSection
        title={t('module.billing.admin.reports.sections.usage.title')}
        description={t(
          'module.billing.admin.reports.sections.usage.description',
        )}
        pageMeta={usagePageMeta}
        loading={usageLoading}
        error={usageError}
        emptyLabel={t('module.billing.reports.loadError')}
      >
        <Table className='min-w-[1040px]'>
          <TableHeader>
            <TableRow>
              <TableHead>
                {t('module.billing.admin.reports.table.creator')}
              </TableHead>
              <TableHead>{t('module.billing.reports.table.date')}</TableHead>
              <TableHead>{t('module.billing.reports.table.shifu')}</TableHead>
              <TableHead>{t('module.billing.reports.table.scene')}</TableHead>
              <TableHead>
                {t('module.billing.reports.table.usageType')}
              </TableHead>
              <TableHead>{t('module.billing.reports.table.metric')}</TableHead>
              <TableHead>{t('module.billing.reports.table.credits')}</TableHead>
              <TableHead>
                {t('module.billing.reports.table.provider')}
              </TableHead>
              <TableHead>{t('module.billing.reports.table.window')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!usageReports?.items?.length ? (
              <TableEmpty colSpan={9}>
                {t('module.billing.reports.empty')}
              </TableEmpty>
            ) : null}
            {(usageReports?.items || []).map(item => (
              <TableRow key={item.daily_usage_metric_bid}>
                <TableCell className='font-medium text-slate-900'>
                  {item.creator_bid}
                </TableCell>
                <TableCell>
                  {formatBillingDate(item.stat_date, i18n.language)}
                </TableCell>
                <TableCell>{item.shifu_bid}</TableCell>
                <TableCell>
                  {resolveBillingUsageSceneLabel(t, item.usage_scene)}
                </TableCell>
                <TableCell>
                  {resolveBillingUsageTypeLabel(t, item.usage_type)}
                </TableCell>
                <TableCell>
                  {resolveBillingMetricLabel(t, item.billing_metric)}
                </TableCell>
                <TableCell>
                  {formatBillingCredits(item.consumed_credits, i18n.language)}
                </TableCell>
                <TableCell>{`${item.provider} / ${item.model}`}</TableCell>
                <TableCell className='text-xs text-slate-500'>
                  {`${formatBillingDateTime(
                    item.window_started_at,
                    i18n.language,
                  )} → ${formatBillingDateTime(
                    item.window_ended_at,
                    i18n.language,
                  )}`}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ReportSection>

      <ReportSection
        title={t('module.billing.admin.reports.sections.ledger.title')}
        description={t(
          'module.billing.admin.reports.sections.ledger.description',
        )}
        pageMeta={ledgerPageMeta}
        loading={ledgerLoading}
        error={ledgerError}
        emptyLabel={t('module.billing.reports.loadError')}
      >
        <Table className='min-w-[880px]'>
          <TableHeader>
            <TableRow>
              <TableHead>
                {t('module.billing.admin.reports.table.creator')}
              </TableHead>
              <TableHead>{t('module.billing.reports.table.date')}</TableHead>
              <TableHead>
                {t('module.billing.reports.table.entryType')}
              </TableHead>
              <TableHead>{t('module.billing.reports.table.source')}</TableHead>
              <TableHead>{t('module.billing.reports.table.credits')}</TableHead>
              <TableHead>{t('module.billing.reports.table.count')}</TableHead>
              <TableHead>{t('module.billing.reports.table.window')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!ledgerReports?.items?.length ? (
              <TableEmpty colSpan={7}>
                {t('module.billing.reports.empty')}
              </TableEmpty>
            ) : null}
            {(ledgerReports?.items || []).map(item => (
              <TableRow key={item.daily_ledger_summary_bid}>
                <TableCell className='font-medium text-slate-900'>
                  {item.creator_bid}
                </TableCell>
                <TableCell>
                  {formatBillingDate(item.stat_date, i18n.language)}
                </TableCell>
                <TableCell>
                  {resolveBillingLedgerEntryLabel(t, item.entry_type)}
                </TableCell>
                <TableCell>
                  {resolveBillingBucketSourceLabel(t, item.source_type)}
                </TableCell>
                <TableCell>
                  {formatBillingCredits(item.amount, i18n.language)}
                </TableCell>
                <TableCell>
                  {item.entry_count.toLocaleString(i18n.language)}
                </TableCell>
                <TableCell className='text-xs text-slate-500'>
                  {`${formatBillingDateTime(
                    item.window_started_at,
                    i18n.language,
                  )} → ${formatBillingDateTime(
                    item.window_ended_at,
                    i18n.language,
                  )}`}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ReportSection>
    </div>
  );
}
