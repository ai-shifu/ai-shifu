'use client';

import { getBrowserTimeZone } from '@/lib/browser-timezone';

const ISO_DATETIME_WITH_TIMEZONE_RE =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

export const parseAdminUtcDateTime = (
  value: string | null | undefined,
): Date | null => {
  const normalizedValue = String(value || '').trim();
  if (!normalizedValue) {
    return null;
  }

  if (!ISO_DATETIME_WITH_TIMEZONE_RE.test(normalizedValue)) {
    return null;
  }

  const date = new Date(normalizedValue);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date;
};

export const formatAdminUtcDateTime = (
  value: string | null | undefined,
): string => {
  const date = parseAdminUtcDateTime(value);
  if (!date) {
    return '';
  }

  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: getBrowserTimeZone() || 'UTC',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });

  const parts = formatter.formatToParts(date);
  const partMap = new Map(parts.map(part => [part.type, part.value]));
  const year = partMap.get('year');
  const month = partMap.get('month');
  const day = partMap.get('day');
  const hour = partMap.get('hour');
  const minute = partMap.get('minute');
  const second = partMap.get('second');

  if (!year || !month || !day || !hour || !minute || !second) {
    return '';
  }

  return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
};

export const formatAdminUtcDateTimeOrEmpty = (
  value: string | null | undefined,
  emptyValue: string,
): string => formatAdminUtcDateTime(value) || emptyValue;
