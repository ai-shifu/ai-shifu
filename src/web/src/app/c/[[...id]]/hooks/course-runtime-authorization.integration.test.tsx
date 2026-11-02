import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import RuntimeConfigInitializer from '@/components/RuntimeConfigInitializer';
import { wechatLogin } from '@/constants/ui-constants';
import { initializeEnvData } from '@/lib/initialize-runtime-config';
import { useEnvStore } from '@/store/env-store';
import { useCourseWechatAuthorizationState } from './use-course-wechat-authorization';

let mockPathname = '/admin';
jest.mock('next/navigation', () => ({ usePathname: () => mockPathname }));
jest.mock('@/constants/ui-constants', () => ({
  inWechat: () => true,
  inMiniProgram: () => false,
  wechatLogin: jest.fn(),
}));

const mockWechatLogin = jest.mocked(wechatLogin);
const authorizeLabel = 'Authorize';
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(accept => {
    resolve = accept;
  });
  return { promise, resolve };
};
const runtimeResponse = (data: Record<string, unknown> = {}) =>
  ({
    ok: true,
    json: async () => ({
      code: 0,
      data: {
        logoWideUrl: '/platform-wide.png',
        logoSquareUrl: '/platform-square.png',
        wechatAppId: 'wx-admin',
        enableWechatCode: true,
        ...data,
      },
    }),
  }) as Response;

const CourseConsumer = ({ courseId }: { courseId: string }) => {
  const runtimeConfigLoaded = useEnvStore(state => state.runtimeConfigLoaded);
  const appId = useEnvStore(state => state.appId);
  const enabled = useEnvStore(state => state.enableWxcode === 'true');
  const authorization = useCourseWechatAuthorizationState({
    courseId,
    runtimeConfigLoaded,
    appId,
    enabled,
    queryCode: '',
    wechatCode: '',
    updateWechatCode: jest.fn(),
  });
  return (
    <>
      <output data-testid='ready'>{String(authorization.ready)}</output>
      <button onClick={() => authorization.authorize({ appId })}>
        {authorizeLabel}
      </button>
    </>
  );
};

// The consumer effect intentionally precedes initialization. Readiness must
// reject the old route's snapshot before the initializer marks it loading.
const RouteHarness = () => (
  <>
    {mockPathname.startsWith('/c/') && (
      <CourseConsumer courseId={mockPathname.split('/')[2]} />
    )}
    <RuntimeConfigInitializer />
  </>
);

describe('course runtime OAuth integration', () => {
  const originalFetch = global.fetch;
  const pending = new Map<string, ReturnType<typeof deferred<Response>>>();
  let resetId = 0;

  beforeEach(async () => {
    jest.clearAllMocks();
    mockWechatLogin.mockReset();
    pending.clear();
    jest.spyOn(console, 'error').mockImplementation(() => {});
    global.fetch = jest.fn(async input => {
      const url = new URL(String(input), 'https://current-site.test');
      if (url.pathname === '/api/config') {
        return { ok: true, json: async () => ({ apiBaseUrl: '' }) } as Response;
      }
      const waiting = pending.get(url.searchParams.get('shifu_bid') || '');
      return waiting ? waiting.promise : runtimeResponse();
    });
    // Move through a unique key so the real module's deduplication can remain
    // enabled between cases, then start from a confirmed admin snapshot.
    await initializeEnvData(`/c/reset-${++resetId}`);
    await initializeEnvData('/admin');
    mockPathname = '/admin';
  });

  afterEach(() => {
    global.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  const navigate = async (
    rerender: (ui: React.ReactNode) => void,
    id: string,
  ) => {
    mockPathname = `/c/${id}`;
    rerender(<RouteHarness />);
    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        `/api/runtime-config?shifu_bid=${id}`,
        { cache: 'no-store' },
      ),
    );
  };

  it('waits for a deferred course response after admin and navigates once with its fresh app ID', async () => {
    const course = deferred<Response>();
    pending.set('admin-to-course', course);
    const { rerender } = render(<RouteHarness />);
    await navigate(rerender, 'admin-to-course');

    expect(useEnvStore.getState().runtimeConfigLoaded).toBe(true);
    expect(screen.getByTestId('ready')).toHaveTextContent('false');
    expect(mockWechatLogin).not.toHaveBeenCalled();

    await act(async () => {
      course.resolve(runtimeResponse({ wechatAppId: 'wx-course' }));
    });
    await waitFor(() => expect(mockWechatLogin).toHaveBeenCalledTimes(1));
    expect(mockWechatLogin).toHaveBeenCalledWith({ appId: 'wx-course' });
  });

  it.each(['success', 'failure'] as const)(
    'ignores stale course A %s while course B is loading',
    async outcome => {
      const a = deferred<Response>();
      const b = deferred<Response>();
      const courseA = `race-a-${outcome}`;
      const courseB = `race-b-${outcome}`;
      pending.set(courseA, a);
      pending.set(courseB, b);
      const { rerender } = render(<RouteHarness />);
      await navigate(rerender, courseA);
      await navigate(rerender, courseB);
      const contextB = useEnvStore.getState().runtimeConfigContext;

      await act(async () => {
        a.resolve(
          outcome === 'success'
            ? runtimeResponse({ wechatAppId: 'wx-stale-a' })
            : ({ ok: false, status: 503 } as Response),
        );
      });
      expect(useEnvStore.getState().runtimeConfigContext).toEqual(contextB);
      expect(screen.getByTestId('ready')).toHaveTextContent('false');
      expect(mockWechatLogin).not.toHaveBeenCalled();

      await act(async () => {
        b.resolve(runtimeResponse({ wechatAppId: 'wx-course-b' }));
      });
      await waitFor(() => expect(mockWechatLogin).toHaveBeenCalledTimes(1));
      expect(mockWechatLogin).toHaveBeenCalledWith({ appId: 'wx-course-b' });
    },
  );

  it('fails open after current-course runtime failure without automatic or manual OAuth using admin settings', async () => {
    const course = deferred<Response>();
    pending.set('failed-current-course', course);
    const { rerender } = render(<RouteHarness />);
    await navigate(rerender, 'failed-current-course');
    await act(async () =>
      course.resolve({ ok: false, status: 503 } as Response),
    );
    await waitFor(() =>
      expect(screen.getByTestId('ready')).toHaveTextContent('true'),
    );
    expect(useEnvStore.getState().runtimeConfigContext).toMatchObject({
      courseId: 'failed-current-course',
      status: 'failed',
    });
    act(() => screen.getByRole('button', { name: 'Authorize' }).click());
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('releases preparation without OAuth when the current customer-domain response disables it', async () => {
    const course = deferred<Response>();
    pending.set('customer-course', course);
    const { rerender } = render(<RouteHarness />);
    await navigate(rerender, 'customer-course');
    expect(mockWechatLogin).not.toHaveBeenCalled();
    await act(async () =>
      course.resolve(
        runtimeResponse({
          wechatAppId: '',
          enableWechatCode: false,
          domain: { is_custom_domain: true },
        }),
      ),
    );
    await waitFor(() =>
      expect(screen.getByTestId('ready')).toHaveTextContent('true'),
    );
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });
});
