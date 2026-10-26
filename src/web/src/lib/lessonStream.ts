import { SSE } from 'sse.js';
import {
  attachSseBusinessResponseFallback,
  getCurrentLanguageHeaders,
} from '@/lib/request';
import { buildTraceHeaders } from '@/lib/request-trace';
import type { CreditInsufficientAudience } from '@/lib/creditInsufficientToast';
import { useUserStore } from '@/store/useUserStore';

export type LessonStreamOutcome =
  | 'terminal'
  | 'eof'
  | 'error'
  | 'cancelled'
  | 'stale';

export interface LessonStreamLifecycle {
  isCurrent?: () => boolean;
  onSettled?: (outcome: LessonStreamOutcome) => void;
}

interface StreamSource {
  readyState?: number;
  addEventListener: (type: string, listener: (event: any) => void) => void;
  close: () => void;
}

interface StreamHandlers extends LessonStreamLifecycle {
  onMessage: (response: any) => void;
  onError?: (error: unknown) => void;
}

export const decodeLessonStreamMessage = (data: unknown): any | null => {
  if (typeof data !== 'string' || !data.trim()) return null;
  try {
    const response = JSON.parse(data.replace(/^data:\s*/, '').trim());
    return response && typeof response === 'object' ? response : null;
  } catch {
    return null;
  }
};

export const resolveLessonStreamTerminal = (response: {
  is_terminal?: unknown;
  content?: unknown;
  data?: unknown;
}): boolean | null => {
  const readFlag = (value: unknown): boolean | null => {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'string') {
      if (value.toLowerCase() === 'true') return true;
      if (value.toLowerCase() === 'false') return false;
    }
    return null;
  };
  const topLevelFlag = readFlag(response.is_terminal);
  if (topLevelFlag !== null) return topLevelFlag;
  const asObject = (value: unknown) =>
    value && typeof value === 'object'
      ? value
      : decodeLessonStreamMessage(value);
  const payload = asObject(response.content) ?? asObject(response.data);
  return readFlag(payload?.is_terminal);
};

const isTerminalMessage = (response: any) => {
  if ((response.type ?? response.event_type) !== 'done') return false;
  // A block-level done(false), text_end, and legacy done have different host
  // continuation rules. Only an explicit terminal marker ends this HTTP run.
  return resolveLessonStreamTerminal(response) === true;
};

/** Bind the same lifecycle to real SSE and offline fixture sources. */
export const bindLessonStream = (
  source: StreamSource,
  {
    onMessage,
    onError,
    isCurrent,
    onSettled,
    onTransportError,
  }: StreamHandlers & { onTransportError?: (error: unknown) => boolean },
) => {
  let settled = false;
  let pendingOutcome: LessonStreamOutcome | undefined;
  let businessResponsePending = false;
  let eofTimer: ReturnType<typeof setTimeout> | null = null;
  const finish = (outcome: LessonStreamOutcome) => {
    if (settled) return;
    settled = true;
    if (eofTimer !== null) {
      clearTimeout(eofTimer);
      eofTimer = null;
    }
    onSettled?.(outcome);
  };
  const isActive = () => {
    if (settled) return false;
    if (isCurrent && !isCurrent()) {
      finish('stale');
      return false;
    }
    return true;
  };
  const close = source.close?.bind(source);
  source.close = () => {
    finish(pendingOutcome ?? 'cancelled');
    close?.();
  };
  source.addEventListener('message', event => {
    if (!isActive()) return;
    const response = decodeLessonStreamMessage(event.data);
    if (!response) return;
    if (isTerminalMessage(response)) pendingOutcome = 'terminal';
    else if ((response.type ?? response.event_type) === 'error') {
      pendingOutcome = 'error';
    }
    try {
      onMessage(response);
    } catch {
      // Preserve the API clients' tolerance of malformed host payloads.
    } finally {
      if (pendingOutcome) finish(pendingOutcome);
    }
  });
  source.addEventListener('error', error => {
    if (!isActive()) return;
    // Non-2xx JSON errors can arrive from sse.js before the XHR load event.
    // Let the same request fallback handle them once, with their business code.
    if (!error.detail && onTransportError?.(error)) return;
    pendingOutcome = 'error';
    onError?.(error);
    finish('error');
  });
  source.addEventListener('abort', () => {
    if (isActive()) finish('cancelled');
  });
  source.addEventListener('readystatechange', event => {
    if ((event?.readyState ?? source.readyState) !== 2) return;
    if (settled || eofTimer !== null) return;
    // sse.js emits CLOSED before the XHR load listener that detects a JSON
    // business response. Browsers can run microtasks between native listeners,
    // so wait for the next task before request.ts releases this response as EOF.
    eofTimer = setTimeout(() => {
      eofTimer = null;
      if (!businessResponsePending && isActive()) finish('eof');
    }, 0);
  });
  return {
    onBusinessResponseDetected: () => {
      businessResponsePending = true;
    },
  };
};

interface CreateSseSourceOptions extends StreamHandlers {
  url: string;
  payload: Record<string, unknown>;
  method?: 'POST' | 'PUT';
  language?: string;
  creditInsufficientAudience: CreditInsufficientAudience;
  skipErrorToast?: boolean;
  start?: boolean;
}

/** Shared request transport; request.ts remains the business-code authority. */
export const createSseSource = ({
  url,
  payload,
  method = 'POST',
  language,
  creditInsufficientAudience,
  skipErrorToast,
  start = true,
  ...handlers
}: CreateSseSourceOptions) => {
  const token = useUserStore.getState().getToken();
  const trace = buildTraceHeaders({
    'Content-Type': 'application/json',
    ...getCurrentLanguageHeaders(language),
    ...(token ? { Authorization: `Bearer ${token}`, Token: token } : {}),
  });
  // sse.js otherwise starts in its constructor, before listeners are attached.
  const source = new SSE(url, {
    headers: trace.headers,
    payload: JSON.stringify(payload),
    method,
    start: false,
  });
  let fallback: ReturnType<typeof attachSseBusinessResponseFallback>;
  const lifecycle = bindLessonStream(source, {
    ...handlers,
    onTransportError: error =>
      fallback?.handleResponse((error as { data?: unknown })?.data) ?? false,
  });
  const stream = source.stream.bind(source);
  source.stream = () => {
    stream();
    // stream() creates the XHR consumed by the existing request fallback.
    fallback = attachSseBusinessResponseFallback(source, {
      requestToken: token || '',
      shouldHandle: handlers.isCurrent,
      meta: {
        url,
        method,
        requestToken: token || '',
        requestId: trace.requestId,
        harnessRunId: trace.harnessRunId,
        creditInsufficientAudience,
        ...(skipErrorToast ? { skipErrorToast } : {}),
      },
      onDetected: lifecycle.onBusinessResponseDetected,
      onHandled: error => {
        const event = new CustomEvent('error', { detail: error }) as Event & {
          data?: string;
          responseCode?: number;
        };
        event.data = error.message;
        event.responseCode = error.code;
        source.dispatchEvent(event);
      },
    });
  };
  if (start) source.stream();
  return source;
};
