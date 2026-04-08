import React, { useState } from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
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
import type {
  AdminBillingSubscriptionItem,
  BillingPagedResponse,
} from '@/types/billing';
import {
  formatBillingCredits,
  formatBillingDateTime,
  registerBillingTranslationUsage,
  resolveBillingProviderLabel,
  resolveBillingSubscriptionStatusLabel,
} from '@/lib/billing';

const ADMIN_BILLING_SUBSCRIPTIONS_PAGE_SIZE = 10;

export function AdminBillingSubscriptionsTable() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const [pageIndex, setPageIndex] = useState(1);
  const { data, error, isLoading } = useSWR<
    BillingPagedResponse<AdminBillingSubscriptionItem>
  >(
    ['admin-billing-subscriptions', pageIndex],
    async () =>
      (await api.getAdminBillingSubscriptions({
        page_index: pageIndex,
        page_size: ADMIN_BILLING_SUBSCRIPTIONS_PAGE_SIZE,
      })) as BillingPagedResponse<AdminBillingSubscriptionItem>,
    {
      revalidateOnFocus: false,
    },
  );

  const items = data?.items || [];
  const canGoPrev = pageIndex > 1;
  const canGoNext = pageIndex < Number(data?.page_count || 1);

  return (
    <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
      <CardHeader className='space-y-2'>
        <CardTitle className='text-lg text-slate-900'>
          {t('module.billing.admin.subscriptions.title')}
        </CardTitle>
        <CardDescription className='leading-6 text-slate-600'>
          {t('module.billing.admin.subscriptions.description')}
        </CardDescription>
      </CardHeader>

      <CardContent className='space-y-4'>
        {error ? (
          <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
            {t('module.billing.admin.subscriptions.loadError')}
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
            <Table className='min-w-[980px]'>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    {t('module.billing.admin.subscriptions.table.creator')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.subscriptions.table.product')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.subscriptions.table.status')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.subscriptions.table.provider')}
                  </TableHead>
                  <TableHead>
                    {t(
                      'module.billing.admin.subscriptions.table.availableCredits',
                    )}
                  </TableHead>
                  <TableHead>
                    {t(
                      'module.billing.admin.subscriptions.table.currentPeriodEnd',
                    )}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.subscriptions.table.renewal')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!items.length ? (
                  <TableEmpty colSpan={7}>
                    {t('module.billing.admin.subscriptions.empty')}
                  </TableEmpty>
                ) : (
                  items.map(item => (
                    <TableRow key={item.subscription_bid}>
                      <TableCell className='min-w-[180px]'>
                        <div className='space-y-1'>
                          <div className='flex items-center gap-2'>
                            <span className='font-medium text-slate-900'>
                              {item.creator_bid}
                            </span>
                            {item.has_attention ? (
                              <Badge
                                variant='outline'
                                className='border-amber-200 bg-amber-50 text-amber-700'
                              >
                                {t('module.billing.admin.attention')}
                              </Badge>
                            ) : null}
                          </div>
                          <div className='text-xs text-slate-500'>
                            {item.subscription_bid}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className='min-w-[180px] text-slate-700'>
                        {item.product_code || item.product_bid}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant='outline'
                          className='border-slate-200 bg-slate-100 text-slate-700'
                        >
                          {resolveBillingSubscriptionStatusLabel(
                            t,
                            item.status,
                          )}
                        </Badge>
                      </TableCell>
                      <TableCell className='text-slate-700'>
                        {resolveBillingProviderLabel(t, item.billing_provider)}
                      </TableCell>
                      <TableCell className='font-medium text-slate-900'>
                        {formatBillingCredits(
                          item.wallet.available_credits,
                          i18n.language,
                        )}
                      </TableCell>
                      <TableCell className='min-w-[180px] text-slate-600'>
                        {formatBillingDateTime(
                          item.current_period_end_at,
                          i18n.language,
                        ) || '--'}
                      </TableCell>
                      <TableCell className='min-w-[240px] text-sm text-slate-600'>
                        {item.latest_renewal_event?.last_error ||
                          (formatBillingDateTime(
                            item.latest_renewal_event?.scheduled_at,
                            i18n.language,
                          ) &&
                            `${t('module.billing.admin.subscriptions.table.scheduled')} ${formatBillingDateTime(
                              item.latest_renewal_event?.scheduled_at,
                              i18n.language,
                            )}`) ||
                          '--'}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </div>

        <div className='flex flex-wrap items-center justify-between gap-3'>
          <div className='text-sm text-slate-500'>
            {t('module.billing.admin.pagination.page', {
              page: data?.page || pageIndex,
              pageCount: data?.page_count || 1,
              total: data?.total || 0,
            })}
          </div>
          <div className='flex gap-2'>
            <Button
              variant='outline'
              disabled={!canGoPrev}
              onClick={() => setPageIndex(current => Math.max(1, current - 1))}
            >
              {t('common.page.previous')}
            </Button>
            <Button
              variant='outline'
              disabled={!canGoNext}
              onClick={() => setPageIndex(current => current + 1)}
            >
              {t('common.page.next')}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
