'use client';

import { useEffect } from 'react';
import { redirectToHomeUrlIfRootPath } from '@/lib/utils';

export default function Home() {
  useEffect(() => {
    const fetchConfigAndRedirect = async () => {
      try {
        const res = await fetch('/api/config', {
          method: 'GET',
          referrer: 'no-referrer',
        });
        if (!res.ok) {
          return;
        }
        const data = await res.json();
        redirectToHomeUrlIfRootPath(data?.homeUrl);
      } catch (error) {
        console.error(error);
      }
    };

    fetchConfigAndRedirect();
  }, []);

  return (
    <div className='grid grid-rows-[20px_1fr_20px] items-center justify-items-center min-h-screen p-8 pb-20 gap-16 sm:p-20 font-[family-name:var(--font-geist-sans)]'></div>
  );
}
