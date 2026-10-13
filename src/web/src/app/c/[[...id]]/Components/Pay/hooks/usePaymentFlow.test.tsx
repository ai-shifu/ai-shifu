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
  it('submits server-owned selection and consumes an added provider action', async () => {
    const option = {
      id: 'fixture-pay:fixture_qr',
      provider: 'fixture-pay',
      channel: 'fixture_qr',
      method: 'alipay',
      scene: 'qr',
      action: 'qr' as const,
      billing_mode: 'platform_managed' as const,
      label_key: 'module.pay.alipay',
      poll_provider: true,
      requires_open_id: false,
    };
    jest
      .mocked(initOrder)
      .mockResolvedValue({ ...orderSnapshot, payment_options: [option] });
    jest
      .mocked(queryOrder)
      .mockResolvedValue({ ...orderSnapshot, payment_options: [option] });
    jest.mocked(getPayUrl).mockResolvedValue({
      order_id: 'order-1',
      user_id: 'user-1',
      price: '200.00',
      channel: option.channel,
      payment_channel: option.provider,
      qr_url: 'obsolete',
      payment_contract_version: 1,
      payment_action: { type: 'qr', url: 'https://fixture.test/qr' },
      poll_provider: true,
    });
    const { result } = renderHook(() =>
      usePaymentFlow({ courseId: 'course-1', isLoggedIn: true }),
    );
    await act(async () => {
      await result.current.initializeOrder();
    });
    await act(async () => {
      await result.current.refreshPayment({
        channel: 'alipay_qr',
        paymentChannel: 'pingxx',
      });
    });
    expect(getPayUrl).toHaveBeenCalledWith({
      channel: 'fixture_qr',
      orderId: 'order-1',
      paymentChannel: 'fixture-pay',
      paymentOption: option.id,
    });
    expect(result.current.paymentOptions).toEqual([option]);
    expect(result.current.paymentInfo.paymentAction).toEqual({
      type: 'qr',
      url: 'https://fixture.test/qr',
    });
    expect(result.current.paymentInfo.pollProvider).toBe(true);
  });
  it('drops prior options and returns to the legacy API after resetting an order', async () => {
    const option = {
      id: 'fixture-pay:fixture_qr',
      provider: 'fixture-pay',
      channel: 'fixture_qr',
      method: 'alipay',
      scene: 'qr',
      action: 'qr' as const,
      billing_mode: 'platform_managed' as const,
      label_key: 'module.pay.alipay',
      poll_provider: true,
      requires_open_id: false,
    };
    jest
      .mocked(initOrder)
      .mockResolvedValueOnce({ ...orderSnapshot, payment_options: [option] })
      .mockResolvedValueOnce({ ...orderSnapshot, order_id: 'order-2' });
    jest
      .mocked(queryOrder)
      .mockResolvedValue({ ...orderSnapshot, order_id: 'order-2' });
    jest.mocked(getPayUrl).mockResolvedValue({
      order_id: 'order-2',
      user_id: 'user-1',
      price: '200',
      channel: 'alipay_qr',
      payment_channel: 'pingxx',
      qr_url: 'https://pay.example/qr',
    });
    const { result } = renderHook(() =>
      usePaymentFlow({ courseId: 'course-1', isLoggedIn: true }),
    );
    await act(async () => {
      await result.current.initializeOrder();
    });
    expect(result.current.paymentOptions).toEqual([option]);
    act(() => result.current.resetState());
    expect(result.current.paymentOptions).toBeUndefined();
    await act(async () => {
      await result.current.initializeOrder();
    });
    await act(async () => {
      await result.current.refreshPayment({
        channel: 'alipay_qr',
        paymentChannel: 'pingxx',
      });
    });
    expect(getPayUrl).toHaveBeenLastCalledWith({
      orderId: 'order-2',
      channel: 'alipay_qr',
      paymentChannel: 'pingxx',
    });
    expect(result.current.paymentOptions).toBeUndefined();
  });
});
