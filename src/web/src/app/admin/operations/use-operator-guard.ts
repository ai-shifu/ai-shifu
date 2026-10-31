'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useUserStore } from '@/store';

const useOperatorGuard = () => {
  const router = useRouter();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const userInfo = useUserStore(state => state.userInfo);
  const isOperator = Boolean(userInfo?.is_operator);

  useEffect(() => {
    if (!isInitialized) {
      return;
    }
    if (isGuest) {
      const currentPath = encodeURIComponent(
        window.location.pathname + window.location.search,
      );
      window.location.href = `/login?redirect=${currentPath}`;
      return;
    }
    if (userInfo == null) {
      return;
    }
    if (!isOperator) {
      router.replace('/admin');
    }
  }, [isGuest, isInitialized, isOperator, router, userInfo]);

  return {
    isInitialized,
    isGuest,
    userInfo,
    isOperator,
    isReady: isInitialized && !isGuest && Boolean(userInfo) && isOperator,
  };
};

export default useOperatorGuard;
