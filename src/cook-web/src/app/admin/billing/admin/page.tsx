'use client';

import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useEnvStore } from '@/c-store';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { Button } from '@/components/ui/Button';
import { AdminBillingConsoleTab } from '@/types/billing';
import { AdminBillingAdjustDialog } from '@/components/billing/AdminBillingAdjustDialog';
import { BillingCapabilitySummary } from '@/components/billing/BillingCapabilitySummary';
import { AdminBillingDomainsTable } from '@/components/billing/AdminBillingDomainsTable';
import { AdminBillingEntitlementsTable } from '@/components/billing/AdminBillingEntitlementsTable';
import { AdminBillingExceptionsPanel } from '@/components/billing/AdminBillingExceptionsPanel';
import { AdminBillingOrdersTable } from '@/components/billing/AdminBillingOrdersTable';
import { AdminBillingReportsPanel } from '@/components/billing/AdminBillingReportsPanel';
import { AdminBillingSubscriptionsTable } from '@/components/billing/AdminBillingSubscriptionsTable';

export default function AdminBillingConsolePage() {
  const { t } = useTranslation();
  const router = useRouter();
  const billingEnabled = useEnvStore(state => state.billingEnabled === 'true');
  const runtimeConfigLoaded = useEnvStore(state => state.runtimeConfigLoaded);
  const [activeTab, setActiveTab] =
    React.useState<AdminBillingConsoleTab>('subscriptions');
  const [adjustDialogOpen, setAdjustDialogOpen] = React.useState(false);
  const [adjustCreatorBid, setAdjustCreatorBid] = React.useState('');

  const handleOpenAdjustDialog = (creatorBid = '') => {
    setAdjustCreatorBid(creatorBid);
    setAdjustDialogOpen(true);
  };

  React.useEffect(() => {
    if (!runtimeConfigLoaded || billingEnabled) {
      return;
    }
    router.replace('/admin');
  }, [billingEnabled, router, runtimeConfigLoaded]);

  if (!runtimeConfigLoaded || !billingEnabled) {
    return null;
  }

  return (
    <>
      <div
        className='flex h-full flex-col pb-4'
        data-testid='admin-billing-console-page'
      >
        <AdminBreadcrumb
          items={[
            {
              label: t('module.billing.page.title'),
              href: '/admin/billing',
            },
            { label: t('module.billing.admin.title') },
          ]}
        />
        <Tabs
          value={activeTab}
          className='flex flex-col'
          onValueChange={value => setActiveTab(value as AdminBillingConsoleTab)}
        >
          <AdminTitle
            title={t('module.billing.admin.title')}
            description={t('module.billing.admin.subtitle')}
            actions={
              <div className='flex flex-wrap items-center gap-2 lg:justify-end'>
                <Button
                  className='rounded-full'
                  onClick={() => handleOpenAdjustDialog()}
                >
                  {t('module.billing.admin.adjust.open')}
                </Button>
                <Button
                  asChild
                  variant='outline'
                  className='rounded-full'
                >
                  <Link href='/admin/billing'>
                    {t('module.billing.admin.backToCreatorBilling')}
                  </Link>
                </Button>
              </div>
            }
            tabs={
              <TabsList className='h-11 rounded-full bg-white/80 p-1 shadow-sm'>
                <TabsTrigger value='subscriptions'>
                  {t('module.billing.admin.tabs.subscriptions')}
                </TabsTrigger>
                <TabsTrigger value='orders'>
                  {t('module.billing.admin.tabs.orders')}
                </TabsTrigger>
                <TabsTrigger value='exceptions'>
                  {t('module.billing.admin.tabs.exceptions')}
                </TabsTrigger>
                <TabsTrigger value='entitlements'>
                  {t('module.billing.admin.tabs.entitlements')}
                </TabsTrigger>
                <TabsTrigger value='domains'>
                  {t('module.billing.admin.tabs.domains')}
                </TabsTrigger>
                <TabsTrigger value='reports'>
                  {t('module.billing.admin.tabs.reports')}
                </TabsTrigger>
              </TabsList>
            }
          />

          <div className='mb-6'>
            <BillingCapabilitySummary audience='admin' />
          </div>
          <TabsContent
            value='subscriptions'
            className='space-y-4'
          >
            <AdminBillingSubscriptionsTable />
          </TabsContent>

          <TabsContent
            value='orders'
            className='space-y-4'
          >
            <AdminBillingOrdersTable />
          </TabsContent>

          <TabsContent
            value='exceptions'
            className='space-y-4'
          >
            <AdminBillingExceptionsPanel
              onAdjustCreatorBid={handleOpenAdjustDialog}
            />
          </TabsContent>

          <TabsContent
            value='entitlements'
            className='space-y-4'
          >
            <AdminBillingEntitlementsTable />
          </TabsContent>

          <TabsContent
            value='domains'
            className='space-y-4'
          >
            <AdminBillingDomainsTable />
          </TabsContent>

          <TabsContent
            value='reports'
            className='space-y-4'
          >
            <AdminBillingReportsPanel />
          </TabsContent>
        </Tabs>
      </div>

      <AdminBillingAdjustDialog
        open={adjustDialogOpen}
        initialCreatorBid={adjustCreatorBid}
        onOpenChange={setAdjustDialogOpen}
      />
    </>
  );
}
