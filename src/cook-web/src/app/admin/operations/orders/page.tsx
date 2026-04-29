'use client';

import React from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import AdminTimezoneHint from '@/app/admin/components/AdminTimezoneHint';
import Loading from '@/components/loading';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import useOperatorGuard from '../useOperatorGuard';
import {
  ORDER_TABS_LIST_CLASSNAME,
  ORDER_TABS_TRIGGER_CLASSNAME,
} from './orderUiShared';
import LearnOrdersTab from './LearnOrdersTab';
import CreditOrdersTab from './CreditOrdersTab';
import {
  resolveOperationOrdersTab,
  type OperationOrdersTab,
} from './orderTabs';

/**
 * t('module.operationsOrder.title')
 * t('module.operationsOrder.tabs.learn')
 * t('module.operationsOrder.tabs.credits')
 */
export default function AdminOperationOrdersPage() {
  const { t } = useTranslation('module.operationsOrder');
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isReady } = useOperatorGuard();
  const activeTabFromUrl = React.useMemo(
    () => resolveOperationOrdersTab(searchParams.get('tab')),
    [searchParams],
  );
  const [activeTab, setActiveTab] =
    React.useState<OperationOrdersTab>(activeTabFromUrl);

  React.useEffect(() => {
    setActiveTab(activeTabFromUrl);
  }, [activeTabFromUrl]);

  const updateTab = React.useCallback(
    (nextTab: OperationOrdersTab) => {
      setActiveTab(nextTab);
      const nextParams = new URLSearchParams(searchParams.toString());
      if (nextTab === 'learn') {
        nextParams.delete('tab');
      } else {
        nextParams.set('tab', nextTab);
      }
      const nextQuery = nextParams.toString();
      router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, {
        scroll: false,
      });
    },
    [pathname, router, searchParams],
  );

  if (!isReady) {
    return <Loading />;
  }

  return (
    <div className='flex h-full flex-col gap-5 p-0'>
      <div>
        <h1 className='text-2xl font-semibold text-gray-900'>{t('title')}</h1>
        <AdminTimezoneHint
          namespace='module.operationsOrder'
          textKey='timezoneHint'
          className='mt-1'
        />
      </div>

      <Tabs
        value={activeTab}
        className='flex h-full flex-col gap-5'
        onValueChange={value => updateTab(value as OperationOrdersTab)}
      >
        <TabsList
          className={ORDER_TABS_LIST_CLASSNAME}
          data-testid='admin-operation-orders-tabs'
        >
          <TabsTrigger
            value='learn'
            className={ORDER_TABS_TRIGGER_CLASSNAME}
          >
            {t('tabs.learn')}
          </TabsTrigger>
          <TabsTrigger
            value='credits'
            className={ORDER_TABS_TRIGGER_CLASSNAME}
          >
            {t('tabs.credits')}
          </TabsTrigger>
        </TabsList>

        <div className='min-h-0 flex-1'>
          {activeTab === 'learn' ? <LearnOrdersTab /> : <CreditOrdersTab />}
        </div>
      </Tabs>
    </div>
  );
}
