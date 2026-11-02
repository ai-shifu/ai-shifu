import React from 'react';
import { act, renderHook } from '@testing-library/react';
import { wechatLogin } from '@/constants/ui-constants';
import { debugWarn } from '@/lib/debug-console';
import { useEnvStore } from '@/store/env-store';
import { useCourseWechatAuthorizationState } from './use-course-wechat-authorization';

let mockInWechat = true;
let mockInMiniProgram = false;

jest.mock('@/constants/ui-constants', () => ({
  inWechat: () => mockInWechat,
  inMiniProgram: () => mockInMiniProgram,
  wechatLogin: jest.fn(),
}));
jest.mock('@/lib/debug-console', () => ({ debugWarn: jest.fn() }));

const mockWechatLogin = jest.mocked(wechatLogin);
const mockDebugWarn = jest.mocked(debugWarn);
type AuthorizationParams = Parameters<
  typeof useCourseWechatAuthorizationState
>[0];

const defaultParams = (): AuthorizationParams => ({
  courseId: 'course-1',
  runtimeConfigLoaded: true,
  enabled: true,
  appId: 'wx-app-id',
  queryCode: '',
  wechatCode: '',
  updateWechatCode: jest.fn(),
});

const renderAuthorization = (overrides: Partial<AuthorizationParams> = {}) => {
  const params = { ...defaultParams(), ...overrides };
  const readiness: boolean[] = [];
  const hook = renderHook(
    props => {
      const authorization = useCourseWechatAuthorizationState(props);
      readiness.push(authorization.ready);
      return authorization;
    },
    { initialProps: params },
  );
  return { ...hook, params, readiness };
};

