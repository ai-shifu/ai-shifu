import request from '@/lib/request';
import { streamProfileOnboardingRuntime } from '@/lib/profileOnboardingSse';
import {
  clearLearnerProfile,
  completeProfileOnboarding,
  createProfileOnboardingSession,
  getLearnerProfile,
  getProfileOnboarding,
  isProfileOnboardingV2Status,
  runProfileOnboardingSession,
  skipProfileOnboarding,
  updateLearnerProfile,
} from './user';
import { LEARNER_PROFILE_CHANGED_EVENT } from '@/lib/learnerProfileEvents';

jest.mock('@/lib/profileOnboardingSse', () => ({
  streamProfileOnboardingRuntime: jest.fn(),
}));

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

  test('ignores an unversioned profile onboarding response', async () => {
    (request.get as jest.Mock).mockResolvedValue({ should_show: true });

    await expect(getProfileOnboarding()).resolves.toEqual({});

    expect(request.get).toHaveBeenCalledWith('/api/user/profile-onboarding');
  });

  test('unwraps the versioned v2 status', async () => {
    (request.get as jest.Mock).mockResolvedValue({
      contract_version: 'profile-v2',
      profile_v2: {
        enabled: true,
        should_show: true,
        presentation: 'blocking',
        legacy_handled: false,
        has_learner_profile: false,
        learner_profile_updated_at: null,
        max_length: 1000,
        config_revision: 9,
        guided_available: true,
      },
    });

    await expect(getProfileOnboarding()).resolves.toEqual({
      contract_version: 'profile-v2',
      enabled: true,
      should_show: true,
      presentation: 'blocking',
      legacy_handled: false,
      has_learner_profile: false,
      learner_profile_updated_at: null,
      max_length: 1000,
      config_revision: 9,
      guided_available: true,
    });
  });

  test('accepts only the explicit complete v2 status contract', () => {
    const v2Status = {
      contract_version: 'profile-v2',
      enabled: true,
      should_show: true,
      presentation: 'blocking',
      legacy_handled: false,
      has_learner_profile: false,
      learner_profile_updated_at: null,
      max_length: 1000,
      config_revision: 9,
      guided_available: true,
    };

    expect(isProfileOnboardingV2Status(v2Status)).toBe(true);
    expect(
      isProfileOnboardingV2Status({
        ...v2Status,
        contract_version: undefined,
      }),
    ).toBe(false);
    expect(
      isProfileOnboardingV2Status({
        ...v2Status,
        guided_available: undefined,
      }),
    ).toBe(false);
  });

  test('submits profile onboarding completion', async () => {
    const response = {
      learner_profile: '我是一名产品经理。',
      learner_profile_updated_at: '2026-08-03T01:02:03Z',
      max_length: 1000,
    };
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
    (request.post as jest.Mock).mockResolvedValue(response);

    await expect(
      completeProfileOnboarding({
        learner_profile: '我是一名产品经理。',
        trigger_source: 'pasted',
      }),
    ).resolves.toEqual(response);

    expect(request.post).toHaveBeenCalledWith(
      '/api/user/profile-onboarding/complete',
      {
        learner_profile: '我是一名产品经理。',
        trigger_source: 'pasted',
      },
    );
    expect(onProfileChanged).toHaveBeenCalledTimes(1);
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('rejects a completion response without the saved learner profile', async () => {
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
    (request.post as jest.Mock).mockResolvedValue({
      completed: true,
    });

    await expect(
      completeProfileOnboarding({
        learner_profile: '需要保留的画像草稿',
        trigger_source: 'pasted',
      }),
    ).rejects.toThrow();

    expect(onProfileChanged).not.toHaveBeenCalled();
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });

  test('skips onboarding and cleans up the active session', async () => {
    (request.post as jest.Mock).mockResolvedValue({ skipped: true });

    await skipProfileOnboarding('session-1');

    expect(request.post).toHaveBeenCalledWith(
      '/api/user/profile-onboarding/skip',
      { session_id: 'session-1' },
    );
  });

  test('creates intent-scoped guided sessions', async () => {
    (request.post as jest.Mock).mockResolvedValue({
      session_id: 'session-1',
    });

    await createProfileOnboardingSession(' zh-CN ');
    await createProfileOnboardingSession('en-US', 'settings');

    expect(request.post).toHaveBeenNthCalledWith(
      1,
      '/api/user/profile-onboarding/session',
      {
        language: 'zh-CN',
        intent: 'onboarding',
      },
    );
    expect(request.post).toHaveBeenNthCalledWith(
      2,
      '/api/user/profile-onboarding/session',
      {
        language: 'en-US',
        intent: 'settings',
      },
    );
  });

  test('sends a stable run identity and expected cursor to the runtime', () => {
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

  test('reads, replaces, and clears the canonical learning profile', async () => {
    const response = {
      learner_profile: '画像',
      learner_profile_updated_at: null,
      max_length: 1000,
    };
    (request.get as jest.Mock).mockResolvedValue(response);
    (request.put as jest.Mock).mockResolvedValue(response);
    (request.delete as jest.Mock).mockResolvedValue({
      ...response,
      learner_profile: '',
    });
    const onProfileChanged = jest.fn();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);

    await expect(getLearnerProfile()).resolves.toEqual(response);
    await expect(updateLearnerProfile('画像')).resolves.toEqual(response);
    await expect(clearLearnerProfile()).resolves.toEqual({
      ...response,
      learner_profile: '',
    });

    expect(request.get).toHaveBeenCalledWith('/api/user/learner-profile');
    expect(request.put).toHaveBeenCalledWith('/api/user/learner-profile', {
      learner_profile: '画像',
    });
    expect(request.delete).toHaveBeenCalledWith('/api/user/learner-profile');
    expect(onProfileChanged).toHaveBeenCalledTimes(2);
    window.removeEventListener(LEARNER_PROFILE_CHANGED_EVENT, onProfileChanged);
  });
});
