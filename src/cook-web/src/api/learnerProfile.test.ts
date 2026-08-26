import request from '@/lib/request';
import { streamProfileOnboardingRuntime } from '@/lib/profileOnboardingSse';
import {
  completeGuidedProfileOnboarding,
  createProfileOnboardingSession,
  getLearnerProfile,
  getProfileOnboarding,
  isProfileOnboardingStatus,
  optimizeLearnerProfile,
  runProfileOnboardingSession,
  skipGuidedProfileOnboarding,
  updateLearnerProfile,
} from './learnerProfile';

jest.mock('@/lib/profileOnboardingSse', () => ({
  streamProfileOnboardingRuntime: jest.fn(),
}));

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
  },
}));

const onboardingStatus = {
  enabled: true,
  should_show: true,
  presentation: 'blocking' as const,
  guided_available: true,
  handled: false,
  has_learner_profile: false,
  learner_profile: '',
  learner_profile_updated_at: null,
  max_length: 1000,
  config_revision: 9,
};

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

  test('keeps the passive onboarding status GET silent', async () => {
    (request.get as jest.Mock).mockResolvedValue(onboardingStatus);

    await expect(getProfileOnboarding()).resolves.toEqual(onboardingStatus);
    expect(request.get).toHaveBeenCalledWith('/api/user/profile-onboarding', {
      skipErrorToast: true,
    });
    expect(isProfileOnboardingStatus(onboardingStatus)).toBe(true);
  });

  test('rejects the retired wrapped contract', () => {
    expect(
      isProfileOnboardingStatus({
        onboarding_status: onboardingStatus,
      }),
    ).toBe(false);
  });

  test('rejects incomplete or unknown status objects', () => {
    expect(
      isProfileOnboardingStatus({
        ...onboardingStatus,
        guided_available: undefined,
      }),
    ).toBe(false);
    expect(
      isProfileOnboardingStatus({
        ...onboardingStatus,
        presentation: 'unexpected',
      }),
    ).toBe(false);
  });

  test('submits and validates guided or settings completion responses', async () => {
    const response = {
      learner_profile: '我是一名产品经理。',
      learner_profile_updated_at: '2026-08-03T01:02:03Z',
      has_learner_profile: true,
      max_length: 1000,
    };
    (request.post as jest.Mock).mockResolvedValue(response);

    await expect(
      completeGuidedProfileOnboarding({
        learner_profile: '我是一名产品经理。',
        trigger_source: 'guided',
        session_id: 'session-1',
      }),
    ).resolves.toEqual(response);

    expect(request.post).toHaveBeenCalledWith(
      '/api/user/profile-onboarding/complete',
      {
        learner_profile: '我是一名产品经理。',
        trigger_source: 'guided',
        session_id: 'session-1',
      },
    );
  });

  test('normalizes profile whitespace before guided completion', async () => {
    const response = {
      learner_profile: '我是一名产品经理。',
      learner_profile_updated_at: '2026-08-03T01:02:03Z',
      has_learner_profile: true,
      max_length: 1000,
    };
    (request.post as jest.Mock).mockResolvedValue(response);

    await expect(
      completeGuidedProfileOnboarding({
        learner_profile: '\n  我是一名产品经理。  \n',
        trigger_source: 'settings',
        session_id: 'session-whitespace',
      }),
    ).resolves.toEqual(response);

    expect(request.post).toHaveBeenCalledWith(
      '/api/user/profile-onboarding/complete',
      {
        learner_profile: '我是一名产品经理。',
        trigger_source: 'settings',
        session_id: 'session-whitespace',
      },
    );
  });

  test('trims an optional nickname and accepts the canonical nickname returned by the backend', async () => {
    const response = {
      learner_profile: '我是一名产品经理。',
      learner_profile_updated_at: '2026-08-03T01:02:03Z',
      has_learner_profile: true,
      max_length: 1000,
      nickname: '',
      nickname_max_length: 64,
    };
    (request.post as jest.Mock).mockResolvedValue(response);

    await expect(
      completeGuidedProfileOnboarding({
        learner_profile: '我是一名产品经理。',
        trigger_source: 'guided',
        session_id: 'session-nickname',
        nickname: '  user@example.com  ',
      }),
    ).resolves.toEqual(response);

    expect(request.post).toHaveBeenCalledWith(
      '/api/user/profile-onboarding/complete',
      {
        learner_profile: '我是一名产品经理。',
        trigger_source: 'guided',
        session_id: 'session-nickname',
        nickname: 'user@example.com',
      },
    );
  });

  test('rejects a completion response with an invalid nickname type', async () => {
    (request.post as jest.Mock).mockResolvedValue({
      learner_profile: '我是一名产品经理。',
      learner_profile_updated_at: '2026-08-03T01:02:03Z',
      has_learner_profile: true,
      max_length: 1000,
      nickname: 123,
      nickname_max_length: 64,
    });

    await expect(
      completeGuidedProfileOnboarding({
        learner_profile: '我是一名产品经理。',
        trigger_source: 'settings',
        nickname: '小明',
      }),
    ).rejects.toThrow();
  });

  test('rejects a completion response that did not save the expected profile', async () => {
    (request.post as jest.Mock).mockResolvedValue({ completed: true });

    await expect(
      completeGuidedProfileOnboarding({
        learner_profile: '需要保留的画像草稿',
        trigger_source: 'settings',
      }),
    ).rejects.toThrow();
  });

  test('creates and skips intent-scoped guided sessions', async () => {
    (request.post as jest.Mock).mockResolvedValue({ session_id: 'session-1' });

    await createProfileOnboardingSession(' zh-CN ');
    await createProfileOnboardingSession('fr-FR', 'settings');
    await skipGuidedProfileOnboarding('session-1');
    await skipGuidedProfileOnboarding();

    expect(request.post).toHaveBeenNthCalledWith(
      1,
      '/api/user/profile-onboarding/session',
      { language: 'zh-CN', intent: 'onboarding' },
    );
    expect(request.post).toHaveBeenNthCalledWith(
      2,
      '/api/user/profile-onboarding/session',
      { language: 'fr-FR', intent: 'settings' },
    );
    expect(request.post).toHaveBeenNthCalledWith(
      3,
      '/api/user/profile-onboarding/skip',
      { session_id: 'session-1' },
    );
    expect(request.post).toHaveBeenNthCalledWith(
      4,
      '/api/user/profile-onboarding/skip',
      {},
    );
  });

  test('sends a stable run identity and cursor through shared SSE transport', () => {
    const onMessage = jest.fn();
    const onError = jest.fn();

    runProfileOnboardingSession({
      sessionId: 'session/with-special-character',
      expectedBlockIndex: 3,
      requestId: 'profile-onboarding-run-2',
      userInput: { profile_goal: ['学会 AI'] },
      language: 'zh-CN',
      onMessage,
      onError,
    });

    expect(streamProfileOnboardingRuntime).toHaveBeenCalledWith({
      path: '/api/user/profile-onboarding/session/session%2Fwith-special-character/run',
      payload: {
        expected_block_index: 3,
        request_id: 'profile-onboarding-run-2',
        user_input: { profile_goal: ['学会 AI'] },
      },
      language: 'zh-CN',
      onMessage,
      onError,
    });
  });
});
