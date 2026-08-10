import { SSE } from 'sse.js';
import { getResolvedBaseURL } from '@/c-utils/envUtils';
import { useUserStore } from '@/store/useUserStore';
import {
  attachSseBusinessResponseFallback,
  getCurrentLanguageHeaders,
} from '@/lib/request';
import { buildTraceHeaders } from '@/lib/request-trace';

export type ProfileOnboardingStreamEvent = {
  type?: string;
  event_type?: string;
  content?: unknown;
  is_terminal?: boolean;
  generated_block_bid?: string | null;
};

const dispatchBusinessError = (
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

export const streamProfileOnboardingRuntime = ({
  path,
  payload,
  language,
  onMessage,
  onError,
}: {
  path: string;
  payload?: Record<string, unknown>;
  language?: string;
  onMessage: (event: ProfileOnboardingStreamEvent) => void;
  onError: (error: unknown) => void;
}) => {
  const token = useUserStore.getState().getToken();
  const url = `${getResolvedBaseURL()}${path}`;
  const traceHeaders = buildTraceHeaders({
    'Content-Type': 'application/json',
    ...getCurrentLanguageHeaders(language),
    ...(token
      ? {
          Authorization: `Bearer ${token}`,
          Token: token,
        }
      : {}),
  });
  const source = new SSE(url, {
    headers: traceHeaders.headers,
    payload: JSON.stringify(payload || {}),
    method: 'POST',
  });

  source.addEventListener('message', event => {
    try {
      onMessage(JSON.parse(event.data) as ProfileOnboardingStreamEvent);
    } catch {
      // Ignore malformed SSE payloads; a later valid event may still recover.
    }
  });
  source.addEventListener('error', error => onError(error));
  attachSseBusinessResponseFallback(source, {
    requestToken: token || '',
    meta: {
      url,
      method: 'POST',
      requestToken: token || '',
      requestId: traceHeaders.requestId,
      harnessRunId: traceHeaders.harnessRunId,
    },
    onHandled: error => dispatchBusinessError(source, error),
  });
  source.stream();
  return source;
};
