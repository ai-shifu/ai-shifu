import request from '@/lib/request';
import {
  clearLearnerProfile,
  completeProfileOnboarding,
  getLearnerProfile,
  getProfileOnboarding,
  updateLearnerProfile,
} from './user';

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
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

  test('reads, replaces, and clears the canonical learning profile', async () => {
    const savedProfile = {
      learner_profile: '我是一名产品经理。',
      learner_profile_updated_at: '2026-08-03T01:02:03Z',
      has_learner_profile: true,
      max_length: 1000,
    };
    const clearedProfile = {
      ...savedProfile,
      learner_profile: '',
      learner_profile_updated_at: null,
      has_learner_profile: false,
    };
    (request.get as jest.Mock).mockResolvedValue(savedProfile);
    (request.put as jest.Mock).mockResolvedValue(savedProfile);
    (request.delete as jest.Mock).mockResolvedValue(clearedProfile);

    await expect(getLearnerProfile()).resolves.toEqual(savedProfile);
    await expect(updateLearnerProfile('我是一名产品经理。')).resolves.toEqual(
      savedProfile,
    );
    await expect(clearLearnerProfile()).resolves.toEqual(clearedProfile);

    expect(request.get).toHaveBeenCalledWith('/api/user/learner-profile');
    expect(request.put).toHaveBeenCalledWith('/api/user/learner-profile', {
      learner_profile: '我是一名产品经理。',
    });
    expect(request.delete).toHaveBeenCalledWith('/api/user/learner-profile');
  });
});
