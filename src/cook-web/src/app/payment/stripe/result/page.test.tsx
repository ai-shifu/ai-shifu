import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { getPaymentDetail, syncStripeCheckout } from '@/c-api/order';
import StripeResultPage from './page';

const mockPush = jest.fn();
const mockSearchParams = new URLSearchParams();

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => ({
    get: (key: string) => mockSearchParams.get(key),
  }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, params?: { seconds?: number }) =>
      params?.seconds !== undefined ? `${key}:${params.seconds}` : key,
  }),
}));

jest.mock('@/c-api/order', () => ({
  getPaymentDetail: jest.fn(),
  syncStripeCheckout: jest.fn(),
}));

jest.mock('@/lib/stripe-storage', () => ({
  consumeStripeCheckoutSession: jest.fn(),
}));

describe('StripeResultPage course return URL', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSearchParams.forEach((_, key) => mockSearchParams.delete(key));
    mockSearchParams.set('order_id', 'order-1');
    jest.useRealTimers();
  });

  test('redirects to the backend canonical course URL after payment', async () => {
    (getPaymentDetail as jest.Mock).mockResolvedValue({
      payment_channel: 'stripe',
      status: 1,
      course_id: 'legacy-bid',
      course_url: '/c/practical-ai-teaching-methods',
    });

    const { unmount } = render(<StripeResultPage />);

    expect(
      await screen.findByText('module.pay.stripeResultSuccessTitle'),
    ).toBeInTheDocument();
    expect(syncStripeCheckout).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.pay.stripeResultBackToChat',
      }),
    );

    expect(mockPush).toHaveBeenCalledWith('/c/practical-ai-teaching-methods');
    unmount();
  });
});
