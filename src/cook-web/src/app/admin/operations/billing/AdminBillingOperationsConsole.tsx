'use client';

import React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useEnvStore } from '@/c-store';
import AdminTitle from '@/app/admin/components/AdminTitle';
import { AdminBillingAdjustDialog } from '@/components/billing/AdminBillingAdjustDialog';
import { AdminBillingEntitlementsTable } from '@/components/billing/AdminBillingEntitlementsTable';
import { AdminBillingReportsPanel } from '@/components/billing/AdminBillingReportsPanel';
import { AdminBillingSubscriptionsTable } from '@/components/billing/AdminBillingSubscriptionsTable';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { Button } from '@/components/ui/Button';
import type { AdminBillingCreatorTarget } from '@/components/billing/AdminBillingShared';
import {
  ADMIN_BILLING_TABS_LIST_CLASSNAME,
  ADMIN_BILLING_TABS_TRIGGER_CLASSNAME,
} from '@/components/billing/AdminBillingShared';

type AdminBillingConsoleTab = 'subscriptions' | 'entitlements' | 'reports';

const ADMIN_BILLING_CONSOLE_TABS: AdminBillingConsoleTab[] = [
  'subscriptions',
  'entitlements',
  'reports',
];

function resolveConsoleTab(
  tab: string | null | undefined,
): AdminBillingConsoleTab {
  return ADMIN_BILLING_CONSOLE_TABS.includes(tab as AdminBillingConsoleTab)
    ? (tab as AdminBillingConsoleTab)
    : 'subscriptions';
}

export function AdminBillingOperationsConsole() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const billingEnabled = useEnvStore(state => state.billingEnabled === 'true');
  const runtimeConfigLoaded = useEnvStore(state => state.runtimeConfigLoaded);
  const activeTabFromUrl = React.useMemo(() => {
    return resolveConsoleTab(searchParams.get('tab'));
  }, [searchParams]);
  const [activeTab, setActiveTab] =
    React.useState<AdminBillingConsoleTab>(activeTabFromUrl);
  const [adjustTarget, setAdjustTarget] =
    React.useState<AdminBillingCreatorTarget | null>(null);
  const [adjustDialogOpen, setAdjustDialogOpen] = React.useState(false);

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
    (nextTab: AdminBillingConsoleTab) => {
      setActiveTab(nextTab);
      if (typeof window === 'undefined') {
        return;
      }
      const nextParams = new URLSearchParams(window.location.search);
      nextParams.set('tab', nextTab);
      nextParams.delete('creator_mobile');
      router.replace(`${window.location.pathname}?${nextParams.toString()}`, {
        scroll: false,
      });
    },
    [router],
  );

  const openAdjustDialog = React.useCallback(
    (target: AdminBillingCreatorTarget) => {
      setAdjustTarget(target);
      setAdjustDialogOpen(true);
    },
    [],
  );

  if (!runtimeConfigLoaded || !billingEnabled) {
    return null;
  }

  return (
    <div
      className='overscroll-none p-0'
      data-testid='admin-billing-console-page'
    >
      <div className='px-1 pb-6'>
        <Tabs
          className='flex flex-col'
          value={activeTab}
          onValueChange={value => updateTab(value as AdminBillingConsoleTab)}
        >
          <AdminTitle
            title={t('module.billing.admin.title')}
            description={t('module.billing.admin.subtitle')}
            actions={
              <div className='flex justify-start lg:justify-end'>
                <Button
                  type='button'
                  className='h-12 rounded-full px-6 text-base font-semibold'
                  onClick={() => openAdjustDialog({})}
                >
                  {t('module.billing.admin.adjust.open')}
                </Button>
              </div>
            }
            tabs={
              <TabsList
                data-testid='admin-billing-tabs'
                className={ADMIN_BILLING_TABS_LIST_CLASSNAME}
              >
                <TabsTrigger
                  value='subscriptions'
                  className={ADMIN_BILLING_TABS_TRIGGER_CLASSNAME}
                >
                  {t('module.billing.admin.tabs.subscriptions')}
                </TabsTrigger>
                <TabsTrigger
                  value='entitlements'
                  className={ADMIN_BILLING_TABS_TRIGGER_CLASSNAME}
                >
                  {t('module.billing.admin.tabs.entitlements')}
                </TabsTrigger>
                <TabsTrigger
                  value='reports'
                  className={ADMIN_BILLING_TABS_TRIGGER_CLASSNAME}
                >
                  {t('module.billing.admin.tabs.reports')}
                </TabsTrigger>
              </TabsList>
            }
          />

          <TabsContent
            value='subscriptions'
            className='mt-0'
          >
            <AdminBillingSubscriptionsTable />
          </TabsContent>
          <TabsContent
            value='entitlements'
            className='mt-0'
          >
            <AdminBillingEntitlementsTable />
          </TabsContent>
          <TabsContent
            value='reports'
            className='mt-0'
          >
            <AdminBillingReportsPanel />
          </TabsContent>
        </Tabs>
      </div>

      <AdminBillingAdjustDialog
        open={adjustDialogOpen}
        initialTarget={adjustTarget}
        onOpenChange={nextOpen => {
          setAdjustDialogOpen(nextOpen);
          if (!nextOpen) {
            setAdjustTarget(null);
          }
        }}
      />
    </div>
  );
}
