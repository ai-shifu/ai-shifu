import { waitFor } from '@testing-library/react';
import { toast, toastOnce } from '@/hooks/useToast';
import i18n from 'i18next';
import {
  Request,
  attachSseBusinessResponseFallback,
  getCurrentLanguageHeaders,
  getCurrentRequestLanguage,
  handleBusinessCode,
  parseBusinessResponsePayload,
} from './request';
import {
  clearPendingRequestLanguage,
  setPendingRequestLanguage,
} from './request-language';
import {
  buildTraceHeaders,
  TRACE_HARNESS_RUN_ID_HEADER,
  TRACE_REQUEST_ID_HEADER,
} from './request-trace';

const mockLogout = jest.fn();
const mockGetToken = jest.fn(() => 'active-token');

jest.mock('@/hooks/useToast', () => ({
  toast: jest.fn(),
  toastOnce: jest.fn(),
}));

jest.mock('@/store', () => ({
  useUserStore: {
    getState: jest.fn(() => ({
      getToken: mockGetToken,
      logout: mockLogout,
    })),
  },
}));

class MockXhr extends EventTarget {
  responseText = '';
}

describe('request SSE business fallback', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    clearPendingRequestLanguage();
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

  test('uses the pending language while i18next is still switching', () => {
    const originalLanguage = i18n.language;
    const originalResolvedLanguage = i18n.resolvedLanguage;

    try {
      i18n.language = 'zh-CN';
      i18n.resolvedLanguage = 'zh-CN';
      setPendingRequestLanguage('fr-FR');

      expect(getCurrentRequestLanguage()).toBe('fr-FR');
      expect(getCurrentLanguageHeaders()).toEqual({
        'Accept-Language': 'fr-FR',
      });
    } finally {
      i18n.language = originalLanguage;
      i18n.resolvedLanguage = originalResolvedLanguage;
      clearPendingRequestLanguage('fr-FR');
    }
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

  test('routes credit errors through the explicit learner audience', async () => {
    await expect(
      handleBusinessCode(
        {
          code: 7101,
          message: 'server message',
        },
        '',
        { creditInsufficientAudience: 'learner' },
      ),
    ).rejects.toMatchObject({ code: 7101, toastHandled: true });

    expect(toastOnce).toHaveBeenCalledWith(
      expect.objectContaining({
        dedupeKey: 'credit-insufficient:learner:7101',
        duration: 0,
        action: undefined,
      }),
    );
    expect(toast).not.toHaveBeenCalled();
  });

  test.each([1001, 1004, 1005])(
    'rejects auth error %s without global recovery when explicitly skipped',
    async code => {
      const hrefBeforeRequest = window.location.href;

      await expect(
        handleBusinessCode(
          {
            code,
            message: 'visit write auth failure',
          },
          'active-token',
          { skipAuthRecovery: true },
        ),
      ).rejects.toMatchObject({ code });

      expect(mockLogout).not.toHaveBeenCalled();
      expect(window.location.href).toBe(hrefBeforeRequest);
    },
  );

  test('passes skipAuthRecovery through the POST request pipeline', async () => {
    const request = new Request();
    const hrefBeforeRequest = window.location.href;
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => ({
        code: 1001,
        message: 'visit write auth failure',
      }),
    }) as jest.Mock;

    await expect(
      request.post(
        'http://example.com/api/learn/shifu/course-1/visit',
        {},
        {
          skipAuthRecovery: true,
          skipErrorToast: true,
        },
      ),
    ).rejects.toMatchObject({ code: 1001 });

    expect(mockLogout).not.toHaveBeenCalled();
    expect(window.location.href).toBe(hrefBeforeRequest);
  });

  test('preserves auth recovery for requests that do not opt out', async () => {
    window.location.pathname = '/login';

    await expect(
      handleBusinessCode(
        {
          code: 1001,
          message: 'expired session',
        },
        'active-token',
      ),
    ).rejects.toMatchObject({ code: 1001 });

    expect(mockLogout).toHaveBeenCalledWith(false);
  });

  test('falls back to serviceUnavailable for server request failures', async () => {
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
      message: 'common.core.serviceUnavailable',
      status: 503,
    });

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'common.core.serviceUnavailable',
        variant: 'destructive',
      }),
    );
  });

  test('keeps requestFailed for client-side HTTP request failures', async () => {
    const request = new Request();
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
      headers: new Headers(),
    }) as jest.Mock;

    await expect(
      request.get('http://example.com/api/missing'),
    ).rejects.toMatchObject({
      code: 404,
      message: 'common.core.requestFailed',
      status: 404,
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
