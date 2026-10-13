import React from 'react';
import { act, renderHook } from '@testing-library/react';
import { wechatLogin } from '@/constants/uiConstants';
import { debugWarn } from '@/lib/debugConsole';
import { useCourseWechatAuthorizationState } from './useCourseWechatAuthorization';

let mockInWechat = true;
let mockInMiniProgram = false;

jest.mock('@/constants/uiConstants', () => ({
  inWechat: () => mockInWechat,
  inMiniProgram: () => mockInMiniProgram,
  wechatLogin: jest.fn(),
}));
jest.mock('@/lib/debugConsole', () => ({ debugWarn: jest.fn() }));

const mockWechatLogin = jest.mocked(wechatLogin);
const mockDebugWarn = jest.mocked(debugWarn);
type AuthorizationParams = Parameters<
  typeof useCourseWechatAuthorizationState
>[0];

const defaultParams = (): AuthorizationParams => ({
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

  it('releases a synchronous navigation failure without retrying that app ID', () => {
    mockWechatLogin.mockImplementation(() => {
      throw new Error('navigation unavailable');
    });
    const { result, rerender, params, readiness } = renderAuthorization();

    expect(readiness[0]).toBe(false);
    expect(result.current.ready).toBe(true);
    expect(mockDebugWarn).toHaveBeenCalled();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);

    rerender({ ...params, wechatCode: 'stale-code' });
    act(() => jest.advanceTimersByTime(60_000));

    expect(result.current.ready).toBe(true);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
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
