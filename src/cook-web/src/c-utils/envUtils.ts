import { useEnvStore } from '@/c-store/envStore';

export const getBoolEnv = key => {
  return useEnvStore.getState()[key] === 'true';
};

export const getIntEnv = key => {
  return parseInt(useEnvStore.getState()[key]);
};

export const getStringEnv = key => {
  return useEnvStore.getState()[key];
};

export const getResolvedBaseURL = (): string => {
  const rawBase = (getStringEnv('baseURL') || '').toString();
  const normalizedBase = rawBase.replace(/\/+$/, '');

  if (normalizedBase && normalizedBase !== '/') {
    return normalizedBase;
  }

  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin;
  }

  return '';
};
