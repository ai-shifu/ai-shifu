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
  AdminBillingOrderItem,
  BillingPagedResponse,
} from '@/types/billing';
import {
  formatBillingDateTime,
  formatBillingPrice,
  registerBillingTranslationUsage,
  resolveBillingEmptyLabel,
  resolveBillingOrderStatusLabel,
  resolveBillingOrderTypeLabel,
  resolveBillingProviderLabel,
} from '@/lib/billing';
import { AdminBillingPager } from './AdminBillingPager';

const ADMIN_BILLING_ORDERS_PAGE_SIZE = 10;

export function AdminBillingOrdersTable() {
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
  } = useBillingAdminPagedQuery<AdminBillingOrderItem>({
    queryKey: 'admin-billing-orders',
    pageSize: ADMIN_BILLING_ORDERS_PAGE_SIZE,
    fetchPage: async params =>
      (await api.getAdminBillingOrders(
        params,
      )) as BillingPagedResponse<AdminBillingOrderItem>,
  });

  return (
    <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
      <CardHeader className='space-y-2'>
        <CardTitle className='text-lg text-slate-900'>
          {t('module.billing.admin.orders.title')}
        </CardTitle>
        <CardDescription className='leading-6 text-slate-600'>
          {t('module.billing.admin.orders.description')}
        </CardDescription>
      </CardHeader>

      <CardContent className='space-y-4'>
        {error ? (
          <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
            {t('module.billing.admin.orders.loadError')}
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
                    {t('module.billing.admin.orders.table.creator')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.orders.table.order')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.orders.table.status')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.orders.table.provider')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.orders.table.amount')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.orders.table.createdAt')}
                  </TableHead>
                  <TableHead>
                    {t('module.billing.admin.orders.table.failure')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!items.length ? (
                  <TableEmpty colSpan={7}>
                    {t('module.billing.admin.orders.empty')}
                  </TableEmpty>
                ) : (
                  items.map(item => (
                    <TableRow key={item.bill_order_bid}>
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
                            {item.bill_order_bid}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className='min-w-[180px] text-slate-700'>
                        {resolveBillingOrderTypeLabel(t, item.order_type)}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant='outline'
                          className='border-slate-200 bg-slate-100 text-slate-700'
                        >
                          {resolveBillingOrderStatusLabel(t, item.status)}
                        </Badge>
                      </TableCell>
                      <TableCell className='text-slate-700'>
                        {resolveBillingProviderLabel(t, item.payment_provider)}
                      </TableCell>
                      <TableCell className='font-medium text-slate-900'>
                        {formatBillingPrice(
                          item.paid_amount || item.payable_amount,
                          item.currency,
                          i18n.language,
                        )}
                      </TableCell>
                      <TableCell className='min-w-[180px] text-slate-600'>
                        {formatBillingDateTime(item.created_at, i18n.language)}
                      </TableCell>
                      <TableCell className='min-w-[220px] text-sm text-slate-600'>
                        {item.failure_message ||
                          item.failure_code ||
                          resolveBillingEmptyLabel(t)}
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
