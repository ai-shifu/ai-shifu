import { toast, toastOnce } from '@/hooks/useToast';
import {
  AI_SERVICE_ERROR_TOAST_DEDUPE_MS,
  AI_SERVICE_ERROR_TOAST_DURATION_MS,
  AI_SERVICE_ERROR_TOAST_KEY,
  resolveAiServiceErrorToast,
} from './aiServiceError';

export const showAiServiceErrorToast = ({
  message,
  fallbackMessage,
  includeUnknown = false,
}: {
  message?: string | null;
  fallbackMessage: string;
  includeUnknown?: boolean;
}) => {
  const displayErrorToast = resolveAiServiceErrorToast({
    message,
    fallbackMessage,
    includeUnknown,
  });

  if (displayErrorToast.isAiServiceUnavailable) {
    toastOnce({
      dedupeKey: AI_SERVICE_ERROR_TOAST_KEY,
      dedupeWindowMs: AI_SERVICE_ERROR_TOAST_DEDUPE_MS,
      title: displayErrorToast.message,
      variant: 'destructive',
      duration: AI_SERVICE_ERROR_TOAST_DURATION_MS,
    });
  } else {
    toast({
      title: displayErrorToast.message,
      variant: 'destructive',
    });
  }

  return displayErrorToast;
};
