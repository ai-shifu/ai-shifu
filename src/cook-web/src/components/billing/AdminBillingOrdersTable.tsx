import React from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminTableShell from '@/components/admin/AdminTableShell';
import {
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/components/admin/adminTableStyles';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  Table,
  TableBody,
  TableCell,
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
  resolveBillingOrderStatusLabel,
  resolveBillingOrderTypeLabel,
  resolveBillingProviderLabel,
} from '@/lib/billing';
import {
  AdminBillingIdentityCell,
  resolveAdminBillingOrderFailure,
  resolveAdminBillingOrderProductName,
  resolveAdminBillingPaginationFootnote,
  AdminBillingSectionCard,
  resolveAdminBillingCreatorPrimary,
  resolveAdminBillingCreatorSecondary,
} from './AdminBillingShared';

const ADMIN_BILLING_ORDERS_PAGE_SIZE = 10;
const BILLING_PASSIVE_REQUEST_CONFIG = { skipErrorToast: true } as const;

export function AdminBillingOrdersTable() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  registerBillingTranslationUsage(t);
  const { error, isLoading, items, page, pageCount, total, setPage } =
    useBillingAdminPagedQuery<AdminBillingOrderItem>({
      queryKey: 'admin-billing-orders',
      pageSize: ADMIN_BILLING_ORDERS_PAGE_SIZE,
      fetchPage: async params =>
        (await api.getAdminBillingOrders(
          params,
          BILLING_PASSIVE_REQUEST_CONFIG,
        )) as BillingPagedResponse<AdminBillingOrderItem>,
    });
  const attentionItems = items.filter(item => item.has_attention);
  const hasRows = attentionItems.length > 0;
  const handleViewOrder = React.useCallback(
    (item: AdminBillingOrderItem) => {
      const params = new URLSearchParams();
      params.set('tab', 'credits');
      if (item.creator_mobile) {
        params.set('creator_keyword', item.creator_mobile);
      }
      if (item.bill_order_bid) {
        params.set('bill_order_bid', item.bill_order_bid);
      }
      if (item.status) {
        params.set('status', item.status);
      }
      if (item.order_type === 'topup') {
        params.set('credit_order_kind', 'topup');
      }
      if (
        item.order_type === 'subscription_renewal' ||
        item.order_type === 'subscription_start' ||
        item.order_type === 'subscription_upgrade'
      ) {
        params.set('credit_order_kind', 'plan');
      }
      router.push(`/admin/operations/orders?${params.toString()}`);
    },
    [router],
  );

  return (
    <AdminBillingSectionCard
      title={t('module.billing.admin.orders.title')}
      description={t('module.billing.admin.orders.description')}
      error={error ? t('module.billing.admin.orders.loadError') : null}
      disableContentShell
    >
      <AdminTableShell
        loading={isLoading}
        isEmpty={!attentionItems.length}
        emptyContent={t('module.billing.admin.orders.empty')}
        emptyColSpan={8}
        stickyActionEmpty={{
          contentColSpan: 7,
          actionClassName: getAdminStickyRightCellClass(
            'w-[96px] min-w-[96px]',
          ),
        }}
        pagination={
          hasRows
            ? {
                pageIndex: page,
                pageCount,
                onPageChange: setPage,
                prevLabel: t('module.dashboard.pagination.prev'),
                nextLabel: t('module.dashboard.pagination.next'),
                prevAriaLabel: t('module.dashboard.pagination.prev'),
                nextAriaLabel: t('module.dashboard.pagination.next'),
              }
            : undefined
        }
        footnote={
          hasRows
            ? resolveAdminBillingPaginationFootnote(t, page, pageCount, total)
            : null
        }
        table={emptyRow => (
          <Table className='min-w-[1100px]'>
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
                <TableHead
                  className={getAdminStickyRightHeaderClass(
                    'w-[96px] min-w-[96px] text-center',
                  )}
                >
                  {t('module.billing.admin.orders.table.actions')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {emptyRow}
              {attentionItems.map(item => (
                <TableRow key={item.bill_order_bid}>
                  <TableCell className='min-w-[180px]'>
                    <AdminBillingIdentityCell
                      primary={resolveAdminBillingCreatorPrimary(item)}
                      secondary={resolveAdminBillingCreatorSecondary(t, item)}
                    />
                  </TableCell>
                  <TableCell className='min-w-[180px] text-slate-700'>
                    <div className='space-y-1.5'>
                      <div className='font-medium text-slate-900'>
                        {resolveAdminBillingOrderProductName(t, item)}
                      </div>
                      <div className='text-xs text-slate-500'>
                        {resolveBillingOrderTypeLabel(t, item.order_type)}
                      </div>
                    </div>
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
                    {resolveAdminBillingOrderFailure(t, item)}
                  </TableCell>
                  <TableCell
                    className={getAdminStickyRightCellClass(
                      'w-[96px] min-w-[96px] text-center',
                    )}
                  >
                    <Button
                      variant='ghost'
                      size='sm'
                      className='h-auto px-0 py-0 text-sm font-semibold text-[#2563EB] hover:bg-transparent hover:text-[#1D4ED8]'
                      onClick={() => handleViewOrder(item)}
                    >
                      {t('module.billing.admin.orders.actions.viewOrder')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      />
    </AdminBillingSectionCard>
  );
}
