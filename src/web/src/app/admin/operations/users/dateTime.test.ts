import {
  formatOperatorNaiveDateTime,
  formatOperatorUtcDateTime,
} from './dateTime';

jest.mock('@/lib/browser-timezone', () => ({
  getBrowserTimeZone: () => 'Asia/Shanghai',
}));

describe('formatOperatorUtcDateTime', () => {
  test('formats ISO datetimes with timezone', () => {
    expect(formatOperatorUtcDateTime('2026-05-01T00:00:00Z')).toBe(
      '2026-05-01 08:00:00',
    );
  });

  test('rejects offsetless legacy datetimes', () => {
    expect(formatOperatorUtcDateTime('2026-05-01 00:00:00')).toBe('');
  });
});

describe('formatOperatorNaiveDateTime', () => {
  test('formats date-only strings with midnight defaults', () => {
    expect(formatOperatorNaiveDateTime('2026-05-01')).toBe(
      '2026-05-01 00:00:00',
    );
  });

  test('formats minute precision strings with zero seconds', () => {
    expect(formatOperatorNaiveDateTime('2026-05-01 08:30')).toBe(
      '2026-05-01 08:30:00',
    );
  });

  test('formats offsetless legacy datetimes without timezone conversion', () => {
    expect(formatOperatorNaiveDateTime('2026-05-01 08:30:15')).toBe(
      '2026-05-01 08:30:15',
    );
  });

  test('preserves wall clock time for date-only payloads with timezone markers', () => {
    expect(formatOperatorNaiveDateTime('2026-05-01Z')).toBe(
      '2026-05-01 00:00:00',
    );
  });

  test('preserves wall clock time for legacy UTC-marked payloads', () => {
    expect(formatOperatorNaiveDateTime('2026-05-01T08:30:15Z')).toBe(
      '2026-05-01 08:30:15',
    );
  });

  test('preserves wall clock time for offset-marked payloads', () => {
    expect(formatOperatorNaiveDateTime('2026-05-01T08:30:15+08:00')).toBe(
      '2026-05-01 08:30:15',
    );
  });

  test('rejects impossible datetimes', () => {
    expect(formatOperatorNaiveDateTime('2026-99-01 08:30:15')).toBe('');
  });
});
