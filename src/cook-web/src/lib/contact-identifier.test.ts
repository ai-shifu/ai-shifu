import {
  isValidContactIdentifier,
  normalizeContactIdentifier,
} from './contact-identifier';

describe('normalizeContactIdentifier', () => {
  it('lowercases emails so drafts and accounts key on one form', () => {
    expect(normalizeContactIdentifier('email', '  Teacher@Example.COM ')).toBe(
      'teacher@example.com',
    );
  });

  it('only trims phone numbers', () => {
    expect(normalizeContactIdentifier('phone', ' 13800138000 ')).toBe(
      '13800138000',
    );
  });
});

describe('isValidContactIdentifier', () => {
  it('accepts an email only in email mode', () => {
    expect(isValidContactIdentifier('email', 'teacher@example.com')).toBe(true);
    expect(isValidContactIdentifier('phone', 'teacher@example.com')).toBe(
      false,
    );
  });

  it('accepts an 11-digit number only in phone mode', () => {
    expect(isValidContactIdentifier('phone', '13800138000')).toBe(true);
    expect(isValidContactIdentifier('email', '13800138000')).toBe(false);
  });

  it('rejects blank and partial values', () => {
    expect(isValidContactIdentifier('phone', '')).toBe(false);
    expect(isValidContactIdentifier('phone', '1380013800')).toBe(false);
    expect(isValidContactIdentifier('email', 'not-an-email')).toBe(false);
  });
});
