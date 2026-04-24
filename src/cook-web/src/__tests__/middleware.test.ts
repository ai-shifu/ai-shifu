jest.mock('next/server', () => ({
  NextResponse: {
    next: () =>
      ({
        status: 200,
        headers: new Headers(),
      }) as Response,
    redirect: (url: string | URL) =>
      ({
        status: 307,
        headers: new Headers({ location: url.toString() }),
      }) as Response,
  },
}));

import type { NextRequest } from 'next/server';
import { middleware } from '@/middleware';

const createRequest = (url: string, userAgent: string): NextRequest => {
  const parsed = new URL(url);

  return {
    headers: new Headers({
      'user-agent': userAgent,
    }),
    nextUrl: {
      clone: () => new URL(url),
      pathname: parsed.pathname,
      search: parsed.search,
    },
  } as unknown as NextRequest;
};

describe('middleware', () => {
  it('redirects unsupported iOS versions on learner routes', () => {
    const request = createRequest(
      'https://app.ai-shifu.cn/c/lesson-id',
      'Mozilla/5.0 (iPhone; CPU iPhone OS 15_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Mobile/15E148 Safari/604.1',
    );

    const response = middleware(request);

    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe(
      'https://app.ai-shifu.cn/unsupported-browser',
    );
  });

  it('allows supported iOS versions', () => {
    const request = createRequest(
      'https://app.ai-shifu.cn/c/lesson-id',
      'Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Mobile/15E148 Safari/604.1',
    );

    const response = middleware(request);

    expect(response.status).toBe(200);
    expect(response.headers.get('location')).toBeNull();
  });

  it('allows non-iOS clients', () => {
    const request = createRequest(
      'https://app.ai-shifu.cn/c/lesson-id',
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    );

    const response = middleware(request);

    expect(response.status).toBe(200);
    expect(response.headers.get('location')).toBeNull();
  });
});
