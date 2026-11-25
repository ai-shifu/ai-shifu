import { isGlobalBillingExperience } from './billing-experience';

describe('isGlobalBillingExperience', () => {
  test.each([
    { channels: ['stripe'], expected: true },
    { channels: [' Stripe '], expected: true },
    { channels: ['stripe', 'stripe'], expected: true },
    { channels: ['alipay'], expected: false },
    { channels: ['stripe', 'alipay'], expected: false },
    { channels: [], expected: false },
    { channels: undefined, expected: false },
    { channels: ['wechatpay'], expected: false },
  ])('returns $expected for $channels', ({ channels, expected }) => {
    expect(isGlobalBillingExperience(channels)).toBe(expected);
  });
});
