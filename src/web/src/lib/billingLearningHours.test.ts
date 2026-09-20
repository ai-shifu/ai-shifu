import {
  formatBillingLearningHours,
  getBillingLearningHours,
} from './billingLearningHours';

describe('billing learning-hour estimates', () => {
  test.each([
    [50, 5],
    [1000, 100],
    [50000, 5000],
    [100000, 10000],
    [220000, 22000],
  ])('scales the course reference for %s catalog credits', (credits, hours) => {
    expect(getBillingLearningHours(credits)).toBe(hours);
  });

  test.each([0, -1, NaN, Infinity])(
    'does not promise learning time for an invalid allocation (%s)',
    credits => {
      const t = jest.fn((key: string) => key);
      expect(getBillingLearningHours(credits)).toBeNull();
      expect(formatBillingLearningHours(t, credits, 'en-US')).toBe(
        'module.billing.package.learningHours.unavailable',
      );
    },
  );

  test('keeps a small positive allocation distinct from unavailable time', () => {
    const t = jest.fn((key: string) => key);
    expect(formatBillingLearningHours(t, 5, 'en-US')).toBe(
      'module.billing.package.learningHours.lessThanOne',
    );
  });

  test('formats the estimated hours in the active locale', () => {
    const t = jest.fn((key: string) => key);
    formatBillingLearningHours(t, 50000, 'fr-FR');
    expect(t).toHaveBeenCalledWith(
      'module.billing.package.learningHours.value',
      {
        hours: '5 000',
      },
    );
  });

  test('preserves fractional hours above the less-than-one threshold', () => {
    const t = jest.fn((key: string) => key);
    formatBillingLearningHours(t, 12.5, 'en-US');
    expect(t).toHaveBeenCalledWith(
      'module.billing.package.learningHours.value',
      {
        hours: '1.25',
      },
    );
  });
});
