import {
  formatBillingLearningTime,
  getBillingLearningMinutes,
} from './billingLearningTime';

describe('billing learning-time estimates', () => {
  test.each([
    [50, 300, '300'],
    [1000, 6000, '6,000'],
    [50000, 300000, '30 万'],
    [100000, 600000, '60 万'],
    [220000, 1320000, '132 万'],
  ])(
    'uses minutes consistently for %s catalog credits',
    (credits, minutes, formatted) => {
      const t = jest.fn((key: string) => key);
      expect(getBillingLearningMinutes(credits)).toBe(minutes);
      formatBillingLearningTime(t, credits, 'zh-CN');
      expect(t).toHaveBeenCalledWith(
        'module.billing.package.learningTime.value',
        {
          minutes: formatted,
        },
      );
    },
  );

  test.each([0, -1, NaN, Infinity])(
    'does not promise learning time for an invalid allocation (%s)',
    credits => {
      const t = jest.fn((key: string) => key);
      expect(getBillingLearningMinutes(credits)).toBeNull();
      expect(formatBillingLearningTime(t, credits, 'en-US')).toBe(
        'module.billing.package.learningTime.unavailable',
      );
    },
  );

  test('keeps a positive sub-minute estimate distinct from unavailable time', () => {
    const t = jest.fn((key: string) => key);
    expect(formatBillingLearningTime(t, 0.1, 'en-US')).toBe(
      'module.billing.package.learningTime.lessThanOne',
    );
  });

  test.each([
    [1000, 'fr-FR', '6 000'],
    [50000, 'en-US', '300K'],
    [220000, 'en-US', '1.32M'],
    [1666, 'zh-CN', '9,996'],
    [1667, 'zh-CN', '1 万'],
    [3.25, 'en-US', '19.5'],
  ])('formats %s credits in %s', (credits, locale, minutes) => {
    const t = jest.fn((key: string) => key);
    formatBillingLearningTime(t, credits, locale);
    expect(t).toHaveBeenCalledWith(
      'module.billing.package.learningTime.value',
      {
        minutes,
      },
    );
  });
});
