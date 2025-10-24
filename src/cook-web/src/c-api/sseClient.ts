import { fetchEventSource, type FetchEventSourceInit } from '@microsoft/fetch-event-source';

type EventListener = (event?: any) => void;

const createListenerMap = () => new Map<string, Set<EventListener>>();

const addListener = (
  listeners: Map<string, Set<EventListener>>,
  type: string,
  listener: EventListener,
) => {
  if (!listeners.has(type)) {
    listeners.set(type, new Set());
  }
  listeners.get(type)!.add(listener);
};

const removeListener = (
  listeners: Map<string, Set<EventListener>>,
  type: string,
  listener: EventListener,
) => {
  const set = listeners.get(type);
  if (!set) return;
  set.delete(listener);
  if (set.size === 0) {
    listeners.delete(type);
  }
};

const dispatchEvent = (
  listeners: Map<string, Set<EventListener>>,
  type: string,
  event: any = {},
) => {
  const set = listeners.get(type);
  if (!set) {
    return;
  }
  set.forEach(callback => {
    try {
      callback({ type, ...event });
    } catch (err) {
      console.error('[SSE listener error]', err);
    }
  });
};

export interface FetchSseSource {
  readyState: number;
  addEventListener: (type: string, listener: EventListener) => void;
  removeEventListener: (type: string, listener: EventListener) => void;
  close: () => void;
  stream: () => void;
}

export interface CreateFetchSseOptions
  extends Omit<FetchEventSourceInit, 'signal' | 'onopen' | 'onmessage' | 'onclose' | 'onerror'> {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: BodyInit | null;
  onOpen?: (response: Response) => void | Promise<void>;
  onMessage?: (event: MessageEvent) => void;
  onClose?: () => void;
  onError?: (error: any) => void;
}

export const createFetchSseSource = ({
  url,
  method = 'GET',
  headers,
  body,
  onOpen,
  onMessage,
  onClose,
  onError,
  ...rest
}: CreateFetchSseOptions): FetchSseSource => {
  const listeners = createListenerMap();
  const abortController = new AbortController();

  const source: FetchSseSource = {
    readyState: 0,
    addEventListener: (type, listener) => {
      addListener(listeners, type, listener);
    },
    removeEventListener: (type, listener) => {
      removeListener(listeners, type, listener);
    },
    close: () => {
      abortController.abort();
      markClosed();
    },
    stream: () => {
      // no-op for backward compatibility; fetch starts immediately
    },
  };

  const markOpen = () => {
    if (source.readyState !== 1) {
      source.readyState = 1;
      dispatchEvent(listeners, 'readystatechange', { readyState: 1 });
    }
  };

  const markClosed = () => {
    if (source.readyState !== 2) {
      source.readyState = 2;
      dispatchEvent(listeners, 'readystatechange', { readyState: 2 });
      dispatchEvent(listeners, 'close');
    }
  };

  fetchEventSource(url, {
    method,
    headers,
    body,
    signal: abortController.signal,
    onopen: async response => {
      if (onOpen) {
        await onOpen(response);
      }
      markOpen();
    },
    onmessage: event => {
      if (onMessage) {
        onMessage(event);
      }
      dispatchEvent(listeners, 'message', event);
    },
    onclose: () => {
      if (onClose) {
        onClose();
      }
      markClosed();
    },
    onerror: err => {
      if (onError) {
        onError(err);
      }
      dispatchEvent(listeners, 'error', { error: err });
      markClosed();
      throw err;
    },
    ...rest,
  }).catch(err => {
    if (err?.name === 'AbortError') {
      markClosed();
      return;
    }
    if (onError) {
      onError(err);
    }
    dispatchEvent(listeners, 'error', { error: err });
  });

  return source;
};

