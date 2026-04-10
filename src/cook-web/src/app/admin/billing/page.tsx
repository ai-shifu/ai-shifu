'use client';

import React from 'react';
import {
  usePathname,
  useRouter,
  useSearchParams,
} from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { BillingCreditDetailsPanel } from '@/components/billing/BillingCreditDetailsPanel';
import { BillingOverviewTab } from '@/components/billing/BillingOverviewTab';
import { BillingPageHeader } from '@/components/billing/BillingPageHeader';
import { BillingRecentActivitySection } from '@/components/billing/BillingRecentActivitySection';

type BillingTab = 'packages' | 'details';

const resolveBillingTab = (tab?: string | null): BillingTab =>
  tab === 'details' ? 'details' : 'packages';

export default function AdminBillingPage() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTabFromUrl = React.useMemo(
    () => resolveBillingTab(searchParams.get('tab')),
    [searchParams],
  );
  const [activeTab, setActiveTab] = React.useState<BillingTab>(activeTabFromUrl);
  const [scrollToOrdersRequested, setScrollToOrdersRequested] =
    React.useState(false);

  React.useEffect(() => {
    setActiveTab(activeTabFromUrl);
  }, [activeTabFromUrl]);

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

  return (
    <div
      className='flex h-full flex-col gap-6 overflow-auto px-1 pb-6'
      data-testid='admin-billing-page'
    >
      <BillingPageHeader />

      <Tabs
        className='space-y-6'
        onValueChange={value => updateTab(value as BillingTab)}
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
            onUpgrade={() => updateTab('packages')}
          />
          <BillingRecentActivitySection />
        </TabsContent>
      </Tabs>
    </div>
  );
}
