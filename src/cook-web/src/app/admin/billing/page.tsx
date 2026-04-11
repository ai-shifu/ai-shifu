'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/Breadcrumb';
import { Tabs, TabsContent } from '@/components/ui/Tabs';
import { BillingCreditDetailsPanel } from '@/components/billing/BillingCreditDetailsPanel';
import { BillingOverviewTab } from '@/components/billing/BillingOverviewTab';
import { BillingPageHeader } from '@/components/billing/BillingPageHeader';
import { BillingRecentActivitySection } from '@/components/billing/BillingRecentActivitySection';

type BillingTab = 'packages' | 'details';
const ADMIN_HOME_HREF = '/admin';
const BILLING_PACKAGES_HREF = '/admin/billing?tab=packages';

const resolveBillingTab = (tab?: string | null): BillingTab =>
  tab === 'details' ? 'details' : 'packages';

function AdminBillingBreadcrumb({ activeTab }: { activeTab: BillingTab }) {
  const { t } = useTranslation();

  return (
    <Breadcrumb
      className='px-1'
      data-testid='admin-billing-breadcrumb'
    >
      <BreadcrumbList className='gap-2 text-sm text-muted-foreground'>
        <BreadcrumbItem>
          <BreadcrumbLink
            asChild
            className='font-normal text-muted-foreground hover:text-foreground'
          >
            <Link href={ADMIN_HOME_HREF}>
              {t('module.billing.page.breadcrumbs.home')}
            </Link>
          </BreadcrumbLink>
        </BreadcrumbItem>
        <BreadcrumbSeparator className='text-muted-foreground' />
        <BreadcrumbItem>
          {activeTab === 'packages' ? (
            <BreadcrumbPage className='font-normal text-foreground'>
              {t('module.billing.page.breadcrumbs.membership')}
            </BreadcrumbPage>
          ) : (
            <BreadcrumbLink
              asChild
              className='font-normal text-muted-foreground hover:text-foreground'
            >
              <Link href={BILLING_PACKAGES_HREF}>
                {t('module.billing.page.breadcrumbs.membership')}
              </Link>
            </BreadcrumbLink>
          )}
        </BreadcrumbItem>
        {activeTab === 'details' ? (
          <>
            <BreadcrumbSeparator className='text-muted-foreground' />
            <BreadcrumbItem>
              <BreadcrumbPage className='font-normal text-foreground'>
                {t('module.billing.page.tabs.ledger')}
              </BreadcrumbPage>
            </BreadcrumbItem>
          </>
        ) : null}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

export default function AdminBillingPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTabFromUrl = React.useMemo(
    () => resolveBillingTab(searchParams.get('tab')),
    [searchParams],
  );
  const [activeTab, setActiveTab] =
    React.useState<BillingTab>(activeTabFromUrl);
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
      <AdminBillingBreadcrumb activeTab={activeTab} />

      <Tabs
        className='space-y-6'
        value={activeTab}
      >
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
          <BillingCreditDetailsPanel onUpgrade={() => updateTab('packages')} />
          <BillingRecentActivitySection />
        </TabsContent>
      </Tabs>
    </div>
  );
}
