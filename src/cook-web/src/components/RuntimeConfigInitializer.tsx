'use client';

import { useEffect } from 'react';
import { initializeEnvData } from '@/lib/initializeEnvData';

const RuntimeConfigInitializer = () => {
  useEffect(() => {
    initializeEnvData();
  }, []);

  return null;
};

export default RuntimeConfigInitializer;
