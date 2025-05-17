import { useEnvStore } from 'stores/envStore';
import { EnvStoreState } from '../types/store';

export const getBoolEnv = (key: keyof EnvStoreState): boolean => {
  return useEnvStore.getState()[key] === 'true';
};

export const getIntEnv = (key: keyof EnvStoreState): number => {
  return parseInt(useEnvStore.getState()[key]);
};

export const getStringEnv = (key: keyof EnvStoreState): string => {
  return useEnvStore.getState()[key];
};
