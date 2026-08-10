import request from '@/lib/request';
import { useSystemStore } from '@/c-store/useSystemStore';
import {
  streamProfileOnboardingRuntime,
  type ProfileOnboardingStreamEvent,
} from '@/lib/profileOnboardingSse';
import { notifyLearnerProfileChanged } from '@/lib/learnerProfileEvents';

const getCurrentShifuBid = (): string => {
  if (typeof window === 'undefined') return '';
  const match = window.location.pathname.match(/^\/c\/([^/]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : '';
};

/**
 * @description Fetch user information
 * @returns
 */
export const getUserInfo = () => {
  return request.get('/api/user/info');
};

/**
 *
 */
export const updateUserInfo = name => {
  return request.post('/api/user/update_info', { name });
};

/**
 * Obtain a temporary token, also required when a user logs in normally
 * @param tmp_id Client-generated id, used to exchange for a token
 * @returns
 *
 * https://agiclass.feishu.cn/docx/WyXhdgeVzoKVqDx1D4wc0eMknmg
 */
export const registerTmp = ({ temp_id }) => {
  const { channel, wechatCode: wxcode, language } = useSystemStore.getState();
  const shifu_bid = getCurrentShifuBid();
  const source = (channel || '').trim() || 'web';

  return request.post('/api/user/require_tmp', {
    temp_id,
    source,
    wxcode,
    language,
    shifu_bid,
  });
};

/**
 * Update WeChat code
 * @returns
 */
export const updateWxcode = ({ wxcode }) => {
  // const { wechatCode: wxcode } = useSystemStore.getState();
  const shifu_bid = getCurrentShifuBid();
  return request.post('/api/user/update_openid', { wxcode, shifu_bid });
};

export type ProfileOnboardingPresentation =
  | 'blocking'
  | 'non_blocking'
  | 'hidden';

export type ProfileOnboardingSessionIntent = 'onboarding' | 'settings';

export const PROFILE_ONBOARDING_CONTRACT_VERSION = 'profile-v2' as const;

export type ProfileOnboardingV2Status = {
  contract_version: typeof PROFILE_ONBOARDING_CONTRACT_VERSION;
  enabled: boolean;
  should_show: boolean;
  presentation: ProfileOnboardingPresentation;
  legacy_handled: boolean;
  has_learner_profile: boolean;
  learner_profile_updated_at: string | null;
  max_length: number;
  config_revision: number;
  guided_available: boolean;
};

export type ProfileOnboardingStatus = Partial<ProfileOnboardingV2Status>;

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
    typeof value.legacy_handled === 'boolean' &&
    typeof value.has_learner_profile === 'boolean' &&
    (typeof value.learner_profile_updated_at === 'string' ||
      value.learner_profile_updated_at === null) &&
    typeof value.max_length === 'number' &&
    typeof value.config_revision === 'number' &&
    typeof value.guided_available === 'boolean'
  );
};

export type CompleteProfileOnboardingPayload = {
  learner_profile: string;
  trigger_source: 'guided' | 'pasted' | 'settings';
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

export type LearnerProfile = {
  learner_profile: string;
  learner_profile_updated_at: string | null;
  max_length: number;
};

export type CompleteProfileOnboardingResponse = LearnerProfile;

const isCompleteProfileOnboardingResponse = (
  value: unknown,
  expectedLearnerProfile: string,
): value is CompleteProfileOnboardingResponse =>
  isRecord(value) &&
  value.learner_profile === expectedLearnerProfile &&
  (typeof value.learner_profile_updated_at === 'string' ||
    value.learner_profile_updated_at === null) &&
  typeof value.max_length === 'number';

export const getProfileOnboarding =
  async (): Promise<ProfileOnboardingStatus> => {
    const response: unknown = await request.get('/api/user/profile-onboarding');
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

export const completeProfileOnboarding = async (
  payload: CompleteProfileOnboardingPayload,
): Promise<CompleteProfileOnboardingResponse> => {
  const response: unknown = await request.post(
    '/api/user/profile-onboarding/complete',
    payload,
  );
  if (
    !isCompleteProfileOnboardingResponse(
      response,
      payload.learner_profile.trim(),
    )
  ) {
    throw new Error();
  }
  notifyLearnerProfileChanged();
  return response;
};

export const skipProfileOnboarding = (sessionId?: string) => {
  return request.post('/api/user/profile-onboarding/skip', {
    ...(sessionId ? { session_id: sessionId } : {}),
  });
};

export const createProfileOnboardingSession = (
  language?: string,
  intent: ProfileOnboardingSessionIntent = 'onboarding',
): Promise<ProfileOnboardingSession> => {
  return request.post('/api/user/profile-onboarding/session', {
    ...(language?.trim() ? { language: language.trim() } : {}),
    intent,
  });
};

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
}) => {
  return streamProfileOnboardingRuntime({
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
};

export const getLearnerProfile = (): Promise<LearnerProfile> => {
  return request.get('/api/user/learner-profile');
};

export const updateLearnerProfile = (
  learnerProfile: string,
): Promise<LearnerProfile> => {
  return request
    .put('/api/user/learner-profile', {
      learner_profile: learnerProfile,
    })
    .then((response: LearnerProfile) => {
      notifyLearnerProfileChanged();
      return response;
    });
};

export const clearLearnerProfile = async (): Promise<LearnerProfile> => {
  const response: LearnerProfile = await request.delete(
    '/api/user/learner-profile',
  );
  notifyLearnerProfileChanged();
  return response;
};

/**
 * Send SMS verification code
 * @param {string} mobile Phone number
 * @param {string} captcha_ticket One-time captcha ticket
 */
export const sendSmsCode = ({ mobile, captcha_ticket }) => {
  return request.post('/api/user/send_sms_code', { mobile, captcha_ticket });
};

// Fetch detailed user profile
export const getUserProfile = courseId => {
  return request
    .get('/api/user/get_profile?course_id=' + courseId)
    .then(res => {
      return res.profiles || [];
    });
};

// Upload avatar
export const uploadAvatar = ({ avatar }) => {
  const formData = new FormData();
  formData.append('avatar', avatar);
  return request.post('/api/user/upload_avatar', formData);
};

// Update detailed user profile
export const updateUserProfile = (data, courseId) => {
  return request.post('/api/user/update_profile', {
    profiles: data,
    course_id: courseId,
  });
};

// submit feedback
export const submitFeedback = feedback => {
  return request.post('/api/user/submit-feedback', { feedback });
};
