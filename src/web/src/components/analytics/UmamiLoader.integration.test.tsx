import { act, render, waitFor } from '@testing-library/react';
import { UmamiLoader } from './UmamiLoader';
import { identifyUmamiUser, tracking } from '@/lib/tracking';
import { useUserStore } from '@/store/useUserStore';

const mockGetUserInfo = jest.fn();
const mockRegisterTmp = jest.fn();
let mockPathname = '/c/private-course';
let mockWebsiteId = 'website-id';
let mockTokenState = { token: 'excluded-token', faked: false };

jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
}));

jest.mock('@/store', () => ({
  useEnvStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      umamiScriptSrc: 'https://analytics.example.test/script.js',
      umamiWebsiteId: mockWebsiteId,
    }),
  useUserStore: jest.requireActual('@/store/useUserStore').useUserStore,
}));

jest.mock('@/api/user', () => ({
  getUserInfo: (...args: unknown[]) => mockGetUserInfo(...args),
  registerTmp: (...args: unknown[]) => mockRegisterTmp(...args),
}));

jest.mock('@/lib/shifu/storeUtil', () => ({
  tokenTool: {
    get: () => ({ ...mockTokenState }),
    set: (value: typeof mockTokenState) => {
      mockTokenState = value;
    },
    remove: () => {
      mockTokenState = { token: '', faked: false };
    },
  },
}));

jest.mock('@/lib/common', () => ({ genUuid: () => 'guest-temp-id' }));
jest.mock('@/lib/debugConsole', () => ({
  debugError: jest.fn(),
  debugInfo: jest.fn(),
  debugWarn: jest.fn(),
}));
jest.mock('@/lib/urlUtils', () => ({
  removeParamFromUrl: (url: string) => url,
}));
jest.mock('@/lib/google-oauth-session', () => ({
  clearGoogleOAuthSession: jest.fn(),
}));
jest.mock('@/i18n', () => ({
  __esModule: true,
  default: { changeLanguage: jest.fn() },
}));

type Payload = Record<string, unknown>;

const installUmami = (identify = jest.fn().mockResolvedValue(undefined)) => {
  const delivered: Payload[] = [];
  const track = jest.fn((transform: (payload: Payload) => Payload) => {
    delivered.push(
      transform({
        url: 'https://app.example.test/c/private-course?token=secret',
        referrer: 'https://external.example.test/private?token=secret',
        title: 'Private title',
      }),
    );
  });
  (window as any).umami = { identify, track };
  return { delivered, identify, track };
};

const createDeferred = () => {
  let resolve = () => {};
  const promise = new Promise<void>(resolvePromise => {
    resolve = resolvePromise;
  });
  return { promise, resolve: () => resolve() };
};