describe('useCourseWechatAuthorizationState', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    mockWechatLogin.mockReset();
    mockInWechat = true;
    mockInMiniProgram = false;
    useEnvStore.setState({
      runtimeConfigLoaded: true,
      runtimeConfigContext: {
        courseId: 'course-1',
        status: 'ready',
        generation: 1,
      },
      appId: 'wx-app-id',
      enableWxcode: 'true',
    });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('closes the first render before navigating when the URL has no code', () => {
    const { result, params, readiness } = renderAuthorization();

    expect(readiness[0]).toBe(false);
    expect(result.current.ready).toBe(false);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockWechatLogin).toHaveBeenCalledWith({ appId: 'wx-app-id' });
    expect(params.updateWechatCode).not.toHaveBeenCalled();
  });

  it('does not accept a stored code when the URL has no code', () => {
    const { result, params, readiness } = renderAuthorization({
      wechatCode: 'stale-code',
    });

    expect(readiness[0]).toBe(false);
    expect(result.current.ready).toBe(false);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(params.updateWechatCode).not.toHaveBeenCalled();
  });

  it('waits for runtime configuration before deciding whether to authorize', () => {
    const { result, rerender, params, readiness } = renderAuthorization({
      runtimeConfigLoaded: false,
    });

    expect(readiness[0]).toBe(false);
    expect(result.current.ready).toBe(false);
    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(params.updateWechatCode).not.toHaveBeenCalled();

    rerender({ ...params, runtimeConfigLoaded: true });

    expect(result.current.ready).toBe(false);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  it('does not authorize a new course using an already-loaded admin context', () => {
    useEnvStore.setState({
      runtimeConfigContext: { courseId: '', status: 'ready', generation: 1 },
    });
    const { result } = renderAuthorization();
    expect(result.current.ready).toBe(false);
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it.each(['ready', 'loading'] as const)(
    'does not use old disabled settings or synchronize a code before its course context is ready (%s)',
    status => {
      useEnvStore.setState({
        runtimeConfigContext: {
          courseId: status === 'ready' ? 'course-2' : 'course-1',
          status,
          generation: 2,
        },
        appId: '',
        enableWxcode: 'false',
      });
      const { result, params } = renderAuthorization({
        enabled: false,
        appId: '',
        queryCode: 'new-course-code',
      });
      expect(result.current.ready).toBe(false);
      expect(params.updateWechatCode).not.toHaveBeenCalled();
      expect(mockWechatLogin).not.toHaveBeenCalled();
    },
  );

  it('fails open after the matching context fails without authorizing its previous app ID', () => {
    useEnvStore.setState({
      runtimeConfigContext: {
        courseId: 'course-1',
        status: 'failed',
        generation: 2,
      },
    });
    const { result } = renderAuthorization();
    expect(result.current.ready).toBe(true);
    act(() => result.current.authorize({ appId: 'wx-app-id' }));
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('rejects a captured callback after its shared context changes before React commits', () => {
    const { result } = renderAuthorization({
      queryCode: 'code',
      wechatCode: 'code',
    });
    const authorize = result.current.authorize;
    act(() => {
      useEnvStore.setState({
        runtimeConfigContext: {
          courseId: 'course-2',
          status: 'loading',
          generation: 2,
        },
      });
      authorize({ appId: 'wx-app-id' });
    });
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('rejects a previous course callback even when both courses use the same app ID', () => {
    const { result, rerender, params } = renderAuthorization({
      queryCode: 'code',
      wechatCode: 'code',
    });
    const authorize = result.current.authorize;
    act(() =>
      useEnvStore.setState({
        runtimeConfigContext: {
          courseId: 'course-2',
          status: 'ready',
          generation: 2,
        },
      }),
    );
    rerender({ ...params, courseId: 'course-2' });
    act(() =>
      authorize({
        appId: 'wx-app-id',
        redirectUrl: 'https://example.test/c/course-1',
      }),
    );
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('rejects a retained callback from an older generation of the same course', () => {
    const { result } = renderAuthorization({
      queryCode: 'code',
      wechatCode: 'code',
    });
    const authorize = result.current.authorize;
    act(() =>
      useEnvStore.setState({
        runtimeConfigContext: {
          courseId: 'course-1',
          status: 'ready',
          generation: 2,
        },
      }),
    );
    act(() => authorize({ appId: 'wx-app-id' }));
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('rejects an unmounted course callback before the new route invalidates the old store snapshot', () => {
    const oldCourse = renderAuthorization({
      queryCode: 'code',
      wechatCode: 'code',
    });
    const authorize = oldCourse.result.current.authorize;
    oldCourse.unmount();
    renderHook(
      () =>
        useCourseWechatAuthorizationState({
          ...defaultParams(),
          courseId: 'course-2',
        }),
      {
        wrapper: function NewRoute({ children }) {
          React.useLayoutEffect(() => {
            authorize({ appId: 'wx-app-id' });
          }, []);
          return <>{children}</>;
        },
      },
    );
    expect(useEnvStore.getState().runtimeConfigContext?.courseId).toBe(
      'course-1',
    );
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('rechecks an authorization effect captured before a layout effect invalidated its context', () => {
    renderHook(() => useCourseWechatAuthorizationState(defaultParams()), {
      wrapper: function ContextInvalidator({ children }) {
        React.useLayoutEffect(() => {
          useEnvStore.setState({
            runtimeConfigContext: {
              courseId: 'course-2',
              status: 'loading',
              generation: 2,
            },
          });
        }, []);
        return <>{children}</>;
      },
    });
    expect(mockWechatLogin).not.toHaveBeenCalled();
    act(() => {
      useEnvStore.setState({
        runtimeConfigContext: {
          courseId: 'course-1',
          status: 'ready',
          generation: 3,
        },
      });
    });
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  it('does not synchronize a URL code from an effect whose context was invalidated', () => {
    const params = { ...defaultParams(), queryCode: 'fresh-code' };
    renderHook(() => useCourseWechatAuthorizationState(params), {
      wrapper: function ContextInvalidator({ children }) {
        React.useLayoutEffect(() => {
          useEnvStore.setState({
            runtimeConfigContext: {
              courseId: 'course-2',
              status: 'loading',
              generation: 2,
            },
          });
        }, []);
        return <>{children}</>;
      },
    });
    expect(params.updateWechatCode).not.toHaveBeenCalled();
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('uses the empty path context for the legacy query-only course route', () => {
    useEnvStore.setState({
      runtimeConfigContext: { courseId: '', status: 'ready', generation: 2 },
    });
    const { result } = renderAuthorization({
      courseId: '',
      queryCode: 'code',
      wechatCode: 'code',
    });
    expect(result.current.ready).toBe(true);
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it.each(['', 'stale-code'])(
    'waits until the URL code replaces stored code %s',
    wechatCode => {
      const { result, rerender, params, readiness } = renderAuthorization({
        queryCode: 'fresh-code',
        wechatCode,
      });

      expect(readiness[0]).toBe(false);
      expect(result.current.ready).toBe(false);
      expect(params.updateWechatCode).toHaveBeenCalledWith('fresh-code');
      expect(mockWechatLogin).not.toHaveBeenCalled();

      rerender({ ...params, wechatCode: 'fresh-code' });

      expect(result.current.ready).toBe(true);
      expect(mockWechatLogin).not.toHaveBeenCalled();
    },
  );

  it('is ready on the first render when the URL and stored codes match', () => {
    const { result, params, readiness } = renderAuthorization({
      queryCode: 'fresh-code',
      wechatCode: 'fresh-code',
    });

    expect(readiness[0]).toBe(true);
    expect(result.current.ready).toBe(true);
    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(params.updateWechatCode).not.toHaveBeenCalled();
  });

  it('issues one navigation when StrictMode replays the authorization effect', () => {
    const readiness: boolean[] = [];
    renderHook(
      () => {
        const authorization =
          useCourseWechatAuthorizationState(defaultParams());
        readiness.push(authorization.ready);
        return authorization;
      },
      {
        wrapper: ({ children }) => (
          <React.StrictMode>{children}</React.StrictMode>
        ),
      },
    );

    expect(readiness.every(ready => !ready)).toBe(true);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  it('releases a synchronous navigation failure after the stored code is cleared', () => {
    mockWechatLogin.mockImplementation(() => {
      throw new Error('navigation unavailable');
    });
    const { result, rerender, params, readiness } = renderAuthorization({
      wechatCode: 'stale-code',
    });

    expect(readiness[0]).toBe(false);
    expect(result.current.ready).toBe(false);
    expect(mockDebugWarn).toHaveBeenCalled();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(params.updateWechatCode).toHaveBeenCalledWith('');

    rerender({ ...params, wechatCode: '' });
    act(() => jest.advanceTimersByTime(60_000));

    expect(result.current.ready).toBe(true);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  it('retries the same app ID for a new course after a previous synchronous navigation failure', () => {
    mockWechatLogin.mockImplementationOnce(() => {
      throw new Error('navigation unavailable');
    });
    const { result, rerender, params } = renderAuthorization();
    expect(result.current.ready).toBe(true);
    act(() =>
      useEnvStore.setState({
        runtimeConfigContext: {
          courseId: 'course-2',
          status: 'ready',
          generation: 2,
        },
      }),
    );
    rerender({ ...params, courseId: 'course-2' });
    expect(result.current.ready).toBe(false);
    expect(mockWechatLogin).toHaveBeenCalledTimes(2);
  });

  it('retains a navigation lock after the URL code and configuration change', () => {
    const { result, rerender, params } = renderAuthorization();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);

    rerender({
      ...params,
      queryCode: 'returned-code',
      wechatCode: 'returned-code',
    });
    expect(result.current.ready).toBe(false);

    rerender({ ...params, enabled: false, appId: '' });
    act(() => jest.advanceTimersByTime(60_000));

    expect(result.current.ready).toBe(false);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  it('locks child-initiated recovery and deduplicates further navigation', () => {
    const { result } = renderAuthorization({
      queryCode: 'spent-code',
      wechatCode: 'spent-code',
    });
    expect(result.current.ready).toBe(true);

    act(() => {
      result.current.authorize({
        appId: 'wx-app-id',
        redirectUrl: 'https://example.com/c/course-a',
      });
    });
    expect(result.current.ready).toBe(false);

    act(() => {
      result.current.authorize({ appId: 'wx-app-id' });
      jest.advanceTimersByTime(60_000);
    });

    expect(result.current.ready).toBe(false);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  it('keeps navigation pending on an ordinary pageshow event', () => {
    const { result } = renderAuthorization();

    act(() => {
      window.dispatchEvent(new PageTransitionEvent('pageshow'));
      jest.advanceTimersByTime(60_000);
    });

    expect(result.current.ready).toBe(false);
    expect(result.current.preparationAbandoned).toBe(false);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['matching', 'fresh-code', true],
    ['mismatching', 'stale-code', false],
  ] as const)(
    'does not abandon preparation on BFCache restoration with %s codes and no navigation',
    (_name, wechatCode, expectedReady) => {
      const { result } = renderAuthorization({
        queryCode: 'fresh-code',
        wechatCode,
      });

      act(() => {
        window.dispatchEvent(
          new PageTransitionEvent('pageshow', { persisted: true }),
        );
      });

      expect(result.current.ready).toBe(expectedReady);
      expect(result.current.preparationAbandoned).toBe(false);
      expect(mockWechatLogin).not.toHaveBeenCalled();
    },
  );

  it('retires a navigation restored from BFCache without authorizing again', () => {
    const { result, rerender, params } = renderAuthorization();
    expect(result.current.ready).toBe(false);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);

    act(() => {
      window.dispatchEvent(
        new PageTransitionEvent('pageshow', { persisted: true }),
      );
      // The old callback can run before React commits the restored state.
      result.current.authorize({ appId: 'wx-app-id' });
    });

    expect(result.current.ready).toBe(true);
    expect(result.current.preparationAbandoned).toBe(true);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);

    rerender({
      ...params,
      appId: 'different-app-id',
      queryCode: 'spent-code',
      wechatCode: 'stale-code',
    });
    expect(result.current.ready).toBe(true);
    expect(result.current.preparationAbandoned).toBe(true);

    rerender({ ...params, appId: 'another-app-id' });
    act(() => {
      result.current.authorize({ appId: 'another-app-id' });
      jest.advanceTimersByTime(60_000);
    });

    expect(result.current.ready).toBe(true);
    expect(result.current.preparationAbandoned).toBe(true);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  it('retires child-initiated recovery when the document returns from BFCache', () => {
    const { result } = renderAuthorization({
      queryCode: 'spent-code',
      wechatCode: 'spent-code',
    });
    act(() => result.current.authorize({ appId: 'wx-app-id' }));
    expect(result.current.ready).toBe(false);

    act(() => {
      window.dispatchEvent(
        new PageTransitionEvent('pageshow', { persisted: true }),
      );
    });

    expect(result.current.ready).toBe(true);
    expect(result.current.preparationAbandoned).toBe(true);

    act(() => result.current.authorize({ appId: 'wx-app-id' }));
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  it('still waits for runtime configuration after abandoning restored preparation', () => {
    const { result, rerender, params } = renderAuthorization();
    rerender({ ...params, runtimeConfigLoaded: false });

    act(() => {
      window.dispatchEvent(
        new PageTransitionEvent('pageshow', { persisted: true }),
      );
    });

    expect(result.current.ready).toBe(false);
    expect(result.current.preparationAbandoned).toBe(true);

    rerender({ ...params, runtimeConfigLoaded: true });

    expect(result.current.ready).toBe(true);
    expect(result.current.preparationAbandoned).toBe(true);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  it.each<
    [
      string,
      { inWechat?: boolean; inMiniProgram?: boolean },
      Partial<AuthorizationParams>,
    ]
  >([
    ['outside WeChat', { inWechat: false }, {}],
    ['inside a mini program', { inMiniProgram: true }, {}],
    ['when the code flow is disabled', {}, { enabled: false }],
    ['when the app ID is missing', {}, { appId: '' }],
  ])('is ready immediately %s', (_name, environment, overrides) => {
    mockInWechat = environment.inWechat ?? true;
    mockInMiniProgram = environment.inMiniProgram ?? false;
    const { result, params, readiness } = renderAuthorization(overrides);

    expect(readiness[0]).toBe(true);
    expect(result.current.ready).toBe(true);
    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(params.updateWechatCode).not.toHaveBeenCalled();
  });
});
