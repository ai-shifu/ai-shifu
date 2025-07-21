"use client";

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import Backend from "i18next-http-backend";

const browserLanguage =
  typeof window !== "undefined" && navigator.language
    ? navigator.language
    : "en-US";

// 确保在客户端环境下初始化
if (typeof window !== "undefined") {
  i18n
    .use(Backend)
    .use(initReactI18next)
    .init({
      fallbackLng: {
        en: ["en-US"],
        zh: ["zh-CN"],
        default: ["en-US"],
      },
      lng: browserLanguage,
      backend: {
        loadPath: `/locales/{{lng}}.json`,
      },
      interpolation: {
        escapeValue: false,
      },
      returnNull: false,
      load: "all",
      supportedLngs: ["en-US", "zh-CN"],
      nonExplicitSupportedLngs: false,
      react: {
        useSuspense: false,
      },
    });
}

export default i18n;
export { browserLanguage };
