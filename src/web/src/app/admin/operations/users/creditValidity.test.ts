import { estimateCreditExpiry } from './creditValidity';

describe('manual credit UTC expiry preview', () => {
  test.each([
    ['2026-01-31T10:20:30Z', '1', 'month', '2026-02-28T10:20:30.000Z'],
    ['2024-02-29T10:20:30Z', '1', 'year', '2025-02-28T10:20:30.000Z'],
    ['2026-09-28T10:20:30Z', '15', 'day', '2026-10-13T10:20:30.000Z'],
    ['2026-08-31T10:20:30Z', '6', 'month', '2027-02-28T10:20:30.000Z'],
    ['2026-08-31T10:20:30Z', '18', 'month', '2028-02-29T10:20:30.000Z'],
    ['2026-03-07T12:00:00-05:00', '1', 'day', '2026-03-08T17:00:00.000Z'],
  ])('%s + %s %s', (start, value, unit, expected) => {
    expect(
      estimateCreditExpiry(new Date(start), value, unit)?.toISOString(),
    ).toBe(expected);
  });

  test.each(['', '0', '-1', '1.5', '1e2', 'abc', '999999999999999999999'])(
    'rejects invalid duration %s',
    value => {
      expect(
        estimateCreditExpiry(new Date('2026-01-01Z'), value, 'day'),
      ).toBeNull();
    },
  );

  test.each(['day', 'month', 'year', 'week'])(
    'rejects overflow or invalid unit %s',
    unit => {
      expect(
        estimateCreditExpiry(new Date('9999-12-31T12:00:00Z'), '1', unit),
      ).toBeNull();
    },
  );
});
