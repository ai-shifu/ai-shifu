'use client';

import React from 'react';
import useSWR from 'swr';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useEnvStore } from '@/c-store';
import AdminTitle from '@/app/admin/components/AdminTitle';
import { AdminBillingAdjustDialog } from '@/components/billing/AdminBillingAdjustDialog';
import { AdminBillingEntitlementsTable } from '@/components/billing/AdminBillingEntitlementsTable';
import { AdminBillingExceptionsPanel } from '@/components/billing/AdminBillingExceptionsPanel';
import { AdminBillingOrdersTable } from '@/components/billing/AdminBillingOrdersTable';
import { AdminBillingReportsPanel } from '@/components/billing/AdminBillingReportsPanel';
import { AdminBillingSubscriptionsTable } from '@/components/billing/AdminBillingSubscriptionsTable';
import { buildBillingSwrKey } from '@/lib/billing';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { Button } from '@/components/ui/Button';
import type {
  AdminBillingOrderItem,
  AdminBillingSubscriptionItem,
  BillingPagedResponse,
} from '@/types/billing';
import {
  ADMIN_BILLING_TABS_LIST_CLASSNAME,
  ADMIN_BILLING_TABS_TRIGGER_CLASSNAME,
  ADMIN_BILLING_EXCEPTION_HANDLED_EVENT,
  applyAdminBillingOpsState,
  readAdminBillingExceptionHandledMap,
  type AdminBillingCreatorTarget,
  type AdminBillingOpsState,
} from '@/components/billing/AdminBillingShared';

type AdminBillingConsoleTab =
  | 'subscriptions'
  | 'orders'
  | 'exceptions'
  | 'entitlements'
  | 'reports';

