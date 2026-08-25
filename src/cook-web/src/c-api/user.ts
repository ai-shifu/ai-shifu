import request from '@/lib/request';
import { useSystemStore } from '@/c-store/useSystemStore';

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

// The maintained `c` route still imports this compatibility module. Keep the
// learner-profile transport and validation owned by the modern API module.
export {
  completeGuidedProfileOnboarding as completeProfileOnboarding,
  createProfileOnboardingSession,
  getProfileOnboarding,
  isProfileOnboardingStatus,
  runProfileOnboardingSession,
  skipGuidedProfileOnboarding as skipProfileOnboarding,
} from '@/api/learnerProfile';
export type {
  CompleteProfileOnboardingPayload,
  LearnerProfile as CompleteProfileOnboardingResponse,
  ProfileOnboardingPresentation,
  ProfileOnboardingRunEvent,
  ProfileOnboardingSession,
  ProfileOnboardingSessionIntent,
  ProfileOnboardingStatus,
  ProfileOnboardingStatusResponse,
} from '@/api/learnerProfile';

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
