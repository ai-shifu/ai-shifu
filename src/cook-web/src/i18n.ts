'use client';

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import Backend from 'i18next-http-backend';

import languages from '../public/locales/languages.json';

const languageCodes = Object.keys(languages);
const fallbackLanguage = languageCodes.includes('en-US')
  ? 'en-US'
  : languageCodes[0];

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

// 确保在客户端环境下初始化
if (typeof window !== 'undefined') {
  i18n
    .use(Backend)
    .use(initReactI18next)
    .init({
      fallbackLng: {
        default: [fallbackLanguage], // All unsupported languages fallback to default locale
      },
      lng: browserLanguage,
      backend: {
        loadPath: `/locales/{{lng}}.json`,
      },
      interpolation: {
        escapeValue: false,
      },
      returnNull: false,
      load: 'all',
      supportedLngs: languageCodes,
      nonExplicitSupportedLngs: false,
      react: {
        useSuspense: false,
      },
    });
}

export default i18n;
