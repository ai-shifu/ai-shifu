'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';

export default function AdminDashboardPage() {
  const { t } = useTranslation();

  return (
    <div className='h-full p-0'>
      <div className='h-full overflow-hidden flex flex-col'>
        <div className='flex items-center justify-between mb-5'>
          <h1 className='text-2xl font-semibold text-gray-900'>
            {t('module.dashboard.title')}
          </h1>
        </div>
      </div>
    </div>
  );
}
