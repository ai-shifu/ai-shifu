'use client';

import i18n from 'i18next';
import ICU from 'i18next-icu';
import { initReactI18next } from 'react-i18next';

import UnifiedI18nBackend from '@/lib/unified-i18n-backend';
import { defaultLocale, localeCodes, namespaces } from '@/lib/i18n-locales';
import {
  clearPendingRequestLanguage,
  setPendingRequestLanguage,
} from '@/lib/request-language';
import { setI18nLoading } from '@/store/useI18nLoadingStore';

const fileNamespaces = namespaces.length ? namespaces : ['common'];
const namespaceList = [
  'translation',
  ...fileNamespaces.filter(ns => ns !== 'translation'),
];
const defaultNamespace = 'translation';

const languageCodes = localeCodes;
const fallbackLanguage = languageCodes.length
  ? languageCodes.includes(defaultLocale)
    ? defaultLocale
    : languageCodes[0]
  : 'en-US';

export const normalizeLanguage = (lang?: string | null): string => {
  if (!lang) {
    return fallbackLanguage;
  }

  const normalized = lang.replace('_', '-');
  if (languageCodes.includes(normalized)) {
    return normalized;
  }

  const baseCode = normalized.split('-')[0]?.toLowerCase();
  if (!baseCode) {
    return fallbackLanguage;
  }

  const matchedCode = languageCodes.find(code =>
    code.toLowerCase().startsWith(baseCode),
  );

  return matchedCode ?? fallbackLanguage;
};

const detectedBrowserLanguage =
  typeof window !== 'undefined'
    ? navigator.language || navigator.languages?.[0] || fallbackLanguage
    : fallbackLanguage;

export const browserLanguage = normalizeLanguage(detectedBrowserLanguage);

const PREFERRED_LANGUAGE_STORAGE_KEY = 'preferred_language';

const readPreferredLanguage = (): string => {
  if (typeof window === 'undefined') {
    return '';
  }
  try {
    const storedLanguage = window.localStorage.getItem(
      PREFERRED_LANGUAGE_STORAGE_KEY,
    );
    return storedLanguage ? normalizeLanguage(storedLanguage) : '';
  } catch {
    return '';
  }
};

const persistPreferredLanguage = (language: string): void => {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(PREFERRED_LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Ignore storage errors in restricted browser modes.
  }
};

const initialLanguage = readPreferredLanguage() || browserLanguage;

if (typeof window !== 'undefined' && !i18n.isInitialized) {
  setI18nLoading(true);
  i18n
    // ICU messageformat support to match server-side formatting features
    .use(new ICU())
    .use(UnifiedI18nBackend)
    .use(initReactI18next)
    .init({
      fallbackLng: {
        default: [fallbackLanguage],
      },
      ns: namespaceList,
      defaultNS: defaultNamespace,
      lng: initialLanguage,
      load: 'currentOnly',
      supportedLngs: languageCodes.length ? languageCodes : undefined,
      nonExplicitSupportedLngs: false,
      interpolation: {
        escapeValue: false,
      },
      returnNull: false,
      react: {
        useSuspense: false,
      },
      backend: {
        namespaces: fileNamespaces,
        includeMetadata: false,
      },
    })
    .finally(() => {
      setI18nLoading(false);
    });
}

type ChangeLanguage = typeof i18n.changeLanguage;
const originalChangeLanguage = i18n.changeLanguage.bind(i18n) as ChangeLanguage;

i18n.changeLanguage = (async (...args: Parameters<ChangeLanguage>) => {
  const requestedLanguage = String(args[0] || '').trim();
  if (requestedLanguage) {
    setPendingRequestLanguage(requestedLanguage);
  }
  setI18nLoading(true);
  try {
    return await originalChangeLanguage(...args);
  } catch (error) {
    // eslint-disable-next-line no-console
    console.error('Failed to change language', error);
    throw error;
  } finally {
    if (requestedLanguage) {
      persistPreferredLanguage(normalizeLanguage(requestedLanguage));
      clearPendingRequestLanguage(requestedLanguage);
    }
    setI18nLoading(false);
  }
}) as ChangeLanguage;

export default i18n;
