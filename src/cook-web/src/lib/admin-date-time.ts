'use client';

import { getBrowserTimeZone } from '@/lib/browser-timezone';

const ISO_DATETIME_WITH_TIMEZONE_RE =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const LOCAL_NAIVE_DATETIME_RE =
  /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?$/;

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

export type AdminNaiveDateTimeParts = {
  year: string;
  month: string;
  day: string;
  hour: string;
  minute: string;
  second: string;
};

const isValidAdminNaiveDateTime = (parts: AdminNaiveDateTimeParts): boolean => {
  const year = Number(parts.year);
  const month = Number(parts.month);
  const day = Number(parts.day);
  const hour = Number(parts.hour);
  const minute = Number(parts.minute);
  const second = Number(parts.second);

  if (
    !Number.isInteger(year) ||
    !Number.isInteger(month) ||
    !Number.isInteger(day) ||
    !Number.isInteger(hour) ||
    !Number.isInteger(minute) ||
    !Number.isInteger(second)
  ) {
    return false;
  }

  const candidate = new Date(
    Date.UTC(year, month - 1, day, hour, minute, second),
  );

  return (
    candidate.getUTCFullYear() === year &&
    candidate.getUTCMonth() === month - 1 &&
    candidate.getUTCDate() === day &&
    candidate.getUTCHours() === hour &&
    candidate.getUTCMinutes() === minute &&
    candidate.getUTCSeconds() === second
  );
};

export const parseAdminNaiveDateTime = (
  value: string | null | undefined,
): AdminNaiveDateTimeParts | null => {
  const normalizedValue = String(value || '').trim();
  if (!normalizedValue) {
    return null;
  }

  const match = normalizedValue.match(LOCAL_NAIVE_DATETIME_RE);
  if (!match) {
    return null;
  }

  const parsedValue = {
    year: match[1],
    month: match[2],
    day: match[3],
    hour: match[4] || '00',
    minute: match[5] || '00',
    second: match[6] || '00',
  };

  if (!isValidAdminNaiveDateTime(parsedValue)) {
    return null;
  }

  return parsedValue;
};

export const formatAdminNaiveDateTime = (
  value: string | null | undefined,
): string => {
  const parsedValue = parseAdminNaiveDateTime(value);
  if (!parsedValue) {
    return '';
  }

  return `${parsedValue.year}-${parsedValue.month}-${parsedValue.day} ${parsedValue.hour}:${parsedValue.minute}:${parsedValue.second}`;
};
