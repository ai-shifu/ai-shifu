'use client';
import { use } from 'react';
import dynamic from 'next/dynamic';
import { useSearchParams } from 'next/navigation';
import Loading from '@/components/loading';
import MobileUnsupportedDialog from '@/components/MobileUnsupportedDialog';
import { getLessonIdFromQuery } from '@/c-utils/urlUtils';

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
  const searchParams = useSearchParams();
  const initialLessonId = getLessonIdFromQuery(searchParams);

  return (
    <>
      <MobileUnsupportedDialog />
      <div className='h-screen w-full'>
        <ShifuRoot
          id={id}
          initialLessonId={initialLessonId}
        />
      </div>
    </>
  );
}
