import request from '@/lib/request';
import { useSystemStore } from '@/c-store/useSystemStore';

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
  const source = (channel || '').trim() || 'web';

  return request.post('/api/user/require_tmp', {
    temp_id,
    source,
    wxcode,
    language,
  });
};

/**
 * Update WeChat code
 * @returns
 */
export const updateWxcode = ({ wxcode }) => {
  // const { wechatCode: wxcode } = useSystemStore.getState();
  return request.post('/api/user/update_openid', { wxcode });
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
