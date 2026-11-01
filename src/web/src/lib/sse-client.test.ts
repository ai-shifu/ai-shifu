import { attachSseBusinessResponseFallback } from '@/lib/request';
import {
  dispatchSseBusinessError,
  onSseData,
  onSseJson,
  openSseStream,
} from '@/lib/sse-client';

// sse.js ships untransformed ESM, so evaluate the real library source here
// to exercise its framing (chunk joins, multi-line data, close) end to end.
jest.mock('sse.js', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const fs = require('fs');
  const source: string = fs.readFileSync(
    require.resolve('sse.js/lib/sse.js'),
    'utf8',
  );
  const moduleBody = source.replace(/export\s*\{\s*SSE\s*\};?/, '');
  return { SSE: new Function(`${moduleBody}\nreturn SSE;`)() };
});

let mockToken = 'token-1';

jest.mock('@/store/use-user-store', () => ({
  useUserStore: {
    getState: () => ({ getToken: () => mockToken }),
  },
}));

jest.mock('@/lib/request', () => ({
  attachSseBusinessResponseFallback: jest.fn(),
  getCurrentLanguageHeaders: (language?: string) => ({
    'Accept-Language': language || 'en-US',
  }),
}));

jest.mock('@/lib/request-trace', () => ({
  buildTraceHeaders: jest.fn(headers => ({
    headers: { ...headers, 'X-Request-ID': 'request-1' },
    requestId: 'request-1',
    harnessRunId: 'harness-1',
  })),
}));

// Drives the real sse.js parser: it reads `responseText` incrementally on
// `progress` and flushes the remaining chunk on `load`.
class FakeXhr {
  static instances: FakeXhr[] = [];
  status = 200;
  readyState = 0;
  responseText = '';
  method = '';
  url = '';
  body: unknown = null;
  withCredentials = false;
  requestHeaders: Record<string, string> = {};
  aborted = false;
  private listeners: Record<string, Array<(event: Event) => void>> = {};

  constructor() {
    FakeXhr.instances.push(this);
  }

