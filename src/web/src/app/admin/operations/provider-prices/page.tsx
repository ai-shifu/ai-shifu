'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import Loading from '@/components/loading';
import ErrorDisplay from '@/components/ErrorDisplay';
import { useBillingPaymentProviders } from '@/hooks/useBillingPaymentProviders';
import { useTracking } from '@/hooks/useTracking';
import { useEnvStore } from '@/store';
import { AdminBillingProviderPricesPanel } from './AdminBillingProviderPricesPanel';
import useOperatorGuard from '../useOperatorGuard';

export default function AdminOperationProviderPricesPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const { isReady } = useOperatorGuard();
  const billingEnabled = useEnvStore(state => state.billingEnabled === 'true');
  const runtimeConfigLoaded = useEnvStore(state => state.runtimeConfigLoaded);
  const { data, error, isLoading, mutate } = useBillingPaymentProviders(
    isReady && billingEnabled,
  );
  const providers = data?.items.filter(item => item.catalog) || [];
  const [selectedProvider, setSelectedProvider] = React.useState('');
  const provider = providers.some(item => item.provider === selectedProvider)
    ? selectedProvider
    : providers[0]?.provider;
  const { trackEvent } = useTracking();
  const canManageProviderPrices = billingEnabled && Boolean(provider);

  React.useEffect(() => {
    if (
      !isReady ||
      !runtimeConfigLoaded ||
      isLoading ||
      error ||
      canManageProviderPrices
    ) {
      return;
    }
    router.replace('/admin/operations');
  }, [
    canManageProviderPrices,
    error,
    isLoading,
    isReady,
    router,
    runtimeConfigLoaded,
  ]);

  if (error) {
    return (
      <ErrorDisplay
        errorCode={500}
        errorMessage={error instanceof Error ? error.message : undefined}
        onRetry={() => void mutate()}
      />
    );
  }

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
      {providers.length > 1 && (
        <label className='mb-4 flex items-center gap-3'>
          {t('module.billing.checkout.providerLabel')}
          <select
            className='rounded-md border border-input bg-background p-2'
            value={provider}
            onChange={event => {
              if (
                event.target.value === provider ||
                !providers.some(item => item.provider === event.target.value)
              )
                return;
              setSelectedProvider(event.target.value);
              try {
                void trackEvent('admin_payment_provider_selected', {
                  surface: 'prices',
                }).catch(() => {});
              } catch {}
            }}
          >
            {providers.map(item => (
              <option
                key={item.provider}
                value={item.provider}
              >
                {t(item.label_key)}
              </option>
            ))}
          </select>
        </label>
      )}
      <AdminBillingProviderPricesPanel
        key={provider}
        provider={provider}
        providerLabel={t(
          providers.find(item => item.provider === provider)!.label_key,
        )}
      />
    </>
  );
}
