import { SSE } from 'sse.js';
import { attachSseBusinessResponseFallback } from '@/lib/request';
import {
  bindLessonStream,
  createSseSource,
  resolveLessonStreamTerminal,
} from './lessonStream';

jest.mock('sse.js', () => ({ SSE: jest.fn() }));
jest.mock('@/lib/request', () => ({
  attachSseBusinessResponseFallback: jest.fn(),
  getCurrentLanguageHeaders: (language = 'fr-FR') => ({
    'Accept-Language': language,
  }),
}));
jest.mock('@/lib/request-trace', () => ({
  buildTraceHeaders: (headers: Record<string, string>) => ({
    headers: { ...headers, 'x-request-id': 'request-1' },
    requestId: 'request-1',
    harnessRunId: 'harness-1',
  }),
}));
jest.mock('@/store/useUserStore', () => ({
  useUserStore: { getState: () => ({ getToken: () => 'request-token' }) },
}));

class MockSource {
  readyState = 0;
  xhr: object | null = null;
  private listeners = new Map<string, Array<(event: any) => void>>();
  addEventListener(type: string, listener: (event: any) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  dispatchEvent(event: Event) {
    this.emit(event.type, event);
    return true;
  }
  emit(type: string, event: any = {}) {
    this.listeners.get(type)?.forEach(listener => listener(event));
  }
  message(response: unknown) {
    this.emit('message', { data: JSON.stringify(response) });
  }
  end() {
    this.readyState = 2;
    this.emit('readystatechange', { readyState: 2 });
  }
  stream = jest.fn(() => {
    this.xhr = {};
  });
  close = jest.fn(() => {
    this.emit('abort');
    this.end();
  });
}

describe('lesson stream lifecycle', () => {
  beforeEach(() => jest.clearAllMocks());

  test('shares auth, language, trace and business fallback after XHR creation', () => {
    const source = new MockSource();
    const nativeStream = source.stream;
    (SSE as jest.Mock).mockReturnValue(source);
    const payload = { input: { answer: ['yes'] } };
    const result = createSseSource({
      url: '/lesson/run',
      payload,
      method: 'PUT',
      language: 'zh-CN',
      creditInsufficientAudience: 'teacher',
      skipErrorToast: true,
      start: false,
      onMessage: jest.fn(),
    });
    expect(SSE).toHaveBeenCalledWith('/lesson/run', {
      method: 'PUT',
      start: false,
      payload: JSON.stringify(payload),
      headers: {
        'Content-Type': 'application/json',
        'Accept-Language': 'zh-CN',
        Authorization: 'Bearer request-token',
        Token: 'request-token',
        'x-request-id': 'request-1',
      },
    });
    expect(attachSseBusinessResponseFallback).not.toHaveBeenCalled();
    result.stream();
    expect(nativeStream).toHaveBeenCalledTimes(1);
    expect(source.xhr).not.toBeNull();
    expect(attachSseBusinessResponseFallback).toHaveBeenCalledWith(
      source,
      expect.objectContaining({
        requestToken: 'request-token',
        meta: {
          url: '/lesson/run',
          method: 'PUT',
          requestToken: 'request-token',
          requestId: 'request-1',
          harnessRunId: 'harness-1',
          creditInsufficientAudience: 'teacher',
          skipErrorToast: true,
        },
      }),
    );
  });

  test('decodes JSON once and preserves legacy event_type and business payloads', () => {
    const source = new MockSource();
    const onMessage = jest.fn();
    bindLessonStream(source, { onMessage });
    source.emit('message', { data: 'malformed' });
    source.emit('message', { data: ' ' });
    const response = { event_type: 'content', data: { mdflow: 'hello' } };
    source.emit('message', { data: `data: ${JSON.stringify(response)}` });
    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(onMessage).toHaveBeenCalledWith(response);
  });

  test('only explicit terminal done settles before a consumer closes the source', async () => {
    const source = new MockSource();
    const onSettled = jest.fn();
    const onMessage = jest.fn(response => {
      if (response.is_terminal === true) source.close();
    });
    bindLessonStream(source, { onMessage, onSettled });
    source.message({ type: 'done', is_terminal: false });
    source.message({ type: 'text_end' });
    source.message({ type: 'done' });
    expect(onSettled).not.toHaveBeenCalled();
    source.message({ type: 'done', is_terminal: true });
    source.emit('error', new Error('late error'));
    source.message({ type: 'content', content: 'late content' });
    await Promise.resolve();
    expect(onMessage).toHaveBeenCalledTimes(4);
    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(onSettled).toHaveBeenCalledWith('terminal');
  });

  test.each([[], [{ type: 'preview_engine', content: '2.0' }]])(
    'settles an empty or control-only HTTP stream at EOF',
    async (...responses) => {
      const source = new MockSource();
      const onSettled = jest.fn();
      bindLessonStream(source, { onMessage: jest.fn(), onSettled });
      responses.forEach(response => source.message(response));
      source.end();
      source.end();
      await new Promise(resolve => setTimeout(resolve, 0));
      expect(onSettled).toHaveBeenCalledTimes(1);
      expect(onSettled).toHaveBeenCalledWith('eof');
    },
  );

  test('settles a transport error once even if its consumer closes the stream', async () => {
    const source = new MockSource();
    const onError = jest.fn(() => source.close());
    const onSettled = jest.fn();
    bindLessonStream(source, { onMessage: jest.fn(), onError, onSettled });
    source.emit('error', new Error('network unavailable'));
    source.end();
    await Promise.resolve();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(onSettled).toHaveBeenCalledWith('error');
  });

  test('cancellation ignores late data, errors and EOF', async () => {
    const source = new MockSource();
    const onMessage = jest.fn();
    const onError = jest.fn();
    const onSettled = jest.fn();
    bindLessonStream(source, { onMessage, onError, onSettled });
    source.close();
    source.message({ type: 'done', is_terminal: true });
    source.emit('error', new Error('late error'));
    await Promise.resolve();
    expect(onMessage).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(onSettled).toHaveBeenCalledWith('cancelled');
  });

  test('a replaced source cannot update the next request', async () => {
    const oldSource = new MockSource();
    const nextSource = new MockSource();
    let current = oldSource;
    const onMessage = jest.fn();
    const onError = jest.fn();
    const oldSettled = jest.fn();
    const nextSettled = jest.fn();
    bindLessonStream(oldSource, {
      isCurrent: () => current === oldSource,
      onMessage,
      onError,
      onSettled: oldSettled,
    });
    current = nextSource;
    bindLessonStream(nextSource, {
      isCurrent: () => current === nextSource,
      onMessage,
      onSettled: nextSettled,
    });
    oldSource.message({ type: 'content', content: 'stale' });
    oldSource.emit('error', new Error('stale error'));
    oldSource.end();
    nextSource.message({ type: 'content', content: 'current' });
    await Promise.resolve();
    expect(oldSettled).toHaveBeenCalledTimes(1);
    expect(oldSettled).toHaveBeenCalledWith('stale');
    expect(onError).not.toHaveBeenCalled();
    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(onMessage).toHaveBeenCalledWith({
      type: 'content',
      content: 'current',
    });
    expect(nextSettled).not.toHaveBeenCalled();
  });

  test.each(['closed', 'http-error'])(
    'keeps the business error when sse.js emits %s before JSON fallback',
    async outcome => {
      const source = new MockSource();
      (SSE as jest.Mock).mockReturnValue(source);
      let fallback: any;
      (attachSseBusinessResponseFallback as jest.Mock).mockImplementationOnce(
        (_source, options) => {
          fallback = options;
          return {
            handleResponse: jest.fn(() => {
              options.onDetected();
              return true;
            }),
          };
        },
      );
      const onError = jest.fn();
      const onSettled = jest.fn();
      createSseSource({
        url: '/lesson/run',
        payload: {},
        creditInsufficientAudience: 'learner',
        onMessage: jest.fn(),
        onError,
        onSettled,
      });
      if (outcome === 'http-error') {
        source.emit('error', { data: '{"code":2301}' });
      } else {
        source.end();
        // Native event dispatch can run microtasks between the sse.js load
        // listener and the following request fallback load listener.
        await Promise.resolve();
        expect(onSettled).not.toHaveBeenCalled();
        fallback.onDetected();
      }
      await new Promise(resolve => setTimeout(resolve, 0));
      expect(onSettled).not.toHaveBeenCalled();
      const error = Object.assign(new Error('Insufficient credit'), {
        code: 2301,
      });
      fallback.onHandled(error);
      source.end();
      await Promise.resolve();
      expect(onError).toHaveBeenCalledTimes(1);
      expect(onError.mock.calls[0][0].detail).toBe(error);
      expect(onSettled).toHaveBeenCalledTimes(1);
      expect(onSettled).toHaveBeenCalledWith('error');
    },
  );

  test.each([
    [{ is_terminal: false, content: { is_terminal: true } }, false],
    [{ content: '{"is_terminal":true}' }, true],
    [{ data: { is_terminal: 'FALSE' } }, false],
    [{ is_terminal: 1 }, true],
    [{}, null],
  ])('preserves terminal flag compatibility for %j', (response, expected) => {
    expect(resolveLessonStreamTerminal(response)).toBe(expected);
  });
});
