'use client';

import { useTranslation } from 'react-i18next';

export default function UnsupportedBrowserPage() {
  const { t } = useTranslation();

  return (
    <main className='min-h-screen bg-[#f5f7fb] px-4 py-6 text-[#1f2937]'>
      <div className='mx-auto mt-[8vh] w-full max-w-[520px] rounded-2xl border border-[#e5e7eb] bg-white px-5 py-6 shadow-[0_10px_30px_rgba(15,99,238,0.08)]'>
        <h1 className='mb-3 text-xl font-semibold leading-7 text-[#0f63ee]'>
          {t('common.core.unsupportedBrowserTitle')}
        </h1>
        <p className='text-sm leading-7'>
          {t('common.core.unsupportedBrowserDescription')}
        </p>
      </div>
    </main>
  );
}
