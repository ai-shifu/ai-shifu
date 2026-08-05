import i18n from 'i18next';

export const AI_SERVICE_ERROR_TOAST_KEY = 'ai-service-unavailable';
export const AI_SERVICE_ERROR_TOAST_DURATION_MS = 8000;
export const AI_SERVICE_ERROR_TOAST_DEDUPE_MS = 10000;

const AI_SERVICE_ERROR_MARKERS = [
  'llm',
  'litellm',
  'model',
  'api key',
  'base_url',
  'not configured',
  'not supported',
  'provider',
  'badrequesterror',
  'apiconnectionerror',
  'internalservererror',
  '模型',
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

  const markers = includeUnknown
    ? [...AI_SERVICE_ERROR_MARKERS, ...UNKNOWN_ERROR_MARKERS]
    : AI_SERVICE_ERROR_MARKERS;

  return markers.some(marker => normalizedMessage.includes(marker));
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
