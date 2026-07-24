import { type ErrorWithCode, getRequestFallbackMessage } from './request';

type LearnerErrorLike = Partial<Pick<ErrorWithCode, 'message' | 'status'>>;

type LearnerToastVariant = 'default' | 'destructive';

const PAYMENT_CANCEL_MARKERS = [
  'cancel',
  'canceled',
  'cancelled',
  'get_brand_wcpay_request:cancel',
] as const;

const PAYMENT_UNSUPPORTED_MARKERS = [
  'wechat_bridge_unavailable',
  'not in wechat',
] as const;

const PAYMENT_INTERNAL_FAILURE_MARKERS = [
  'get_brand_wcpay_request:fail',
  'wechat_pay_failed',
] as const;

const hasOfflineSignal = () =>
  typeof navigator !== 'undefined' && navigator.onLine === false;

const hasRequestContext = (error?: LearnerErrorLike | null) =>
  hasOfflineSignal() || typeof error?.status === 'number';

const getNormalizedErrorMessage = (
  error?: LearnerErrorLike | string | null,
  message?: string | null,
) => {
  if (typeof message === 'string' && message.trim()) {
    return message.trim();
  }

  if (typeof error === 'string' && error.trim()) {
    return error.trim();
  }

  if (
    error &&
    typeof error !== 'string' &&
    typeof error.message === 'string' &&
    error.message.trim()
  ) {
    return error.message.trim();
  }

  return '';
};

const includesAnyMarker = (message: string, markers: readonly string[]) => {
  const normalizedMessage = message.trim().toLowerCase();
  return markers.some(marker => normalizedMessage.includes(marker));
};

export const resolveLearnerErrorMessage = ({
  error,
  message,
  fallbackMessage,
}: {
  error?: LearnerErrorLike | null;
  message?: string | null;
  fallbackMessage: string;
}) => {
  const normalizedMessage = getNormalizedErrorMessage(error, message);

  if (normalizedMessage) {
    return normalizedMessage;
  }

  if (hasRequestContext(error)) {
    return getRequestFallbackMessage(error as Partial<ErrorWithCode>);
  }

  return fallbackMessage;
};

export const resolveLearnerPaymentToast = ({
  error,
  message,
  fallbackMessage,
  canceledMessage,
  unsupportedMessage,
}: {
  error?: LearnerErrorLike | string | null;
  message?: string | null;
  fallbackMessage: string;
  canceledMessage: string;
  unsupportedMessage: string;
}): { message: string; variant: LearnerToastVariant } => {
  const normalizedMessage = getNormalizedErrorMessage(error, message);

  if (normalizedMessage) {
    if (includesAnyMarker(normalizedMessage, PAYMENT_CANCEL_MARKERS)) {
      return {
        message: canceledMessage,
        variant: 'default',
      };
    }

    if (includesAnyMarker(normalizedMessage, PAYMENT_UNSUPPORTED_MARKERS)) {
      return {
        message: unsupportedMessage,
        variant: 'destructive',
      };
    }

    if (
      includesAnyMarker(normalizedMessage, PAYMENT_INTERNAL_FAILURE_MARKERS)
    ) {
      return {
        message: fallbackMessage,
        variant: 'destructive',
      };
    }

    return {
      message: normalizedMessage,
      variant: 'destructive',
    };
  }

  return {
    message: resolveLearnerErrorMessage({
      error: typeof error === 'string' ? undefined : error,
      fallbackMessage,
    }),
    variant: 'destructive',
  };
};
