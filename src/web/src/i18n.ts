import i18n from 'i18next';
import Backend from 'i18next-http-backend';
import { initReactI18next } from 'react-i18next';

const fallbackLanguage = 'en-US';

export const browserLanguage =
  typeof window !== 'undefined'
    ? navigator.language || navigator.languages?.[0] || fallbackLanguage
    : fallbackLanguage;

i18n
  .use(Backend)
  .use(initReactI18next)
  .init({
    fallbackLng: fallbackLanguage,
    debug: false,
    lng: browserLanguage,
    backend: {
      loadPath: `/locales/{{lng}}.json`,
    },
    interpolation: {
      escapeValue: false,
    },
    returnNull: false,
  });

export default i18n;
