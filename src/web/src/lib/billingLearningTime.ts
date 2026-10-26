// AI literacy course reference: a reading completion used 25.24 credits at 1×.
// Assuming 2.5 hours per completion gives about 6,000 minutes per 1,000 credits.
// Methodology: docs/product-specs/billing-learning-hours-estimate.md.
const READING_MINUTES_PER_1000_CREDITS = 6000;

type BillingTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export function getBillingLearningMinutes(creditAmount: number) {
  if (!Number.isFinite(creditAmount) || creditAmount <= 0) {
    return null;
  }

  return (creditAmount / 1000) * READING_MINUTES_PER_1000_CREDITS;
}

export function formatBillingLearningTime(
  t: BillingTranslator,
  creditAmount: number,
  locale: string,
): string {
  const estimate = getBillingLearningMinutes(creditAmount);
  if (estimate === null) {
    return t('module.billing.package.learningTime.unavailable');
  }
  if (estimate < 1) {
    return t('module.billing.package.learningTime.lessThanOne');
  }
  const isCompact = estimate >= 10000;
  const minutes = new Intl.NumberFormat(locale || 'en-US', {
    notation: isCompact ? 'compact' : 'standard',
    maximumFractionDigits: 2,
  })
    .formatToParts(estimate)
    .map(part =>
      part.type === 'compact' && locale.startsWith('zh')
        ? ` ${part.value}`
        : part.value,
    )
    .join('');

  return t(
    isCompact
      ? 'module.billing.package.learningTime.compactValue'
      : 'module.billing.package.learningTime.value',
    { minutes },
  );
}
