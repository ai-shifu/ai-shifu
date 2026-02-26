'use client';

import React, { useCallback, useEffect, useMemo } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import Loading from '@/components/loading';
import LearnerDetailSheet from '@/components/dashboard/LearnerDetailSheet';
import { Button } from '@/components/ui/Button';
import { ArrowLeft } from 'lucide-react';
import { useUserStore } from '@/store';

export default function AdminDashboardLearnerDetailPage() {
  const { t } = useTranslation();
  const params = useParams<{
    shifu_bid?: string | string[];
    user_bid?: string | string[];
  }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);

  const shifuBid = useMemo(() => {
    const value = params?.shifu_bid;
    if (Array.isArray(value)) {
      return value[0] || '';
    }
    return value || '';
  }, [params]);

  const userBid = useMemo(() => {
    const value = params?.user_bid;
    if (Array.isArray(value)) {
      return value[0] || '';
    }
    return value || '';
  }, [params]);

  const startDate = searchParams.get('start_date') || undefined;
  const endDate = searchParams.get('end_date') || undefined;

  const handleBackToCourseDetail = useCallback(() => {
    const query = new URLSearchParams();
    if (startDate) {
      query.set('start_date', startDate);
    }
    if (endDate) {
      query.set('end_date', endDate);
    }
    const queryText = query.toString();
    const fallbackPath = queryText
      ? `/admin/dashboard/shifu/${shifuBid}?${queryText}`
      : `/admin/dashboard/shifu/${shifuBid}`;

    if (typeof window !== 'undefined' && window.history.length > 1) {
      router.back();
      return;
    }
    router.push(fallbackPath);
  }, [endDate, router, shifuBid, startDate]);

  useEffect(() => {
    if (!isInitialized) {
      return;
    }
    if (isGuest) {
      const currentPath = encodeURIComponent(
        window.location.pathname + window.location.search,
      );
      window.location.href = `/login?redirect=${currentPath}`;
    }
  }, [isInitialized, isGuest]);

  if (!isInitialized || isGuest || !shifuBid || !userBid) {
    return (
      <div className='flex h-full items-center justify-center'>
        <Loading />
      </div>
    );
  }

  return (
    <div className='h-full p-0 flex flex-col gap-3'>
      <div>
        <Button
          size='sm'
          variant='outline'
          type='button'
          onClick={handleBackToCourseDetail}
        >
          <ArrowLeft className='mr-1 h-4 w-4' />
          {t('module.dashboard.actions.back')}
        </Button>
      </div>
      <div className='flex-1 min-h-0'>
        <LearnerDetailSheet
          mode='page'
          shifuBid={shifuBid}
          userBid={userBid}
          startDate={startDate}
          endDate={endDate}
        />
      </div>
    </div>
  );
}
