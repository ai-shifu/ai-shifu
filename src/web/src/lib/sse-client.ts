import { SSE } from 'sse.js';
import { useUserStore } from '@/store/use-user-store';
import {
  attachSseBusinessResponseFallback,
  getCurrentLanguageHeaders,
  type ErrorWithCode,
  type RequestDebugMeta,
} from '@/lib/request';
import { buildTraceHeaders } from '@/lib/request-trace';

export type SseSource = InstanceType<typeof SSE>;

type SseEventTarget = {
  addEventListener: (
    type: string,
    listener: (event: MessageEvent | Event) => void,
  ) => void;
};

export type OpenSseStreamOptions = {
  url: string;
  method: 'POST' | 'PUT';
  payload: unknown;
  /** Explicit request language; falls back to the current UI language. */
  language?: string;
  /** Set to false for endpoints that never received Accept-Language. */
  includeLanguageHeaders?: boolean;
  /** Extra fields for business-code handling (toasts, credit audience). */
  meta?: Pick<
    RequestDebugMeta,
    'skipErrorToast' | 'creditInsufficientAudience'
  >;
  /** Called once when the response body turns out to be a business error. */
  onBusinessError: (error: ErrorWithCode, source: SseSource) => void;
};

/**
 * Re-emit a business error (non-zero code in a JSON response body) as an
 * `error` event on the stream, so `error` listeners see it as well.
 */
export const dispatchSseBusinessError = (
  source: { dispatchEvent: (event: Event) => void },
  error: { message: string; code?: number },
) => {
  const event = new CustomEvent('error', {
    detail: error,
  }) as CustomEvent<{ message: string; code?: number }> & {
    data?: string;
    responseCode?: number;
  };
  event.data = error.message;
  event.responseCode = error.code;
  source.dispatchEvent(event);
};

/**
 * Create an authenticated, traced SSE request and attach the business-code
 * fallback. Callers attach their own listeners and then call `stream()`.
 */
export const openSseStream = ({
  url,
  method,
  payload,
  language,
  includeLanguageHeaders = true,
  meta,
  onBusinessError,
}: OpenSseStreamOptions): SseSource => {
  const token = useUserStore.getState().getToken();
  const traceHeaders = buildTraceHeaders({
    'Content-Type': 'application/json',
    ...(includeLanguageHeaders ? getCurrentLanguageHeaders(language) : {}),
    ...(token
      ? {
          Authorization: `Bearer ${token}`,
          Token: token,
        }
      : {}),
  });
  const source = new SSE(url, {
    headers: traceHeaders.headers,
    payload: JSON.stringify(payload),
    method,
  });
  attachSseBusinessResponseFallback(source, {
    requestToken: token || '',
    meta: {
      url,
      method,
      requestToken: token || '',
      requestId: traceHeaders.requestId,
      harnessRunId: traceHeaders.harnessRunId,
      ...meta,
    },
    onHandled: error => onBusinessError(error, source),
  });
  return source;
};

/** Listen for `message` events whose trimmed data is non-empty. */
export const onSseData = (
  source: SseEventTarget,
  onData: (data: string) => void,
) => {
  source.addEventListener('message', event => {
    const raw = (event as MessageEvent).data;
    if (!raw) return;
    const data = String(raw).trim();
    if (data) {
      onData(data);
    }
  });
};

/**
 * Listen for JSON `message` events. Errors thrown while parsing or inside
 * `onMessage` go to `onError`, or are ignored so a later frame can recover.
 */
export const onSseJson = <T = any>(
  source: SseEventTarget,
  onMessage: (message: T) => void,
  onError?: (error: unknown) => void,
) => {
  onSseData(source, data => {
    try {
      onMessage(JSON.parse(data) as T);
    } catch (error) {
      onError?.(error);
    }
  });
};
