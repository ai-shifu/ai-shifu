'use client';

import { useEffect } from 'react';
import { redirectToHomeUrlIfRootPath } from '@/lib/utils';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';

export default function Home() {
  const homeUrl = useEnvStore((state: EnvStoreState) => state.homeUrl);
  const runtimeConfigLoaded = useEnvStore(
    (state: EnvStoreState) => state.runtimeConfigLoaded,
  );

  useEffect(() => {
    if (!runtimeConfigLoaded) {
      return;
    }
    redirectToHomeUrlIfRootPath(homeUrl || '/admin');
  }, [homeUrl, runtimeConfigLoaded]);

  return (
    <div className='grid grid-rows-[20px_1fr_20px] items-center justify-items-center min-h-screen p-8 pb-20 gap-16 sm:p-20 font-[family-name:var(--font-geist-sans)]'></div>
  );
}
