'use client';

const STORAGE_PREFIX = 'lesson_preview_variables';
const GLOBAL_STORAGE_KEY = STORAGE_PREFIX;

export type PreviewVariablesMap = Record<string, string>;

export interface StoredVariablesByScope {
  system: PreviewVariablesMap;
  custom: PreviewVariablesMap;
}

export interface StoredHiddenByShifu {
  hiddenKeys: string[];
}

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

const buildCustomStorageKey = (shifuBid?: string) => {
  if (!shifuBid) {
    return '';
  }
  return `${STORAGE_PREFIX}:${shifuBid}`;
};

const buildHiddenStorageKey = (shifuBid?: string) => {
  if (!shifuBid) {
    return '';
  }
  return `${STORAGE_PREFIX}:hidden:${shifuBid}`;
};

const readStorage = (key: string): PreviewVariablesMap => {
  if (typeof window === 'undefined' || !key) {
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

const writeStorage = (key: string, data: PreviewVariablesMap) => {
  if (typeof window === 'undefined' || !key) {
    return;
  }
  try {
    window.localStorage.setItem(key, JSON.stringify(data));
  } catch (error) {
    console.warn('Failed to save preview variables to storage', error);
  }
};

export const getStoredPreviewVariables = (
  shifuBid?: string,
): StoredVariablesByScope => {
  const customKey = buildCustomStorageKey(shifuBid);
  return {
    system: readStorage(GLOBAL_STORAGE_KEY),
    custom: customKey ? readStorage(customKey) : {},
  };
};

export const mapKeysToStoredVariables = (
  keys: string[],
  stored: StoredVariablesByScope,
  systemVariableKeys: Set<string> | string[],
): PreviewVariablesMap => {
  const systemSet = new Set(systemVariableKeys);
  return keys.reduce<PreviewVariablesMap>((acc, key) => {
    const source = systemSet.has(key) ? stored.system : stored.custom;
    acc[key] = source?.[key] || '';
    return acc;
  }, {});
};

export const savePreviewVariables = (
  shifuBid?: string,
  variables?: PreviewVariablesMap,
  systemVariableKeys: Set<string> | string[] = [],
) => {
  if (typeof window === 'undefined') {
    return;
  }
  const systemSet = new Set(systemVariableKeys);
  const stored = getStoredPreviewVariables(shifuBid);
  const customKey = buildCustomStorageKey(shifuBid);
  let hasSystemChanges = false;
  let hasCustomChanges = false;
  Object.entries(variables || {}).forEach(([name, value]) => {
    const normalized = normalizeValue(value);
    if (systemSet.has(name)) {
      if (stored.system[name] !== normalized) {
        stored.system[name] = normalized;
        hasSystemChanges = true;
      }
    } else if (customKey) {
      if (stored.custom[name] !== normalized) {
        stored.custom[name] = normalized;
        hasCustomChanges = true;
      }
    }
  });
  if (hasSystemChanges) {
    writeStorage(GLOBAL_STORAGE_KEY, stored.system);
  }
  if (customKey && hasCustomChanges) {
    writeStorage(customKey, stored.custom);
  }
};

export const getStoredHiddenKeys = (shifuBid?: string): string[] => {
  if (typeof window === 'undefined') {
    return [];
  }
  const key = buildHiddenStorageKey(shifuBid);
  if (!key) return [];
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return [];
    const parsed: StoredHiddenByShifu = JSON.parse(raw) || { hiddenKeys: [] };
    return parsed.hiddenKeys || [];
  } catch (error) {
    console.warn('Failed to parse hidden keys from storage', error);
    return [];
  }
};

export const saveHiddenKeys = (shifuBid: string, hiddenKeys: string[]) => {
  if (typeof window === 'undefined') return;
  const key = buildHiddenStorageKey(shifuBid);
  if (!key) return;
  try {
    window.localStorage.setItem(key, JSON.stringify({ hiddenKeys }));
  } catch (error) {
    console.warn('Failed to save hidden keys to storage', error);
  }
};

export const clearHiddenKeys = (shifuBid?: string) => {
  if (typeof window === 'undefined') return;
  const key = buildHiddenStorageKey(shifuBid);
  if (!key) return;
  window.localStorage.removeItem(key);
};
