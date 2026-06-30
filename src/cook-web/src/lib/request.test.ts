import { waitFor } from '@testing-library/react';
import { toast } from '@/hooks/useToast';
import {
  Request,
  attachSseBusinessResponseFallback,
  handleBusinessCode,
  parseBusinessResponsePayload,
} from './request';
import {
  buildTraceHeaders,
  TRACE_HARNESS_RUN_ID_HEADER,
  TRACE_REQUEST_ID_HEADER,
} from './request-trace';

jest.mock('@/hooks/useToast', () => ({
  toast: jest.fn(),
}));

jest.mock('@/store', () => ({
  useUserStore: {
    getState: jest.fn(() => ({
      getToken: jest.fn(() => ''),
      logout: jest.fn(),
    })),
  },
}));

class MockXhr extends EventTarget {
  responseText = '';
}

describe('request SSE business fallback', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.location.pathname = '/';
    window.location.search = '';
    window.sessionStorage.clear();
    delete window.__HARNESS_RUN_ID__;
  });

  test('adds request and harness trace headers while preserving caller request ids', () => {
    window.sessionStorage.setItem('harness_run_id', 'harness-test-run');

    const traceHeaders = buildTraceHeaders({
      'Content-Type': 'application/json',
      'x-request-id': 'caller-request-id',
    });

    expect(traceHeaders.requestId).toBe('caller-request-id');
    expect(traceHeaders.harnessRunId).toBe('harness-test-run');
    expect(traceHeaders.headers['x-request-id']).toBe('caller-request-id');
    expect(traceHeaders.headers[TRACE_HARNESS_RUN_ID_HEADER]).toBe(
      'harness-test-run',
    );
  });

  test('generates a request id when the caller does not provide one', () => {
    const traceHeaders = buildTraceHeaders(undefined, () => 'generated-id');

    expect(traceHeaders.requestId).toBe('generated-id');
    expect(traceHeaders.headers[TRACE_REQUEST_ID_HEADER]).toBe('generated-id');
  });

  test('parses a business response payload from JSON text', () => {
    expect(
      parseBusinessResponsePayload(
        JSON.stringify({
          code: 2301,
          message: '积分余额不足',
        }),
      ),
    ).toEqual({
      code: 2301,
      message: '积分余额不足',
    });
  });

  test('handles JSON business responses returned before SSE starts streaming', async () => {
    const xhr = new MockXhr();
    const onHandled = jest.fn();

    attachSseBusinessResponseFallback(
      { xhr: xhr as unknown as XMLHttpRequest },
      {
        meta: {
          requestId: 'fallback-request-id',
          harnessRunId: 'fallback-run-id',
        },
        onHandled,
      },
    );

    xhr.responseText = JSON.stringify({
      code: 2301,
      message: '积分余额不足，暂时无法继续调用，请先开通订阅或购买积分',
    });
    xhr.dispatchEvent(new Event('load'));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: '积分余额不足，暂时无法继续调用，请先开通订阅或购买积分',
          variant: 'destructive',
        }),
      );
      expect(onHandled).toHaveBeenCalledTimes(1);
      expect(onHandled.mock.calls[0][0]).toMatchObject({
        code: 2301,
        message: '积分余额不足，暂时无法继续调用，请先开通订阅或购买积分',
        requestId: 'fallback-request-id',
        harnessRunId: 'fallback-run-id',
      });
    });
  });

  test('falls back to actionFailed for business errors without a message', async () => {
    await expect(
      handleBusinessCode({
        code: 2301,
      }),
    ).rejects.toMatchObject({
      code: 2301,
      message: 'common.core.actionFailed',
    });

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'common.core.actionFailed',
        variant: 'destructive',
      }),
    );
  });

  test('falls back to requestFailed for HTTP request failures', async () => {
    const request = new Request();
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 503,
      headers: new Headers(),
    }) as jest.Mock;

    await expect(
      request.get('http://example.com/api/demo'),
    ).rejects.toMatchObject({
      code: 503,
      message: 'common.core.requestFailed',
      status: 503,
    });

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'common.core.requestFailed',
        variant: 'destructive',
      }),
    );
  });

  test('ignores normal SSE transcript payloads', async () => {
    const xhr = new MockXhr();
    const onHandled = jest.fn();

    attachSseBusinessResponseFallback(
      { xhr: xhr as unknown as XMLHttpRequest },
      { onHandled },
    );

    xhr.responseText = 'data: {"type":"content","content":"hello"}\n\n';
    xhr.dispatchEvent(new Event('load'));

    await new Promise(resolve => setTimeout(resolve, 0));

    expect(toast).not.toHaveBeenCalled();
    expect(onHandled).not.toHaveBeenCalled();
  });
});
