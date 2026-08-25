'use client';

import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { normalizeLanguage } from '@/i18n';
import { isRtlLocale } from '@/lib/i18n-locales';

/** Keep the document language and writing direction in sync with i18n. */
export default function I18nDocumentAttributes() {
  const { i18n } = useTranslation();

  useEffect(() => {
    const language = normalizeLanguage(i18n.language);
    document.documentElement.lang = language;
    document.documentElement.dir = isRtlLocale(language) ? 'rtl' : 'ltr';
  }, [i18n.language]);

  return null;
}
