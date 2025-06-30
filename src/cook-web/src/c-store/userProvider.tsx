'use client';

import { useEffect } from 'react';
import { useUserStore } from '@/c-store/useUserStore';

export const UserProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const initProfileFetch = useUserStore((state) => state.initProfileFetch);

  useEffect(() => {
    initProfileFetch();
  }, [initProfileFetch]);

  return <>{children}</>;
};