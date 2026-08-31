import type { MarkdownFlowLocale } from 'markdown-flow-ui/renderer';

const MARKDOWN_FLOW_LOCALES: readonly MarkdownFlowLocale[] = [
  'en-US',
  'fr-FR',
  'zh-CN',
  'ar-SA',
  'th-TH',
];

const localeByBaseCode: Record<string, MarkdownFlowLocale> = Object.assign(
  Object.create(null),
  {
    en: 'en-US',
    fr: 'fr-FR',
    zh: 'zh-CN',
    ar: 'ar-SA',
    th: 'th-TH',
  },
);

export const resolveMarkdownFlowLocale = (
  language?: string | null,
): MarkdownFlowLocale => {
  if (!language) {
    return 'en-US';
  }

  const normalizedLanguage = language.replace('_', '-');
  if (
    MARKDOWN_FLOW_LOCALES.includes(normalizedLanguage as MarkdownFlowLocale)
  ) {
    return normalizedLanguage as MarkdownFlowLocale;
  }

  const baseCode = normalizedLanguage.split('-')[0]?.toLowerCase();
  return (baseCode && localeByBaseCode[baseCode]) || 'en-US';
};
