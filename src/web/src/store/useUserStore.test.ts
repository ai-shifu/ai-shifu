import { useUserStore } from './useUserStore';

const mockGetUserInfo = jest.fn();
const mockRegisterTmp = jest.fn();
const mockIdentifyUmamiUser = jest.fn();
const mockChangeLanguage = jest.fn();

let mockTokenState = {
  token: '',
  faked: false,
};

jest.mock('@/c-api/user', () => ({
  getUserInfo: (...args: unknown[]) => mockGetUserInfo(...args),
  registerTmp: (...args: unknown[]) => mockRegisterTmp(...args),
}));

jest.mock('@/c-service/storeUtil', () => ({
  tokenTool: {
    get: jest.fn(() => ({ ...mockTokenState })),
    set: jest.fn(({ token, faked }: { token: string; faked: boolean }) => {
      mockTokenState = { token, faked };
    }),
    remove: jest.fn(() => {
      mockTokenState = { token: '', faked: false };
    }),
  },
}));

jest.mock('@/c-utils/common', () => ({
  genUuid: jest.fn(() => 'guest-temp-id'),
}));

jest.mock('@/c-utils/debugConsole', () => ({
  debugError: jest.fn(),
  debugInfo: jest.fn(),
  debugWarn: jest.fn(),
}));

jest.mock('@/c-utils/urlUtils', () => ({
  removeParamFromUrl: jest.fn((url: string) => url),
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    changeLanguage: (...args: unknown[]) => mockChangeLanguage(...args),
  },
}));

jest.mock('@/lib/google-oauth-session', () => ({
  clearGoogleOAuthSession: jest.fn(),
}));

jest.mock('@/c-common/tools/tracking', () => ({
  identifyUmamiUser: (...args: unknown[]) => mockIdentifyUmamiUser(...args),
}));

