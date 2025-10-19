'use client';

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import Backend from 'i18next-http-backend';

import { defaultLocale, localeCodes, namespaces } from '@/lib/i18n-locales';

const namespaceList = namespaces.length ? namespaces : ['common'];
const defaultNamespace = namespaceList.includes('common')
  ? 'common'
  : namespaceList[0];

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

// Ensure initialization only happens in the browser
if (typeof window !== 'undefined') {
  i18n
    .use(Backend)
    .use(initReactI18next)
    .init({
      fallbackLng: {
        default: [fallbackLanguage], // All unsupported languages fallback to default locale
      },
      ns: namespaceList,
      defaultNS: defaultNamespace,
      lng: browserLanguage,
      backend: {
        loadPath: `/api/i18n/{{lng}}/{{ns}}`,
      },
      interpolation: {
        escapeValue: false,
      },
      returnNull: false,
      load: 'all',
      supportedLngs: languageCodes.length ? languageCodes : undefined,
      nonExplicitSupportedLngs: false,
      react: {
        useSuspense: false,
      },
    });
}

export default i18n;
