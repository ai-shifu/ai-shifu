'use client';

import {
  readLocalStorageItem,
  writeLocalStorageItem,
} from '@/lib/runtimeStorage';
import { debugWarn } from '@/lib/debugConsole';
import type {
  DebugVariableValues,
  StoredDebugVariableValues,
} from '@/types/debug-session';

// Preserve saved editor Debug variables under the existing storage key.
const VARIABLE_STORAGE_KEY_PREFIX = 'lesson_preview_variables';
const SYSTEM_VARIABLES_STORAGE_KEY = VARIABLE_STORAGE_KEY_PREFIX;

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

const buildCourseVariableStorageKey = (shifuBid?: string) => {
  if (!shifuBid) {
    return '';
  }
  return `${VARIABLE_STORAGE_KEY_PREFIX}:${shifuBid}`;
};

const readVariableValues = (key: string): DebugVariableValues => {
  if (typeof window === 'undefined' || !key) {
    return {};
  }

  const raw = readLocalStorageItem(
    key,
    '[debug-variable-storage] failed to read localStorage',
  );
  if (!raw) {
    return {};
  }

  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') {
      return {};
    }
    return Object.entries(parsed).reduce<DebugVariableValues>((acc, entry) => {
      const [name, storedValue] = entry;
      acc[name] = normalizeValue(storedValue);
      return acc;
    }, {});
  } catch (error) {
    debugWarn('[debug-variable-storage] failed to parse localStorage JSON', {
      key,
      error,
    });
    return {};
  }
};

const writeVariableValues = (key: string, data: DebugVariableValues) => {
  if (typeof window === 'undefined' || !key) {
    return;
  }
  writeLocalStorageItem(
    key,
    JSON.stringify(data),
    '[debug-variable-storage] failed to write localStorage',
  );
};

export const readStoredDebugVariableValues = (
  shifuBid?: string,
): StoredDebugVariableValues => {
  const courseStorageKey = buildCourseVariableStorageKey(shifuBid);
  return {
    system: readVariableValues(SYSTEM_VARIABLES_STORAGE_KEY),
    course: courseStorageKey ? readVariableValues(courseStorageKey) : {},
  };
};

export const selectDebugVariableValues = (
  keys: string[],
  stored: StoredDebugVariableValues,
  systemVariableKeys: Set<string> | string[],
): DebugVariableValues => {
  const systemSet = new Set(systemVariableKeys);
  return keys.reduce<DebugVariableValues>((acc, key) => {
    const source = systemSet.has(key) ? stored.system : stored.course;
    acc[key] = source?.[key] || '';
    return acc;
  }, {});
};

export const mergeStoredDebugVariableValues = (
  shifuBid?: string,
  variableValues?: DebugVariableValues,
  systemVariableKeys: Set<string> | string[] = [],
) => {
  if (typeof window === 'undefined') {
    return;
  }
  const systemSet = new Set(systemVariableKeys);
  const stored = readStoredDebugVariableValues(shifuBid);
  const courseStorageKey = buildCourseVariableStorageKey(shifuBid);
  let hasSystemChanges = false;
  let hasCourseChanges = false;
  Object.entries(variableValues || {}).forEach(([name, value]) => {
    const normalized = normalizeValue(value);
    if (systemSet.has(name)) {
      if (stored.system[name] !== normalized) {
        stored.system[name] = normalized;
        hasSystemChanges = true;
      }
    } else if (courseStorageKey) {
      if (stored.course[name] !== normalized) {
        stored.course[name] = normalized;
        hasCourseChanges = true;
      }
    }
  });
  if (hasSystemChanges) {
    writeVariableValues(SYSTEM_VARIABLES_STORAGE_KEY, stored.system);
  }
  if (courseStorageKey && hasCourseChanges) {
    writeVariableValues(courseStorageKey, stored.course);
  }
};
