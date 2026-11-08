'use client';

import {
  readLocalStorageItem,
  writeLocalStorageItem,
} from '@/lib/runtime-storage';
import { debugWarn } from '@/lib/debug-console';
import type {
  DebugCourseAliases,
  DebugCourseAliasPatch,
  DebugVariableValues,
  StoredDebugVariableValues,
} from '@/types/debug-session';

// Preserve saved editor Debug variables under the existing storage key.
const VARIABLE_STORAGE_KEY_PREFIX = 'lesson_preview_variables';
const SYSTEM_VARIABLES_STORAGE_KEY = VARIABLE_STORAGE_KEY_PREFIX;
const COURSE_ALIASES_STORAGE_KEY_PREFIX = 'lesson_preview_course_aliases';

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

const readStoredObject = (key: string): Record<string, unknown> => {
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
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return {};
    }
    return parsed;
  } catch (error) {
    debugWarn('[debug-variable-storage] failed to parse localStorage JSON', {
      key,
      error,
    });
    return {};
  }
};

const readVariableValues = (key: string): DebugVariableValues =>
  Object.fromEntries(
    Object.entries(readStoredObject(key)).map(([name, value]) => [
      name,
      normalizeValue(value),
    ]),
  );

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

const buildCourseAliasStorageKey = (shifuBid?: string) =>
  shifuBid ? `${COURSE_ALIASES_STORAGE_KEY_PREFIX}:${shifuBid}` : '';

export const normalizeDebugCourseAliasPatch = (
  input: Record<string, unknown> | null,
): DebugCourseAliasPatch => {
  const patch = new Map<string, string | null>();
  for (const [alias, target] of Object.entries(
    input && !Array.isArray(input) ? input : {},
  )) {
    if (
      alias &&
      (target === null ||
        (typeof target === 'string' && target && alias !== target))
    ) {
      patch.set(alias, target);
    }
  }
  return Object.fromEntries(patch);
};

export const applyDebugCourseAliasPatch = (
  aliases: DebugCourseAliases,
  patch: DebugCourseAliasPatch,
): DebugCourseAliases => {
  const updated = new Map(Object.entries(aliases));
  for (const [alias, target] of Object.entries(patch)) {
    if (target === null) {
      updated.delete(alias);
    } else {
      updated.set(alias, target);
    }
  }
  return Object.fromEntries(updated);
};

export const readStoredDebugCourseAliases = (shifuBid?: string) =>
  applyDebugCourseAliasPatch(
    {},
    normalizeDebugCourseAliasPatch(
      readStoredObject(buildCourseAliasStorageKey(shifuBid)),
    ),
  );

export const mergeStoredDebugCourseAliases = (
  shifuBid: string | undefined,
  patch: DebugCourseAliasPatch,
) => {
  if (!Object.keys(patch).length) {
    return;
  }
  writeVariableValues(
    buildCourseAliasStorageKey(shifuBid),
    applyDebugCourseAliasPatch(readStoredDebugCourseAliases(shifuBid), patch),
  );
};

export const canonicalizeDebugVariableValues = <T>(
  values: Record<string, T>,
  aliases: DebugCourseAliases,
): Record<string, T> =>
  Object.fromEntries(
    Object.entries(values).map(([key, value]) => [
      Object.hasOwn(aliases, key) ? aliases[key] : key,
      value,
    ]),
  );

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
  courseAliases: DebugCourseAliases = {},
): DebugVariableValues => {
  const systemSet = new Set(systemVariableKeys);
  return Object.fromEntries(
    keys.map(key => {
      const isSystem = systemSet.has(key);
      const canonicalKey =
        !isSystem && Object.hasOwn(courseAliases, key)
          ? courseAliases[key]
          : key;
      const source = isSystem ? stored.system : stored.course;
      return [
        canonicalKey,
        Object.hasOwn(source, canonicalKey) ? source[canonicalKey] : '',
      ];
    }),
  );
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
