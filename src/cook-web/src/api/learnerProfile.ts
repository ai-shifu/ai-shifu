import request from '@/lib/request';
import {
  streamProfileOnboardingRuntime,
  type ProfileOnboardingStreamEvent,
} from '@/lib/profileOnboardingSse';

export type LearnerProfile = {
  learner_profile: string;
  learner_profile_updated_at: string | null;
  has_learner_profile: boolean;
  max_length: number;
  nickname?: string;
  nickname_max_length?: number;
  legacy_profile_values?: Partial<
    Record<
      'sys_user_nickname' | 'sys_user_background' | 'sys_user_style',
      string
    >
  >;
};

export type OptimizedLearnerProfile = {
  optimized_learner_profile: string;
};

export type ProfileOnboardingPresentation =
  | 'blocking'
  | 'non_blocking'
  | 'hidden';

export type ProfileOnboardingSessionIntent = 'onboarding' | 'settings';

export const PROFILE_ONBOARDING_CONTRACT_VERSION = 'profile-v2' as const;

export type ProfileOnboardingV2Status = LearnerProfile & {
  contract_version: typeof PROFILE_ONBOARDING_CONTRACT_VERSION;
  enabled: boolean;
  guided_available: boolean;
  should_show: boolean;
  presentation: ProfileOnboardingPresentation;
  handled: boolean;
  legacy_handled: boolean;
  config_revision?: number;
};

export type ProfileOnboardingStatus = {
  enabled: boolean;
  should_show: boolean;
  markdownflow: string;
  allowed_variable_keys: string[];
  current_values: Record<string, string>;
  contract_version?: typeof PROFILE_ONBOARDING_CONTRACT_VERSION;
  profile_v2?: Omit<ProfileOnboardingV2Status, 'contract_version'>;
};

export type ProfileOnboardingV2AdapterStatus =
  Partial<ProfileOnboardingV2Status>;

export type CompleteProfileOnboardingPayload = {
  learner_profile: string;
  trigger_source: 'guided' | 'settings';
  session_id?: string;
};

export type ProfileOnboardingSession = {
  session_id: string;
  block_index: number;
  block_count: number;
  profile_draft_block_index: number;
  done: boolean;
  expires_in: number;
};

export type ProfileOnboardingRunEvent = ProfileOnboardingStreamEvent;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export const isProfileOnboardingV2Status = (
  value: unknown,
): value is ProfileOnboardingV2Status => {
  if (!isRecord(value)) {
    return false;
  }
  return (
    value.contract_version === PROFILE_ONBOARDING_CONTRACT_VERSION &&
    typeof value.enabled === 'boolean' &&
    typeof value.should_show === 'boolean' &&
    ['blocking', 'non_blocking', 'hidden'].includes(
      String(value.presentation || ''),
    ) &&
    typeof value.guided_available === 'boolean' &&
    typeof value.handled === 'boolean' &&
    typeof value.legacy_handled === 'boolean' &&
    typeof value.has_learner_profile === 'boolean' &&
    typeof value.learner_profile === 'string' &&
    (typeof value.learner_profile_updated_at === 'string' ||
      value.learner_profile_updated_at === null) &&
    typeof value.max_length === 'number' &&
    (value.config_revision === undefined ||
      typeof value.config_revision === 'number')
  );
};

export const getProfileOnboarding = (): Promise<ProfileOnboardingStatus> =>
  request.get('/api/user/profile-onboarding', { skipErrorToast: true });

export const getProfileOnboardingV2 =
  async (): Promise<ProfileOnboardingV2AdapterStatus> => {
    const response: unknown = await getProfileOnboarding();
    if (
      isRecord(response) &&
      response.contract_version === PROFILE_ONBOARDING_CONTRACT_VERSION &&
      isRecord(response.profile_v2)
    ) {
      return {
        ...response.profile_v2,
        contract_version: PROFILE_ONBOARDING_CONTRACT_VERSION,
      };
    }
    return {};
  };

export const createProfileOnboardingSession = (
  language?: string,
  intent: ProfileOnboardingSessionIntent = 'onboarding',
): Promise<ProfileOnboardingSession> =>
  request.post('/api/user/profile-onboarding/session', {
    ...(language?.trim() ? { language: language.trim() } : {}),
    intent,
  });

export const completeGuidedProfileOnboarding = async (
  payload: CompleteProfileOnboardingPayload,
): Promise<LearnerProfile> => {
  const response: unknown = await request.post(
    '/api/user/profile-onboarding/complete',
    payload,
  );
  if (
    !isRecord(response) ||
    response.learner_profile !== payload.learner_profile.trim() ||
    (typeof response.learner_profile_updated_at !== 'string' &&
      response.learner_profile_updated_at !== null) ||
    typeof response.has_learner_profile !== 'boolean' ||
    typeof response.max_length !== 'number'
  ) {
    throw new Error();
  }
  return response as LearnerProfile;
};

export const skipGuidedProfileOnboarding = (sessionId?: string) =>
  request.post(
    '/api/user/profile-onboarding/skip',
    sessionId ? { session_id: sessionId } : {},
  );

export const runProfileOnboardingSession = ({
  sessionId,
  expectedBlockIndex,
  requestId,
  userInput,
  language,
  onMessage,
  onError,
}: {
  sessionId: string;
  expectedBlockIndex: number;
  requestId: string;
  userInput?: Record<string, string[]>;
  language?: string;
  onMessage: (event: ProfileOnboardingRunEvent) => void;
  onError: (error: unknown) => void;
}) =>
  streamProfileOnboardingRuntime({
    path: `/api/user/profile-onboarding/session/${encodeURIComponent(sessionId)}/run`,
    payload: {
      expected_block_index: expectedBlockIndex,
      request_id: requestId,
      ...(userInput ? { user_input: userInput } : {}),
    },
    language,
    onMessage,
    onError,
  });

export const getLearnerProfile = (): Promise<LearnerProfile> =>
  request.get('/api/user/learner-profile', { skipErrorToast: true });

export const updateLearnerProfile = (
  learnerProfile: string,
  nickname?: string,
): Promise<LearnerProfile> => {
  const payload: { learner_profile: string; nickname?: string } = {
    learner_profile: learnerProfile,
  };
  if (nickname !== undefined) {
    payload.nickname = nickname;
  }
  return request.put('/api/user/learner-profile', payload, {
    skipErrorToast: true,
  });
};

export const optimizeLearnerProfile = (
  learnerProfile: string,
): Promise<OptimizedLearnerProfile> => {
  return request.post(
    '/api/user/learner-profile/optimize',
    { learner_profile: learnerProfile },
    { skipErrorToast: true },
  );
};
