'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import Loading from '@/components/loading';
import { AdminBillingProviderPricesPanel } from './AdminBillingProviderPricesPanel';
import useOperatorGuard from '../useOperatorGuard';

export default function AdminOperationProviderPricesPage() {
  const { t } = useTranslation();
  const { isReady } = useOperatorGuard();

  if (!isReady) {
    return <Loading />;
  }

  return (
    <>
      <AdminBreadcrumb
        items={[{ label: t('module.billing.admin.providerPrices.menuTitle') }]}
      />
      <AdminTitle
        title={t('module.billing.admin.providerPrices.menuTitle')}
        description={t('module.billing.admin.providerPrices.pageDescription')}
      />
      <AdminBillingProviderPricesPanel />
    </>
  );
}
