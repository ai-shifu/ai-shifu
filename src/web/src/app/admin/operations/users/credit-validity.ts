export type CreditValidityUnit = 'day' | 'month' | 'year';

export const CREDIT_VALIDITY_UNITS: CreditValidityUnit[] = [
  'day',
  'month',
  'year',
];

// Match the backend UTC calendar arithmetic, including month-end clipping.
// This is a preview only; persisted expiry always comes from the server.
export function estimateCreditExpiry(
  grantedAt: Date,
  value: string,
  unit: string,
): Date | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const count = Number(value);
  if (!Number.isSafeInteger(count) || count <= 0) return null;
  if (!CREDIT_VALIDITY_UNITS.includes(unit as CreditValidityUnit)) return null;

  const expiry = new Date(grantedAt.getTime());
  if (unit === 'day') {
    expiry.setTime(expiry.getTime() + count * 86400000);
  } else {
    const monthIndex =
      grantedAt.getUTCFullYear() * 12 +
      grantedAt.getUTCMonth() +
      count * (unit === 'year' ? 12 : 1);
    const year = Math.floor(monthIndex / 12);
    const month = monthIndex % 12;
    if (year > 9999) return null;
    const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
    expiry.setUTCFullYear(
      year,
      month,
      Math.min(grantedAt.getUTCDate(), lastDay),
    );
  }
  return Number.isFinite(expiry.getTime()) && expiry.getUTCFullYear() <= 9999
    ? expiry
    : null;
}
