import {
  formatOperatorNaiveDateTime,
  formatOperatorUtcDateTime,
} from './dateTime';

jest.mock('@/lib/browser-timezone', () => ({
  getBrowserTimeZone: () => 'UTC',
}));

describe('formatOperatorUtcDateTime', () => {
  test('formats ISO datetimes with timezone', () => {
    expect(formatOperatorUtcDateTime('2026-05-01T00:00:00Z')).toBe(
      '2026-05-01 00:00:00',
    );
  });

  test('rejects offsetless legacy datetimes', () => {
    expect(formatOperatorUtcDateTime('2026-05-01 00:00:00')).toBe('');
  });
});

describe('formatOperatorNaiveDateTime', () => {
  test('formats offsetless legacy datetimes without timezone conversion', () => {
    expect(formatOperatorNaiveDateTime('2026-05-01 08:30:15')).toBe(
      '2026-05-01 08:30:15',
    );
  });

  test('preserves wall clock time for legacy UTC-marked payloads', () => {
    expect(formatOperatorNaiveDateTime('2026-05-01T08:30:15Z')).toBe(
      '2026-05-01 08:30:15',
    );
  });
});
