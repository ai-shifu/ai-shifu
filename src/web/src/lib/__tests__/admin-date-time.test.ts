import {
  formatAdminDateRangeEndUtc,
  formatAdminDateRangeStartUtc,
} from '@/lib/admin-date-time';

const isoWithoutMilliseconds = (date: Date): string =>
  date.toISOString().replace(/\.\d{3}Z$/, 'Z');

describe('admin date range UTC boundary helpers', () => {
  test('converts browser-local date start to UTC ISO', () => {
    expect(formatAdminDateRangeStartUtc('2026-07-02')).toBe(
      isoWithoutMilliseconds(new Date(2026, 6, 2, 0, 0, 0, 0)),
    );
  });

  test('converts browser-local date end to UTC ISO', () => {
    expect(formatAdminDateRangeEndUtc('2026-07-02')).toBe(
      isoWithoutMilliseconds(new Date(2026, 6, 2, 23, 59, 59, 0)),
    );
  });

  test('rejects invalid date-only values', () => {
    expect(formatAdminDateRangeStartUtc('2026-02-30')).toBe('');
    expect(formatAdminDateRangeEndUtc('2026-07-02T00:00:00Z')).toBe('');
  });
});
