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
  AdminBillingDomainBindingItem,
  BillingPagedResponse,
} from '@/types/billing';
import {
  formatBillingDateTime,
  registerBillingTranslationUsage,
} from '@/lib/billing';
import {
  AdminBillingIdentityCell,
  resolveAdminBillingPaginationFootnote,
  AdminBillingSectionCard,
  resolveAdminBillingCreatorPrimary,
  resolveAdminBillingCreatorSecondary,
} from './AdminBillingShared';

const ADMIN_BILLING_DOMAIN_AUDITS_PAGE_SIZE = 10;
const BILLING_PASSIVE_REQUEST_CONFIG = { skipErrorToast: true } as const;
const EMPTY_CELL_PLACEHOLDER = '-';

export function AdminBillingDomainsTable() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const { error, isLoading, items, page, pageCount, total, setPage } =
    useBillingAdminPagedQuery<AdminBillingDomainBindingItem>({
      queryKey: 'admin-billing-domain-audits',
      pageSize: ADMIN_BILLING_DOMAIN_AUDITS_PAGE_SIZE,
      fetchPage: async params =>
        (await api.getAdminBillingDomainAudits(
          params,
          BILLING_PASSIVE_REQUEST_CONFIG,
        )) as BillingPagedResponse<AdminBillingDomainBindingItem>,
    });

  return (
    <AdminBillingSectionCard
      title={t('module.billing.admin.domains.title')}
      description={t('module.billing.admin.domains.description')}
      error={error ? t('module.billing.admin.domains.loadError') : null}
      disableContentShell
    >
      <AdminTableShell
        loading={isLoading}
        isEmpty={!items.length}
        emptyContent={t('module.billing.admin.domains.empty')}
        emptyColSpan={8}
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
          <Table className='min-w-[1080px]'>
            <TableHeader>
              <TableRow>
                <TableHead>
                  {t('module.billing.admin.domains.table.creator')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.table.attentionStatus')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.domains.table.host')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.domains.table.status')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.domains.table.effective')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.domains.table.entitlement')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.domains.table.ssl')}
                </TableHead>
                <TableHead>
                  {t('module.billing.admin.domains.table.lastVerified')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {emptyRow}
              {items.map(item => (
                <TableRow key={item.domain_binding_bid}>
                  <TableCell className='min-w-[160px]'>
                    <AdminBillingIdentityCell
                      primary={resolveAdminBillingCreatorPrimary(item)}
                      secondary={resolveAdminBillingCreatorSecondary(t, item)}
                    />
                  </TableCell>
                  <TableCell className='min-w-[110px]'>
                    {item.has_attention ? (
                      <Badge
                        variant='outline'
                        className='border-amber-200 bg-amber-50 text-amber-700'
                      >
                        {t('module.billing.admin.attention')}
                      </Badge>
                    ) : (
                      <span className='text-slate-400'>
                        {EMPTY_CELL_PLACEHOLDER}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className='min-w-[260px]'>
                    <div className='space-y-1'>
                      <div className='font-medium text-slate-900'>
                        {item.host}
                      </div>
                      <div className='text-xs text-slate-500'>
                        {item.verification_record_name}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant='outline'
                      className='border-slate-200 bg-white text-slate-700'
                    >
                      {t(`module.billing.domains.status.${item.status}`)}
                    </Badge>
                  </TableCell>
                  <TableCell className='text-slate-700'>
                    {item.is_effective
                      ? t('module.billing.admin.domains.values.effective')
                      : t('module.billing.admin.domains.values.inactive')}
                  </TableCell>
                  <TableCell className='text-slate-700'>
                    {item.custom_domain_enabled
                      ? t('module.billing.entitlements.flags.enabled')
                      : t('module.billing.entitlements.flags.disabled')}
                  </TableCell>
                  <TableCell className='text-slate-700'>
                    {t(`module.billing.domains.ssl.${item.ssl_status}`)}
                  </TableCell>
                  <TableCell className='min-w-[180px] text-slate-600'>
                    {formatBillingDateTime(
                      item.last_verified_at,
                      i18n.language,
                    ) || t('module.billing.domains.records.neverVerified')}
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
