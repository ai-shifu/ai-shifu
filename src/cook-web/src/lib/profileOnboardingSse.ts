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
  let settled = false;
  let closedByConsumer = false;
  const reportTransportError = (error: unknown) => {
    if (settled || closedByConsumer) {
      return;
    }
    settled = true;
    onError(error);
  };
  const closeSource = source.close.bind(source);
  source.close = () => {
    closedByConsumer = true;
    closeSource();
  };

  source.addEventListener('message', event => {
    try {
      const parsed = JSON.parse(event.data) as ProfileOnboardingStreamEvent;
      const eventType = parsed.event_type || parsed.type || '';
      if (eventType === 'done' && parsed.is_terminal === true) {
        settled = true;
      }
      onMessage(parsed);
    } catch {
      // Ignore malformed SSE payloads; a later valid event may still recover.
    }
  });
  source.addEventListener('error', error => reportTransportError(error));
  source.addEventListener('readystatechange', event => {
    const readyState = (event as Event & { readyState?: number }).readyState;
    if ((readyState ?? source.readyState) === 2 && !settled) {
      reportTransportError(
        new Error('Profile onboarding stream closed before a terminal event'),
      );
    }
  });
  attachSseBusinessResponseFallback(source, {
    requestToken: token || '',
    meta: {
      url,
      method: 'POST',
      requestToken: token || '',
      requestId: traceHeaders.requestId,
      harnessRunId: traceHeaders.harnessRunId,
      skipErrorToast: true,
    },
    onHandled: error => dispatchBusinessError(source, error),
  });
  source.stream();
  return source;
};
