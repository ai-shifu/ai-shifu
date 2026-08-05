import i18n from 'i18next';

export const AI_SERVICE_ERROR_TOAST_KEY = 'ai-service-unavailable';
export const AI_SERVICE_ERROR_TOAST_DURATION_MS = 8000;
export const AI_SERVICE_ERROR_TOAST_DEDUPE_MS = 10000;

const AI_SERVICE_IDENTITY_MARKERS = [
  'llm',
  'litellm',
  'langfuse',
  'model',
  'api key',
  'base_url',
  'provider',
  '模型',
] as const;

const AI_SERVICE_ERROR_STATE_MARKERS = [
  'missing',
  'failed',
  'failure',
  'error',
  'unavailable',
  'not configured',
  'not supported',
  'badrequesterror',
  'apiconnectionerror',
  'internalservererror',
  'object has no attribute',
  'attributeerror',
  '调用失败',
  '没有配置',
  '不支持',
] as const;

const UNKNOWN_ERROR_MARKERS = [
  '未知错误',
  'unknown error',
  'erreur inconnue',
] as const;

const normalizeErrorMessage = (message?: string | null) =>
  String(message || '').trim();

export const isAiServiceUnavailableMessage = (
  message?: string | null,
  { includeUnknown = false }: { includeUnknown?: boolean } = {},
) => {
  const normalizedMessage = normalizeErrorMessage(message).toLowerCase();
  if (!normalizedMessage) {
    return false;
  }

  const hasUnknownMarker =
    includeUnknown &&
    UNKNOWN_ERROR_MARKERS.some(marker => normalizedMessage.includes(marker));
  if (hasUnknownMarker) {
    return true;
  }

  const hasAiIdentity = AI_SERVICE_IDENTITY_MARKERS.some(marker =>
    normalizedMessage.includes(marker),
  );
  const hasErrorState = AI_SERVICE_ERROR_STATE_MARKERS.some(marker =>
    normalizedMessage.includes(marker),
  );

  return hasAiIdentity && hasErrorState;
};

export const resolveAiServiceErrorToast = ({
  message,
  fallbackMessage,
  includeUnknown = false,
}: {
  message?: string | null;
  fallbackMessage: string;
  includeUnknown?: boolean;
}) => {
  const normalizedMessage = normalizeErrorMessage(message);
  if (isAiServiceUnavailableMessage(normalizedMessage, { includeUnknown })) {
    return {
      message: i18n.t('module.chat.contentGenerationUnavailable'),
      isAiServiceUnavailable: true,
    };
  }

  return {
    message: normalizedMessage || fallbackMessage,
    isAiServiceUnavailable: false,
  };
};
