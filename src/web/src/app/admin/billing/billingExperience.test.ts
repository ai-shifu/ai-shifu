import { isGlobalBillingExperience } from './billingExperience';

describe('isGlobalBillingExperience', () => {
  test.each([
    { channels: ['stripe'], expected: true },
    { channels: [' Stripe '], expected: true },
    { channels: ['stripe', 'stripe'], expected: true },
    { channels: ['pingxx'], expected: false },
    { channels: ['stripe', 'pingxx'], expected: false },
    { channels: [], expected: false },
    { channels: undefined, expected: false },
    { channels: ['wechatpay'], expected: false },
  ])('returns $expected for $channels', ({ channels, expected }) => {
    expect(isGlobalBillingExperience(channels)).toBe(expected);
  });
});
