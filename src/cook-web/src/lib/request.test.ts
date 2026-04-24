import { waitFor } from '@testing-library/react';
import { toast } from '@/hooks/useToast';
import {
  attachSseBusinessResponseFallback,
  parseBusinessResponsePayload,
} from './request';

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
      { onHandled },
    );

    xhr.responseText = JSON.stringify({
      code: 2301,
      message: '积分余额不足，暂时无法继续调用，请先充值或开通订阅',
    });
    xhr.dispatchEvent(new Event('load'));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: '积分余额不足，暂时无法继续调用，请先充值或开通订阅',
          variant: 'destructive',
        }),
      );
      expect(onHandled).toHaveBeenCalledTimes(1);
      expect(onHandled.mock.calls[0][0]).toMatchObject({
        code: 2301,
        message: '积分余额不足，暂时无法继续调用，请先充值或开通订阅',
      });
    });
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