describe('useUserStore.initUser', () => {
  beforeEach(() => {
    mockTokenState = {
      token: '',
      faked: false,
    };
    mockGetUserInfo.mockReset();
    mockRegisterTmp.mockReset();
    mockIdentifyUmamiUser.mockReset();
    mockChangeLanguage.mockReset();
    window.localStorage.clear();
    window.sessionStorage.clear();
    useUserStore.setState({
      userInfo: null,
      isGuest: false,
      isLoggedIn: false,
      isInitialized: false,
      _initializingPromise: null,
    });
  });

  test('falls back to guest state when guest bootstrap fails before any token exists', async () => {
    mockRegisterTmp.mockRejectedValueOnce(new Error('guest bootstrap failed'));

    await useUserStore.getState().initUser();

    expect(mockRegisterTmp).toHaveBeenCalledWith({ temp_id: 'guest-temp-id' });
    expect(useUserStore.getState()).toMatchObject({
      userInfo: null,
      isGuest: true,
      isLoggedIn: false,
      isInitialized: true,
      _initializingPromise: null,
    });
    expect(mockTokenState).toEqual({
      token: '',
      faked: false,
    });
    expect(mockIdentifyUmamiUser).not.toHaveBeenCalled();
    expect(mockChangeLanguage).not.toHaveBeenCalled();
  });

  test('recovers a missing profile quietly after initialization preserves a signed-in session', async () => {
    mockTokenState = { token: 'owner-token', faked: false };
    mockGetUserInfo.mockRejectedValueOnce(new Error('Temporary failure'));
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

    try {
      await useUserStore.getState().initUser();
    } finally {
      warnSpy.mockRestore();
    }

    expect(useUserStore.getState()).toMatchObject({
      userInfo: null,
      isInitialized: true,
      isLoggedIn: true,
      isGuest: false,
    });
    const profile = {
      user_id: 'owner-id',
      user_bid: 'owner-id',
      email: 'owner@example.com',
      language: 'zh-CN',
    };
    mockGetUserInfo.mockResolvedValueOnce(profile);

    await useUserStore.getState().refreshUserInfo({ skipErrorToast: true });

    expect(mockGetUserInfo).toHaveBeenLastCalledWith({ skipErrorToast: true });
    expect(useUserStore.getState().userInfo).toEqual(profile);
    expect(mockTokenState).toEqual({ token: 'owner-token', faked: false });
    expect(mockRegisterTmp).not.toHaveBeenCalled();
  });

  test('ignores a refresh response after the signed-in account changes', async () => {
    let resolveRefresh: (value: {
      user_id: string;
      name: string;
      language: string;
    }) => void = () => undefined;
    mockTokenState = {
      token: 'token-a',
      faked: false,
    };
    useUserStore.setState({
      userInfo: {
        user_id: 'user-a',
        name: 'Account A',
        language: 'zh-CN',
      },
    });
    mockGetUserInfo.mockReturnValueOnce(
      new Promise(resolve => {
        resolveRefresh = resolve;
      }),
    );

    const pendingRefresh = useUserStore.getState().refreshUserInfo();
    mockTokenState = {
      token: 'token-b',
      faked: false,
    };
    useUserStore.setState({
      userInfo: {
        user_id: 'user-b',
        name: 'Account B',
        language: 'en-US',
      },
    });
    resolveRefresh({
      user_id: 'user-a',
      name: 'Late Account A',
      language: 'zh-CN',
    });
    await pendingRefresh;

    expect(useUserStore.getState().userInfo).toMatchObject({
      user_id: 'user-b',
      name: 'Account B',
    });
    expect(mockIdentifyUmamiUser).not.toHaveBeenCalled();
    expect(mockChangeLanguage).not.toHaveBeenCalled();
  });

  test('ignores a refresh failure after the signed-in account changes', async () => {
    let rejectRefresh: (reason: Error) => void = () => undefined;
    mockTokenState = {
      token: 'token-a',
      faked: false,
    };
    mockGetUserInfo.mockReturnValueOnce(
      new Promise((_resolve, reject) => {
        rejectRefresh = reject;
      }),
    );

    const pendingRefresh = useUserStore.getState().refreshUserInfo();
    mockTokenState = {
      token: 'token-b',
      faked: false,
    };
    rejectRefresh(new Error('Late Account A refresh failed'));

    await expect(pendingRefresh).resolves.toBeUndefined();
  });

  test('ignores a refresh response after user identity changes with the same token', async () => {
    let resolveRefresh: (value: {
      user_id: string;
      name: string;
      language: string;
    }) => void = () => undefined;
    mockTokenState = {
      token: 'shared-token',
      faked: false,
    };
    useUserStore.setState({
      userInfo: {
        user_id: 'user-a',
        name: 'Account A',
        language: 'zh-CN',
      },
    });
    mockGetUserInfo.mockReturnValueOnce(
      new Promise(resolve => {
        resolveRefresh = resolve;
      }),
    );

    const pendingRefresh = useUserStore.getState().refreshUserInfo();
    useUserStore.setState({
      userInfo: {
        user_id: 'user-b',
        name: 'Account B',
        language: 'en-US',
      },
    });
    resolveRefresh({
      user_id: 'user-a',
      name: 'Late Account A',
      language: 'zh-CN',
    });
    await pendingRefresh;

    expect(useUserStore.getState().userInfo).toMatchObject({
      user_id: 'user-b',
      name: 'Account B',
    });
    expect(mockIdentifyUmamiUser).not.toHaveBeenCalled();
    expect(mockChangeLanguage).not.toHaveBeenCalled();
  });
});

test('clears private assistant drafts when logging out even if guest bootstrap fails', async () => {
  window.sessionStorage.setItem(
    'profile-onboarding-paste-draft:active-user:profile-v2',
    'profile-onboarding-paste-draft:profile-v2:account',
  );
  window.sessionStorage.setItem(
    'profile-onboarding-paste-draft:profile-v2:account',
    'Private pasted profile',
  );
  mockRegisterTmp.mockRejectedValue(new Error('Guest unavailable'));
  await useUserStore
    .getState()
    .logout(false)
    .catch(() => undefined);
  expect(
    window.sessionStorage.getItem(
      'profile-onboarding-paste-draft:profile-v2:account',
    ),
  ).toBeNull();
  expect(
    window.sessionStorage.getItem(
      'profile-onboarding-paste-draft:active-user:profile-v2',
    ),
  ).toBeNull();
});
