'use client';
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

export default function Page({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  return (
    <div className='h-screen w-full'>
      <ShifuRoot id={id} />
    </div>
  );
}
