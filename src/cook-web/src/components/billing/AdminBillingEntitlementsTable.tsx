import React from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
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
import { useBillingAdminPagedQuery } from '@/hooks/useBillingAdminPagedQuery';
import type {
  AdminBillingEntitlementItem,
  BillingAnalyticsTier,
  BillingPagedResponse,
  BillingPriorityClass,
  BillingSupportTier,
} from '@/types/billing';
import {
  formatBillingDateTime,
  registerBillingTranslationUsage,
  resolveBillingEmptyLabel,
} from '@/lib/billing';
import { AdminBillingPager } from './AdminBillingPager';

const ADMIN_BILLING_ENTITLEMENTS_PAGE_SIZE = 10;

function resolvePriorityLabel(
  t: (key: string) => string,
  priorityClass: BillingPriorityClass,
): string {
  switch (priorityClass) {
    case 'priority':
      return t('module.billing.entitlements.priority.priority');
    case 'vip':
      return t('module.billing.entitlements.priority.vip');
    default:
      return t('module.billing.entitlements.priority.standard');
  }
}

function resolveAnalyticsLabel(
  t: (key: string) => string,
  analyticsTier: BillingAnalyticsTier,
): string {
  switch (analyticsTier) {
    case 'advanced':
      return t('module.billing.entitlements.analytics.advanced');
    case 'enterprise':
      return t('module.billing.entitlements.analytics.enterprise');
    default:
      return t('module.billing.entitlements.analytics.basic');
  }
}

function resolveSupportLabel(
  t: (key: string) => string,
  supportTier: BillingSupportTier,
): string {
  switch (supportTier) {
    case 'business_hours':
      return t('module.billing.entitlements.support.businessHours');
    case 'priority':
      return t('module.billing.entitlements.support.priority');
    default:
      return t('module.billing.entitlements.support.selfServe');
  }
}

function resolveEntitlementSourceLabel(
  t: (key: string) => string,
  item: AdminBillingEntitlementItem,
): string {
  switch (item.source_kind) {
    case 'snapshot':
      return t('module.billing.admin.entitlements.source.snapshot');
    case 'product_payload':
      return t('module.billing.admin.entitlements.source.productPayload');
    default:
      return t('module.billing.admin.entitlements.source.default');
  }
}

export function AdminBillingEntitlementsTable() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const {
    error,
    isLoading,
    items,
    page,
    pageCount,
    total,
    canGoNext,
    canGoPrev,
    goNext,
    goPrev,
  } = useBillingAdminPagedQuery<AdminBillingEntitlementItem>({
    queryKey: 'admin-billing-entitlements',
    pageSize: ADMIN_BILLING_ENTITLEMENTS_PAGE_SIZE,
    fetchPage: async params =>
      (await api.getAdminBillingEntitlements(
        params,
      )) as BillingPagedResponse<AdminBillingEntitlementItem>,
  });

  return (
    <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
      <CardHeader className='space-y-2'>
        <CardTitle className='text-lg text-slate-900'>
          {t('module.billing.admin.entitlements.title')}
        </CardTitle>
        <CardDescription className='leading-6 text-slate-600'>
          {t('module.billing.admin.entitlements.description')}
        </CardDescription>
      </CardHeader>

      <CardContent className='space-y-4'>
        {error ? (
          <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
            {t('module.billing.admin.entitlements.loadError')}
          </div>
        ) : null}

        <div className='rounded-[24px] border border-slate-200 bg-slate-50/60 px-1 py-1'>
          {isLoading ? (
            <div className='space-y-3 px-4 py-4'>
              <Skeleton className='h-12 rounded-2xl' />
              <Skeleton className='h-12 rounded-2xl' />
              <Skeleton className='h-12 rounded-2xl' />
            </div>
          ) : (
            <Table className='min-w-[1080px]'>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    {t('module.billing.admin.entitlements.table.creator')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.entitlements.table.source')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.entitlements.table.priority')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.entitlements.table.analytics')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.entitlements.table.support')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.entitlements.table.features')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.entitlements.table.window')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!items.length ? (
                  <TableEmpty colSpan={7}>
                    {t('module.billing.admin.entitlements.empty')}
                  </TableEmpty>
                ) : (
                  items.map(item => (
                    <TableRow key={`${item.creator_bid}-${item.source_kind}`}>
                      <TableCell className='min-w-[160px] font-medium text-slate-900'>
                        {item.creator_bid}
                      </TableCell>
                      <TableCell className='min-w-[220px]'>
                        <div className='space-y-1'>
                          <div className='text-slate-700'>
                            {resolveEntitlementSourceLabel(t, item)}
                          </div>
                          <div className='text-xs text-slate-500'>
                            {item.source_bid ||
                              item.product_bid ||
                              resolveBillingEmptyLabel(t)}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className='text-slate-700'>
                        {resolvePriorityLabel(t, item.priority_class)}
                      </TableCell>
                      <TableCell className='text-slate-700'>
                        {resolveAnalyticsLabel(t, item.analytics_tier)}
                      </TableCell>
                      <TableCell className='text-slate-700'>
                        {resolveSupportLabel(t, item.support_tier)}
                      </TableCell>
                      <TableCell className='min-w-[220px]'>
                        <div className='flex flex-wrap gap-2'>
                          <Badge
                            variant='outline'
                            className='border-slate-200 bg-white text-slate-700'
                          >
                            {t('module.billing.entitlements.flags.branding')} ·{' '}
                            {item.branding_enabled
                              ? t('module.billing.entitlements.flags.enabled')
                              : t('module.billing.entitlements.flags.disabled')}
                          </Badge>
                          <Badge
                            variant='outline'
                            className='border-slate-200 bg-white text-slate-700'
                          >
                            {t(
                              'module.billing.entitlements.flags.customDomain',
                            )}{' '}
                            ·{' '}
                            {item.custom_domain_enabled
                              ? t('module.billing.entitlements.flags.enabled')
                              : t('module.billing.entitlements.flags.disabled')}
                          </Badge>
                        </div>
                      </TableCell>
                      <TableCell className='min-w-[220px] text-xs text-slate-500'>
                        {`${formatBillingDateTime(item.effective_from, i18n.language) || resolveBillingEmptyLabel(t)} → ${
                          formatBillingDateTime(
                            item.effective_to,
                            i18n.language,
                          ) || t('module.billing.ledger.neverExpires')
                        }`}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </div>

        <AdminBillingPager
          canGoNext={canGoNext}
          canGoPrev={canGoPrev}
          onNext={goNext}
          onPrev={goPrev}
          page={page}
          pageCount={pageCount}
          total={total}
        />
      </CardContent>
    </Card>
  );
}
