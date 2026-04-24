import { formatOperatorUtcDateTime } from './dateTime';

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
