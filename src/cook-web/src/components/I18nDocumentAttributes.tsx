'use client';

import { useEffect, type ReactNode } from 'react';
import { DirectionProvider } from '@radix-ui/react-direction';
import { useTranslation } from 'react-i18next';

import { normalizeLanguage } from '@/i18n';
import { isRtlLocale } from '@/lib/i18n-locales';

/** Keep the document and Radix direction context in sync with i18n. */
export default function I18nDocumentAttributes({
  children,
}: {
  children: ReactNode;
}) {
  const { i18n } = useTranslation();
  const language = normalizeLanguage(i18n.language);
  const direction = isRtlLocale(language) ? 'rtl' : 'ltr';

  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = direction;
  }, [language, direction]);

  return <DirectionProvider dir={direction}>{children}</DirectionProvider>;
}
