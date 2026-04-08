'use client';

import React from 'react';
import { Badge } from '@/components/ui/Badge';
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { useTranslation } from 'react-i18next';

const MetricCard = ({ label, value }: { label: string; value: string }) => (
  <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
    <CardHeader className='pb-3'>
      <CardDescription>{label}</CardDescription>
      <CardTitle className='text-3xl font-semibold tracking-tight text-slate-900'>
        {value}
      </CardTitle>
    </CardHeader>
  </Card>
);

const PlaceholderSection = ({
  title,
  description,
}: {
  title: string;
  description: string;
}) => (
  <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
    <CardHeader>
      <CardTitle className='text-lg text-slate-900'>{title}</CardTitle>
      <CardDescription className='leading-6'>{description}</CardDescription>
    </CardHeader>
  </Card>
);

export default function AdminBillingPage() {
  const { t } = useTranslation();
  const placeholderValue = t('module.billing.sidebar.placeholderValue');
  const pendingValue = t('module.billing.overview.pendingValue');

  return (
    <div
      className='flex h-full flex-col gap-6 overflow-auto pb-4'
      data-testid='admin-billing-page'
    >
      <div className='flex flex-col gap-3 rounded-[28px] border border-slate-200 bg-[linear-gradient(135deg,#fff7ed_0%,#ffffff_58%,#f8fafc_100%)] p-6 shadow-[0_18px_50px_rgba(15,23,42,0.08)]'>
        <div className='flex items-center gap-3'>
          <Badge className='rounded-full bg-amber-100 px-3 py-1 text-amber-800 hover:bg-amber-100'>
            {t('module.billing.page.badge')}
          </Badge>
          <span className='text-sm text-slate-500'>
            {t('module.billing.page.subtitle')}
          </span>
        </div>
        <div>
          <h2 className='text-3xl font-semibold tracking-tight text-slate-900'>
            {t('module.billing.page.title')}
          </h2>
        </div>
      </div>

      <Tabs
        defaultValue='plans'
        className='flex flex-col gap-4'
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
        </TabsList>

        <TabsContent
          value='plans'
          className='space-y-4'
        >
          <div>
            <h3 className='text-lg font-semibold text-slate-900'>
              {t('module.billing.overview.walletTitle')}
            </h3>
          </div>
          <div className='grid gap-4 md:grid-cols-3'>
            <MetricCard
              label={t('module.billing.overview.availableCreditsLabel')}
              value={placeholderValue}
            />
            <MetricCard
              label={t('module.billing.overview.subscriptionStatusLabel')}
              value={pendingValue}
            />
            <MetricCard
              label={t('module.billing.overview.nextActionLabel')}
              value={pendingValue}
            />
          </div>
          <div className='grid gap-4 xl:grid-cols-[1.1fr,0.9fr]'>
            <PlaceholderSection
              title={t('module.billing.overview.subscriptionTitle')}
              description={t('module.billing.overview.helper')}
            />
            <PlaceholderSection
              title={t('module.billing.overview.catalogTitle')}
              description={t('module.billing.overview.helper')}
            />
          </div>
        </TabsContent>

        <TabsContent value='ledger'>
          <PlaceholderSection
            title={t('module.billing.ledger.title')}
            description={t('module.billing.ledger.description')}
          />
        </TabsContent>

        <TabsContent value='orders'>
          <PlaceholderSection
            title={t('module.billing.orders.title')}
            description={t('module.billing.orders.description')}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
