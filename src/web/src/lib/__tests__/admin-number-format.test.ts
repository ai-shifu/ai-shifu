import {
  formatAdminCount,
  formatAdminCredits,
  formatAdminPrice,
} from '@/lib/admin-number-format';

describe('formatAdminCount', () => {
  test('hides grouping for Chinese locales', () => {
    expect(formatAdminCount(76384, 'zh-CN')).toBe('76384');
    expect(formatAdminCount(1234567, 'zh-HK')).toBe('1234567');
  });

  test('keeps grouping for non-Chinese locales', () => {
    expect(formatAdminCount(76384, 'en-US')).toBe('76,384');
    expect(formatAdminCount(1234567, 'fr-FR')).toBe('1 234 567');
  });

  test('returns the provided empty value for non-finite input', () => {
    expect(formatAdminCount(undefined, 'zh-CN')).toBe('--');
    expect(formatAdminCount(Number.NaN, 'en-US', 'N/A')).toBe('N/A');
  });
});

describe('formatAdminCredits', () => {
  test('applies locale-aware grouping rules', () => {
    expect(formatAdminCredits(10000, 'zh-CN')).toBe('10000');
    expect(formatAdminCredits(10000, 'en-US')).toBe('10,000');
  });

  test('preserves meaningful decimals', () => {
    expect(formatAdminCredits(50.5, 'zh-CN')).toBe('50.5');
    expect(formatAdminCredits(12345.67, 'en-US')).toBe('12,345.67');
  });
});

describe('formatAdminPrice', () => {
  test('formats Chinese admin prices without grouping', () => {
    expect(formatAdminPrice(123456700, 'CNY', 'zh-CN')).toBe('¥1234567');
    expect(formatAdminPrice(9950, 'CNY', 'zh-CN')).toBe('¥99.5');
  });

  test('formats non-Chinese admin prices with grouping', () => {
    expect(formatAdminPrice(123456700, 'CNY', 'en-US')).toBe('¥1,234,567');
    expect(formatAdminPrice(9950, 'USD', 'en-US')).toBe('$99.5');
  });
});
