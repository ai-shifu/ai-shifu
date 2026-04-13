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
  resolveBillingUsageSceneLabel,
  withBillingTimezone,
} from '@/lib/billing';
import type {
  BillingDailyLedgerSummaryItem,
  BillingDailyUsageMetricItem,
  BillingMetricName,
  BillingPagedResponse,
  BillingUsageType,
} from '@/types/billing';

const REPORT_PAGE_SIZE = 8;

function resolveUsageTypeLabel(
  t: (key: string) => string,
  usageType: BillingUsageType,
): string {
  switch (usageType) {
    case 'tts':
      return t('module.billing.reports.usageType.tts');
    default:
      return t('module.billing.reports.usageType.llm');
  }
}

function resolveBillingMetricLabel(
  t: (key: string) => string,
  metric: BillingMetricName,
): string {
  switch (metric) {
    case 'llm_input_tokens':
      return t('module.billing.reports.metric.llmInputTokens');
    case 'llm_cache_tokens':
      return t('module.billing.reports.metric.llmCacheTokens');
    case 'tts_request_count':
      return t('module.billing.reports.metric.ttsRequestCount');
    case 'tts_output_chars':
      return t('module.billing.reports.metric.ttsOutputChars');
    case 'tts_input_chars':
      return t('module.billing.reports.metric.ttsInputChars');
    default:
      return t('module.billing.reports.metric.llmOutputTokens');
  }
}

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

export function BillingReportsTab() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const timezone = getBrowserTimeZone();
  const {
    data: usageReports,
    error: usageError,
    isLoading: usageLoading,
  } = useSWR<BillingPagedResponse<BillingDailyUsageMetricItem>>(
    buildBillingSwrKey('billing-daily-usage-metrics', timezone),
    async () =>
      (await api.getBillingDailyUsageMetrics({
        ...withBillingTimezone(
          {
            page_index: 1,
            page_size: REPORT_PAGE_SIZE,
          },
          timezone,
        ),
      })) as BillingPagedResponse<BillingDailyUsageMetricItem>,
    {
      revalidateOnFocus: false,
    },
  );
  const {
    data: ledgerReports,
    error: ledgerError,
    isLoading: ledgerLoading,
  } = useSWR<BillingPagedResponse<BillingDailyLedgerSummaryItem>>(
    buildBillingSwrKey('billing-daily-ledger-summary', timezone),
    async () =>
      (await api.getBillingDailyLedgerSummary({
        ...withBillingTimezone(
          {
            page_index: 1,
            page_size: REPORT_PAGE_SIZE,
          },
          timezone,
        ),
      })) as BillingPagedResponse<BillingDailyLedgerSummaryItem>,
    {
      revalidateOnFocus: false,
    },
  );

  const usagePageMeta = usageReports
    ? t('module.billing.reports.pagination.page', {
        page: usageReports.page,
        pageCount: usageReports.page_count,
        total: usageReports.total,
      })
    : '';
  const ledgerPageMeta = ledgerReports
    ? t('module.billing.reports.pagination.page', {
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
            {t('module.billing.reports.title')}
          </CardTitle>
          <CardDescription className='leading-6 text-slate-600'>
            {t('module.billing.reports.description')}
          </CardDescription>
        </CardHeader>
      </Card>

      <ReportSection
        title={t('module.billing.reports.sections.usage.title')}
        description={t('module.billing.reports.sections.usage.description')}
        pageMeta={usagePageMeta}
        loading={usageLoading}
        error={usageError}
        emptyLabel={t('module.billing.reports.loadError')}
      >
        <Table className='min-w-[880px]'>
          <TableHeader>
            <TableRow>
              <TableHead>{t('module.billing.reports.table.date')}</TableHead>
              <TableHead>{t('module.billing.reports.table.shifu')}</TableHead>
              <TableHead>{t('module.billing.reports.table.scene')}</TableHead>
              <TableHead>
                {t('module.billing.reports.table.usageType')}
              </TableHead>
              <TableHead>{t('module.billing.reports.table.metric')}</TableHead>
              <TableHead>
                {t('module.billing.reports.table.rawAmount')}
              </TableHead>
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
                <TableCell>
                  {formatBillingDate(item.stat_date, i18n.language)}
                </TableCell>
                <TableCell>{item.shifu_bid}</TableCell>
                <TableCell>
                  {resolveBillingUsageSceneLabel(t, item.usage_scene)}
                </TableCell>
                <TableCell>
                  {resolveUsageTypeLabel(t, item.usage_type)}
                </TableCell>
                <TableCell>
                  {resolveBillingMetricLabel(t, item.billing_metric)}
                </TableCell>
                <TableCell>
                  {item.raw_amount.toLocaleString(i18n.language)}
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
        title={t('module.billing.reports.sections.ledger.title')}
        description={t('module.billing.reports.sections.ledger.description')}
        pageMeta={ledgerPageMeta}
        loading={ledgerLoading}
        error={ledgerError}
        emptyLabel={t('module.billing.reports.loadError')}
      >
        <Table className='min-w-[760px]'>
          <TableHeader>
            <TableRow>
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
              <TableEmpty colSpan={6}>
                {t('module.billing.reports.empty')}
              </TableEmpty>
            ) : null}
            {(ledgerReports?.items || []).map(item => (
              <TableRow key={item.daily_ledger_summary_bid}>
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