  addEventListener(type: string, listener: (event: Event) => void) {
    (this.listeners[type] ||= []).push(listener);
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  setRequestHeader(name: string, value: string) {
    this.requestHeaders[name] = value;
  }

  send(body: unknown) {
    this.body = body;
  }

  getAllResponseHeaders() {
    return '';
  }

  abort() {
    this.aborted = true;
    this.emit('abort');
  }

  push(text: string) {
    this.responseText += text;
    this.emit('progress');
  }

  finish() {
    this.readyState = 4;
    this.emit('load');
  }

  private emit(type: string) {
    (this.listeners[type] || []).forEach(listener => listener(new Event(type)));
  }
}

const originalXhr = global.XMLHttpRequest;

const latestXhr = () => FakeXhr.instances[FakeXhr.instances.length - 1];

const openTestStream = (
  overrides: Partial<Parameters<typeof openSseStream>[0]> = {},
) =>
  openSseStream({
    url: 'https://api.example.com/stream',
    method: 'POST',
    payload: { a: 1 },
    onBusinessError: jest.fn(),
    ...overrides,
  });

describe('sse-client', () => {
  beforeAll(() => {
    global.XMLHttpRequest = FakeXhr as unknown as typeof XMLHttpRequest;
  });

  afterAll(() => {
    global.XMLHttpRequest = originalXhr;
  });

  beforeEach(() => {
    jest.clearAllMocks();
    FakeXhr.instances = [];
    mockToken = 'token-1';
  });

  describe('openSseStream', () => {
    test('sends an authenticated, traced JSON request', () => {
      openTestStream({ method: 'PUT', language: 'fr-FR' });

      const xhr = latestXhr();
      expect(xhr.method).toBe('PUT');
      expect(xhr.url).toBe('https://api.example.com/stream');
      expect(xhr.body).toBe(JSON.stringify({ a: 1 }));
      expect(xhr.requestHeaders).toEqual({
        'Content-Type': 'application/json',
        'Accept-Language': 'fr-FR',
        Authorization: 'Bearer token-1',
        Token: 'token-1',
        'X-Request-ID': 'request-1',
      });
    });

    test('omits auth headers without a token and language when disabled', () => {
      mockToken = '';
      openTestStream({ includeLanguageHeaders: false });

      expect(latestXhr().requestHeaders).toEqual({
        'Content-Type': 'application/json',
        'X-Request-ID': 'request-1',
      });
    });

    test('attaches the business fallback with request metadata', () => {
      const onBusinessError = jest.fn();
      const source = openTestStream({
        meta: { skipErrorToast: true, creditInsufficientAudience: 'teacher' },
        onBusinessError,
      });

      expect(attachSseBusinessResponseFallback).toHaveBeenCalledWith(source, {
        requestToken: 'token-1',
        meta: {
          url: 'https://api.example.com/stream',
          method: 'POST',
          requestToken: 'token-1',
          requestId: 'request-1',
          harnessRunId: 'harness-1',
          skipErrorToast: true,
          creditInsufficientAudience: 'teacher',
        },
        onHandled: expect.any(Function),
      });

      const error = Object.assign(new Error('busy'), { code: 409 });
      (
        attachSseBusinessResponseFallback as jest.Mock
      ).mock.calls[0][1].onHandled(error);
      expect(onBusinessError).toHaveBeenCalledWith(error, source);
    });

    test('close aborts the request and marks the stream closed', () => {
      const source = openTestStream();
      const onAbort = jest.fn();
      source.addEventListener('abort', onAbort);

      source.close();

      expect(latestXhr().aborted).toBe(true);
      expect(onAbort).toHaveBeenCalledTimes(1);
      expect(source.readyState).toBe(2);
    });
  });

  describe('message framing', () => {
    test('joins events split across chunk boundaries', () => {
      const source = openTestStream();
      const onMessage = jest.fn();
      onSseJson(source, onMessage);

      const xhr = latestXhr();
      xhr.push('data: {"type":"te');
      expect(onMessage).not.toHaveBeenCalled();
      xhr.push('xt","content":"hi"}\n');
      xhr.push('\ndata: {"type":"done"}\n\n');

      expect(onMessage.mock.calls).toEqual([
        [{ type: 'text', content: 'hi' }],
        [{ type: 'done' }],
      ]);
    });

    test('joins multi-line data fields with newlines', () => {
      const source = openTestStream();
      const onData = jest.fn();
      onSseData(source, onData);

      latestXhr().push('data: first\ndata: second\n\n');

      expect(onData).toHaveBeenCalledWith('first\nsecond');
    });

    test('flushes the trailing event when the response ends', () => {
      const source = openTestStream();
      const onMessage = jest.fn();
      onSseJson(source, onMessage);

      const xhr = latestXhr();
      xhr.push('data: {"type":"done","is_terminal":true}');
      expect(onMessage).not.toHaveBeenCalled();
      xhr.finish();

      expect(onMessage).toHaveBeenCalledWith({
        type: 'done',
        is_terminal: true,
      });
      expect(source.readyState).toBe(2);
    });
  });

  describe('onSseData', () => {
    test('trims data and skips empty frames', () => {
      const listeners: Record<string, (event: Event) => void> = {};
      const target = {
        addEventListener: (type: string, listener: (event: Event) => void) => {
          listeners[type] = listener;
        },
      };
      const onData = jest.fn();
      onSseData(target, onData);

      const emit = (data: unknown) =>
        listeners.message(Object.assign(new Event('message'), { data }));
      emit(undefined);
      emit('');
      emit('   ');
      emit('  {"a":1}  ');

      expect(onData).toHaveBeenCalledTimes(1);
      expect(onData).toHaveBeenCalledWith('{"a":1}');
    });
  });

  describe('onSseJson', () => {
    const createTarget = () => {
      const listeners: Record<string, (event: Event) => void> = {};
      return {
        target: {
          addEventListener: (
            type: string,
            listener: (event: Event) => void,
          ) => {
            listeners[type] = listener;
          },
        },
        emit: (data: string) =>
          listeners.message(Object.assign(new Event('message'), { data })),
      };
    };

    test('ignores malformed frames when no error handler is given', () => {
      const { target, emit } = createTarget();
      const onMessage = jest.fn();
      onSseJson(target, onMessage);

      emit('{not-json');
      emit('{"type":"text"}');

      expect(onMessage).toHaveBeenCalledTimes(1);
      expect(onMessage).toHaveBeenCalledWith({ type: 'text' });
    });

    test('reports parse and handler errors to the error handler', () => {
      const { target, emit } = createTarget();
      const handlerError = new Error('handler failed');
      const onError = jest.fn();
      onSseJson(
        target,
        () => {
          throw handlerError;
        },
        onError,
      );

      emit('{not-json');
      emit('{"type":"text"}');

      expect(onError).toHaveBeenCalledTimes(2);
      expect(onError.mock.calls[0][0]).toBeInstanceOf(SyntaxError);
      expect(onError.mock.calls[1][0]).toBe(handlerError);
    });
  });

  describe('dispatchSseBusinessError', () => {
    test('re-emits the business error as an error event', () => {
      const source = openTestStream();
      const onError = jest.fn();
      source.addEventListener('error', onError);

      dispatchSseBusinessError(source, { message: 'busy', code: 409 });

      expect(onError).toHaveBeenCalledTimes(1);
      const event = onError.mock.calls[0][0] as CustomEvent & {
        data?: string;
        responseCode?: number;
      };
      expect(event.detail).toEqual({ message: 'busy', code: 409 });
      expect(event.data).toBe('busy');
      expect(event.responseCode).toBe(409);
    });
  });
});
