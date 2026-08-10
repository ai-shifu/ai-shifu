import request from '@/lib/request';
import { completeProfileOnboarding, getProfileOnboarding } from './user';

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

jest.mock('@/c-store/useSystemStore', () => ({
  useSystemStore: {
    getState: () => ({
      channel: 'web',
      language: 'zh-CN',
      wechatCode: '',
    }),
  },
}));

describe('user profile onboarding c-api', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('fetches profile onboarding status', async () => {
    (request.get as jest.Mock).mockResolvedValue({ should_show: true });

    await expect(getProfileOnboarding()).resolves.toEqual({
      should_show: true,
    });

    expect(request.get).toHaveBeenCalledWith('/api/user/profile-onboarding');
  });

  test('submits profile onboarding completion', async () => {
    (request.post as jest.Mock).mockResolvedValue({ completed: true });

    await expect(
      completeProfileOnboarding({
        skipped: false,
        variables: {
          sys_user_nickname: '小明',
        },
      }),
    ).resolves.toEqual({ completed: true });

    expect(request.post).toHaveBeenCalledWith(
      '/api/user/profile-onboarding/complete',
      {
        skipped: false,
        variables: {
          sys_user_nickname: '小明',
        },
      },
    );
  });
});
