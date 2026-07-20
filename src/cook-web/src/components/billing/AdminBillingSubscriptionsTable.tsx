import React from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminTableShell from '@/components/admin/AdminTableShell';
import { Badge } from '@/components/ui/Badge';
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
  AdminBillingSubscriptionItem,
  BillingPagedResponse,
} from '@/types/billing';
import {
  formatBillingCreditBalance,
  formatBillingDateTime,
  registerBillingTranslationUsage,
  resolveBillingEmptyLabel,
  resolveBillingProviderLabel,
  resolveBillingSubscriptionStatusLabel,
} from '@/lib/billing';
import {
  AdminBillingIdentityCell,
  resolveAdminBillingPaginationFootnote,
  AdminBillingSectionCard,
  resolveAdminBillingCreatorPrimary,
  resolveAdminBillingCreatorSecondary,
  resolveAdminBillingProductName,
} from './AdminBillingShared';

const ADMIN_BILLING_SUBSCRIPTIONS_PAGE_SIZE = 10;
const BILLING_PASSIVE_REQUEST_CONFIG = { skipErrorToast: true } as const;

function resolveAdminBillingSubscriptionOutcome(
  t: (key: string, options?: Record<string, unknown>) => string,
  locale: string,
  item: AdminBillingSubscriptionItem,
): string {
  const currentPeriodEnd =
    formatBillingDateTime(item.current_period_end_at, locale) ||
    formatBillingDateTime(item.latest_renewal_event?.scheduled_at, locale);

  if (item.next_product_bid) {
    const product = resolveAdminBillingProductName(
      t,
      item.next_product_name_key,
      item.next_product_code || item.next_product_bid,
    );
    return currentPeriodEnd
      ? t('module.billing.admin.subscriptions.results.preorderWithDate', {
          product,
          date: currentPeriodEnd,
        })
      : t('module.billing.admin.subscriptions.results.preorder', {
          product,
        });
  }

  if (item.cancel_at_period_end) {
    return currentPeriodEnd
      ? t(
          'module.billing.admin.subscriptions.results.cancelAtPeriodEndWithDate',
          {
            date: currentPeriodEnd,
          },
        )
      : t('module.billing.admin.subscriptions.results.cancelAtPeriodEnd');
  }

  const event = item.latest_renewal_event;
  if (!event) {
    return resolveBillingEmptyLabel(t);
  }

  if (event.status === 'failed') {
    return event.last_error
      ? t('module.billing.admin.subscriptions.results.renewalFailedWithError', {
          error: event.last_error,
        })
      : t('module.billing.admin.subscriptions.results.renewalFailed');
  }

  if (event.event_type === 'expire') {
    return currentPeriodEnd
      ? t('module.billing.admin.subscriptions.results.expireWithDate', {
          date: currentPeriodEnd,
        })
      : t('module.billing.admin.subscriptions.results.expire');
  }

  if (event.event_type === 'retry' || event.event_type === 'renewal') {
    const scheduledAt =
      formatBillingDateTime(event.scheduled_at, locale) || currentPeriodEnd;
    return scheduledAt
      ? t(
          'module.billing.admin.subscriptions.results.renewalScheduledWithDate',
          {
            date: scheduledAt,
          },
        )
      : t('module.billing.admin.subscriptions.results.renewalScheduled');
  }

  if (event.event_type === 'cancel_effective') {
    return currentPeriodEnd
      ? t(
          'module.billing.admin.subscriptions.results.cancelAtPeriodEndWithDate',
          {
            date: currentPeriodEnd,
          },
        )
      : t('module.billing.admin.subscriptions.results.cancelAtPeriodEnd');
  }

  return resolveBillingEmptyLabel(t);
}

export function AdminBillingSubscriptionsTable() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const { error, isLoading, items, page, pageCount, total, setPage } =
    useBillingAdminPagedQuery<AdminBillingSubscriptionItem>({
      queryKey: 'admin-billing-subscriptions',
      pageSize: ADMIN_BILLING_SUBSCRIPTIONS_PAGE_SIZE,
      fetchPage: async params =>
        (await api.getAdminBillingSubscriptions(
          {
            ...params,
            attention_only: true,
          },
          BILLING_PASSIVE_REQUEST_CONFIG,
        )) as BillingPagedResponse<AdminBillingSubscriptionItem>,
    });

  return (
    <AdminBillingSectionCard
      title={t('module.billing.admin.subscriptions.title')}
      description={t('module.billing.admin.subscriptions.description')}
      error={error ? t('module.billing.admin.subscriptions.loadError') : null}
      disableContentShell
    >
      <AdminTableShell
        loading={isLoading}
        isEmpty={!items.length}
        emptyContent={t('module.billing.admin.subscriptions.empty')}
        emptyColSpan={7}
        pagination={{
          pageIndex: page,
          pageCount,
          onPageChange: setPage,
          prevLabel: t('module.dashboard.pagination.prev'),
          nextLabel: t('module.dashboard.pagination.next'),
          prevAriaLabel: t('module.dashboard.pagination.prev'),
          nextAriaLabel: t('module.dashboard.pagination.next'),
        }}
        footnote={resolveAdminBillingPaginationFootnote(
          t,
          page,
          pageCount,
          total,
        )}
        table={emptyRow => (
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
              {emptyRow}
              {items.map(item => (
                <TableRow key={item.subscription_bid}>
                  <TableCell className='min-w-[180px]'>
                    <AdminBillingIdentityCell
                      primary={resolveAdminBillingCreatorPrimary(item)}
                      secondary={resolveAdminBillingCreatorSecondary(t, item)}
                    />
                  </TableCell>
                  <TableCell className='min-w-[180px] text-slate-700'>
                    <div className='space-y-2'>
                      <div className='font-medium text-slate-900'>
                        {resolveAdminBillingProductName(
                          t,
                          item.product_name_key,
                          item.product_code || item.product_bid,
                        )}
                      </div>
                      {item.next_product_bid ? (
                        <Badge
                          variant='outline'
                          className='border-sky-200 bg-sky-50 text-sky-700'
                        >
                          {t(
                            'module.billing.admin.subscriptions.preorderTarget',
                            {
                              product:
                                resolveAdminBillingProductName(
                                  t,
                                  item.next_product_name_key,
                                  item.next_product_code ||
                                    item.next_product_bid,
                                ) ||
                                item.next_product_code ||
                                item.next_product_bid,
                            },
                          )}
                        </Badge>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant='outline'
                      className='border-slate-200 bg-slate-100 text-slate-700'
                    >
                      {resolveBillingSubscriptionStatusLabel(t, item.status)}
                    </Badge>
                  </TableCell>
                  <TableCell className='text-slate-700'>
                    {resolveBillingProviderLabel(t, item.billing_provider)}
                  </TableCell>
                  <TableCell className='font-medium text-slate-900'>
                    {formatBillingCreditBalance(item.wallet.available_credits)}
                  </TableCell>
                  <TableCell className='min-w-[180px] text-slate-600'>
                    {formatBillingDateTime(
                      item.current_period_end_at,
                      i18n.language,
                    ) || resolveBillingEmptyLabel(t)}
                  </TableCell>
                  <TableCell className='min-w-[280px] text-sm text-slate-600'>
                    {resolveAdminBillingSubscriptionOutcome(
                      t,
                      i18n.language,
                      item,
                    )}
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