describe('UmamiLoader eligibility integration', () => {
  beforeEach(() => {
    mockGetUserInfo.mockReset();
    mockRegisterTmp.mockReset();
    mockPathname = '/c/private-course';
    mockWebsiteId = 'website-id';
    mockTokenState = { token: 'excluded-token', faked: false };
    useUserStore.setState({
      userInfo: { user_id: 'excluded-user', analytics_enabled: false },
      isInitialized: true,
      isLoggedIn: true,
      isGuest: false,
      _initializingPromise: null,
    });
    identifyUmamiUser({ user_id: 'excluded-user', analytics_enabled: false });
    Object.assign(window.location, {
      href: 'http://localhost:3000/c/private-course?token=secret#private',
      pathname: mockPathname,
      search: '?token=secret',
      hash: '#private',
    });
    document.getElementById('umami-analytics-script')?.remove();
    delete (window as any).umami;
  });

  afterEach(() => {
    document.getElementById('umami-analytics-script')?.remove();
    delete (window as any).umami;
  });

  it('owns one sanitized same-path pageview when logout restores an eligible guest', async () => {
    const { delivered, identify } = installUmami();
    const { rerender } = render(<UmamiLoader />);
    await tracking('excluded_action');
    expect(delivered).toEqual([]);
    expect(identify).not.toHaveBeenCalled();
    mockRegisterTmp.mockResolvedValueOnce({
      token: 'guest-token',
      userInfo: { user_id: 'guest-user', analytics_enabled: true },
    });

    await act(async () => useUserStore.getState().logout(false));

    await waitFor(() => expect(delivered).toHaveLength(1));
    expect(useUserStore.getState().userInfo).toBeNull();
    expect(identify).toHaveBeenCalledTimes(1);
    expect(identify).toHaveBeenCalledWith('guest-user');
    expect(delivered[0]).toMatchObject({
      url: '/c/:dynamic',
      referrer: undefined,
      title: undefined,
    });
    expect(delivered[0].name).toBeUndefined();
    expect(JSON.stringify(delivered)).not.toContain('secret');

    rerender(<UmamiLoader />);
    mockWebsiteId = 'updated-website-id';
    rerender(<UmamiLoader />);
    mockGetUserInfo.mockResolvedValueOnce({
      user_id: 'guest-user',
      analytics_enabled: true,
      language: 'en-US',
    });
    await act(async () => useUserStore.getState().refreshUserInfo());
    expect(delivered).toHaveLength(1);
    expect(identify).toHaveBeenCalledTimes(1);
  });

  it('queues one current pageview when the same user becomes eligible before the script is ready', async () => {
    const { rerender } = render(<UmamiLoader />);
    mockGetUserInfo.mockResolvedValueOnce({
      user_id: 'excluded-user',
      analytics_enabled: true,
      language: 'en-US',
    });

    await act(async () => useUserStore.getState().refreshUserInfo());

    const { delivered, identify } = installUmami();
    await act(async () => {
      document
        .getElementById('umami-analytics-script')
        ?.dispatchEvent(new Event('load'));
    });
    expect(identify).toHaveBeenCalledWith('excluded-user');
    expect(delivered).toEqual([
      expect.objectContaining({ url: '/c/:dynamic', referrer: undefined }),
    ]);
    rerender(<UmamiLoader />);
    expect(delivered).toHaveLength(1);
  });

  it('keeps the resumed pageview queued when identify fails and sends it once after retry', async () => {
    const identify = jest
      .fn()
      .mockRejectedValueOnce(new Error('identify unavailable'))
      .mockResolvedValue(undefined);
    const { delivered } = installUmami(identify);
    render(<UmamiLoader />);
    await act(async () =>
      identifyUmamiUser({ user_id: 'allowed-user', analytics_enabled: true }),
    );
    expect(identify).toHaveBeenCalledTimes(1);
    expect(delivered).toEqual([]);

    await act(async () => {
      document
        .getElementById('umami-analytics-script')
        ?.dispatchEvent(new Event('load'));
    });

    expect(identify).toHaveBeenCalledTimes(2);
    expect(delivered).toEqual([
      expect.objectContaining({ url: '/c/:dynamic', referrer: undefined }),
    ]);
  });

  it('drops a resumed pageview on re-exclusion and ignores a late identify before a fresh guest resumes', async () => {
    const oldIdentify = createDeferred();
    const guestIdentify = createDeferred();
    const identify = jest
      .fn()
      .mockReturnValueOnce(oldIdentify.promise)
      .mockReturnValueOnce(guestIdentify.promise);
    const { delivered } = installUmami(identify);
    const { rerender } = render(<UmamiLoader />);

    await act(async () =>
      identifyUmamiUser({
        user_id: 'previous-allowed-user',
        analytics_enabled: true,
      }),
    );
    act(() =>
      identifyUmamiUser({ user_id: 'excluded-user', analytics_enabled: false }),
    );
    await tracking('excluded_action');
    mockPathname = '/admin/billing';
    rerender(<UmamiLoader />);
    await act(async () => oldIdentify.resolve());
    expect(delivered).toEqual([]);
    expect(identify).toHaveBeenCalledTimes(1);

    await act(async () =>
      identifyUmamiUser({ user_id: 'guest-user', analytics_enabled: true }),
    );
    expect(identify).toHaveBeenCalledTimes(2);
    expect(delivered).toEqual([]);
    await act(async () => guestIdentify.resolve());

    expect(delivered).toEqual([
      expect.objectContaining({ url: '/admin/billing', referrer: undefined }),
    ]);
    expect(delivered[0].name).toBeUndefined();
  });
});
