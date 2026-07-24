import { type ErrorWithCode, getRequestFallbackMessage } from './request';

type LearnerErrorLike = Partial<Pick<ErrorWithCode, 'message' | 'status'>>;

const hasOfflineSignal = () =>
  typeof navigator !== 'undefined' && navigator.onLine === false;

const hasRequestContext = (error?: LearnerErrorLike | null) =>
  hasOfflineSignal() || typeof error?.status === 'number';

export const resolveLearnerErrorMessage = ({
  error,
  message,
  fallbackMessage,
}: {
  error?: LearnerErrorLike | null;
  message?: string | null;
  fallbackMessage: string;
}) => {
  const normalizedMessage =
    typeof message === 'string' && message.trim()
      ? message.trim()
      : typeof error?.message === 'string' && error.message.trim()
        ? error.message.trim()
        : '';

  if (normalizedMessage) {
    return normalizedMessage;
  }

  if (hasRequestContext(error)) {
    return getRequestFallbackMessage(error as Partial<ErrorWithCode>);
  }

  return fallbackMessage;
};
