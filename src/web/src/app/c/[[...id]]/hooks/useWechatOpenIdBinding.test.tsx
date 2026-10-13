import React from 'react';
import { act, renderHook } from '@testing-library/react';
import { updateWxcode } from '@/api/user';
import { wechatLogin } from '@/constants/uiConstants';
import { debugWarn } from '@/lib/debugConsole';
import {
  useWechatOpenIdBinding,
  WECHAT_OPENID_BINDING_TIMEOUT_MS,
} from './useWechatOpenIdBinding';

let mockInWechat = true;
let mockInMiniProgram = false;

jest.mock('@/api/user', () => ({ updateWxcode: jest.fn() }));
jest.mock('@/constants/uiConstants', () => ({
  inWechat: () => mockInWechat,
  inMiniProgram: () => mockInMiniProgram,
  wechatLogin: jest.fn(),
}));
jest.mock('@/lib/debugConsole', () => ({ debugWarn: jest.fn() }));

const mockUpdateWxcode = jest.mocked(updateWxcode);
const mockWechatLogin = jest.mocked(wechatLogin);
const mockDebugWarn = jest.mocked(debugWarn);
const REBIND_SESSION_KEY = 'wechat_openid_rebind_attempted';

type HookParams = Parameters<typeof useWechatOpenIdBinding>[0];

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

const defaultParams = (): HookParams => ({
  initialized: true,
  isLoggedIn: true,
  userId: 'learner-a',
  token: 'token-a',
  userProfileLoaded: true,
  openId: '',
  code: 'code-a',
  enabled: true,
  appId: 'wx-app-id',
  refreshUserInfo: jest.fn().mockResolvedValue(undefined),
});

const renderBinding = (overrides: Partial<HookParams> = {}) => {
  const params = { ...defaultParams(), ...overrides };
  const hook = renderHook(props => useWechatOpenIdBinding(props), {
    initialProps: params,
  });
  return { ...hook, params };
};

