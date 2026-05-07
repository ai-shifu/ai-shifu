'use client';

type AdminNumberFormatOptions = {
  currency?: string;
  maximumFractionDigits?: number;
  minimumFractionDigits?: number;
};

const DEFAULT_ADMIN_NUMBER_FORMAT = {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
} as const;

const shouldUseAdminNumberGrouping = (locale?: string | null): boolean => {
  const normalizedLocale = String(locale || '')
    .trim()
    .toLowerCase();
  return !normalizedLocale.startsWith('zh');
};

export function formatAdminNumber(
  value: unknown,
  locale: string,
  options?: AdminNumberFormatOptions,
): string {
  const numeric = Number(value ?? 0);
  const safeValue = Number.isFinite(numeric) ? numeric : 0;

  return new Intl.NumberFormat(locale || 'en-US', {
    useGrouping: shouldUseAdminNumberGrouping(locale),
    minimumFractionDigits:
      options?.minimumFractionDigits ??
      DEFAULT_ADMIN_NUMBER_FORMAT.minimumFractionDigits,
    maximumFractionDigits:
      options?.maximumFractionDigits ??
      DEFAULT_ADMIN_NUMBER_FORMAT.maximumFractionDigits,
    ...(options?.currency
      ? {
          style: 'currency',
          currency: options.currency,
          currencyDisplay: 'narrowSymbol',
        }
      : {}),
  }).format(safeValue);
}

export function formatAdminCount(
  value: unknown,
  locale: string,
  emptyValue = '--',
): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return emptyValue;
  }

  return formatAdminNumber(numeric, locale, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

export function formatAdminCredits(value: unknown, locale: string): string {
  return formatAdminNumber(value, locale);
}

export function formatAdminPrice(
  amountInMinor: number,
  currency: string,
  locale: string,
): string {
  const resolvedCurrency = currency || 'CNY';
  const fractionDigits =
    new Intl.NumberFormat(locale || 'en-US', {
      style: 'currency',
      currency: resolvedCurrency,
    }).resolvedOptions().maximumFractionDigits ?? 2;

  return formatAdminNumber(
    Number(amountInMinor || 0) / 10 ** fractionDigits,
    locale,
    {
      currency: resolvedCurrency,
      maximumFractionDigits: fractionDigits,
    },
  );
}
