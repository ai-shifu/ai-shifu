import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import RuntimeConfigInitializer from '@/components/RuntimeConfigInitializer';
import { wechatLogin } from '@/constants/ui-constants';
import { initializeEnvData } from '@/lib/initialize-runtime-config';
import { useEnvStore } from '@/store/env-store';
import { updateWxcode } from '@/api/user';
import { useCourseWechatAuthorizationState } from './use-course-wechat-authorization';
import { useWechatOpenIdBinding } from './use-wechat-open-id-binding';

let mockPathname = '/admin';
let mockCourseCode = '';
jest.mock('next/navigation', () => ({ usePathname: () => mockPathname }));
jest.mock('@/api/user', () => ({ updateWxcode: jest.fn() }));
jest.mock('@/constants/ui-constants', () => ({
  inWechat: () => true,
  inMiniProgram: () => false,
  wechatLogin: jest.fn(),
}));

const mockWechatLogin = jest.mocked(wechatLogin);
const mockUpdateWxcode = jest.mocked(updateWxcode);
const refreshUserInfo = jest.fn().mockResolvedValue(undefined);
const rebindSessionKey = 'wechat_openid_rebind_attempted';
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
    queryCode: mockCourseCode,
    wechatCode: mockCourseCode,
    updateWechatCode: jest.fn(),
  });
  const bindingReady = useWechatOpenIdBinding({
    initialized: authorization.ready && !authorization.preparationAbandoned,
    isLoggedIn: true,
    userId: 'learner-a',
    token: 'learner-token',
    userProfileLoaded: true,
    openId: '',
    code: mockCourseCode,
    enabled,
    appId,
    refreshUserInfo,
    authorize: authorization.authorize,
  });
  return (
    <>
      <output data-testid='ready'>{String(authorization.ready)}</output>
      <output data-testid='startup-ready'>
        {String(authorization.ready && bindingReady)}
      </output>
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
    mockUpdateWxcode.mockReset();
    sessionStorage.clear();
    mockCourseCode = '';
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
    jest.useRealTimers();
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
    jest.useFakeTimers();
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
    expect(useEnvStore.getState().appId).toBe('wx-admin');
    expect(useEnvStore.getState().enableWxcode).toBe('true');
    expect(screen.getByTestId('startup-ready')).toHaveTextContent('true');
    act(() => jest.advanceTimersByTime(60_001));
    expect(screen.getByTestId('startup-ready')).toHaveTextContent('true');
    expect(sessionStorage.getItem(rebindSessionKey)).toBeNull();
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    act(() => screen.getByRole('button', { name: 'Authorize' }).click());
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('keeps startup locked after valid current-course OpenID recovery issues navigation', async () => {
    const course = deferred<Response>();
    pending.set('valid-recovery-course', course);
    mockCourseCode = 'spent-code';
    mockUpdateWxcode.mockResolvedValue('');
    const { rerender } = render(<RouteHarness />);
    await navigate(rerender, 'valid-recovery-course');
    jest.useFakeTimers();
    await act(async () =>
      course.resolve(runtimeResponse({ wechatAppId: 'wx-course' })),
    );
    await waitFor(() => expect(mockWechatLogin).toHaveBeenCalledTimes(1));
    expect(mockWechatLogin).toHaveBeenCalledWith(
      expect.objectContaining({
        appId: 'wx-course',
        redirectUrl: expect.any(String),
      }),
    );
    expect(sessionStorage.getItem(rebindSessionKey)).toBe('1');
    act(() => jest.advanceTimersByTime(60_001));
    expect(screen.getByTestId('startup-ready')).toHaveTextContent('false');
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
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
