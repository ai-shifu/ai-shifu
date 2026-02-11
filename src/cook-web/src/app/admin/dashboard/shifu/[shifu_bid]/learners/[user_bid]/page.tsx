'use client';

import React, { useEffect, useMemo } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import Loading from '@/components/loading';
import LearnerDetailSheet from '@/components/dashboard/LearnerDetailSheet';
import { useUserStore } from '@/store';

export default function AdminDashboardLearnerDetailPage() {
  const params = useParams<{
    shifu_bid?: string | string[];
    user_bid?: string | string[];
  }>();
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
    <div className='h-full p-0'>
      <LearnerDetailSheet
        mode='page'
        shifuBid={shifuBid}
        userBid={userBid}
        startDate={startDate}
        endDate={endDate}
      />
    </div>
  );
}
