'use client';

import React from 'react';
import Link from 'next/link';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { Button } from '@/components/ui/Button';
import { useTranslation } from 'react-i18next';
import {
  BillingDomainsTab,
  BillingEntitlementsTab,
  BillingLedgerTab,
  BillingOrdersTab,
  BillingOverviewTab,
  BillingPageHeader,
  BillingReportsTab,
} from '@/components/billing';
import { BillingCenterTab } from '@/types/billing';

export default function AdminBillingPage() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = React.useState<BillingCenterTab>('plans');

  return (
    <div
      className='flex h-full flex-col gap-6 overflow-auto pb-4'
      data-testid='admin-billing-page'
    >
      <BillingPageHeader />

      <div className='flex justify-end'>
        <Button
          asChild
          variant='outline'
          className='rounded-full'
        >
          <Link href='/admin/billing/admin'>
            {t('module.billing.page.adminLink')}
          </Link>
        </Button>
      </div>

      <Tabs
        value={activeTab}
        className='flex flex-col gap-4'
        onValueChange={value => setActiveTab(value as BillingCenterTab)}
      >
        <TabsList className='h-11 rounded-full bg-white/80 p-1 shadow-sm'>
          <TabsTrigger value='plans'>
            {t('module.billing.page.tabs.plans')}
          </TabsTrigger>
          <TabsTrigger value='ledger'>
            {t('module.billing.page.tabs.ledger')}
          </TabsTrigger>
          <TabsTrigger value='orders'>
            {t('module.billing.page.tabs.orders')}
          </TabsTrigger>
          <TabsTrigger value='entitlements'>
            {t('module.billing.page.tabs.entitlements')}
          </TabsTrigger>
          <TabsTrigger value='domains'>
            {t('module.billing.page.tabs.domains')}
          </TabsTrigger>
          <TabsTrigger value='reports'>
            {t('module.billing.page.tabs.reports')}
          </TabsTrigger>
        </TabsList>

        <TabsContent
          value='plans'
          className='space-y-4'
        >
          <BillingOverviewTab onOpenOrdersTab={() => setActiveTab('orders')} />
        </TabsContent>

        <TabsContent value='ledger'>
          <BillingLedgerTab />
        </TabsContent>

        <TabsContent value='orders'>
          <BillingOrdersTab />
        </TabsContent>

        <TabsContent value='entitlements'>
          <BillingEntitlementsTab />
        </TabsContent>

        <TabsContent value='domains'>
          <BillingDomainsTab />
        </TabsContent>

        <TabsContent value='reports'>
          <BillingReportsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
