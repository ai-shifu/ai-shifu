'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  BillingCreditDetailsPanel,
  BillingOverviewTab,
  BillingPageHeader,
  BillingRecentActivitySection,
} from '@/components/billing';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';

export default function AdminBillingPage() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = React.useState<'packages' | 'details'>(
    'packages',
  );
  const [scrollToOrdersRequested, setScrollToOrdersRequested] =
    React.useState(false);

  const handleOpenOrdersSection = React.useCallback(() => {
    setActiveTab('details');
    setScrollToOrdersRequested(true);
  }, []);

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

  return (
    <div
      className='flex h-full flex-col gap-6 overflow-auto px-1 pb-6'
      data-testid='admin-billing-page'
    >
      <BillingPageHeader />

      <Tabs
        className='space-y-6'
        onValueChange={value => setActiveTab(value as 'packages' | 'details')}
        value={activeTab}
      >
        <TabsList className='h-auto rounded-xl border border-slate-200 bg-white p-1 shadow-sm'>
          <TabsTrigger
            className='rounded-lg px-4 py-2 text-sm font-semibold text-slate-500 data-[state=active]:bg-slate-950 data-[state=active]:text-white'
            value='packages'
          >
            {t('module.billing.page.tabs.plans')}
          </TabsTrigger>
          <TabsTrigger
            className='rounded-lg px-4 py-2 text-sm font-semibold text-slate-500 data-[state=active]:bg-slate-950 data-[state=active]:text-white'
            value='details'
          >
            {t('module.billing.page.tabs.ledger')}
          </TabsTrigger>
        </TabsList>

        <TabsContent
          className='mt-0'
          value='packages'
        >
          <BillingOverviewTab onOpenOrdersTab={handleOpenOrdersSection} />
        </TabsContent>

        <TabsContent
          className='mt-0 space-y-8'
          value='details'
        >
          <BillingCreditDetailsPanel
            onUpgrade={() => setActiveTab('packages')}
          />
          <BillingRecentActivitySection />
        </TabsContent>
      </Tabs>
    </div>
  );
}
