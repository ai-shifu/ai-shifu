import { act, renderHook } from '@testing-library/react';
import { rememberStripeCheckoutSession } from '@/lib/stripe-storage';
import {
  usePaymentAnalytics,
  usePaymentAnalyticsLifecycle,
  usePaymentOutcomeHandlers,
  type PaymentModalSurface,
} from './use-payment-analytics';

const mockTrackEvent = jest.fn();

jest.mock('@/hooks/use-tracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/lib/currency', () => ({
  getCurrencyCode: (symbol: string) => (symbol === '¥' ? 'CNY' : symbol),
}));

jest.mock('@/lib/learner-error', () => ({
  resolveLearnerPaymentToast: ({
    error,
    message,
    canceledMessage,
  }: {
    error?: Error;
    message?: string;
    canceledMessage: string;
  }) =>
    (message || error?.message || '').includes('cancel')
      ? { message: canceledMessage, variant: 'default' }
      : { message: 'resolved-payment-error', variant: 'destructive' },
}));

jest.mock('@/lib/stripe-storage', () => ({
  rememberStripeCheckoutSession: jest.fn(),
}));

interface HarnessProps {
  surface: PaymentModalSurface;
  open: boolean;
  ready: boolean;
  orderId: string;
  isTimeout: boolean;
  displayPrice: string;
}

const defaultProps: HarnessProps = {
  surface: 'desktop',
  open: true,
  ready: true,
  orderId: 'order-1',
  isTimeout: false,
  displayPrice: '99',
};

const mockSyncOrderStatus = jest.fn();
const mockToast = jest.fn();

const renderAnalytics = (overrides: Partial<HarnessProps> = {}) =>
  renderHook(
    ({ surface, open, ready, orderId, isTimeout, displayPrice }) => {
      const analytics = usePaymentAnalytics({ courseId: 'course-1', surface });
      const lifecycle = usePaymentAnalyticsLifecycle(analytics, {
        open,
        ready,
        orderId,
        isTimeout,
        displayPrice,
        currencySymbol: '¥',
      });
      const handlers = usePaymentOutcomeHandlers(analytics, {
        orderId,
        stripeCheckoutUrl: '',
        syncOrderStatus: mockSyncOrderStatus,
        toast: mockToast,
      });
      return { ...analytics, ...lifecycle, ...handlers };
    },
    { initialProps: { ...defaultProps, ...overrides } },
  );

const eventCalls = (name: string) =>
  mockTrackEvent.mock.calls
    .filter(([eventName]) => eventName === name)
    .map(([, payload]) => payload);

