'use client';

import {
  readLocalStorageItem,
  writeLocalStorageItem,
} from '@/lib/runtimeStorage';
import { debugWarn } from '@/lib/debugConsole';

// Preserve saved preview answers from releases using the legacy storage label.
const STORAGE_PREFIX = 'lesson_preview_variables';
const GLOBAL_STORAGE_KEY = STORAGE_PREFIX;

export type PreviewMemoryMap = Record<string, string>;

export interface StoredMemoryByScope {
  system: PreviewMemoryMap;
  custom: PreviewMemoryMap;
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

const readStorage = (key: string): PreviewMemoryMap => {
  if (typeof window === 'undefined' || !key) {
    return {};
  }

  const raw = readLocalStorageItem(
    key,
    '[preview-memory-storage] failed to read localStorage',
  );
  if (!raw) {
    return {};
  }

  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') {
      return {};
    }
    return Object.entries(parsed).reduce<PreviewMemoryMap>((acc, entry) => {
      const [name, storedValue] = entry;
      acc[name] = normalizeValue(storedValue);
      return acc;
    }, {});
  } catch (error) {
    debugWarn('[preview-memory-storage] failed to parse localStorage JSON', {
      key,
      error,
    });
    return {};
  }
};

const writeStorage = (key: string, data: PreviewMemoryMap) => {
  if (typeof window === 'undefined' || !key) {
    return;
  }
  writeLocalStorageItem(
    key,
    JSON.stringify(data),
    '[preview-memory-storage] failed to write localStorage',
  );
};

export const getStoredPreviewMemory = (
  shifuBid?: string,
): StoredMemoryByScope => {
  const customKey = buildCustomStorageKey(shifuBid);
  return {
    system: readStorage(GLOBAL_STORAGE_KEY),
    custom: customKey ? readStorage(customKey) : {},
  };
};

export const mapKeysToStoredMemory = (
  keys: string[],
  stored: StoredMemoryByScope,
  systemMemoryKeys: Set<string> | string[],
): PreviewMemoryMap => {
  const systemSet = new Set(systemMemoryKeys);
  return keys.reduce<PreviewMemoryMap>((acc, key) => {
    const source = systemSet.has(key) ? stored.system : stored.custom;
    acc[key] = source?.[key] || '';
    return acc;
  }, {});
};

export const savePreviewMemory = (
  shifuBid?: string,
  memory?: PreviewMemoryMap,
  systemMemoryKeys: Set<string> | string[] = [],
) => {
  if (typeof window === 'undefined') {
    return;
  }
  const systemSet = new Set(systemMemoryKeys);
  const stored = getStoredPreviewMemory(shifuBid);
  const customKey = buildCustomStorageKey(shifuBid);
  let hasSystemChanges = false;
  let hasCustomChanges = false;
  Object.entries(memory || {}).forEach(([name, value]) => {
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
