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
});
