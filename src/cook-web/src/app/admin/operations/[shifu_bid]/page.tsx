'use client';

import { useParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import useOperatorGuard from '../useOperatorGuard';

export default function AdminOperationCourseDetailPage() {
  const router = useRouter();
  const params = useParams<{ shifu_bid?: string }>();
  const { t } = useTranslation();
  const { isReady } = useOperatorGuard();

  const shifuBid = Array.isArray(params?.shifu_bid)
    ? params.shifu_bid[0] || ''
    : params?.shifu_bid || '';

  if (!isReady) {
    return <Loading />;
  }

  return (
    <div className='h-full overflow-auto'>
      <div className='max-w-5xl mx-auto py-6 space-y-4'>
        <div className='flex items-center justify-between'>
          <div>
            <h1 className='text-2xl font-semibold text-gray-900'>
              {t('module.operationsCourse.detail.title')}
            </h1>
            <p className='mt-1 text-sm text-muted-foreground'>{shifuBid}</p>
          </div>
          <Button
            variant='outline'
            onClick={() => router.push('/admin/operations')}
          >
            {t('module.operationsCourse.detail.back')}
          </Button>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>
              {t('module.operationsCourse.detail.basicInfo')}
            </CardTitle>
          </CardHeader>
          <CardContent className='text-sm text-muted-foreground'>
            {t('common.core.waitingForCompletion')}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
