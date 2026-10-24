import {
  formatBillingLearningTime,
  getBillingLearningMinutes,
} from './billingLearningTime';

describe('billing learning-time estimates', () => {
  test.each([
    [50, 300, '300', 'value'],
    [1000, 6000, '6,000', 'value'],
    [50000, 300000, '30 万', 'compactValue'],
    [100000, 600000, '60 万', 'compactValue'],
    [220000, 1320000, '132 万', 'compactValue'],
  ])(
    'uses minutes consistently for %s catalog credits',
    (credits, minutes, formatted, template) => {
      const t = jest.fn((key: string) => key);
      expect(getBillingLearningMinutes(credits)).toBe(minutes);
      formatBillingLearningTime(t, credits, 'zh-CN');
      expect(t).toHaveBeenCalledWith(
        `module.billing.package.learningTime.${template}`,
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
    [1000, 'fr-FR', '6 000', 'value'],
    [50000, 'en-US', '300K', 'compactValue'],
    [220000, 'en-US', '1.32M', 'compactValue'],
    [1666, 'zh-CN', '9,996', 'value'],
    [1667, 'zh-CN', '1 万', 'compactValue'],
    [3.25, 'en-US', '19.5', 'value'],
  ])('formats %s credits in %s', (credits, locale, minutes, template) => {
    const t = jest.fn((key: string) => key);
    formatBillingLearningTime(t, credits, locale);
    expect(t).toHaveBeenCalledWith(
      `module.billing.package.learningTime.${template}`,
      {
        minutes,
      },
    );
  });
});