const BILLING_PASSIVE_REQUEST_CONFIG = { skipErrorToast: true } as const;
const TAB_BADGE_OVERFLOW_LABEL = '99+';
const ADMIN_BILLING_CONSOLE_TABS: AdminBillingConsoleTab[] = [
  'subscriptions',
  'orders',
  'exceptions',
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

function resolvePendingExceptionCount(params: {
  handledMap: Record<string, boolean>;
  subscriptionItems: AdminBillingSubscriptionItem[];
  orderItems: AdminBillingOrderItem[];
}): number {
  const { handledMap, subscriptionItems, orderItems } = params;
  const pendingSubscriptionCount = subscriptionItems.filter(
    item => !handledMap[`subscription:${item.subscription_bid}`],
  ).length;
  const pendingOrderCount = orderItems.filter(
    item => !handledMap[`order:${item.bill_order_bid}`],
  ).length;

  return pendingSubscriptionCount + pendingOrderCount;
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
  const [handledMap, setHandledMap] = React.useState(() =>
    readAdminBillingExceptionHandledMap(),
  );

  React.useEffect(() => {
    setActiveTab(activeTabFromUrl);
  }, [activeTabFromUrl]);

  React.useEffect(() => {
    if (!runtimeConfigLoaded || billingEnabled) {
      return;
    }
    router.replace('/admin');
  }, [billingEnabled, router, runtimeConfigLoaded]);

  React.useEffect(() => {
    const handleHandledStateChange = () => {
      setHandledMap(readAdminBillingExceptionHandledMap());
    };

    window.addEventListener(
      ADMIN_BILLING_EXCEPTION_HANDLED_EVENT,
      handleHandledStateChange,
    );
    return () => {
      window.removeEventListener(
        ADMIN_BILLING_EXCEPTION_HANDLED_EVENT,
        handleHandledStateChange,
      );
    };
  }, []);

  const { data: opsState } = useSWR<AdminBillingOpsState>(
    billingEnabled && runtimeConfigLoaded
      ? buildBillingSwrKey('admin-billing-ops-state')
      : null,
    async () =>
      (await api.getAdminBillingOpsState(
        {},
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as AdminBillingOpsState,
    { revalidateOnFocus: false },
  );

  React.useEffect(() => {
    if (!opsState) {
      return;
    }
    applyAdminBillingOpsState(opsState);
    setHandledMap(readAdminBillingExceptionHandledMap());
  }, [opsState]);

  const updateTab = React.useCallback(
    (nextTab: AdminBillingConsoleTab) => {
      setActiveTab(nextTab);
      if (typeof window === 'undefined') {
        return;
      }
      const nextParams = new URLSearchParams(window.location.search);
      nextParams.set('tab', nextTab);
      if (nextTab !== 'exceptions') {
        nextParams.delete('creator_mobile');
      }
      router.replace(`${window.location.pathname}?${nextParams.toString()}`, {
        scroll: false,
      });
    },
    [router],
  );

  const { data: subscriptionCountPage } = useSWR<
    BillingPagedResponse<AdminBillingSubscriptionItem>
  >(
    billingEnabled && runtimeConfigLoaded
      ? buildBillingSwrKey('admin-billing-subscriptions-exception-count')
      : null,
    async () =>
      (await api.getAdminBillingSubscriptions(
        {
          page_index: 1,
          page_size: 1,
          attention_only: true,
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingPagedResponse<AdminBillingSubscriptionItem>,
    { revalidateOnFocus: false },
  );

  const { data: orderCountPage } = useSWR<
    BillingPagedResponse<AdminBillingOrderItem>
  >(
    billingEnabled && runtimeConfigLoaded
      ? buildBillingSwrKey('admin-billing-orders-exception-count')
      : null,
    async () =>
      (await api.getAdminBillingOrders(
        {
          page_index: 1,
          page_size: 1,
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingPagedResponse<AdminBillingOrderItem>,
    { revalidateOnFocus: false },
  );

  const subscriptionExceptionTotal = Math.max(
    Number(subscriptionCountPage?.total || 0),
    0,
  );
  const orderExceptionTotal = Math.max(Number(orderCountPage?.total || 0), 0);

  const { data: allExceptionSubscriptions } = useSWR<
    BillingPagedResponse<AdminBillingSubscriptionItem>
  >(
    billingEnabled && runtimeConfigLoaded
      ? buildBillingSwrKey(
          'admin-billing-subscriptions-exception-badge-all',
          subscriptionExceptionTotal,
        )
      : null,
    async () =>
      (await api.getAdminBillingSubscriptions(
        {
          page_index: 1,
          page_size: Math.max(subscriptionExceptionTotal, 1),
          attention_only: true,
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingPagedResponse<AdminBillingSubscriptionItem>,
    { revalidateOnFocus: false },
  );

  const { data: allExceptionOrders } = useSWR<
    BillingPagedResponse<AdminBillingOrderItem>
  >(
    billingEnabled && runtimeConfigLoaded
      ? buildBillingSwrKey(
          'admin-billing-orders-exception-badge-all',
          orderExceptionTotal,
        )
      : null,
    async () =>
      (await api.getAdminBillingOrders(
        {
          page_index: 1,
          page_size: Math.max(orderExceptionTotal, 1),
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingPagedResponse<AdminBillingOrderItem>,
    { revalidateOnFocus: false },
  );

  const pendingExceptionCount = React.useMemo(() => {
    const subscriptionItems = allExceptionSubscriptions?.items || [];
    const orderItems = allExceptionOrders?.items || [];
    const subscriptionsReady =
      subscriptionExceptionTotal === 0 || Boolean(allExceptionSubscriptions);
    const ordersReady =
      orderExceptionTotal === 0 || Boolean(allExceptionOrders);

    if (subscriptionsReady && ordersReady) {
      return resolvePendingExceptionCount({
        handledMap,
        subscriptionItems,
        orderItems,
      });
    }

    return subscriptionExceptionTotal + orderExceptionTotal;
  }, [
    allExceptionOrders,
    allExceptionSubscriptions,
    handledMap,
    orderExceptionTotal,
    subscriptionExceptionTotal,
  ]);

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
                  value='orders'
                  className={ADMIN_BILLING_TABS_TRIGGER_CLASSNAME}
                >
                  {t('module.billing.admin.tabs.orders')}
                </TabsTrigger>
                <TabsTrigger
                  value='exceptions'
                  aria-label={t('module.billing.admin.tabs.exceptions')}
                  className={ADMIN_BILLING_TABS_TRIGGER_CLASSNAME}
                >
                  <span className='inline-flex items-center gap-2'>
                    <span>{t('module.billing.admin.tabs.exceptions')}</span>
                    {pendingExceptionCount > 0 ? (
                      <span className='inline-flex min-w-4 items-center justify-center rounded-full bg-rose-500 px-1.5 py-0 text-[10px] font-semibold leading-4 text-white'>
                        {pendingExceptionCount > 99
                          ? TAB_BADGE_OVERFLOW_LABEL
                          : pendingExceptionCount}
                      </span>
                    ) : null}
                  </span>
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
            value='orders'
            className='mt-0'
          >
            <AdminBillingOrdersTable />
          </TabsContent>
          <TabsContent
            value='exceptions'
            className='mt-0'
          >
            <AdminBillingExceptionsPanel
              onAdjustCreatorBid={openAdjustDialog}
            />
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
