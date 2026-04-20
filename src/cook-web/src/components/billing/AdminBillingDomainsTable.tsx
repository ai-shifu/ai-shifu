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
  AdminBillingDomainBindingItem,
  BillingPagedResponse,
} from '@/types/billing';
import {
  formatBillingDateTime,
  registerBillingTranslationUsage,
} from '@/lib/billing';
import { AdminBillingPager } from './AdminBillingPager';

const ADMIN_BILLING_DOMAIN_AUDITS_PAGE_SIZE = 10;

export function AdminBillingDomainsTable() {
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
  } = useBillingAdminPagedQuery<AdminBillingDomainBindingItem>({
    queryKey: 'admin-billing-domain-audits',
    pageSize: ADMIN_BILLING_DOMAIN_AUDITS_PAGE_SIZE,
    fetchPage: async params =>
      (await api.getAdminBillingDomainAudits(
        params,
      )) as BillingPagedResponse<AdminBillingDomainBindingItem>,
  });

  return (
    <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
      <CardHeader className='space-y-2'>
        <CardTitle className='text-lg text-slate-900'>
          {t('module.billing.admin.domains.title')}
        </CardTitle>
        <CardDescription className='leading-6 text-slate-600'>
          {t('module.billing.admin.domains.description')}
        </CardDescription>
      </CardHeader>

      <CardContent className='space-y-4'>
        {error ? (
          <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
            {t('module.billing.admin.domains.loadError')}
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
                    {t('module.billing.admin.domains.table.creator')}
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
                {!items.length ? (
                  <TableEmpty colSpan={7}>
                    {t('module.billing.admin.domains.empty')}
                  </TableEmpty>
                ) : (
                  items.map(item => (
                    <TableRow key={item.domain_binding_bid}>
                      <TableCell className='min-w-[160px]'>
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
