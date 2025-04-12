import { useEnvStore } from 'stores/envStore';

export const getBoolEnv = (key) => {
  return useEnvStore.getState()[key] === 'true';
};

export const getIntEnv = (key) => {
  return parseInt(useEnvStore.getState()[key]);
};

export const getStringEnv = (key) => {
  return useEnvStore.getState()[key];
};