describe('useWechatOpenIdBinding', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    mockInWechat = true;
    mockInMiniProgram = false;
    sessionStorage.clear();
    window.location.href = `${window.location.origin}/c/course-a`;
    mockUpdateWxcode.mockReturnValue(new Promise(() => {}));
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  it.each<
    [
      string,
      { inWechat?: boolean; inMiniProgram?: boolean },
      Partial<HookParams>,
    ]
  >([
    ['outside WeChat', { inWechat: false }, {}],
    ['inside a mini program', { inMiniProgram: true }, {}],
    ['when the code flow is disabled', {}, { enabled: false }],
    ['for a signed-out learner', {}, { isLoggedIn: false }],
  ])('is ready immediately %s', (_name, environment, overrides) => {
    mockInWechat = environment.inWechat ?? true;
    mockInMiniProgram = environment.inMiniProgram ?? false;

    const { result } = renderBinding(overrides);

    expect(result.current).toBe(true);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('blocks the first render before an OpenID exchange starts', () => {
    const readiness: boolean[] = [];
    const params = defaultParams();
    renderHook(() => {
      const ready = useWechatOpenIdBinding(params);
      readiness.push(ready);
      return ready;
    });

    expect(readiness[0]).toBe(false);
    expect(mockUpdateWxcode).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).toHaveBeenCalledWith({ wxcode: 'code-a' });
  });

  it('waits for the account profile before deciding to redirect', () => {
    const { result, rerender, params } = renderBinding({
      code: '',
      userProfileLoaded: false,
    });

    expect(result.current).toBe(false);
    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(mockUpdateWxcode).not.toHaveBeenCalled();

    rerender({ ...params, userProfileLoaded: true, openId: 'bound-openid' });

    expect(result.current).toBe(true);
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('releases Profile after the account information wait times out', () => {
    const { result } = renderBinding({
      userId: '',
      userProfileLoaded: false,
    });

    act(() => jest.advanceTimersByTime(WECHAT_OPENID_BINDING_TIMEOUT_MS - 1));
    expect(result.current).toBe(false);
    act(() => jest.advanceTimersByTime(1));

    expect(result.current).toBe(true);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it.each(['', 'code-a'])(
    'does not bind a late account after its information wait expired with code %s',
    code => {
      const { result, rerender, params } = renderBinding({
        userId: '',
        userProfileLoaded: false,
        code,
      });
      act(() => jest.advanceTimersByTime(WECHAT_OPENID_BINDING_TIMEOUT_MS));
      expect(result.current).toBe(true);

      rerender({
        ...params,
        userId: 'learner-a',
        userProfileLoaded: true,
        openId: '',
      });

      expect(result.current).toBe(true);
      expect(mockUpdateWxcode).not.toHaveBeenCalled();
      expect(mockWechatLogin).not.toHaveBeenCalled();
      expect(params.refreshUserInfo).not.toHaveBeenCalled();
    },
  );

  it('counts the account information wait toward the same binding deadline', async () => {
    const exchange = deferred<string>();
    mockUpdateWxcode.mockReturnValue(exchange.promise);
    const { result, rerender, params } = renderBinding({
      userId: '',
      userProfileLoaded: false,
    });
    const profileWait = 7_500;
    act(() => jest.advanceTimersByTime(profileWait));
    expect(mockUpdateWxcode).not.toHaveBeenCalled();

    rerender({ ...params, userId: 'learner-a', userProfileLoaded: true });
    expect(mockUpdateWxcode).toHaveBeenCalledTimes(1);
    act(() =>
      jest.advanceTimersByTime(
        WECHAT_OPENID_BINDING_TIMEOUT_MS - profileWait - 1,
      ),
    );
    expect(result.current).toBe(false);
    act(() => jest.advanceTimersByTime(1));

    expect(result.current).toBe(true);
    await act(async () => exchange.reject(new Error('late exchange failure')));
    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(params.refreshUserInfo).not.toHaveBeenCalled();
  });

  it('is ready for a bound account when no OAuth code remains', () => {
    const { result } = renderBinding({ code: '', openId: 'bound-openid' });

    expect(result.current).toBe(true);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('waits for a successful binding and the following user refresh', async () => {
    const exchange = deferred<string>();
    const refresh = deferred<unknown>();
    mockUpdateWxcode.mockReturnValue(exchange.promise);
    const refreshUserInfo = jest.fn().mockReturnValue(refresh.promise);
    const { result, rerender, params } = renderBinding({ refreshUserInfo });

    expect(result.current).toBe(false);
    await act(async () => exchange.resolve('new-openid'));

    expect(refreshUserInfo).toHaveBeenCalledTimes(1);
    expect(result.current).toBe(false);
    rerender({ ...params, openId: 'new-openid' });
    expect(result.current).toBe(false);
    expect(mockUpdateWxcode).toHaveBeenCalledTimes(1);

    await act(async () => refresh.resolve(undefined));

    expect(result.current).toBe(true);
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('skips the refresh when the code resolves to the current OpenID', async () => {
    const exchange = deferred<string>();
    mockUpdateWxcode.mockReturnValue(exchange.promise);
    const { result, params } = renderBinding({ openId: 'bound-openid' });

    await act(async () => exchange.resolve('bound-openid'));

    expect(result.current).toBe(true);
    expect(params.refreshUserInfo).not.toHaveBeenCalled();
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('refreshes the binding when a different WeChat account supplies a code', async () => {
    const exchange = deferred<string>();
    mockUpdateWxcode.mockReturnValue(exchange.promise);
    const { result, params } = renderBinding({ openId: 'previous-openid' });

    await act(async () => exchange.resolve('different-openid'));

    expect(result.current).toBe(true);
    expect(params.refreshUserInfo).toHaveBeenCalledTimes(1);
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('releases Profile after a successful binding even if the user refresh fails', async () => {
    const exchange = deferred<string>();
    const refreshError = new Error('refresh failed');
    mockUpdateWxcode.mockReturnValue(exchange.promise);
    const { result } = renderBinding({
      refreshUserInfo: jest.fn().mockRejectedValue(refreshError),
    });

    await act(async () => exchange.resolve('new-openid'));

    expect(result.current).toBe(true);
    expect(mockDebugWarn).toHaveBeenCalled();
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('requests a fresh code before Profile starts and removes spent OAuth parameters', () => {
    window.location.href = `${window.location.origin}/c/course-a?lessonid=lesson-a&code=spent&state=old#section`;
    const { result } = renderBinding({ code: '', openId: '  ' });

    expect(result.current).toBe(false);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockWechatLogin).toHaveBeenCalledWith({
      appId: 'wx-app-id',
      redirectUrl: `${window.location.origin}/c/course-a?lessonid=lesson-a#section`,
    });
    expect(sessionStorage.getItem(REBIND_SESSION_KEY)).toBe('1');
  });

  it.each(['empty', 'rejected'])(
    'requests one fresh code after an unbound exchange is %s',
    async outcome => {
      const exchange = deferred<string>();
      mockUpdateWxcode.mockReturnValue(exchange.promise);
      const { result, rerender, params } = renderBinding();

      await act(async () => {
        if (outcome === 'empty') {
          exchange.resolve('');
        } else {
          exchange.reject(new Error('exchange failed'));
        }
      });

      expect(result.current).toBe(false);
      expect(mockWechatLogin).toHaveBeenCalledTimes(1);
      rerender({ ...params });
      expect(mockUpdateWxcode).toHaveBeenCalledTimes(1);
      expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    },
  );

  it.each(['empty', 'rejected'])(
    'keeps an existing binding when the exchange is %s',
    async outcome => {
      const exchange = deferred<string>();
      mockUpdateWxcode.mockReturnValue(exchange.promise);
      const { result, params } = renderBinding({ openId: 'bound-openid' });

      await act(async () => {
        if (outcome === 'empty') {
          exchange.resolve('');
        } else {
          exchange.reject(new Error('exchange failed'));
        }
      });

      expect(result.current).toBe(true);
      expect(params.refreshUserInfo).not.toHaveBeenCalled();
      expect(mockWechatLogin).not.toHaveBeenCalled();
    },
  );

  it('does not redirect again after the session already attempted rebinding', () => {
    sessionStorage.setItem(REBIND_SESSION_KEY, '1');

    const { result } = renderBinding({ code: '' });

    expect(result.current).toBe(true);
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('keeps Profile closed while an issued OAuth navigation is pending', () => {
    const { result } = renderBinding({ code: '' });
    expect(result.current).toBe(false);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);

    act(() => jest.advanceTimersByTime(WECHAT_OPENID_BINDING_TIMEOUT_MS));

    expect(result.current).toBe(false);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  it('releases Profile if starting OAuth navigation throws', () => {
    mockWechatLogin.mockImplementationOnce(() => {
      throw new Error('navigation unavailable');
    });

    const { result } = renderBinding({ code: '' });

    expect(result.current).toBe(true);
    expect(mockDebugWarn).toHaveBeenCalled();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  it('releases Profile when no WeChat app ID is configured', () => {
    const { result } = renderBinding({ code: '', appId: '' });

    expect(result.current).toBe(true);
    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(REBIND_SESSION_KEY)).toBeNull();
  });

  it.each(['getItem', 'setItem'] as const)(
    'releases Profile when sessionStorage.%s is unavailable',
    method => {
      jest.spyOn(Storage.prototype, method).mockImplementation(() => {
        throw new Error('storage unavailable');
      });

      const { result } = renderBinding({ code: '' });

      expect(result.current).toBe(true);
      expect(mockWechatLogin).not.toHaveBeenCalled();
    },
  );

  it.each(['empty', 'rejected'])(
    'ignores a late %s exchange after the binding timeout',
    async outcome => {
      const exchange = deferred<string>();
      mockUpdateWxcode.mockReturnValue(exchange.promise);
      const { result } = renderBinding();

      act(() => jest.advanceTimersByTime(WECHAT_OPENID_BINDING_TIMEOUT_MS));
      expect(result.current).toBe(true);

      await act(async () => {
        if (outcome === 'empty') {
          exchange.resolve('');
        } else {
          exchange.reject(new Error('late exchange failure'));
        }
      });

      expect(result.current).toBe(true);
      expect(mockWechatLogin).not.toHaveBeenCalled();
    },
  );

  it('releases Profile when refreshing a successful binding takes too long', async () => {
    const exchange = deferred<string>();
    const refresh = deferred<unknown>();
    mockUpdateWxcode.mockReturnValue(exchange.promise);
    const { result } = renderBinding({
      refreshUserInfo: jest.fn().mockReturnValue(refresh.promise),
    });
    await act(async () => exchange.resolve('new-openid'));
    expect(result.current).toBe(false);

    act(() => jest.advanceTimersByTime(WECHAT_OPENID_BINDING_TIMEOUT_MS));
    expect(result.current).toBe(true);
    await act(async () => refresh.reject(new Error('late refresh failure')));

    expect(result.current).toBe(true);
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('does not refresh the account when an exchange succeeds after the timeout', async () => {
    const exchange = deferred<string>();
    mockUpdateWxcode.mockReturnValue(exchange.promise);
    const { result, params } = renderBinding();
    act(() => jest.advanceTimersByTime(WECHAT_OPENID_BINDING_TIMEOUT_MS));

    await act(async () => exchange.resolve('late-openid'));

    expect(result.current).toBe(true);
    expect(params.refreshUserInfo).not.toHaveBeenCalled();
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it.each<[string, Partial<HookParams>]>([
    ['account', { userId: 'learner-b', token: 'token-b' }],
    ['account with a retained token', { userId: 'learner-b' }],
    ['token', { token: 'replacement-token' }],
    ['code', { code: 'replacement-code' }],
  ])('ignores stale results after the %s changes', async (_name, changes) => {
    const previousExchange = deferred<string>();
    const nextExchange = deferred<string>();
    mockUpdateWxcode
      .mockReturnValueOnce(previousExchange.promise)
      .mockReturnValueOnce(nextExchange.promise);
    const { result, rerender, params } = renderBinding();

    rerender({ ...params, ...changes });
    expect(result.current).toBe(false);
    expect(mockUpdateWxcode).toHaveBeenCalledTimes(2);
    await act(async () => previousExchange.resolve(''));

    expect(result.current).toBe(false);
    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(params.refreshUserInfo).not.toHaveBeenCalled();

    await act(async () => nextExchange.resolve('next-openid'));
    expect(result.current).toBe(true);
    expect(params.refreshUserInfo).toHaveBeenCalledTimes(1);
  });

  it('does not refresh the new account when the old exchange succeeds late', async () => {
    const previousExchange = deferred<string>();
    mockUpdateWxcode.mockReturnValue(previousExchange.promise);
    const { result, rerender, params } = renderBinding();
    rerender({ ...params, userId: 'learner-b', token: 'token-b', code: '' });

    await act(async () => previousExchange.resolve('old-openid'));

    expect(params.refreshUserInfo).not.toHaveBeenCalled();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(result.current).toBe(false);
  });

  it('ignores a failed exchange after the learner signs out', async () => {
    const exchange = deferred<string>();
    mockUpdateWxcode.mockReturnValue(exchange.promise);
    const { result, rerender, params } = renderBinding();
    rerender({ ...params, isLoggedIn: false, token: '', userId: '' });

    expect(result.current).toBe(true);
    await act(async () => exchange.reject(new Error('late exchange failure')));

    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(params.refreshUserInfo).not.toHaveBeenCalled();
  });

  it('ignores exchange results after the route unmounts', async () => {
    const exchange = deferred<string>();
    mockUpdateWxcode.mockReturnValue(exchange.promise);
    const { unmount, params } = renderBinding();
    unmount();

    await act(async () => exchange.resolve(''));

    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(params.refreshUserInfo).not.toHaveBeenCalled();
  });

  it('exchanges one code and releases Profile after StrictMode effect replay', async () => {
    const exchange = deferred<string>();
    mockUpdateWxcode.mockReturnValue(exchange.promise);
    const params = defaultParams();
    const { result } = renderHook(() => useWechatOpenIdBinding(params), {
      wrapper: ({ children }: React.PropsWithChildren) => (
        <React.StrictMode>{children}</React.StrictMode>
      ),
    });

    expect(result.current).toBe(false);
    expect(mockUpdateWxcode).toHaveBeenCalledTimes(1);
    await act(async () => exchange.resolve('new-openid'));

    expect(result.current).toBe(true);
    expect(params.refreshUserInfo).toHaveBeenCalledTimes(1);
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  it('starts OAuth navigation once during StrictMode effect replay', () => {
    const params = { ...defaultParams(), code: '' };
    const { result } = renderHook(() => useWechatOpenIdBinding(params), {
      wrapper: ({ children }: React.PropsWithChildren) => (
        <React.StrictMode>{children}</React.StrictMode>
      ),
    });

    expect(result.current).toBe(false);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
  });
});
