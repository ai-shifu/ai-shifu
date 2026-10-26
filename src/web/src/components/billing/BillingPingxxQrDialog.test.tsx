import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { BillingPingxxQrDialog } from './BillingPingxxQrDialog';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { countdown?: string }) =>
      options?.countdown || key,
    i18n: { language: 'en-US' },
  }),
}));

jest.mock('@/lib/billing', () => ({
  formatBillingPrice: () => '99.00',
  getPaymentAgreementUrl: () => null,
  resolveBillingPingxxChannelLabel: () => 'Alipay',
}));

describe('BillingPingxxQrDialog payment expiry', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  test('resets the countdown only when the payment order changes', () => {
    const props = {
      amountInMinor: 9900,
      currency: 'CNY',
      description: 'Subscription payment',
      expiresInSeconds: 1800,
      open: true,
      productName: 'Monthly plan',
      provider: 'alipay' as const,
      qrUrl: 'https://payments.test/old',
      selectedChannel: 'alipay_qr' as const,
      agreed: true,
      onChannelChange: jest.fn(),
      onAgreedChange: jest.fn(),
      onOpenChange: jest.fn(),
    };
    const { rerender, unmount } = render(
      <BillingPingxxQrDialog
        {...props}
        billingOrderBid='old-order'
      />,
    );
    const countdown = () =>
      screen.getByTestId('billing-pingxx-expiration-countdown');
    expect(countdown()).toHaveTextContent('30:00');
    act(() => jest.advanceTimersByTime(300000));
    expect(countdown()).toHaveTextContent('25:00');

    rerender(
      <BillingPingxxQrDialog
        {...props}
        billingOrderBid='old-order'
      />,
    );
    expect(countdown()).toHaveTextContent('25:00');
    rerender(
      <BillingPingxxQrDialog
        {...props}
        billingOrderBid='new-order'
        qrUrl='https://payments.test/new'
      />,
    );
    expect(countdown()).toHaveTextContent('30:00');
    act(() => jest.advanceTimersByTime(1000));
    expect(countdown()).toHaveTextContent('29:59');
    unmount();
  });
});
