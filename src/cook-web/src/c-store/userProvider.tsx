'use client';

import { useEffect } from 'react';
import { useUserStore } from '@/c-store/useUserStore';

export const UserProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const initUser = useUserStore((state) => state.initUser);

  useEffect(() => {
    initUser();
  }, [initUser]);

  return <>{children}</>;
};