import {
  resolveLearnerErrorMessage,
  resolveLearnerPaymentToast,
} from './learnerError';
import { getRequestFallbackMessage } from './request';

jest.mock('i18next', () => ({
  t: (key: string) => `i18n:${key}`,
}));

jest.mock('./request', () => ({
  getRequestFallbackMessage: jest.fn(() => 'request-fallback'),
}));

describe('resolveLearnerErrorMessage', () => {
  const originalNavigatorOnLine = Object.getOwnPropertyDescriptor(
    Navigator.prototype,
    'onLine',
  );

  afterEach(() => {
    jest.clearAllMocks();

    if (originalNavigatorOnLine) {
      Object.defineProperty(
        Navigator.prototype,
        'onLine',
        originalNavigatorOnLine,
      );
    } else {
      delete (Navigator.prototype as { onLine?: boolean }).onLine;
    }
  });

  it('prefers explicit learner-facing messages', () => {
    expect(
      resolveLearnerErrorMessage({
        message: '  backend message  ',
        fallbackMessage: 'i18n:module.chat.requestFailed',
      }),
    ).toBe('backend message');
    expect(getRequestFallbackMessage).not.toHaveBeenCalled();
  });

  it('uses shared request fallback for HTTP-style failures', () => {
    expect(
      resolveLearnerErrorMessage({
        error: { status: 503 },
        fallbackMessage: 'i18n:module.preview.requestFailed',
      }),
    ).toBe('request-fallback');
    expect(getRequestFallbackMessage).toHaveBeenCalledWith({ status: 503 });
  });

  it('uses shared request fallback when the browser is offline', () => {
    Object.defineProperty(Navigator.prototype, 'onLine', {
      configurable: true,
      value: false,
    });

    expect(
      resolveLearnerErrorMessage({
        fallbackMessage: 'i18n:module.preview.requestFailed',
      }),
    ).toBe('request-fallback');
    expect(getRequestFallbackMessage).toHaveBeenCalledWith(undefined);
  });

  it('falls back to the learner-context i18n copy when no request context exists', () => {
    expect(
      resolveLearnerErrorMessage({
        fallbackMessage: 'i18n:module.chat.requestFailed',
      }),
    ).toBe('i18n:module.chat.requestFailed');
    expect(getRequestFallbackMessage).not.toHaveBeenCalled();
  });
});

describe('resolveLearnerPaymentToast', () => {
  it('maps payment cancellation to a non-destructive canceled message', () => {
    expect(
      resolveLearnerPaymentToast({
        error: 'get_brand_wcpay_request:cancel',
        fallbackMessage: 'fallback',
        canceledMessage: 'canceled',
        unsupportedMessage: 'unsupported',
      }),
    ).toEqual({
      message: 'canceled',
      variant: 'default',
    });
  });

  it('maps unsupported environment markers to the unsupported message', () => {
    expect(
      resolveLearnerPaymentToast({
        error: 'wechat_bridge_unavailable',
        fallbackMessage: 'fallback',
        canceledMessage: 'canceled',
        unsupportedMessage: 'unsupported',
      }),
    ).toEqual({
      message: 'unsupported',
      variant: 'destructive',
    });
  });

  it('preserves backend payment messages when they are user-facing', () => {
    expect(
      resolveLearnerPaymentToast({
        message: '支付渠道暂时不可用，请稍后再试',
        fallbackMessage: 'fallback',
        canceledMessage: 'canceled',
        unsupportedMessage: 'unsupported',
      }),
    ).toEqual({
      message: '支付渠道暂时不可用，请稍后再试',
      variant: 'destructive',
    });
  });

  it('maps internal WeChat bridge failures to the localized fallback', () => {
    expect(
      resolveLearnerPaymentToast({
        error: 'get_brand_wcpay_request:fail',
        fallbackMessage: 'pay failed',
        canceledMessage: 'canceled',
        unsupportedMessage: 'unsupported',
      }),
    ).toEqual({
      message: 'pay failed',
      variant: 'destructive',
    });

    expect(
      resolveLearnerPaymentToast({
        error: 'wechat_pay_failed',
        fallbackMessage: 'pay failed',
        canceledMessage: 'canceled',
        unsupportedMessage: 'unsupported',
      }),
    ).toEqual({
      message: 'pay failed',
      variant: 'destructive',
    });
  });
});
