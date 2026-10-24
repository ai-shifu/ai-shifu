import { act, renderHook } from '@testing-library/react';
import { getPayUrl, initOrder, queryOrder } from '@/api/order';
import { usePaymentFlow } from './usePaymentFlow';

jest.mock('@/api/order', () => ({
  applyDiscountCode: jest.fn(),
  getPayUrl: jest.fn(),
  initActiveOrder: jest.fn(),
  initOrder: jest.fn(),
  queryOrder: jest.fn(),
  syncPaymentOrder: jest.fn(),
}));

jest.mock('react-use', () => ({
  useInterval: jest.fn(),
}));

const orderSnapshot = {
  order_id: 'order-1',
  price: '200.00',
  value_to_pay: '200.00',
  status: 0,
};

describe('usePaymentFlow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(initOrder).mockResolvedValue(orderSnapshot);
    jest.mocked(queryOrder).mockResolvedValue(orderSnapshot);
  });

  it('does not return a stale payment response after the channel changes', async () => {
    type PayUrlResponse = Awaited<ReturnType<typeof getPayUrl>>;
    let resolveOldPayment: ((value: PayUrlResponse) => void) | undefined;
    const oldPayment = new Promise<PayUrlResponse>(resolve => {
      resolveOldPayment = resolve;
    });
    const currentPayment = {
      order_id: 'order-1',
      user_id: 'user-1',
      price: '200.00',
      channel: 'alipay_qr',
      payment_channel: 'alipay' as const,
      qr_url: 'https://pay.example/alipay',
      payment_payload: {},
      status: 0,
    };
    jest
      .mocked(getPayUrl)
      .mockReturnValueOnce(oldPayment)
      .mockResolvedValueOnce(currentPayment);

    const { result } = renderHook(() =>
      usePaymentFlow({
        courseId: 'course-1',
        isLoggedIn: true,
      }),
    );
    await act(async () => {
      await result.current.initializeOrder();
    });

    let oldResult: unknown;
    await act(async () => {
      const oldRequest = result.current
        .refreshPayment({ channel: 'wx_wap', paymentChannel: 'pingxx' })
        .then(value => {
          oldResult = value;
        });
      await Promise.resolve();
      await Promise.resolve();

      const latestResult = await result.current.refreshPayment({
        channel: 'alipay_qr',
        paymentChannel: 'alipay',
      });
      expect(latestResult).toEqual(currentPayment);

      resolveOldPayment?.({
        order_id: 'order-1',
        user_id: 'user-1',
        price: '200.00',
        channel: 'wx_wap',
        payment_channel: 'pingxx',
        qr_url: 'https://pay.example/cancelled',
        payment_payload: {},
        status: 0,
      });
      await oldRequest;
    });

    expect(oldResult).toBeNull();
    expect(result.current.paymentInfo.qrUrl).toBe(currentPayment.qr_url);
  });
});
