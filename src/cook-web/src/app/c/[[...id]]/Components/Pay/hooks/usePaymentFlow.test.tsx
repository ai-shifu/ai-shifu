import { act, renderHook } from '@testing-library/react';
import {
  getPayUrl,
  initOrder,
  queryOrder,
  syncPaymentOrder,
} from '@/c-api/order';
import { ORDER_STATUS } from '../constans';
import { usePaymentFlow } from './usePaymentFlow';

let mockIntervalCallback: (() => Promise<void>) | null = null;
let mockNowMs = 0;

const POLLING_TIMEOUT_MS = 1000 * 60 * 3;

jest.mock('react-use', () => ({
  useInterval: (callback: () => Promise<void>, delay: number | null): void => {
    mockIntervalCallback = delay === null ? null : callback;
  },
}));

jest.mock('@/c-api/order', () => ({
  applyDiscountCode: jest.fn(),
  getPayUrl: jest.fn(),
  initActiveOrder: jest.fn(),
  initOrder: jest.fn(),
  queryOrder: jest.fn(),
  syncPaymentOrder: jest.fn(),
}));

const mockedGetPayUrl = getPayUrl as jest.MockedFunction<typeof getPayUrl>;
const mockedInitOrder = initOrder as jest.MockedFunction<typeof initOrder>;
const mockedQueryOrder = queryOrder as jest.MockedFunction<typeof queryOrder>;
const mockedSyncPaymentOrder = syncPaymentOrder as jest.MockedFunction<
  typeof syncPaymentOrder
>;

const pendingOrder = {
  order_id: 'order-1',
  price: '99',
  value_to_pay: '99',
  price_item: [],
  status: ORDER_STATUS.BUY_STATUS_TO_BE_PAID,
};

const paidOrder = {
  ...pendingOrder,
  status: ORDER_STATUS.BUY_STATUS_SUCCESS,
};

const paymentPayload = {
  order_id: 'order-1',
  user_id: 'user-1',
  price: '99',
  channel: 'wx_pub_qr',
  qr_url: 'https://provider.example/qr',
  payment_channel: 'pingxx' as const,
  payment_payload: {},
  status: ORDER_STATUS.BUY_STATUS_TO_BE_PAID,
};

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(resolvePromise => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
};

const runPollingTicks = async (
  count: number,
  elapsedPerTickMs = 1000,
): Promise<void> => {
  for (let tick = 0; tick < count; tick += 1) {
    mockNowMs += elapsedPerTickMs;
    const callback = mockIntervalCallback;
    expect(callback).not.toBeNull();
    await act(async () => {
      await callback?.();
    });
  }
};

const startPendingPayment = async ({
  onOrderPaid,
  onPollingTimeout,
}: {
  onOrderPaid: jest.Mock;
  onPollingTimeout: jest.Mock;
}) => {
  const hook = renderHook(() =>
    usePaymentFlow({
      courseId: 'course-1',
      isLoggedIn: true,
      onOrderPaid,
      onPollingTimeout,
    }),
  );

  await act(async () => {
    await hook.result.current.initializeOrder();
  });
  await act(async () => {
    await hook.result.current.refreshPayment({
      channel: 'wx_pub_qr',
      paymentChannel: 'pingxx',
    });
  });

  expect(mockIntervalCallback).not.toBeNull();
  return hook;
};

