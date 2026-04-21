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
  AdminBillingSubscriptionItem,
  BillingPagedResponse,
} from '@/types/billing';
import {
  buildBillingRenewalContextLabel,
  formatBillingCreditBalance,
  formatBillingDateTime,
  registerBillingTranslationUsage,
  resolveBillingEmptyLabel,
  resolveBillingRenewalEventStatusLabel,
  resolveBillingRenewalEventTypeLabel,
  resolveBillingProviderLabel,
  resolveBillingSubscriptionStatusLabel,
} from '@/lib/billing';
import { AdminBillingPager } from './AdminBillingPager';

const ADMIN_BILLING_SUBSCRIPTIONS_PAGE_SIZE = 10;

export function AdminBillingSubscriptionsTable() {
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
  } = useBillingAdminPagedQuery<AdminBillingSubscriptionItem>({
    queryKey: 'admin-billing-subscriptions',
    pageSize: ADMIN_BILLING_SUBSCRIPTIONS_PAGE_SIZE,
    fetchPage: async params =>
      (await api.getAdminBillingSubscriptions(
        params,
      )) as BillingPagedResponse<AdminBillingSubscriptionItem>,
  });

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
                  <TableHead>
                    {t(
                      'module.billing.admin.subscriptions.table.renewalStatus',
                    )}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!items.length ? (
                  <TableEmpty colSpan={8}>
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
                        {formatBillingCreditBalance(
                          item.wallet.available_credits,
                        )}
                      </TableCell>
                      <TableCell className='min-w-[180px] text-slate-600'>
                        {formatBillingDateTime(
                          item.current_period_end_at,
                          i18n.language,
                        ) || resolveBillingEmptyLabel(t)}
                      </TableCell>
                      <TableCell className='min-w-[240px] text-sm text-slate-600'>
                        {buildBillingRenewalContextLabel(
                          t,
                          i18n.language,
                          item.latest_renewal_event,
                        )}
                      </TableCell>
                      <TableCell className='min-w-[220px]'>
                        {item.latest_renewal_event ? (
                          <div className='flex flex-wrap gap-2'>
                            <Badge
                              variant='outline'
                              className='border-sky-200 bg-sky-50 text-sky-700'
                            >
                              {resolveBillingRenewalEventTypeLabel(
                                t,
                                item.latest_renewal_event.event_type,
                              )}
                            </Badge>
                            <Badge
                              variant='outline'
                              className='border-violet-200 bg-violet-50 text-violet-700'
                            >
                              {resolveBillingRenewalEventStatusLabel(
                                t,
                                item.latest_renewal_event.status,
                              )}
                            </Badge>
                          </div>
                        ) : (
                          <span className='text-sm text-slate-500'>
                            {resolveBillingEmptyLabel(t)}
                          </span>
                        )}
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
