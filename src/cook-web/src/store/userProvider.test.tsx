import React from 'react';
import { render, waitFor } from '@testing-library/react';
import { UserProvider } from './userProvider';

const mockInitUser = jest.fn();
const mockUpdateWechatCode = jest.fn();
const mockWechatLogin = jest.fn();
const mockParseUrlParams = jest.fn();
const mockInWechat = jest.fn();
const mockInMiniProgram = jest.fn();

const mockEnvState = {
  runtimeConfigLoaded: true,
  enableWxcode: 'true',
  appId: 'wx-app-id',
};

const mockSystemState = {
  wechatCode: '',
  updateWechatCode: (...args: unknown[]) => mockUpdateWechatCode(...args),
};

const mockUserState = {
  initUser: (...args: unknown[]) => mockInitUser(...args),
  isInitialized: false,
};

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
  useSystemStore: (selector: (state: typeof mockSystemState) => unknown) =>
    selector(mockSystemState),
}));

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (selector: (state: typeof mockUserState) => unknown) =>
    selector(mockUserState),
}));

jest.mock('@/c-utils/urlUtils', () => ({
  parseUrlParams: () => mockParseUrlParams(),
}));

jest.mock('@/c-constants/uiConstants', () => ({
  inWechat: () => mockInWechat(),
  inMiniProgram: () => mockInMiniProgram(),
  wechatLogin: (...args: unknown[]) => mockWechatLogin(...args),
}));

describe('UserProvider', () => {
  beforeEach(() => {
    mockInitUser.mockReset();
    mockUpdateWechatCode.mockReset();
    mockWechatLogin.mockReset();
    mockParseUrlParams.mockReset();
    mockInWechat.mockReset();
    mockInMiniProgram.mockReset();

    mockEnvState.runtimeConfigLoaded = true;
    mockEnvState.enableWxcode = 'true';
    mockEnvState.appId = 'wx-app-id';

    mockSystemState.wechatCode = '';
    mockUserState.isInitialized = false;

    Object.assign(window.location, {
      href: 'https://app.ai-shifu.cn/admin',
      pathname: '/admin',
      search: '',
    });
  });

  test('redirects admin route to WeChat OAuth before init when wxcode is missing', async () => {
    mockInWechat.mockReturnValue(true);
    mockInMiniProgram.mockReturnValue(false);
    mockParseUrlParams.mockReturnValue({});

    render(
      <UserProvider>
        <div aria-label='content' />
      </UserProvider>,
    );

    await waitFor(() => {
      expect(mockWechatLogin).toHaveBeenCalledWith({ appId: 'wx-app-id' });
    });
    expect(mockInitUser).not.toHaveBeenCalled();
    expect(mockUpdateWechatCode).not.toHaveBeenCalled();
  });

  test('hydrates wxcode from admin url and continues init', async () => {
    mockInWechat.mockReturnValue(true);
    mockInMiniProgram.mockReturnValue(false);
    mockParseUrlParams.mockReturnValue({ code: 'wx-code-1' });

    render(
      <UserProvider>
        <div aria-label='content' />
      </UserProvider>,
    );

    await waitFor(() => {
      expect(mockUpdateWechatCode).toHaveBeenCalledWith('wx-code-1');
      expect(mockInitUser).toHaveBeenCalledTimes(1);
    });
    expect(mockWechatLogin).not.toHaveBeenCalled();
  });

  test('continues init on admin route when wxcode is enabled but appId is missing', async () => {
    mockEnvState.appId = '';
    mockInWechat.mockReturnValue(true);
    mockInMiniProgram.mockReturnValue(false);
    mockParseUrlParams.mockReturnValue({});

    render(
      <UserProvider>
        <div aria-label='content' />
      </UserProvider>,
    );

    await waitFor(() => {
      expect(mockInitUser).toHaveBeenCalledTimes(1);
    });
    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(mockUpdateWechatCode).not.toHaveBeenCalled();
  });

  test('keeps course-route wxcode waiting in the shared provider without triggering OAuth redirect', () => {
    mockInWechat.mockReturnValue(true);
    mockInMiniProgram.mockReturnValue(false);
    mockParseUrlParams.mockReturnValue({});
    Object.assign(window.location, {
      href: 'https://app.ai-shifu.cn/c/test-course',
      pathname: '/c/test-course',
      search: '',
    });

    render(
      <UserProvider>
        <div aria-label='content' />
      </UserProvider>,
    );

    expect(mockInitUser).not.toHaveBeenCalled();
    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(mockUpdateWechatCode).not.toHaveBeenCalled();
  });
});
