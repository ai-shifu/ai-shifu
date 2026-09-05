import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import StripeResultPage from './page';
import { getPaymentDetail, syncStripeCheckout } from '@/api/order';

const mockPush = jest.fn();
const mockTrackEvent = jest.fn();
const mockSearchParams = new URLSearchParams();
const mockStableSearchParams = {
  get: (key: string) => mockSearchParams.get(key),
};
const mockT = (key: string) => key;

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => mockStableSearchParams,
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: mockT }),
}));

jest.mock('@/api/order', () => ({
  getPaymentDetail: jest.fn(),
  syncStripeCheckout: jest.fn(),
}));

jest.mock('@/lib/stripe-storage', () => ({
  consumeStripeCheckoutSession: jest.fn(),
}));

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

const mockGetPaymentDetail = getPaymentDetail as jest.Mock;
const mockSyncStripeCheckout = syncStripeCheckout as jest.Mock;

describe('StripeResultPage analytics contract', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockTrackEvent.mockReset();
    mockGetPaymentDetail.mockReset();
    mockSyncStripeCheckout.mockReset();
    Array.from(mockSearchParams.keys()).forEach(key =>
      mockSearchParams.delete(key),
    );
  });

  it('records one successful terminal result with stable identifiers', async () => {
    mockSearchParams.set('order_id', 'order-1');
    mockGetPaymentDetail.mockResolvedValue({
      payment_channel: 'stripe',
      status: 1,
      course_id: 'course-1',
    });

    render(<StripeResultPage />);

    expect(
      await screen.findByText('module.pay.stripeResultSuccessTitle'),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith('learner_payment_result', {
        shifu_bid: 'course-1',
        order_id: 'order-1',
        channel: 'stripe',
        surface: 'stripe_return',
        outcome: 'success',
      }),
    );
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
  });

  it('records pending status without misclassifying it as failure', async () => {
    mockSearchParams.set('order_id', 'order-2');
    mockGetPaymentDetail.mockResolvedValue({
      payment_channel: 'stripe',
      status: 0,
      course_id: 'course-2',
    });

    render(<StripeResultPage />);

    expect(
      await screen.findByText('module.pay.stripeResultPendingTitle'),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith('learner_payment_status', {
        shifu_bid: 'course-2',
        order_id: 'order-2',
        channel: 'stripe',
        surface: 'stripe_return',
        status: 'pending',
      }),
    );
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_payment_result',
      expect.anything(),
    );
  });

  it('records an explicit Stripe cancel return as a cancelled result', async () => {
    mockSearchParams.set('order_id', 'order-cancelled');
    mockSearchParams.set('canceled', '1');
    mockGetPaymentDetail.mockResolvedValue({
      payment_channel: 'stripe',
      status: 0,
      course_id: 'course-cancelled',
    });

    render(<StripeResultPage />);

    expect(
      await screen.findByText('module.pay.stripeResultPendingTitle'),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith('learner_payment_result', {
        shifu_bid: 'course-cancelled',
        order_id: 'order-cancelled',
        channel: 'stripe',
        surface: 'stripe_return',
        outcome: 'cancelled',
      }),
    );
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_payment_status',
      expect.anything(),
    );
  });

  it.each(['pingxx', 'alipay', 'wechatpay'])(
    'does not attribute a cancelled %s order to Stripe',
    async paymentChannel => {
      mockSearchParams.set('order_id', `order-${paymentChannel}`);
      mockSearchParams.set('session_id', 'unrelated-stripe-session');
      mockSearchParams.set('canceled', '1');
      mockGetPaymentDetail.mockResolvedValue({
        payment_channel: paymentChannel,
        status: 0,
        course_id: 'course-other-provider',
      });

      render(<StripeResultPage />);

      expect(
        await screen.findByText('module.pay.stripeResultPendingTitle'),
      ).toBeInTheDocument();
      expect(mockSyncStripeCheckout).not.toHaveBeenCalled();
      await waitFor(() => expect(mockGetPaymentDetail).toHaveBeenCalled());
      expect(mockTrackEvent).not.toHaveBeenCalled();
    },
  );

  it('uses a bounded missing-order category while analytics remains best-effort', async () => {
    mockTrackEvent.mockResolvedValue(undefined);

    render(<StripeResultPage />);

    expect(
      await screen.findByText('module.pay.stripeResultErrorTitle'),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith('learner_payment_result', {
        channel: 'stripe',
        surface: 'stripe_return',
        outcome: 'failed',
        failure_category: 'missing_order',
      }),
    );
  });

  it('does not include a raw status lookup error in the failure event', async () => {
    mockSearchParams.set('order_id', 'private-person@example.test');
    mockGetPaymentDetail.mockRejectedValue(
      new Error('private provider response'),
    );

    render(<StripeResultPage />);

    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith('learner_payment_result', {
        channel: 'stripe',
        surface: 'stripe_return',
        outcome: 'failed',
        failure_category: 'status_lookup_failed',
      }),
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private provider response',
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private-person@example.test',
    );
  });
});
