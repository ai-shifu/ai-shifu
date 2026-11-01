const PROTECTED_ERROR_CODES = new Set([401, 403, 9002, 1001, 1004, 1005]);

const normalizeErrorMessage = (errorMessage?: string | null) => {
  const normalizedMessage = errorMessage?.trim();
  return normalizedMessage ? normalizedMessage : '';
};

export const shouldHideErrorDisplayMessage = (errorCode: number) =>
  PROTECTED_ERROR_CODES.has(errorCode);

export const resolveErrorDisplayMessage = ({
  errorCode,
  errorMessage,
  fallbackMessage,
  showDetails = true,
}: {
  errorCode: number;
  errorMessage?: string | null;
  fallbackMessage: string;
  showDetails?: boolean;
}) => {
  if (!showDetails || shouldHideErrorDisplayMessage(errorCode)) {
    return fallbackMessage;
  }

  const normalizedMessage = normalizeErrorMessage(errorMessage);
  return normalizedMessage || fallbackMessage;
};
