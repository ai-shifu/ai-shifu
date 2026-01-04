'use client';
import { use } from 'react';
import dynamic from 'next/dynamic';
import Loading from '@/components/loading';

const ShifuRoot = dynamic(() => import('@/components/shifu-root'), {
  ssr: false,
  loading: () => (
    <div className='h-screen w-full flex items-center justify-center'>
      <Loading />
    </div>
  ),
});

type ShifuPageParams = { id: string };

export default function Page({ params }: { params: Promise<ShifuPageParams> }) {
  const { id } = use(params);
  return (
    <div className='h-screen w-full'>
      <ShifuRoot id={id} />
    </div>
  );
}
