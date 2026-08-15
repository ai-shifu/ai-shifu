import request from '@/lib/request';
import {
  getLearnerProfile,
  optimizeLearnerProfile,
  updateLearnerProfile,
} from './learnerProfile';

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
  },
}));

describe('learner profile api', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('reads and replaces the canonical learner profile', async () => {
    const savedProfile = {
      learner_profile: '我是一名产品经理。',
      learner_profile_updated_at: '2026-08-03T01:02:03Z',
      has_learner_profile: true,
      max_length: 1000,
      nickname: '小明',
      nickname_max_length: 64,
    };
    (request.get as jest.Mock).mockResolvedValue(savedProfile);
    (request.put as jest.Mock).mockResolvedValue(savedProfile);

    await expect(getLearnerProfile()).resolves.toEqual(savedProfile);
    await expect(
      updateLearnerProfile('我是一名产品经理。', '小明'),
    ).resolves.toEqual(savedProfile);

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
  });

  test('preserves the nickname when an older caller only updates the profile', async () => {
    await updateLearnerProfile('Only the introduction changes');

    expect(request.put).toHaveBeenCalledWith(
      '/api/user/learner-profile',
      { learner_profile: 'Only the introduction changes' },
      { skipErrorToast: true },
    );
  });

  test('requests an optimized draft without showing a global error toast', async () => {
    const optimized = {
      optimized_learner_profile: 'A clearer learner introduction',
    };
    (request.post as jest.Mock).mockResolvedValue(optimized);

    await expect(
      optimizeLearnerProfile('My learner introduction'),
    ).resolves.toEqual(optimized);

    expect(request.post).toHaveBeenCalledWith(
      '/api/user/learner-profile/optimize',
      { learner_profile: 'My learner introduction' },
      { skipErrorToast: true },
    );
  });
});
