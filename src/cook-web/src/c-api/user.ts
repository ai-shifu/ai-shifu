import request from '@/lib/request';
import { useSystemStore } from '@/c-store/useSystemStore';

/**
 * @description 用户注册接口
 * @param {*} username
 * @param {*} password
 * @param {*} name
 * @param {*} mobile
 * @param {*} email
 * @returns
 */
export const register = ({ username, password, mobile, email }) => {
  return request.post('/api/user/register', { username, password, email, mobile });
};

/**
 * 用户注册接口
 * @param {*} username
 * @param {*} password
 * @returns
 */
export const login = (username, password) => {
  return request.post('/api/user/login', { username, password });
};

/**
 * @description 查询用户信息
 * @returns
 */
export const getUserInfo = () => {
  return request.get('/api/user/info');
};


/**
 *
 */
export const updateUserInfo = (name) => {
  return request.post('/api/user/update_info', { name });
};


export const updatePassword = (old_password, new_password) => {
  return request.post('/api/user/update_password', { old_password, new_password });
};

export const requireResetPasswordCode = (username) => {
  return request.post('/api/user/require_reset_code', { username });
};


export const resetPassword = (username, new_password, code) => {
  return request.post('/api/user/reset_password', { username, new_password, code });
};

/**
 * 获取临时 token，在用户正常登录的时候，也需要有一个 token
 * @param tmp_id 客户端生成的 id，可以用来换 token
 * @returns
 *
 * https://agiclass.feishu.cn/docx/WyXhdgeVzoKVqDx1D4wc0eMknmg
 */
export const registerTmp = ({ temp_id }) => {
  const { channel: source, wechatCode: wxcode,language } = useSystemStore.getState();

  return request.post('/api/user/require_tmp', { temp_id, source, wxcode,language });
};

/**
 * 更新微信code
 * @returns
 */
export const updateWxcode = ({ wxcode }) => {
  // const { wechatCode: wxcode } = useSystemStore.getState();
  return request.post('/api/user/update_openid', { wxcode });
};

/**
 * 获取图形验证码
 */
export const genCheckCode = (mobile) => {
  return request.post('/api/user/generate_chk_code', { mobile });
};

/**
 * 发送手机验证码
 * @param {string} mobile 手机号
 * @param {string} check_code 图形验证码
 */
export const sendSmsCode = ({ mobile, check_code }) => {
  return request.post('/api/user/send_sms_code', { mobile, check_code });
};

// 获取用户详细信息
export const getUserProfile = (courseId) => {
  return request.get('/api/user/get_profile', { params: { course_id: courseId } });
};

// 上传头像
export const uploadAvatar = ({ avatar }) => {
  const formData = new FormData();
  formData.append('avatar', avatar);
  return request.post('/api/user/upload_avatar', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
};

// 更新用户详细信息
export const updateUserProfile = (data, courseId) => {
  return request.post('/api/user/update_profile', {
    "profiles": data,
    "course_id": courseId
  });
};


// submit feedback
export const submitFeedback = (feedback) => {
  return request.post('/api/user/submit-feedback', {feedback});
};
