import request from '@/lib/request';
import {
  clearLearnerProfile,
  getLearnerProfile,
  updateLearnerProfile,
} from './learnerProfile';

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  },
}));

describe('learner profile api', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('reads, replaces, and clears the canonical learner profile', async () => {
    const savedProfile = {
      learner_profile: '我是一名产品经理。',
      learner_profile_updated_at: '2026-08-03T01:02:03Z',
      has_learner_profile: true,
      max_length: 1000,
      nickname: '小明',
      nickname_max_length: 64,
    };
    const clearedProfile = {
      ...savedProfile,
      learner_profile: '',
      learner_profile_updated_at: null,
      has_learner_profile: false,
      legacy_profile_values: {
        sys_user_nickname: '小明',
        sys_user_background: '产品经理',
        sys_user_style: '简洁',
      },
    };
    (request.get as jest.Mock).mockResolvedValue(savedProfile);
    (request.put as jest.Mock).mockResolvedValue(savedProfile);
    (request.delete as jest.Mock).mockResolvedValue(clearedProfile);

    await expect(getLearnerProfile()).resolves.toEqual(savedProfile);
    await expect(
      updateLearnerProfile('我是一名产品经理。', '小明'),
    ).resolves.toEqual(savedProfile);
    await expect(clearLearnerProfile()).resolves.toEqual(clearedProfile);

    expect(request.get).toHaveBeenCalledWith('/api/user/learner-profile', {
      skipErrorToast: true,
    });
    expect(request.put).toHaveBeenCalledWith(
      '/api/user/learner-profile',
      {
        learner_profile: '我是一名产品经理。',
        nickname: '小明',
      },
      { skipErrorToast: true },
    );
    expect(request.delete).toHaveBeenCalledWith('/api/user/learner-profile', {
      skipErrorToast: true,
    });
  });

  test('preserves the nickname when an older caller only updates the profile', async () => {
    await updateLearnerProfile('Only the introduction changes');

    expect(request.put).toHaveBeenCalledWith(
      '/api/user/learner-profile',
      { learner_profile: 'Only the introduction changes' },
      { skipErrorToast: true },
    );
  });
});
