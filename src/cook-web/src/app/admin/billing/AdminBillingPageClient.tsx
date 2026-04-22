'use client';

import React from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useEnvStore } from '@/c-store';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { BillingCreditDetailsPanel } from '@/components/billing/BillingCreditDetailsPanel';
import { BillingOverviewTab } from '@/components/billing/BillingOverviewTab';
import { BillingRecentActivitySection } from '@/components/billing/BillingRecentActivitySection';
import { resolveBillingTab, type BillingTab } from './billingTabs';

type AdminBillingPageClientProps = {
  initialTab?: BillingTab;
};

export function AdminBillingPageClient({
  initialTab = 'packages',
}: AdminBillingPageClientProps) {
  const { t } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const billingEnabled = useEnvStore(state => state.billingEnabled === 'true');
  const runtimeConfigLoaded = useEnvStore(state => state.runtimeConfigLoaded);
  const activeTabFromUrl = React.useMemo(
    () => resolveBillingTab(searchParams.get('tab') ?? initialTab),
    [initialTab, searchParams],
  );
  const [activeTab, setActiveTab] = React.useState<BillingTab>(initialTab);
  const [scrollToOrdersRequested, setScrollToOrdersRequested] =
    React.useState(false);

  React.useEffect(() => {
    setActiveTab(activeTabFromUrl);
  }, [activeTabFromUrl]);

  React.useEffect(() => {
    if (!runtimeConfigLoaded || billingEnabled) {
      return;
    }
    router.replace('/admin');
  }, [billingEnabled, router, runtimeConfigLoaded]);

  const updateTab = React.useCallback(
    (nextTab: BillingTab) => {
      setActiveTab(nextTab);
      const nextParams = new URLSearchParams(searchParams.toString());
      nextParams.set('tab', nextTab);
      router.replace(`${pathname}?${nextParams.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const handleOpenOrdersSection = React.useCallback(() => {
    updateTab('details');
    setScrollToOrdersRequested(true);
  }, [updateTab]);

  React.useEffect(() => {
    if (!scrollToOrdersRequested || activeTab !== 'details') {
      return;
    }
    let canceled = false;
    let attempts = 0;

    const scrollWhenReady = () => {
      if (canceled) {
        return;
      }
      const target = document.getElementById('billing-recent-orders');
      if (!target) {
        if (attempts < 10) {
          attempts += 1;
          window.setTimeout(scrollWhenReady, 0);
        }
        return;
      }
      target.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
      setScrollToOrdersRequested(false);
    };

    scrollWhenReady();

    return () => {
      canceled = true;
    };
  }, [activeTab, scrollToOrdersRequested]);

  if (!runtimeConfigLoaded || !billingEnabled) {
    return null;
  }

  return (
    <div
      className='h-full min-h-0 overflow-hidden bg-stone-50 p-0'
      data-testid='admin-billing-page'
    >
      <div className='flex h-full min-h-0 flex-col px-1 pb-6'>
        <Tabs
          className='flex min-h-0 flex-1 flex-col gap-6'
          value={activeTab}
          onValueChange={v => updateTab(v as BillingTab)}
        >
          <TabsList
            data-testid='admin-billing-tabs'
            className='shrink-0'
          >
            <TabsTrigger value='packages'>
              {t('module.billing.page.tabs.plans')}
            </TabsTrigger>
            <TabsTrigger value='details'>
              {t('module.billing.page.tabs.ledger')}
            </TabsTrigger>
          </TabsList>

          <TabsContent
            className='mt-0 min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain'
            value='packages'
            data-testid='admin-billing-packages-panel'
          >
            <div className='pb-6'>
              <BillingOverviewTab onOpenOrdersTab={handleOpenOrdersSection} />
            </div>
          </TabsContent>

          <TabsContent
            className='mt-0 min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain'
            value='details'
            data-testid='admin-billing-details-panel'
          >
            <div className='space-y-8 pb-6'>
              <BillingCreditDetailsPanel
                onUpgrade={() => updateTab('packages')}
              />
              <BillingRecentActivitySection />
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
