import React from 'react';
import { Badge } from '@/components/ui/Badge';
import { useTranslation } from 'react-i18next';

export function BillingPageHeader() {
  const { t } = useTranslation();

  return (
    <div className='grid gap-6 overflow-hidden rounded-[32px] border border-slate-200 bg-[linear-gradient(135deg,#fff8ef_0%,#ffffff_48%,#f4f8ff_100%)] p-6 shadow-[0_20px_50px_rgba(15,23,42,0.08)] lg:grid-cols-[1.1fr,0.9fr] lg:p-8'>
      <div className='space-y-4'>
        <div className='flex flex-wrap items-center gap-3'>
          <Badge className='rounded-full bg-amber-100 px-3 py-1 text-amber-800 hover:bg-amber-100'>
            {t('module.billing.page.badge')}
          </Badge>
          <span className='text-sm text-slate-500'>
            {t('module.billing.page.subtitle')}
          </span>
        </div>
        <div className='space-y-3'>
          <h2 className='max-w-2xl text-3xl font-semibold tracking-tight text-slate-950 md:text-4xl'>
            {t('module.billing.page.title')}
          </h2>
          <p className='max-w-2xl text-sm leading-7 text-slate-600 md:text-base'>
            {t('module.billing.page.subtitle')}
          </p>
        </div>
      </div>

      <div className='grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3'>
        <div className='rounded-[24px] border border-white/70 bg-white/80 p-4 shadow-sm backdrop-blur'>
          <div className='text-xs font-medium uppercase tracking-[0.14em] text-slate-400'>
            {t('module.billing.overview.walletTitle')}
          </div>
          <div className='mt-3 text-sm leading-6 text-slate-600'>
            {t('module.billing.overview.availableCreditsLabel')}
          </div>
        </div>
        <div className='rounded-[24px] border border-white/70 bg-white/80 p-4 shadow-sm backdrop-blur'>
          <div className='text-xs font-medium uppercase tracking-[0.14em] text-slate-400'>
            {t('module.billing.catalog.sections.plans')}
          </div>
          <div className='mt-3 text-sm leading-6 text-slate-600'>
            {t('module.billing.overview.subscriptionTitle')}
          </div>
        </div>
        <div className='rounded-[24px] border border-white/70 bg-white/80 p-4 shadow-sm backdrop-blur'>
          <div className='text-xs font-medium uppercase tracking-[0.14em] text-slate-400'>
            {t('module.billing.orders.title')}
          </div>
          <div className='mt-3 text-sm leading-6 text-slate-600'>
            {t('module.billing.orders.description')}
          </div>
        </div>
      </div>
    </div>
  );
}