describe('usePaymentAnalytics', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSyncOrderStatus.mockResolvedValue({});
  });

  it.each<PaymentModalSurface>(['desktop', 'mobile'])(
    'tracks the main %s payment flow with surface-specific payloads',
    surface => {
      const { result } = renderAnalytics({ surface });

      expect(eventCalls('learner_pay_modal_view')).toEqual([
        { shifu_bid: 'course-1', price_amount: 99, currency: 'CNY' },
      ]);

      act(() => {
        result.current.trackPaymentAttempt('wx_pub_qr');
      });
      expect(eventCalls('learner_payment_attempt')).toEqual([
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'wechat_qr',
          surface,
        },
      ]);

      act(() => {
        result.current.trackCouponApplied();
      });
      expect(eventCalls('learner_coupon_apply')).toEqual([
        { shifu_bid: 'course-1', outcome: 'success' },
      ]);

      act(() => {
        result.current.trackPaymentResult('success');
      });
      expect(eventCalls('learner_payment_result')).toEqual([
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'wechat_qr',
          surface,
          outcome: 'success',
        },
      ]);
      expect(mockTrackEvent.mock.calls.map(([name]) => name)).toEqual([
        'learner_pay_modal_view',
        'learner_payment_attempt',
        'learner_coupon_apply',
        'learner_payment_result',
      ]);
    },
  );

  it('tracks the modal view once per open lifecycle after it is ready', () => {
    const { rerender } = renderAnalytics({ ready: false });
    expect(eventCalls('learner_pay_modal_view')).toHaveLength(0);

    rerender({ ...defaultProps, ready: true });
    rerender({ ...defaultProps, displayPrice: '88' });
    expect(eventCalls('learner_pay_modal_view')).toHaveLength(1);

    rerender({ ...defaultProps, open: false });
    rerender({ ...defaultProps, open: true, displayPrice: 'not-a-number' });
    expect(eventCalls('learner_pay_modal_view')).toEqual([
      { shifu_bid: 'course-1', price_amount: 99, currency: 'CNY' },
      { shifu_bid: 'course-1', price_amount: 0, currency: 'CNY' },
    ]);
  });

  it('reports a timeout as pending once per timeout', () => {
    const { result, rerender } = renderAnalytics({ surface: 'mobile' });
    act(() => {
      result.current.trackPaymentAttempt('alipay_qr');
    });

    rerender({ ...defaultProps, surface: 'mobile', isTimeout: true });
    rerender({
      ...defaultProps,
      surface: 'mobile',
      isTimeout: true,
      displayPrice: '1',
    });
    expect(eventCalls('learner_payment_status')).toEqual([
      {
        shifu_bid: 'course-1',
        order_id: 'order-1',
        channel: 'alipay_qr',
        surface: 'mobile',
        status: 'pending',
      },
    ]);
  });

  it('records whether a payment was attempted on dismissal', () => {
    const { result } = renderAnalytics({ orderId: '' });
    act(() => {
      result.current.trackModalDismiss();
    });
    act(() => {
      result.current.trackPaymentAttempt('stripe');
      result.current.trackModalDismiss('payment_page');
    });

    expect(eventCalls('learner_pay_modal_dismiss')).toEqual([
      {
        shifu_bid: 'course-1',
        dismiss_surface: 'modal',
        had_payment_attempt: false,
      },
      {
        shifu_bid: 'course-1',
        dismiss_surface: 'payment_page',
        had_payment_attempt: true,
      },
    ]);
  });

  it('drops attempt attribution when the order changes or the modal closes', () => {
    const { result, rerender } = renderAnalytics();
    act(() => {
      result.current.trackPaymentAttempt('wx_pub_qr');
    });
    rerender({ ...defaultProps, orderId: 'order-2' });
    act(() => {
      result.current.trackPaymentResult('success');
    });

    act(() => {
      result.current.trackPaymentAttempt('alipay_qr');
    });
    rerender({ ...defaultProps, orderId: 'order-2', open: false });
    act(() => {
      result.current.trackPaymentResult('success');
      result.current.trackModalDismiss();
    });

    expect(eventCalls('learner_payment_result')).toHaveLength(0);
    expect(eventCalls('learner_pay_modal_dismiss')).toEqual([
      {
        shifu_bid: 'course-1',
        order_id: 'order-2',
        dismiss_surface: 'modal',
        had_payment_attempt: false,
      },
    ]);
  });

  it('tracks a QR attempt once per order, channel and QR URL', () => {
    const { result } = renderAnalytics();
    act(() => {
      result.current.trackQrPaymentAttempt('wx_pub_qr', 'order-1', 'qr-a');
      result.current.trackQrPaymentAttempt('wx_pub_qr', 'order-1', 'qr-a');
      result.current.trackQrPaymentAttempt('wx_pub_qr', 'order-1', 'qr-b');
    });
    expect(eventCalls('learner_payment_attempt')).toHaveLength(2);
  });
});

