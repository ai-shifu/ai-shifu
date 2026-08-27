import { resolveMarkdownFlowLocale } from './markdown-flow-locale';

describe('resolveMarkdownFlowLocale', () => {
  it.each([
    ['en-US', 'en-US'],
    ['fr-FR', 'fr-FR'],
    ['zh-CN', 'zh-CN'],
    ['ar-SA', 'ar-SA'],
    ['th-TH', 'th-TH'],
    ['zh_CN', 'zh-CN'],
    ['ar_SA', 'ar-SA'],
    ['th_TH', 'th-TH'],
    ['en', 'en-US'],
    ['fr-CA', 'fr-FR'],
    ['zh-Hant', 'zh-CN'],
    ['ar', 'ar-SA'],
    ['th', 'th-TH'],
  ])('maps %s to %s', (language, expected) => {
    expect(resolveMarkdownFlowLocale(language)).toBe(expected);
  });

  it.each([undefined, null, '', 'de-DE'])(
    'falls back to English for %s',
    language => {
      expect(resolveMarkdownFlowLocale(language)).toBe('en-US');
    },
  );
});
