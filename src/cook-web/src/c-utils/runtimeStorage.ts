'use client';

import { debugWarn } from './debugConsole';

export const readLocalStorageItem = (
  key: string,
  debugLabel: string,
): string | null => {
  if (typeof window === 'undefined' || !key) {
    return null;
  }

  try {
    return window.localStorage.getItem(key);
  } catch (error) {
    debugWarn(debugLabel, error);
    return null;
  }
};

export const writeLocalStorageItem = (
  key: string,
  value: string,
  debugLabel: string,
) => {
  if (typeof window === 'undefined' || !key) {
    return;
  }

  try {
    window.localStorage.setItem(key, value);
  } catch (error) {
    debugWarn(debugLabel, error);
  }
};
