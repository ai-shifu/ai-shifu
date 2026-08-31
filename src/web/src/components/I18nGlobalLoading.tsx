'use client';

import { useI18nLoadingStore } from '@/store/useI18nLoadingStore';
import Loading from '@/components/loading';
import { usePathname } from 'next/navigation';

const I18nGlobalLoading = () => {
  const isLoading = useI18nLoadingStore(state => state.isLoading);

  const pathname = usePathname();
  const shouldSkipLoading = pathname.startsWith('/c/');
  if (!isLoading || shouldSkipLoading) {
    return null;
  }

  return (
    <div
      id='root-loading'
      className='pointer-events-none fixed inset-0 z-[9999] flex items-center justify-center bg-white'
    >
      <Loading />
    </div>
  );
};

export default I18nGlobalLoading;
