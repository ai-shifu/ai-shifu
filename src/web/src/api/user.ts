import request, { type RequestConfig } from '@/lib/request';
import { useSystemStore } from '@/store/use-system-store';

const getCurrentShifuBid = (): string => {
  if (typeof window === 'undefined') return '';
  const match = window.location.pathname.match(/^\/c\/([^/]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : '';
};

/**
 * @description Fetch user information
 * @returns
 */
export const getUserInfo = (config?: Pick<RequestConfig, 'skipErrorToast'>) => {
  return request.get('/api/user/info', config);
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
} from '@/api/learner-profile';
export type {
  CompleteProfileOnboardingPayload,
  LearnerProfile as CompleteProfileOnboardingResponse,
  ProfileOnboardingPresentation,
  ProfileOnboardingRunEvent,
  ProfileOnboardingSession,
  ProfileOnboardingSessionIntent,
  ProfileOnboardingStatus,
  ProfileOnboardingStatusResponse,
} from '@/api/learner-profile';

/**
 * Send SMS verification code
 * @param {string} mobile Phone number
 * @param {string} captcha_ticket One-time captcha ticket
 */
export const sendSmsCode = ({ mobile, captcha_ticket }) => {
  return request.post('/api/user/send_sms_code', { mobile, captcha_ticket });
};
