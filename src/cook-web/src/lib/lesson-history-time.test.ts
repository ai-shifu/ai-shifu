import {
  formatLessonRelativeTime,
  parseLessonHistoryDate,
} from '@/lib/lesson-history-time';

const labels = {
  justNow: 'just now',
  minutesAgo: (count: number) => `${count}m`,
  hoursAgo: (count: number) => `${count}h`,
  daysAgo: (count: number) => `${count}d`,
};

describe('parseLessonHistoryDate', () => {
  test('parses UTC and offset ISO timestamps', () => {
    expect(parseLessonHistoryDate('2026-06-30T05:37:42Z')?.toISOString()).toBe(
      '2026-06-30T05:37:42.000Z',
    );
    expect(
      parseLessonHistoryDate('2026-06-30T13:37:42+08:00')?.toISOString(),
    ).toBe('2026-06-30T05:37:42.000Z');
  });

  test('parses legacy space-separated timestamps', () => {
    const parsed = parseLessonHistoryDate('2026-06-30 13:37:42');

    expect(parsed).not.toBeNull();
    expect(Number.isNaN(parsed?.getTime())).toBe(false);
  });

  test('returns null for empty or invalid values', () => {
    expect(parseLessonHistoryDate('')).toBeNull();
    expect(parseLessonHistoryDate('not-a-date')).toBeNull();
    expect(parseLessonHistoryDate(null)).toBeNull();
  });
});

describe('formatLessonRelativeTime', () => {
  const now = new Date(Date.UTC(2026, 5, 30, 12, 0, 0));

  test('formats relative time boundaries', () => {
    expect(
      formatLessonRelativeTime(
        new Date(Date.UTC(2026, 5, 30, 11, 59, 30)),
        labels,
        now,
      ),
    ).toBe('just now');
    expect(
      formatLessonRelativeTime(
        new Date(Date.UTC(2026, 5, 30, 11, 55, 0)),
        labels,
        now,
      ),
    ).toBe('5m');
    expect(
      formatLessonRelativeTime(
        new Date(Date.UTC(2026, 5, 30, 10, 0, 0)),
        labels,
        now,
      ),
    ).toBe('2h');
    expect(
      formatLessonRelativeTime(
        new Date(Date.UTC(2026, 5, 28, 12, 0, 0)),
        labels,
        now,
      ),
    ).toBe('2d');
  });
});
