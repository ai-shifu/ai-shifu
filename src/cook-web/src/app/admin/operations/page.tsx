'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import Loading from '@/components/loading';
import { useUserStore } from '@/store';

export default function AdminOperationsPage() {
  const router = useRouter();
  const { t } = useTranslation();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const userInfo = useUserStore(state => state.userInfo);
  const isOperator = Boolean(userInfo?.is_operator);

  useEffect(() => {
    if (!isInitialized) {
      return;
    }
    if (isGuest) {
      const currentPath = encodeURIComponent('/admin/operations');
      window.location.href = `/login?redirect=${currentPath}`;
      return;
    }
    if (!userInfo || !isOperator) {
      router.replace('/admin');
    }
  }, [isGuest, isInitialized, isOperator, router, userInfo]);

  if (!isInitialized || isGuest || !userInfo || !isOperator) {
    return <Loading />;
  }

  return (
    <div className='h-full overflow-auto'>
      <div className='max-w-4xl mx-auto py-6'>
        <Card>
          <CardHeader>
            <CardTitle>{t('common.core.operations')}</CardTitle>
          </CardHeader>
          <CardContent className='text-sm text-muted-foreground'>
            {t('common.core.waitingForCompletion')}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
