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
  default: () => <div data-testid='pay-channel-switch' />,
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
  }: {
    onAttempt: () => void;
    onConfirmSuccess: () => Promise<void>;
  }) => (
    <button
      data-testid='stripe-submit'
      onClick={() => {
        onAttempt();
        void onConfirmSuccess();
      }}
    />
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
  getCurrencyCode: (symbol: string) => (symbol === '¥' ? 'CNY' : 'USD'),
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
    onOrderPaid: () => void;
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
