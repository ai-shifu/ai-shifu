import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { PayModal } from './PayModal';
import { PayModalM } from './PayModalM';
import { ORDER_STATUS } from './constans';

const mockTrackEvent = jest.fn();
const mockToast = jest.fn();
const mockPayByJsApi = jest.fn();
const mockInitializeOrder = jest.fn();
const mockRefreshPayment = jest.fn();
const mockApplyCoupon = jest.fn();
const mockSyncOrderStatus = jest.fn();
const mockUsePaymentFlow = jest.fn();

let mockPaymentFlowState: Record<string, any>;
let mockEnvState: Record<string, any>;
let mockWechatJsapiAvailable = false;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('zustand/react/shallow', () => ({
  useShallow: (selector: unknown) => selector,
}));

jest.mock('next/image', () => ({
  __esModule: true,
  default: ({
    alt = '',
    ...props
  }: React.ImgHTMLAttributes<HTMLImageElement>) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      alt={alt}
      {...props}
    />
  ),
}));

jest.mock('qrcode.react', () => ({
  QRCodeSVG: ({ value }: { value: string }) => (
    <div data-testid='qr-code'>{value}</div>
  ),
}));

jest.mock('@/components/ui/Dialog', () => ({
  Dialog: ({
    children,
    onOpenChange,
    open,
  }: React.PropsWithChildren<{
    onOpenChange?: (open: boolean) => void;
    open?: boolean;
  }>) =>
    open ? (
      <div>
        {children}
        <button
          data-testid='dialog-dismiss'
          onClick={() => onOpenChange?.(false)}
        />
      </div>
    ) : null,
  DialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

jest.mock('@/components/ui/Button', () => ({
  Button: ({
    children,
    disabled,
    onClick,
  }: React.PropsWithChildren<{
    disabled?: boolean;
    onClick?: React.MouseEventHandler<HTMLButtonElement>;
  }>) => (
    <button
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  ),
}));

jest.mock('@/components/ui/RadioGroup', () => ({
  RadioGroup: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  RadioGroupItem: ({ value }: { value: string }) => (
    <span data-testid={`radio-${value}`} />
  ),
}));

jest.mock('@/c-components/m/MainButtonM', () => ({
  __esModule: true,
  default: ({
    children,
    disabled,
    onClick,
  }: React.PropsWithChildren<{
    disabled?: boolean;
    onClick?: React.MouseEventHandler<HTMLButtonElement>;
  }>) => (
    <button
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  ),
}));

jest.mock('./PayModalFooter', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('./PayChannelSwitch', () => ({
  __esModule: true,
  default: ({
    onChange,
  }: {
    onChange?: (value: { channel: string }) => void;
  }) => (
    <button
      data-testid='pay-channel-switch'
      onClick={() => onChange?.({ channel: 'alipay_qr' })}
    />
  ),
}));

jest.mock('./CouponCodeModal', () => ({
  __esModule: true,
  default: ({
    onOk,
  }: {
    onOk?: (values: { couponCode: string }) => void | Promise<void>;
  }) => (
    <button
      data-testid='desktop-coupon-submit'
      onClick={() => void onOk?.({ couponCode: 'desktop-sensitive-coupon' })}
    />
  ),
}));

jest.mock('@/c-components/m/SettingInputM', () => ({
  SettingInputM: ({
    onChange,
    value,
  }: {
    onChange?: (value: string) => void;
    value?: string;
  }) => (
    <input
      data-testid='mobile-coupon-input'
      value={value}
      onChange={event => onChange?.(event.target.value)}
    />
  ),
}));

jest.mock('./StripeCardForm', () => ({
  __esModule: true,
  default: ({
    onAttempt,
    onConfirmSuccess,
    onError,
  }: {
    onAttempt: () => void;
    onConfirmSuccess: () => Promise<void>;
    onError: (message: string) => void;
  }) => (
    <>
      <button
        data-testid='stripe-submit'
        onClick={() => {
          onAttempt();
          void onConfirmSuccess();
        }}
      />
      <button
        data-testid='stripe-fail'
        onClick={() => {
          onAttempt();
          onError('private-stripe-provider-error');
        }}
      />
      <button
        data-testid='stripe-late-fail'
        onClick={() => onError('private-stripe-late-error')}
      />
    </>
  ),
}));

jest.mock('./hooks/usePaymentFlow', () => ({
  usePaymentFlow: (options: Record<string, unknown>) =>
    mockUsePaymentFlow(options),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/store', () => ({
  useUserStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      isLoggedIn: true,
      userInfo: { openid: 'openid-1', language: 'zh-CN' },
    }),
}));

jest.mock('@/c-store/envStore', () => ({
  useEnvStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('@/c-store/useSystemStore', () => ({
  useSystemStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({ previewMode: false }),
}));

jest.mock('@/c-utils/envUtils', () => ({
  getStringEnv: () => 'course-1',
}));

jest.mock('@/c-utils/currency', () => ({
  getCurrencyCode: (symbol: string) => {
    if (symbol === '¥') return 'CNY';
    if (symbol === '$') return 'USD';
    return symbol.trim().toUpperCase();
  },
}));

jest.mock('@/i18n', () => ({
  normalizeLanguage: () => 'zh-CN',
}));

jest.mock('@/c-common/hooks/useDisclosure', () => {
  const actualReact = jest.requireActual('react') as typeof import('react');

  return {
    useDisclosure: () => {
      const [open, setOpen] = actualReact.useState(false);
      return {
        open,
        onOpen: () => setOpen(true),
        onClose: () => setOpen(false),
      };
    },
  };
});

jest.mock('@/c-common/hooks/useWechat', () => ({
  useWechat: () => ({ payByJsApi: mockPayByJsApi }),
}));

jest.mock('./wechatJsapi', () => ({
  isWechatJsapiAvailable: () => mockWechatJsapiAvailable,
}));

jest.mock('@/c-constants/uiConstants', () => ({
  inWechat: () => false,
}));

jest.mock('@/hooks/useToast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
  useToast: () => ({ toast: (...args: unknown[]) => mockToast(...args) }),
}));

jest.mock('@/lib/learnerError', () => ({
  resolveLearnerPaymentToast: () => ({
    message: 'resolved-payment-error',
    variant: 'destructive',
  }),
}));

jest.mock('@/lib/stripe-storage', () => ({
  rememberStripeCheckoutSession: jest.fn(),
}));

jest.mock('@/c-api/course', () => ({
  getCourseInfo: jest.fn(),
}));

jest.mock('@/c-service/Shifu', () => ({
  shifu: { loginTools: { openLogin: jest.fn() } },
}));

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

const qrPayment = {
  order_id: 'order-1',
  user_id: 'user-1',
  price: '99',
  channel: 'wx_pub_qr',
  qr_url: 'https://provider.example/private-qr',
  payment_channel: 'pingxx',
  payment_payload: {},
  status: ORDER_STATUS.BUY_STATUS_TO_BE_PAID,
};

const eventCalls = (name: string) =>
  mockTrackEvent.mock.calls.filter(([eventName]) => eventName === name);

const latestPaymentFlowOptions = () =>
  mockUsePaymentFlow.mock.calls[
    mockUsePaymentFlow.mock.calls.length - 1
  ][0] as {
    onOrderPaid: (context?: { confirmedAttemptChannel: string }) => void;
    onPollingTimeout: () => void;
  };

const requiredModalProps = {
  onCancel: jest.fn(),
  onOk: jest.fn(),
};

describe('learner payment modal analytics producers', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockWechatJsapiAvailable = false;
    mockEnvState = {
      stripePublishableKey: '',
      stripeEnabled: 'false',
      paymentChannels: ['pingxx'],
      currencySymbol: '¥',
      enableWxcode: 'false',
    };
    mockInitializeOrder.mockResolvedValue(pendingOrder);
    mockRefreshPayment.mockResolvedValue(qrPayment);
    mockApplyCoupon.mockResolvedValue(pendingOrder);
    mockSyncOrderStatus.mockResolvedValue(pendingOrder);
    mockPayByJsApi.mockResolvedValue(undefined);
    mockPaymentFlowState = {
      orderId: 'order-1',
      price: '99',
      originalPrice: '99',
      priceItems: [],
      couponCode: '',
      paymentInfo: {
        channel: 'wx_pub_qr',
        qrUrl: 'https://provider.example/private-qr',
        status: ORDER_STATUS.BUY_STATUS_TO_BE_PAID,
        paymentChannel: 'pingxx',
        paymentPayload: {},
      },
      isLoading: false,
      initLoading: false,
      isTimeout: false,
      isCompleted: false,
      initializeOrder: mockInitializeOrder,
      refreshPayment: mockRefreshPayment,
      applyCoupon: mockApplyCoupon,
      syncOrderStatus: mockSyncOrderStatus,
    };
    mockUsePaymentFlow.mockImplementation(() => mockPaymentFlowState);
    jest.spyOn(window, 'open').mockImplementation(() => null);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('bounds runtime currency values on both payment modal surfaces', async () => {
    mockEnvState.currencySymbol = 'private-person@example.test';

    const desktop = render(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );

    await waitFor(() => {
      expect(eventCalls('learner_pay_modal_view')).toEqual([
        [
          'learner_pay_modal_view',
          { shifu_bid: 'course-1', price_amount: 99, currency: 'other' },
        ],
      ]);
    });
    desktop.unmount();
    mockTrackEvent.mockClear();

    render(
      <PayModalM
        {...requiredModalProps}
        open
      />,
    );

    await waitFor(() => {
      expect(eventCalls('learner_pay_modal_view')).toEqual([
        [
          'learner_pay_modal_view',
          { shifu_bid: 'course-1', price_amount: 99, currency: 'other' },
        ],
      ]);
    });
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private-person@example.test',
    );
  });

  it('tracks desktop QR timeout as pending and retries independently', async () => {
    const { rerender } = render(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );

    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(1);
    });
    expect(eventCalls('learner_pay_modal_view')).toEqual([
      [
        'learner_pay_modal_view',
        { shifu_bid: 'course-1', price_amount: 99, currency: 'CNY' },
      ],
    ]);
    expect(eventCalls('learner_payment_attempt')).toEqual([
      [
        'learner_payment_attempt',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'wechat_qr',
          surface: 'desktop',
        },
      ],
    ]);

    act(() => {
      latestPaymentFlowOptions().onPollingTimeout();
    });
    expect(eventCalls('learner_payment_status')).toEqual([
      [
        'learner_payment_status',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'wechat_qr',
          surface: 'desktop',
          status: 'pending',
        },
      ],
    ]);
    expect(eventCalls('learner_payment_result')).toHaveLength(0);

    mockPaymentFlowState = { ...mockPaymentFlowState, isTimeout: true };
    rerender(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    fireEvent.click(screen.getByText('module.pay.clickRefresh'));

    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(2);
    });
    act(() => {
      latestPaymentFlowOptions().onPollingTimeout();
    });
    expect(eventCalls('learner_payment_status')).toHaveLength(2);
    expect(eventCalls('learner_payment_status')[1]).toEqual(
      eventCalls('learner_payment_status')[0],
    );
    expect(eventCalls('learner_payment_result')).toHaveLength(0);
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private-qr',
    );
  });

  it('does not guess a desktop result when multiple attempted channels remain unresolved', async () => {
    const { rerender } = render(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(1);
    });

    fireEvent.click(screen.getByTestId('pay-channel-switch'));
    mockPaymentFlowState = {
      ...mockPaymentFlowState,
      paymentInfo: {
        ...mockPaymentFlowState.paymentInfo,
        channel: 'alipay_qr',
        qrUrl: 'https://provider.example/private-alipay-qr',
      },
    };
    rerender(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );

    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(2);
    });
    act(() => {
      latestPaymentFlowOptions().onPollingTimeout();
    });
    expect(eventCalls('learner_payment_status')).toEqual([
      [
        'learner_payment_status',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'other',
          surface: 'desktop',
          status: 'pending',
        },
      ],
    ]);
    act(() => {
      latestPaymentFlowOptions().onOrderPaid();
    });

    expect(eventCalls('learner_payment_attempt')).toEqual([
      [
        'learner_payment_attempt',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'wechat_qr',
          surface: 'desktop',
        },
      ],
      [
        'learner_payment_attempt',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'alipay_qr',
          surface: 'desktop',
        },
      ],
    ]);
    expect(eventCalls('learner_payment_result')).toEqual([
      [
        'learner_payment_result',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'other',
          surface: 'desktop',
          outcome: 'success',
        },
      ],
    ]);
    expect(requiredModalProps.onOk).toHaveBeenCalledTimes(1);
    const trackedPayloads = JSON.stringify(mockTrackEvent.mock.calls);
    expect(trackedPayloads).not.toContain('private-qr');
    expect(trackedPayloads).not.toContain('private-alipay-qr');
  });

  it('uses the confirmed desktop Stripe channel when an older QR attempt remains unresolved', async () => {
    mockEnvState = {
      ...mockEnvState,
      stripePublishableKey: 'private-stripe-publishable-key',
      stripeEnabled: 'true',
      paymentChannels: ['pingxx', 'stripe'],
    };
    const { rerender } = render(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(1);
    });

    fireEvent.click(screen.getByText('module.pay.payChannelStripeCard'));
    mockPaymentFlowState = {
      ...mockPaymentFlowState,
      paymentInfo: {
        channel: 'stripe',
        qrUrl: '',
        status: ORDER_STATUS.BUY_STATUS_TO_BE_PAID,
        paymentChannel: 'stripe',
        paymentPayload: {
          mode: 'payment_intent',
          client_secret: 'client-secret-never-tracked',
        },
      },
    };
    rerender(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    mockSyncOrderStatus.mockImplementationOnce(
      async (params: { confirmedAttemptChannel?: string } = {}) => {
        latestPaymentFlowOptions().onOrderPaid(
          params.confirmedAttemptChannel
            ? { confirmedAttemptChannel: params.confirmedAttemptChannel }
            : undefined,
        );
        return paidOrder;
      },
    );

    fireEvent.click(await screen.findByTestId('stripe-submit'));

    await waitFor(() => {
      expect(eventCalls('learner_payment_result')).toHaveLength(1);
    });
    expect(mockSyncOrderStatus).toHaveBeenLastCalledWith({
      confirmedAttemptChannel: 'stripe:checkout_session',
    });
    expect(
      eventCalls('learner_payment_attempt').map(
        ([, payload]) => payload.channel,
      ),
    ).toEqual(['wechat_qr', 'stripe']);
    expect(eventCalls('learner_payment_result')).toEqual([
      [
        'learner_payment_result',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'stripe',
          surface: 'desktop',
          outcome: 'success',
        },
      ],
    ]);
    expect(requiredModalProps.onOk).toHaveBeenCalledTimes(1);
    const trackedPayloads = JSON.stringify(mockTrackEvent.mock.calls);
    expect(trackedPayloads).not.toContain('private-stripe-publishable-key');
    expect(trackedPayloads).not.toContain('client-secret-never-tracked');
  });

  it('clears unresolved desktop channels when the order changes', async () => {
    const { rerender } = render(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(1);
    });

    fireEvent.click(screen.getByTestId('pay-channel-switch'));
    mockPaymentFlowState = {
      ...mockPaymentFlowState,
      paymentInfo: {
        ...mockPaymentFlowState.paymentInfo,
        channel: 'alipay_qr',
        qrUrl: 'https://provider.example/private-alipay-qr',
      },
    };
    rerender(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(2);
    });

    mockPaymentFlowState = {
      ...mockPaymentFlowState,
      orderId: 'order-2',
      paymentInfo: {
        ...mockPaymentFlowState.paymentInfo,
        qrUrl: 'https://provider.example/private-order-2-qr',
      },
    };
    rerender(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(3);
    });
    act(() => {
      latestPaymentFlowOptions().onOrderPaid();
    });

    expect(eventCalls('learner_payment_result')).toEqual([
      [
        'learner_payment_result',
        {
          shifu_bid: 'course-1',
          order_id: 'order-2',
          channel: 'alipay_qr',
          surface: 'desktop',
          outcome: 'success',
        },
      ],
    ]);
    expect(requiredModalProps.onOk).toHaveBeenCalledTimes(1);
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private-order-2-qr',
    );
  });

  it('keeps an older desktop channel eligible after Stripe fails', async () => {
    mockEnvState = {
      ...mockEnvState,
      stripePublishableKey: 'private-stripe-key',
      stripeEnabled: 'true',
      paymentChannels: ['pingxx', 'stripe'],
    };
    const { rerender } = render(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(1);
    });

    fireEvent.click(screen.getByText('module.pay.payChannelStripeCard'));
    mockPaymentFlowState = {
      ...mockPaymentFlowState,
      paymentInfo: {
        channel: 'stripe',
        qrUrl: '',
        status: ORDER_STATUS.BUY_STATUS_TO_BE_PAID,
        paymentChannel: 'stripe',
        paymentPayload: {
          mode: 'payment_intent',
          client_secret: 'private-stripe-client-secret',
        },
      },
    };
    rerender(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    fireEvent.click(screen.getByTestId('stripe-fail'));
    fireEvent.click(screen.getByTestId('stripe-late-fail'));

    expect(
      eventCalls('learner_payment_attempt').map(
        ([, payload]) => payload.channel,
      ),
    ).toEqual(['wechat_qr', 'stripe']);
    expect(eventCalls('learner_payment_result')).toEqual([
      [
        'learner_payment_result',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'stripe',
          surface: 'desktop',
          outcome: 'failed',
          failure_category: 'provider_failed',
        },
      ],
    ]);

    act(() => {
      latestPaymentFlowOptions().onOrderPaid();
    });
    expect(eventCalls('learner_payment_result')[1]).toEqual([
      'learner_payment_result',
      {
        shifu_bid: 'course-1',
        order_id: 'order-1',
        channel: 'wechat_qr',
        surface: 'desktop',
        outcome: 'success',
      },
    ]);
    expect(requiredModalProps.onOk).toHaveBeenCalledTimes(1);
    const trackedPayloads = JSON.stringify(mockTrackEvent.mock.calls);
    expect(trackedPayloads).not.toContain('private-stripe-key');
    expect(trackedPayloads).not.toContain('private-stripe-client-secret');
    expect(trackedPayloads).not.toContain('private-stripe-provider-error');
    expect(trackedPayloads).not.toContain('private-stripe-late-error');
  });

  it('does not start a desktop retry attempt until refresh returns a usable QR', async () => {
    const { rerender } = render(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(1);
      expect(mockRefreshPayment).toHaveBeenCalled();
    });

    mockRefreshPayment.mockResolvedValueOnce(null);
    mockPaymentFlowState = { ...mockPaymentFlowState, isTimeout: true };
    rerender(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    fireEvent.click(screen.getByText('module.pay.clickRefresh'));

    await waitFor(() => {
      expect(mockRefreshPayment).toHaveBeenCalledTimes(2);
    });
    expect(eventCalls('learner_payment_attempt')).toHaveLength(1);
  });

  it('tracks a desktop coupon application without exposing the coupon value', async () => {
    render(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );

    fireEvent.click(screen.getByText('module.groupon.useOtherPayment'));
    fireEvent.click(await screen.findByTestId('desktop-coupon-submit'));

    await waitFor(() => {
      expect(mockApplyCoupon).toHaveBeenCalledWith({
        code: 'desktop-sensitive-coupon',
        channel: 'wx_pub_qr',
        paymentChannel: 'pingxx',
      });
    });
    expect(eventCalls('learner_coupon_apply')).toEqual([
      ['learner_coupon_apply', { shifu_bid: 'course-1', outcome: 'success' }],
    ]);
    expect(JSON.stringify(eventCalls('learner_coupon_apply'))).not.toContain(
      'coupon_code',
    );
    expect(JSON.stringify(eventCalls('learner_coupon_apply'))).not.toContain(
      'desktop-sensitive-coupon',
    );
  });

  it('resets the desktop open lifecycle without retrying an expired QR', async () => {
    const { rerender } = render(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(1);
    });

    act(() => {
      latestPaymentFlowOptions().onPollingTimeout();
    });
    fireEvent.click(screen.getByTestId('dialog-dismiss'));
    expect(eventCalls('learner_payment_status')).toHaveLength(1);
    expect(eventCalls('learner_payment_result')).toHaveLength(1);
    expect(eventCalls('learner_pay_cancel')).toHaveLength(0);

    mockPaymentFlowState = { ...mockPaymentFlowState, isTimeout: true };
    rerender(
      <PayModal
        {...requiredModalProps}
        open={false}
      />,
    );
    rerender(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );

    await waitFor(() => {
      expect(eventCalls('learner_pay_modal_view')).toHaveLength(2);
    });
    expect(eventCalls('learner_payment_attempt')).toHaveLength(1);

    fireEvent.click(screen.getByText('module.pay.clickRefresh'));
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(2);
    });
    act(() => {
      latestPaymentFlowOptions().onPollingTimeout();
    });
    expect(eventCalls('learner_payment_status')).toHaveLength(2);
    expect(eventCalls('learner_payment_result')).toHaveLength(1);
  });

  it('tracks desktop dismissal and cancellation only for an unfinished attempt', async () => {
    render(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(1);
    });

    fireEvent.click(screen.getByTestId('dialog-dismiss'));

    expect(eventCalls('learner_pay_modal_dismiss')).toEqual([
      [
        'learner_pay_modal_dismiss',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          dismiss_surface: 'modal',
          had_payment_attempt: true,
        },
      ],
    ]);
    expect(eventCalls('learner_payment_result')).toEqual([
      [
        'learner_payment_result',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'wechat_qr',
          surface: 'desktop',
          outcome: 'cancelled',
        },
      ],
    ]);
    expect(eventCalls('learner_pay_cancel')).toHaveLength(0);
  });

  it('omits an unavailable order id from modal dismissal', () => {
    mockPaymentFlowState = {
      ...mockPaymentFlowState,
      orderId: '',
      paymentInfo: { ...mockPaymentFlowState.paymentInfo, qrUrl: '' },
    };
    render(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );

    fireEvent.click(screen.getByTestId('dialog-dismiss'));

    expect(eventCalls('learner_pay_modal_dismiss')).toEqual([
      [
        'learner_pay_modal_dismiss',
        {
          shifu_bid: 'course-1',
          dismiss_surface: 'modal',
          had_payment_attempt: false,
        },
      ],
    ]);
    expect(eventCalls('learner_payment_result')).toHaveLength(0);
    expect(eventCalls('learner_pay_cancel')).toHaveLength(0);
  });

  it('tracks a mobile timeout as pending and retries independently', async () => {
    render(
      <PayModalM
        {...requiredModalProps}
        open
      />,
    );

    fireEvent.click(screen.getByText('module.pay.pay'));
    await waitFor(() => {
      expect(window.open).toHaveBeenCalledWith(
        'https://provider.example/private-qr',
      );
    });
    expect(eventCalls('learner_pay_modal_view')).toEqual([
      [
        'learner_pay_modal_view',
        { shifu_bid: 'course-1', price_amount: 99, currency: 'CNY' },
      ],
    ]);
    expect(eventCalls('learner_payment_attempt')).toEqual([
      [
        'learner_payment_attempt',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'alipay_qr',
          surface: 'mobile',
        },
      ],
    ]);

    act(() => {
      latestPaymentFlowOptions().onPollingTimeout();
    });
    expect(eventCalls('learner_payment_status')).toEqual([
      [
        'learner_payment_status',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'alipay_qr',
          surface: 'mobile',
          status: 'pending',
        },
      ],
    ]);
    expect(eventCalls('learner_payment_result')).toHaveLength(0);

    fireEvent.click(screen.getByText('module.pay.pay'));
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(2);
    });
    act(() => {
      latestPaymentFlowOptions().onPollingTimeout();
    });
    expect(eventCalls('learner_payment_status')).toHaveLength(2);
    expect(eventCalls('learner_payment_result')).toHaveLength(0);
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private-qr',
    );
  });

  it('does not guess a mobile success when multiple attempted channels remain unresolved', async () => {
    render(
      <PayModalM
        {...requiredModalProps}
        open
      />,
    );

    fireEvent.click(screen.getByText('module.pay.pay'));
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(1);
    });
    fireEvent.click(screen.getByText('module.pay.wechatPay'));
    fireEvent.click(screen.getByText('module.pay.pay'));
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(2);
    });
    act(() => {
      latestPaymentFlowOptions().onOrderPaid();
    });

    expect(eventCalls('learner_payment_attempt')).toEqual([
      [
        'learner_payment_attempt',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'alipay_qr',
          surface: 'mobile',
        },
      ],
      [
        'learner_payment_attempt',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'wechat_qr',
          surface: 'mobile',
        },
      ],
    ]);
    expect(eventCalls('learner_payment_result')).toEqual([
      [
        'learner_payment_result',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'other',
          surface: 'mobile',
          outcome: 'success',
        },
      ],
    ]);
    expect(requiredModalProps.onOk).toHaveBeenCalledTimes(1);
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private-qr',
    );
  });

  it('uses the confirmed mobile WeChat JSAPI channel when an older QR attempt remains unresolved', async () => {
    mockWechatJsapiAvailable = true;
    mockEnvState = {
      ...mockEnvState,
      paymentChannels: ['pingxx', 'wechatpay'],
      enableWxcode: 'true',
    };
    render(
      <PayModalM
        {...requiredModalProps}
        open
      />,
    );

    fireEvent.click(screen.getByText('module.pay.pay'));
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(1);
    });

    mockRefreshPayment.mockResolvedValue({
      ...qrPayment,
      channel: 'wx_pub',
      qr_url: { timeStamp: 'private-provider-credential' },
      payment_channel: 'wechatpay',
      payment_payload: {
        mode: 'jsapi',
        jsapi_params: { timeStamp: 'private-provider-credential' },
      },
    });
    mockSyncOrderStatus.mockImplementationOnce(
      async (params: { confirmedAttemptChannel?: string } = {}) => {
        latestPaymentFlowOptions().onOrderPaid(
          params.confirmedAttemptChannel
            ? { confirmedAttemptChannel: params.confirmedAttemptChannel }
            : undefined,
        );
        return paidOrder;
      },
    );

    fireEvent.click(screen.getByText('module.pay.wechatPay'));
    fireEvent.click(screen.getByText('module.pay.pay'));

    await waitFor(() => {
      expect(eventCalls('learner_payment_result')).toHaveLength(1);
    });
    expect(mockSyncOrderStatus).toHaveBeenLastCalledWith({
      paymentChannel: 'wechatpay',
      confirmedAttemptChannel: 'wx_pub',
    });
    expect(
      eventCalls('learner_payment_attempt').map(
        ([, payload]) => payload.channel,
      ),
    ).toEqual(['alipay_qr', 'wechat_jsapi']);
    expect(eventCalls('learner_payment_result')).toEqual([
      [
        'learner_payment_result',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'wechat_jsapi',
          surface: 'mobile',
          outcome: 'success',
        },
      ],
    ]);
    expect(requiredModalProps.onOk).toHaveBeenCalledTimes(1);
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private-provider-credential',
    );
  });

  it('tracks the effective mobile WeChat QR fallback channel', async () => {
    mockEnvState = {
      ...mockEnvState,
      paymentChannels: ['wechatpay'],
    };
    mockRefreshPayment.mockResolvedValue({
      ...qrPayment,
      channel: 'wx_pub_qr',
      payment_channel: 'wechatpay',
    });
    render(
      <PayModalM
        {...requiredModalProps}
        open
      />,
    );

    fireEvent.click(screen.getByText('module.pay.wechatPay'));
    fireEvent.click(screen.getByText('module.pay.pay'));

    await waitFor(() => {
      expect(window.open).toHaveBeenCalledWith(
        'https://provider.example/private-qr',
      );
    });
    expect(mockRefreshPayment).toHaveBeenLastCalledWith({
      channel: 'wx_pub_qr',
      paymentChannel: 'wechatpay',
    });
    expect(eventCalls('learner_payment_attempt')).toEqual([
      [
        'learner_payment_attempt',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'wechat_qr',
          surface: 'mobile',
        },
      ],
    ]);
    expect(JSON.stringify(eventCalls('learner_payment_attempt'))).not.toContain(
      'wechat_jsapi',
    );
  });

  it('tracks a mobile coupon application without exposing the coupon value', async () => {
    render(
      <PayModalM
        {...requiredModalProps}
        open
      />,
    );

    fireEvent.click(screen.getByText('module.groupon.useOtherPayment'));
    fireEvent.change(await screen.findByTestId('mobile-coupon-input'), {
      target: { value: 'mobile-sensitive-coupon' },
    });
    fireEvent.click(screen.getByText('common.core.ok'));

    await waitFor(() => {
      expect(mockApplyCoupon).toHaveBeenCalledWith({
        code: 'mobile-sensitive-coupon',
        channel: 'alipay_qr',
        paymentChannel: 'pingxx',
      });
    });
    expect(eventCalls('learner_coupon_apply')).toEqual([
      ['learner_coupon_apply', { shifu_bid: 'course-1', outcome: 'success' }],
    ]);
    expect(JSON.stringify(eventCalls('learner_coupon_apply'))).not.toContain(
      'coupon_code',
    );
    expect(JSON.stringify(eventCalls('learner_coupon_apply'))).not.toContain(
      'mobile-sensitive-coupon',
    );
  });

  it('tracks mobile dismissal and cancellation for an unfinished attempt', async () => {
    render(
      <PayModalM
        {...requiredModalProps}
        open
      />,
    );
    fireEvent.click(screen.getByText('module.pay.pay'));
    await waitFor(() => {
      expect(eventCalls('learner_payment_attempt')).toHaveLength(1);
    });

    fireEvent.click(screen.getByTestId('dialog-dismiss'));

    expect(eventCalls('learner_pay_modal_dismiss')).toEqual([
      [
        'learner_pay_modal_dismiss',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          dismiss_surface: 'modal',
          had_payment_attempt: true,
        },
      ],
    ]);
    expect(eventCalls('learner_payment_result')).toEqual([
      [
        'learner_payment_result',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'alipay_qr',
          surface: 'mobile',
          outcome: 'cancelled',
        },
      ],
    ]);
    expect(eventCalls('learner_pay_cancel')).toHaveLength(0);
  });

  it('does not track a mobile attempt when the payment action is not accepted', async () => {
    mockRefreshPayment.mockResolvedValue(null);
    render(
      <PayModalM
        {...requiredModalProps}
        open
      />,
    );

    fireEvent.click(screen.getByText('module.pay.pay'));

    await waitFor(() => {
      expect(mockRefreshPayment).toHaveBeenCalledTimes(2);
    });
    expect(eventCalls('learner_payment_attempt')).toHaveLength(0);
    expect(eventCalls('learner_payment_result')).toHaveLength(0);
    expect(window.open).not.toHaveBeenCalled();
  });

  it('keeps the mobile action fail-open when tracking throws', async () => {
    mockTrackEvent.mockImplementation(() => {
      throw new Error('analytics unavailable');
    });
    render(
      <PayModalM
        {...requiredModalProps}
        open
      />,
    );

    fireEvent.click(screen.getByText('module.pay.pay'));

    await waitFor(() => expect(mockRefreshPayment).toHaveBeenCalled());
    expect(window.open).toHaveBeenCalledWith(
      'https://provider.example/private-qr',
    );
  });

  it('reports desktop Stripe pending status without a false success', async () => {
    mockEnvState = {
      ...mockEnvState,
      stripePublishableKey: 'pk_test',
      stripeEnabled: 'true',
      paymentChannels: ['stripe'],
    };
    mockPaymentFlowState = {
      ...mockPaymentFlowState,
      paymentInfo: {
        channel: 'stripe:checkout_session',
        qrUrl: '',
        status: ORDER_STATUS.BUY_STATUS_TO_BE_PAID,
        paymentChannel: 'stripe',
        paymentPayload: {
          mode: 'payment_intent',
          client_secret: 'client-secret-never-tracked',
        },
      },
    };
    render(
      <PayModal
        {...requiredModalProps}
        open
      />,
    );

    fireEvent.click(await screen.findByTestId('stripe-submit'));

    await waitFor(() => {
      expect(eventCalls('learner_payment_status')).toHaveLength(1);
    });
    expect(eventCalls('learner_payment_attempt')).toEqual([
      [
        'learner_payment_attempt',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'stripe',
          surface: 'desktop',
        },
      ],
    ]);
    expect(eventCalls('learner_payment_status')).toEqual([
      [
        'learner_payment_status',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'stripe',
          surface: 'desktop',
          status: 'pending',
        },
      ],
    ]);
    expect(eventCalls('learner_payment_result')).toHaveLength(0);
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.pay.paymentStatusSyncPending',
      variant: 'default',
    });
    expect(mockToast).not.toHaveBeenCalledWith({
      title: 'module.pay.paySuccess',
    });
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'client-secret-never-tracked',
    );

    fireEvent.click(screen.getByTestId('dialog-dismiss'));
    expect(eventCalls('learner_payment_result')).toEqual([
      [
        'learner_payment_result',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'stripe',
          surface: 'desktop',
          outcome: 'cancelled',
        },
      ],
    ]);
  });

  it('reports mobile WeChat JSAPI pending status without a false success', async () => {
    mockWechatJsapiAvailable = true;
    mockEnvState = {
      ...mockEnvState,
      paymentChannels: ['wechatpay'],
      enableWxcode: 'true',
    };
    mockRefreshPayment.mockResolvedValue({
      ...qrPayment,
      channel: 'wx_pub',
      qr_url: { timeStamp: 'private-provider-credential' },
      payment_channel: 'wechatpay',
      payment_payload: {
        mode: 'jsapi',
        jsapi_params: { timeStamp: 'private-provider-credential' },
      },
    });
    render(
      <PayModalM
        {...requiredModalProps}
        open
      />,
    );

    fireEvent.click(screen.getByText('module.pay.wechatPay'));
    fireEvent.click(screen.getByText('module.pay.pay'));

    await waitFor(() => {
      expect(eventCalls('learner_payment_status')).toHaveLength(1);
    });
    expect(eventCalls('learner_payment_attempt')).toEqual([
      [
        'learner_payment_attempt',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'wechat_jsapi',
          surface: 'mobile',
        },
      ],
    ]);
    expect(eventCalls('learner_payment_status')).toEqual([
      [
        'learner_payment_status',
        {
          shifu_bid: 'course-1',
          order_id: 'order-1',
          channel: 'wechat_jsapi',
          surface: 'mobile',
          status: 'pending',
        },
      ],
    ]);
    expect(eventCalls('learner_payment_result')).toHaveLength(0);
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.pay.paymentStatusSyncPending',
      variant: 'default',
    });
    expect(mockToast).not.toHaveBeenCalledWith({
      title: 'module.pay.paySuccess',
    });
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private-provider-credential',
    );
  });
});
