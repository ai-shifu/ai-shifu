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

const adminNumberFormatterCache = new Map<string, Intl.NumberFormat>();

const buildAdminNumberFormatterKey = (
  locale: string,
  options?: AdminNumberFormatOptions,
): string => {
  return JSON.stringify({
    locale: locale || 'en-US',
    useGrouping: shouldUseAdminNumberGrouping(locale),
    currency: options?.currency || '',
    minimumFractionDigits:
      options?.minimumFractionDigits ??
      DEFAULT_ADMIN_NUMBER_FORMAT.minimumFractionDigits,
    maximumFractionDigits:
      options?.maximumFractionDigits ??
      DEFAULT_ADMIN_NUMBER_FORMAT.maximumFractionDigits,
  });
};

const getAdminNumberFormatter = (
  locale: string,
  options?: AdminNumberFormatOptions,
): Intl.NumberFormat => {
  const cacheKey = buildAdminNumberFormatterKey(locale, options);
  const cachedFormatter = adminNumberFormatterCache.get(cacheKey);
  if (cachedFormatter) {
    return cachedFormatter;
  }

  const formatter = new Intl.NumberFormat(locale || 'en-US', {
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
  });
  adminNumberFormatterCache.set(cacheKey, formatter);
  return formatter;
};

export function formatAdminNumber(
  value: unknown,
  locale: string,
  options?: AdminNumberFormatOptions,
): string {
  const numeric = Number(value ?? 0);
  const safeValue = Number.isFinite(numeric) ? numeric : 0;

  return getAdminNumberFormatter(locale, options).format(safeValue);
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