describe('usePaymentOutcomeHandlers', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSyncOrderStatus.mockResolvedValue({});
  });

  it('attributes a confirmed WeChat JSAPI payment to its attempt', async () => {
    const { result } = renderAnalytics({ surface: 'mobile' });
    const pay = jest.fn().mockResolvedValue(undefined);

    await act(async () => {
      result.current.trackPaymentAttempt('wx_pub_qr');
      const attempt = result.current.trackPaymentAttempt('wx_pub');
      await result.current.settleWechatJsapiPayment({
        attempt,
        pay,
        syncParams: { paymentChannel: 'wechatpay' },
      });
      // The order poll reports success after the provider confirmed it.
      result.current.trackPaymentResult('success');
    });

    expect(pay).toHaveBeenCalledTimes(1);
    expect(mockSyncOrderStatus).toHaveBeenCalledWith({
      paymentChannel: 'wechatpay',
    });
    expect(mockToast).toHaveBeenCalledWith({ title: 'module.pay.paySuccess' });
    expect(eventCalls('learner_payment_result')).toEqual([
      {
        shifu_bid: 'course-1',
        order_id: 'order-1',
        channel: 'wechat_jsapi',
        surface: 'mobile',
        outcome: 'success',
      },
    ]);
  });

  it('reports a pending status when the order sync fails after payment', async () => {
    mockSyncOrderStatus.mockRejectedValueOnce(new Error('sync failed'));
    const { result } = renderAnalytics();

    await act(async () => {
      const attempt = result.current.trackPaymentAttempt('wx_pub');
      await result.current.settleWechatJsapiPayment({
        attempt,
        pay: () => Promise.resolve(),
        syncParams: {},
      });
    });

    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.pay.paymentStatusSyncPending',
      variant: 'default',
    });
    expect(eventCalls('learner_payment_status')).toEqual([
      {
        shifu_bid: 'course-1',
        order_id: 'order-1',
        channel: 'wechat_jsapi',
        surface: 'desktop',
        status: 'pending',
      },
    ]);
    expect(eventCalls('learner_payment_result')).toHaveLength(0);
  });

  it.each([
    ['get_brand_wcpay_request:cancel', 'cancelled', undefined],
    ['provider exploded', 'failed', 'provider_failed'],
  ])(
    'maps a JSAPI rejection "%s" to a %s result',
    async (message, outcome, failureCategory) => {
      const onPayError = jest.fn();
      const { result } = renderAnalytics();

      await act(async () => {
        const attempt = result.current.trackPaymentAttempt('wx_pub');
        await result.current.settleWechatJsapiPayment({
          attempt,
          pay: () => Promise.reject(new Error(message)),
          syncParams: {},
          onPayError,
        });
      });

      expect(onPayError).toHaveBeenCalledWith(new Error(message));
      expect(mockSyncOrderStatus).not.toHaveBeenCalled();
      expect(eventCalls('learner_payment_result')).toEqual([
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'wechat_jsapi',
          surface: 'desktop',
          outcome,
          ...(failureCategory ? { failure_category: failureCategory } : {}),
        },
      ]);
    },
  );

  it('tracks Stripe errors and pending confirmations for the attempt', () => {
    const { result } = renderAnalytics();

    act(() => {
      const pendingAttempt = result.current.trackPaymentAttempt('stripe');
      result.current.handleStripeConfirmationUnavailable(pendingAttempt!);
      result.current.handleStripeError(
        'card declined',
        'failed',
        pendingAttempt,
      );
    });

    expect(eventCalls('learner_payment_status')).toEqual([
      {
        shifu_bid: 'course-1',
        order_id: 'order-1',
        channel: 'stripe',
        surface: 'desktop',
        status: 'pending',
      },
    ]);
    expect(eventCalls('learner_payment_result')).toEqual([
      {
        shifu_bid: 'course-1',
        order_id: 'order-1',
        channel: 'stripe',
        surface: 'desktop',
        outcome: 'failed',
        failure_category: 'provider_failed',
      },
    ]);
    expect(mockToast).toHaveBeenCalledWith({
      title: 'resolved-payment-error',
      variant: 'destructive',
    });
  });

  it('does not start a Stripe checkout attempt without a checkout URL', () => {
    const { result } = renderAnalytics();
    act(() => {
      result.current.handleStripeCheckout();
    });
    expect(eventCalls('learner_payment_attempt')).toHaveLength(0);
    expect(rememberStripeCheckoutSession).not.toHaveBeenCalled();
  });
});
