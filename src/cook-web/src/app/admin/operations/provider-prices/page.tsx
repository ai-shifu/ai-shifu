'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import Loading from '@/components/loading';
import { useEnvStore } from '@/c-store';
import { AdminBillingProviderPricesPanel } from './AdminBillingProviderPricesPanel';
import useOperatorGuard from '../useOperatorGuard';

export default function AdminOperationProviderPricesPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const { isReady } = useOperatorGuard();
  const billingEnabled = useEnvStore(state => state.billingEnabled === 'true');
  const stripeEnabled = useEnvStore(state => state.stripeEnabled === 'true');
  const paymentChannels = useEnvStore(state => state.paymentChannels);
  const runtimeConfigLoaded = useEnvStore(state => state.runtimeConfigLoaded);
  const hasStripeChannel = React.useMemo(
    () =>
      (Array.isArray(paymentChannels) ? paymentChannels : []).some(
        channel =>
          String(channel || '')
            .trim()
            .toLowerCase() === 'stripe',
      ),
    [paymentChannels],
  );
  const canManageProviderPrices =
    billingEnabled && stripeEnabled && hasStripeChannel;

  React.useEffect(() => {
    if (!runtimeConfigLoaded || canManageProviderPrices) {
      return;
    }
    router.replace('/admin/operations');
  }, [canManageProviderPrices, router, runtimeConfigLoaded]);

  if (!isReady || !runtimeConfigLoaded || !canManageProviderPrices) {
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