describe('usePaymentFlow polling timeout', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIntervalCallback = null;
    mockNowMs = 0;
    jest.spyOn(Date, 'now').mockImplementation(() => mockNowMs);
    mockedInitOrder.mockResolvedValue(pendingOrder);
    mockedQueryOrder.mockResolvedValue(pendingOrder);
    mockedGetPayUrl.mockResolvedValue(paymentPayload);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('uses the wall-clock deadline when interval ticks are skipped', async () => {
    const onOrderPaid = jest.fn();
    const onPollingTimeout = jest.fn();
    const hook = await startPendingPayment({
      onOrderPaid,
      onPollingTimeout,
    });

    await runPollingTicks(1, POLLING_TIMEOUT_MS);

    expect(mockedQueryOrder).toHaveBeenCalledTimes(2);
    expect(onPollingTimeout).toHaveBeenCalledTimes(1);
    expect(onOrderPaid).not.toHaveBeenCalled();
    expect(hook.result.current.countDownMs).toBe(0);
    expect(hook.result.current.isTimeout).toBe(true);
  });

  it('does not extend the deadline while an order query is in flight', async () => {
    const onOrderPaid = jest.fn();
    const onPollingTimeout = jest.fn();
    const hook = await startPendingPayment({
      onOrderPaid,
      onPollingTimeout,
    });
    const deferredQuery = createDeferred<typeof pendingOrder>();
    mockedQueryOrder.mockReturnValueOnce(deferredQuery.promise);
    const callback = mockIntervalCallback;
    let inFlightTick: Promise<void> | undefined;

    mockNowMs += 1000;
    await act(async () => {
      inFlightTick = callback?.();
      await Promise.resolve();
    });
    mockNowMs += POLLING_TIMEOUT_MS - 1000;
    await act(async () => {
      await callback?.();
    });

    expect(mockedQueryOrder).toHaveBeenCalledTimes(2);
    expect(hook.result.current.countDownMs).toBe(0);
    expect(hook.result.current.isTimeout).toBe(true);
    expect(onPollingTimeout).not.toHaveBeenCalled();

    await act(async () => {
      deferredQuery.resolve(pendingOrder);
      await inFlightTick;
    });

    expect(onPollingTimeout).toHaveBeenCalledTimes(1);
    expect(onOrderPaid).not.toHaveBeenCalled();
    expect(hook.result.current.isTimeout).toBe(true);
  });

  it('preserves a paid result returned by the final deadline query', async () => {
    const onOrderPaid = jest.fn();
    const onPollingTimeout = jest.fn();
    const hook = await startPendingPayment({
      onOrderPaid,
      onPollingTimeout,
    });

    await runPollingTicks(179);
    mockedQueryOrder.mockResolvedValueOnce(paidOrder);
    const deadlineCallback = mockIntervalCallback;
    await runPollingTicks(1);
    await act(async () => {
      await deadlineCallback?.();
    });

    expect(onOrderPaid).toHaveBeenCalledTimes(1);
    expect(onPollingTimeout).not.toHaveBeenCalled();
    expect(hook.result.current.isCompleted).toBe(true);
    expect(hook.result.current.isTimeout).toBe(false);
  });

  it('does not restart polling when a late paid result wins during a retry', async () => {
    const onOrderPaid = jest.fn();
    const onPollingTimeout = jest.fn();
    const hook = await startPendingPayment({ onOrderPaid, onPollingTimeout });
    const latePoll = createDeferred<typeof paidOrder>();
    const retryPayment = createDeferred<typeof paymentPayload>();
    mockedQueryOrder.mockReturnValueOnce(latePoll.promise);
    mockedQueryOrder.mockResolvedValueOnce(pendingOrder);
    mockedGetPayUrl.mockReturnValueOnce(retryPayment.promise);
    const pollingCallback = mockIntervalCallback;
    let inFlightPoll: Promise<void> | undefined;
    let retry: Promise<unknown> | undefined;

    mockNowMs += 1000;
    await act(async () => {
      inFlightPoll = pollingCallback?.();
      await Promise.resolve();
    });
    mockNowMs += POLLING_TIMEOUT_MS - 1000;
    await act(async () => {
      await pollingCallback?.();
    });

    expect(hook.result.current.isTimeout).toBe(true);
    await act(async () => {
      retry = hook.result.current.refreshPayment({
        channel: 'wx_pub_qr',
        paymentChannel: 'pingxx',
      });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mockedGetPayUrl).toHaveBeenCalledTimes(2);

    await act(async () => {
      latePoll.resolve(paidOrder);
      await inFlightPoll;
    });
    expect(onOrderPaid).toHaveBeenCalledTimes(1);
    expect(hook.result.current.isCompleted).toBe(true);
    expect(hook.result.current.isTimeout).toBe(false);

    let retryResult: unknown;
    await act(async () => {
      retryPayment.resolve(paymentPayload);
      retryResult = await retry;
    });

    expect(retryResult).toBeNull();
    expect(hook.result.current.isCompleted).toBe(true);
    expect(hook.result.current.isTimeout).toBe(false);
    expect(mockIntervalCallback).toBeNull();
    expect(onPollingTimeout).not.toHaveBeenCalled();
  });

  it('accepts a stale-generation paid result after a retry restarts polling', async () => {
    const onOrderPaid = jest.fn();
    const onPollingTimeout = jest.fn();
    const hook = await startPendingPayment({ onOrderPaid, onPollingTimeout });
    const latePoll = createDeferred<typeof paidOrder>();
    mockedQueryOrder.mockReturnValueOnce(latePoll.promise);
    mockedQueryOrder.mockResolvedValueOnce(pendingOrder);
    const pollingCallback = mockIntervalCallback;
    let inFlightPoll: Promise<void> | undefined;

    mockNowMs += 1000;
    await act(async () => {
      inFlightPoll = pollingCallback?.();
      await Promise.resolve();
    });
    mockNowMs += POLLING_TIMEOUT_MS - 1000;
    await act(async () => {
      await pollingCallback?.();
    });

    expect(hook.result.current.isTimeout).toBe(true);
    await act(async () => {
      await hook.result.current.refreshPayment({
        channel: 'wx_pub_qr',
        paymentChannel: 'pingxx',
      });
    });
    expect(hook.result.current.isTimeout).toBe(false);
    expect(mockIntervalCallback).not.toBeNull();
    const currentPoll = createDeferred<typeof paidOrder>();
    mockedQueryOrder.mockReturnValueOnce(currentPoll.promise);
    const restartedPollingCallback = mockIntervalCallback;
    let currentGenerationPoll: Promise<void> | undefined;
    await act(async () => {
      currentGenerationPoll = restartedPollingCallback?.();
      await Promise.resolve();
    });

    await act(async () => {
      latePoll.resolve(paidOrder);
      await inFlightPoll;
    });

    expect(onOrderPaid).toHaveBeenCalledTimes(1);
    expect(onPollingTimeout).not.toHaveBeenCalled();
    expect(hook.result.current.isCompleted).toBe(true);
    expect(hook.result.current.isTimeout).toBe(false);
    expect(mockIntervalCallback).toBeNull();

    await act(async () => {
      currentPoll.resolve(paidOrder);
      await currentGenerationPoll;
    });
    expect(onOrderPaid).toHaveBeenCalledTimes(1);
  });

  it('keeps paid ahead of a concurrent pending deadline result', async () => {
    const onOrderPaid = jest.fn();
    const onPollingTimeout = jest.fn();
    const hook = await startPendingPayment({ onOrderPaid, onPollingTimeout });
    const pendingDeadlineQuery = createDeferred<typeof pendingOrder>();
    mockedQueryOrder.mockReturnValueOnce(pendingDeadlineQuery.promise);
    mockedQueryOrder.mockResolvedValueOnce(paidOrder);
    const deadlineCallback = mockIntervalCallback;
    let deadlinePoll: Promise<void> | undefined;

    mockNowMs += POLLING_TIMEOUT_MS;
    await act(async () => {
      deadlinePoll = deadlineCallback?.();
      await Promise.resolve();
    });
    expect(hook.result.current.isTimeout).toBe(true);

    await act(async () => {
      await hook.result.current.syncOrderStatus();
    });
    expect(onOrderPaid).toHaveBeenCalledTimes(1);
    expect(hook.result.current.isCompleted).toBe(true);
    expect(hook.result.current.isTimeout).toBe(false);

    await act(async () => {
      pendingDeadlineQuery.resolve(pendingOrder);
      await deadlinePoll;
    });

    expect(onOrderPaid).toHaveBeenCalledTimes(1);
    expect(onPollingTimeout).not.toHaveBeenCalled();
    expect(hook.result.current.isCompleted).toBe(true);
    expect(hook.result.current.isTimeout).toBe(false);
    expect(mockIntervalCallback).toBeNull();
  });

  it('lets only the latest overlapping retry restart polling', async () => {
    const onOrderPaid = jest.fn();
    const onPollingTimeout = jest.fn();
    const hook = await startPendingPayment({ onOrderPaid, onPollingTimeout });
    const firstPayment = createDeferred<typeof paymentPayload>();
    const secondPayment = createDeferred<typeof paymentPayload>();
    mockedGetPayUrl.mockReturnValueOnce(firstPayment.promise);
    mockedGetPayUrl.mockReturnValueOnce(secondPayment.promise);
    let firstRetry: Promise<unknown> | undefined;
    let secondRetry: Promise<unknown> | undefined;

    await act(async () => {
      firstRetry = hook.result.current.refreshPayment({
        channel: 'wx_pub_qr',
        paymentChannel: 'pingxx',
      });
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      secondRetry = hook.result.current.refreshPayment({
        channel: 'wx_pub_qr',
        paymentChannel: 'pingxx',
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    let firstResult: unknown;
    await act(async () => {
      firstPayment.resolve({
        ...paymentPayload,
        qr_url: 'https://provider.example/stale-qr',
      });
      firstResult = await firstRetry;
    });
    expect(firstResult).toBeNull();
    expect(hook.result.current.isLoading).toBe(true);

    const latestPayment = {
      ...paymentPayload,
      qr_url: 'https://provider.example/latest-qr',
    };
    let secondResult: unknown;
    await act(async () => {
      secondPayment.resolve(latestPayment);
      secondResult = await secondRetry;
    });

    expect(secondResult).toEqual(latestPayment);
    expect(hook.result.current.paymentInfo.qrUrl).toBe(latestPayment.qr_url);
    expect(hook.result.current.isLoading).toBe(false);
    expect(mockIntervalCallback).not.toBeNull();
    expect(onOrderPaid).not.toHaveBeenCalled();
    expect(onPollingTimeout).not.toHaveBeenCalled();
  });

  it('accepts a stale paid retry query when the latest retry fails', async () => {
    const onOrderPaid = jest.fn();
    const onPollingTimeout = jest.fn();
    const hook = await startPendingPayment({ onOrderPaid, onPollingTimeout });
    await runPollingTicks(180);
    const stalePaidQuery = createDeferred<typeof paidOrder>();
    mockedQueryOrder.mockReturnValueOnce(stalePaidQuery.promise);
    let staleRetry: Promise<unknown> | undefined;

    await act(async () => {
      staleRetry = hook.result.current.refreshPayment({
        channel: 'wx_pub_qr',
        paymentChannel: 'pingxx',
      });
      await Promise.resolve();
    });
    mockedQueryOrder.mockResolvedValueOnce(pendingOrder);
    mockedGetPayUrl.mockRejectedValueOnce(new Error('provider unavailable'));
    let latestRetryError: unknown;
    await act(async () => {
      try {
        await hook.result.current.refreshPayment({
          channel: 'wx_pub_qr',
          paymentChannel: 'pingxx',
        });
      } catch (error) {
        latestRetryError = error;
      }
    });

    expect(latestRetryError).toEqual(new Error('provider unavailable'));
    expect(hook.result.current.isTimeout).toBe(true);
    expect(mockIntervalCallback).toBeNull();

    let staleRetryResult: unknown;
    await act(async () => {
      stalePaidQuery.resolve(paidOrder);
      staleRetryResult = await staleRetry;
    });

    expect(staleRetryResult).toBeNull();
    expect(onOrderPaid).toHaveBeenCalledTimes(1);
    expect(onPollingTimeout).toHaveBeenCalledTimes(1);
    expect(hook.result.current.isCompleted).toBe(true);
    expect(hook.result.current.isTimeout).toBe(false);
    expect(mockIntervalCallback).toBeNull();
  });

  it('reports one timeout per still-pending attempt and resets for a retry', async () => {
    const onOrderPaid = jest.fn();
    const onPollingTimeout = jest.fn();
    const hook = await startPendingPayment({
      onOrderPaid,
      onPollingTimeout,
    });

    await runPollingTicks(180);

    expect(onPollingTimeout).toHaveBeenCalledTimes(1);
    expect(onOrderPaid).not.toHaveBeenCalled();
    expect(hook.result.current.isTimeout).toBe(true);

    await act(async () => {
      await hook.result.current.refreshPayment({
        channel: 'wx_pub_qr',
        paymentChannel: 'pingxx',
      });
    });
    expect(hook.result.current.isTimeout).toBe(false);

    await runPollingTicks(180);
    expect(onPollingTimeout).toHaveBeenCalledTimes(2);
    expect(onOrderPaid).not.toHaveBeenCalled();
  });

  it('expires the UI without reporting pending when the deadline query rejects', async () => {
    const onOrderPaid = jest.fn();
    const onPollingTimeout = jest.fn();
    const hook = await startPendingPayment({ onOrderPaid, onPollingTimeout });

    await runPollingTicks(179);
    mockedQueryOrder.mockRejectedValueOnce(new Error('query unavailable'));
    const deadlineCallback = mockIntervalCallback;
    let deadlineError: unknown;
    mockNowMs += 1000;
    await act(async () => {
      try {
        await deadlineCallback?.();
      } catch (error) {
        deadlineError = error;
      }
    });

    expect(deadlineError).toEqual(new Error('query unavailable'));
    expect(onPollingTimeout).not.toHaveBeenCalled();
    expect(onOrderPaid).not.toHaveBeenCalled();
    expect(hook.result.current.countDownMs).toBe(0);
    expect(hook.result.current.isTimeout).toBe(true);
    expect(mockIntervalCallback).toBeNull();
    expect(mockedSyncPaymentOrder).not.toHaveBeenCalled();
  });
});
