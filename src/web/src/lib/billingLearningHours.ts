import { formatBillingNumber } from '@/lib/billing';

// AI literacy course reference: a reading completion used 25.24 credits at 1×.
// Assuming 2.5 hours per completion gives about 100 hours per 1,000 credits.
// Methodology: docs/product-specs/billing-learning-hours-estimate.md.
const READING_HOURS_PER_1000_CREDITS = 100;

type BillingTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export function getBillingLearningHours(creditAmount: number) {
  if (!Number.isFinite(creditAmount) || creditAmount <= 0) {
    return null;
  }

  return (creditAmount / 1000) * READING_HOURS_PER_1000_CREDITS;
}

export function formatBillingLearningHours(
  t: BillingTranslator,
  creditAmount: number,
  locale: string,
): string {
  const estimate = getBillingLearningHours(creditAmount);
  if (estimate === null) {
    return t('module.billing.package.learningHours.unavailable');
  }
  if (estimate < 1) {
    return t('module.billing.package.learningHours.lessThanOne');
  }
  return t('module.billing.package.learningHours.value', {
    hours: formatBillingNumber(estimate, locale),
  });
}
