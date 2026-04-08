import React from 'react';
import { Badge } from '@/components/ui/Badge';
import { useTranslation } from 'react-i18next';

export function BillingPageHeader() {
  const { t } = useTranslation();

  return (
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
  );
}
