'use client';

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import UnifiedI18nBackend from '@/lib/unified-i18n-backend';
import { defaultLocale, localeCodes, namespaces } from '@/lib/i18n-locales';

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

if (typeof window !== 'undefined' && !i18n.isInitialized) {
  i18n
    .use(UnifiedI18nBackend)
    .use(initReactI18next)
    .init({
      fallbackLng: {
        default: [fallbackLanguage],
      },
      ns: namespaceList,
      defaultNS: defaultNamespace,
      lng: browserLanguage,
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
    });
}

export default i18n;
