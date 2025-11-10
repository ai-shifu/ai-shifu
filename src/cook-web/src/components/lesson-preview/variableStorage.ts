'use client';

const STORAGE_PREFIX = 'lesson_preview_variables';

export type PreviewVariablesMap = Record<string, string>;

const normalizeValue = (value: unknown): string => {
  if (typeof value === 'string') {
    return value;
  }
  if (Array.isArray(value) && value.length > 0) {
    return String(value[value.length - 1]);
  }
  if (value === null || value === undefined) {
    return '';
  }
  return String(value);
};

const buildStorageKey = (shifuBid?: string) => {
  if (!shifuBid) {
    return '';
  }
  return `${STORAGE_PREFIX}:${shifuBid}`;
};

export const getStoredPreviewVariables = (
  shifuBid?: string,
  outlineBid?: string,
): PreviewVariablesMap => {
  if (typeof window === 'undefined') {
    return {};
  }
  const key = buildStorageKey(shifuBid);
  if (!key) {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') {
      return {};
    }
    return Object.entries(parsed).reduce<PreviewVariablesMap>((acc, entry) => {
      const [name, storedValue] = entry;
      acc[name] = normalizeValue(storedValue);
      return acc;
    }, {});
  } catch (error) {
    console.warn('Failed to parse preview variables from storage', error);
    return {};
  }
};

export const savePreviewVariables = (
  shifuBid?: string,
  outlineBid?: string,
  variables?: PreviewVariablesMap,
) => {
  if (typeof window === 'undefined') {
    return;
  }
  const key = buildStorageKey(shifuBid);
  if (!key) {
    return;
  }
  const payload: PreviewVariablesMap = {};
  Object.entries(variables || {}).forEach(([name, value]) => {
    payload[name] = normalizeValue(value);
  });
  try {
    window.localStorage.setItem(key, JSON.stringify(payload));
  } catch (error) {
    console.warn('Failed to save preview variables to storage', error);
  }
};

export const mapKeysToStoredVariables = (
  keys: string[],
  stored: PreviewVariablesMap,
): PreviewVariablesMap =>
  keys.reduce<PreviewVariablesMap>((acc, key) => {
    acc[key] = stored?.[key] || '';
    return acc;
  }, {});
