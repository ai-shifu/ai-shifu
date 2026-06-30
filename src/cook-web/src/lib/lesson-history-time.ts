const normalizeDateString = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) {
    return '';
  }
  if (trimmed.includes('T') || /[zZ]|[+-]\d{2}:\d{2}$/.test(trimmed)) {
    return trimmed;
  }
  return trimmed.replace(' ', 'T');
};

export const parseLessonHistoryDate = (
  value?: string | Date | null,
): Date | null => {
  if (!value) {
    return null;
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  const normalized = normalizeDateString(value);
  if (!normalized) {
    return null;
  }
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

export const formatLessonRelativeTime = (
  updatedAt: Date,
  labels: {
    justNow: string;
    minutesAgo: (count: number) => string;
    hoursAgo: (count: number) => string;
    daysAgo: (count: number) => string;
  },
  now = new Date(),
) => {
  const diffMs = Math.max(0, now.getTime() - updatedAt.getTime());
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (diffMs < minute) {
    return labels.justNow;
  }
  if (diffMs < hour) {
    return labels.minutesAgo(Math.max(1, Math.floor(diffMs / minute)));
  }
  if (diffMs < day) {
    return labels.hoursAgo(Math.max(1, Math.floor(diffMs / hour)));
  }
  return labels.daysAgo(Math.max(1, Math.floor(diffMs / day)));
};
